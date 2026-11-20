import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from src.visuals.asset_optimizer import optimize_render_asset, prepare_render_asset


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestAssetOptimizer(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_plate_oversized_resizes_to_max_width_2560_preserving_aspect(self):
        src = self.tmp_dir / "plate_4k.jpg"
        dst = self.tmp_dir / "out" / "plate_4k.jpg"
        Image.new("RGB", (4096, 2304), color=(80, 120, 160)).save(src, format="JPEG", quality=95)

        info = optimize_render_asset(src, dst, kind="plate")
        self.assertTrue(dst.exists())
        self.assertTrue(info.resized)
        self.assertFalse(info.cache_hit)
        self.assertEqual(info.original_size, (4096, 2304))
        self.assertEqual(info.output_size, (2560, 1440))

        with Image.open(dst) as out_img:
            self.assertEqual(out_img.size, (2560, 1440))
            self.assertEqual(out_img.mode, "RGB")

    def test_full_image_oversized_resizes_to_max_width_2304(self):
        src = self.tmp_dir / "scene_4k.jpg"
        dst = self.tmp_dir / "out" / "scene_4k.jpg"
        Image.new("RGB", (3840, 2160), color=(40, 50, 60)).save(src, format="JPEG", quality=95)

        out_path = prepare_render_asset(src, dst, kind="full_image")
        self.assertEqual(out_path, dst)
        with Image.open(dst) as out_img:
            self.assertEqual(out_img.size, (2304, 1296))

    def test_cutout_oversized_resizes_to_max_height_1920_preserving_rgba_alpha(self):
        src = self.tmp_dir / "char_tall.png"
        dst = self.tmp_dir / "out" / "char_tall.png"

        img = Image.new("RGBA", (1600, 3200), color=(0, 0, 0, 0))
        # Vẽ vùng đục ở trung tâm để kiểm tra alpha không bị mất
        for y in range(800, 2400):
            for x in range(400, 1200):
                img.putpixel((x, y), (200, 100, 50, 255))
        img.save(src, format="PNG")

        info = optimize_render_asset(src, dst, kind="cutout")
        self.assertTrue(info.resized)
        self.assertEqual(info.output_size, (960, 1920))

        with Image.open(dst) as out_img:
            self.assertEqual(out_img.size, (960, 1920))
            self.assertEqual(out_img.mode, "RGBA")
            # Góc ảnh phải giữ nguyên trong suốt (alpha = 0)
            self.assertEqual(out_img.getpixel((5, 5))[3], 0)
            # Trung tâm phải đục hoàn toàn (alpha = 255)
            self.assertEqual(out_img.getpixel((480, 960))[3], 255)

    def test_within_threshold_skips_resize_and_copies_verbatim(self):
        src = self.tmp_dir / "plate_1080p.jpg"
        dst = self.tmp_dir / "out" / "plate_1080p.jpg"
        Image.new("RGB", (1920, 1080), color=(15, 25, 35)).save(src, format="JPEG", quality=90)

        info = optimize_render_asset(src, dst, kind="plate")
        self.assertFalse(info.resized)
        self.assertEqual(info.output_size, (1920, 1080))
        # Không mã hóa lại → khớp SHA-256 tuyệt đối với tệp gốc
        self.assertEqual(_sha256(src), _sha256(dst))

        src_cut = self.tmp_dir / "cutout_small.png"
        dst_cut = self.tmp_dir / "out" / "cutout_small.png"
        Image.new("RGBA", (900, 1800), color=(10, 20, 30, 128)).save(src_cut, format="PNG")
        info_cut = optimize_render_asset(src_cut, dst_cut, kind="cutout")
        self.assertFalse(info_cut.resized)
        self.assertEqual(_sha256(src_cut), _sha256(dst_cut))

    def test_cache_hit_and_invalidation_on_source_change_or_kind_change(self):
        src = self.tmp_dir / "plate_big.jpg"
        dst = self.tmp_dir / "out" / "plate_big.jpg"
        Image.new("RGB", (3200, 1800), color=(90, 90, 90)).save(src, format="JPEG", quality=92)

        first = optimize_render_asset(src, dst, kind="plate")
        self.assertFalse(first.cache_hit)
        self.assertTrue(first.resized)
        self.assertEqual(first.output_size, (2560, 1440))
        mtime_after_first = dst.stat().st_mtime_ns

        # Lần 2 không đổi nguồn → cache hit, không xử lý lại
        second = optimize_render_asset(src, dst, kind="plate")
        self.assertTrue(second.cache_hit)
        self.assertEqual(dst.stat().st_mtime_ns, mtime_after_first)

        # Đổi target kind (plate 2560 -> full_image 2304) → cache miss và resize lại đúng 2304
        third = optimize_render_asset(src, dst, kind="full_image")
        self.assertFalse(third.cache_hit)
        self.assertTrue(third.resized)
        self.assertEqual(third.output_size, (2304, 1296))

        # Sửa tệp nguồn (đổi kích thước / mtime) → cache miss
        Image.new("RGB", (3600, 2025), color=(120, 60, 30)).save(src, format="JPEG", quality=92)
        os.utime(src, (src.stat().st_atime + 10, src.stat().st_mtime + 10))
        fourth = optimize_render_asset(src, dst, kind="full_image")
        self.assertFalse(fourth.cache_hit)
        self.assertEqual(fourth.original_size, (3600, 2025))
        self.assertEqual(fourth.output_size, (2304, 1296))

    def test_webp_output_and_invalid_inputs(self):
        src = self.tmp_dir / "plate_4k.webp"
        dst = self.tmp_dir / "out" / "plate_4k.webp"
        Image.new("RGB", (3840, 2160), color=(30, 80, 140)).save(src, format="WEBP", quality=90)

        info = optimize_render_asset(src, dst, kind="plate")
        self.assertTrue(info.resized)
        self.assertEqual(info.output_size, (2560, 1440))
        with Image.open(dst) as out_img:
            self.assertEqual(out_img.format, "WEBP")

        with self.assertRaises(ValueError):
            prepare_render_asset(src, dst, kind="invalid_kind")  # type: ignore[arg-type]

        with self.assertRaises(FileNotFoundError):
            prepare_render_asset(self.tmp_dir / "does_not_exist.jpg", dst, kind="plate")

    def test_non_image_stub_file_falls_back_to_safe_copy(self):
        src = self.tmp_dir / "stub.jpg"
        dst = self.tmp_dir / "out" / "stub.jpg"
        src.write_bytes(b"FAKE_TEST_BYTES")
        out = prepare_render_asset(src, dst, kind="full_image")
        self.assertEqual(out, dst)
        self.assertEqual(dst.read_bytes(), b"FAKE_TEST_BYTES")

    def test_resize_over_existing_hardlink_does_not_corrupt_source(self):
        src = self.tmp_dir / "assets_plate_2500.jpg"
        dst = self.tmp_dir / "public" / "assets_plate_2500.jpg"
        dst.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (2500, 1406), color=(64, 96, 128)).save(src, format="JPEG", quality=92)
        orig_sha = _sha256(src)

        # Tạo hardlink đích trỏ thẳng tới ảnh gốc (giống kịch bản Phase 4 hardlink-first)
        os.link(src, dst)
        self.assertTrue(os.path.samefile(src, dst))

        # Chạy optimize với ngưỡng nhỏ hơn (full_image: 2304 < 2500) -> phải ghi ra .tmp rồi os.replace()
        info = optimize_render_asset(src, dst, kind="full_image")
        self.assertTrue(info.resized)
        self.assertEqual(info.output_size, (2304, 1296))
        self.assertFalse(os.path.samefile(src, dst))

        # Ảnh gốc trong assets/ tuyệt đối không bị thay đổi kích thước hay nội dung
        self.assertEqual(_sha256(src), orig_sha)
        with Image.open(src) as orig_img:
            self.assertEqual(orig_img.size, (2500, 1406))
        with Image.open(dst) as dst_img:
            self.assertEqual(dst_img.size, (2304, 1296))

    def test_fallback_copy_over_existing_hardlink_does_not_corrupt_original(self):
        orig_asset = self.tmp_dir / "orig_asset.jpg"
        orig_asset.write_bytes(b"ORIGINAL_ASSET_BYTES_PROTECTED")
        dst = self.tmp_dir / "public" / "target.jpg"
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.link(orig_asset, dst)

        non_image_src = self.tmp_dir / "stub_new.jpg"
        non_image_src.write_bytes(b"NEW_STUB_CONTENT")

        prepare_render_asset(non_image_src, dst, kind="full_image")
        self.assertEqual(dst.read_bytes(), b"NEW_STUB_CONTENT")
        self.assertEqual(orig_asset.read_bytes(), b"ORIGINAL_ASSET_BYTES_PROTECTED")
        self.assertFalse(os.path.samefile(orig_asset, dst))


if __name__ == "__main__":
    unittest.main()
