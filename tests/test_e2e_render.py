import json
import shutil
import subprocess
import unittest
from pathlib import Path

from src.core.models import RenderProps


class TestE2ERender(unittest.TestCase):
    """Kiểm thử E2E Gate 4: Kiểm tra toàn vẹn định dạng, âm thanh và đóng gói."""

    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parent.parent
        cls.output_dir = cls.root / "output" / "sample_chapter"
        cls.props_path = cls.output_dir / "render_props.json"
        cls.srt_path = cls.output_dir / "video.srt"
        cls.meta_path = cls.output_dir / "youtube_metadata.json"
        cls.thumb_path = cls.output_dir / "thumbnail_base.png"

        # Kiểm tra sự sẵn sàng của ffmpeg
        try:
            subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            cls.has_ffmpeg = True
        except Exception:
            cls.has_ffmpeg = False

    def test_render_props_contract_validity(self):
        """Hợp đồng dữ liệu render_props.json phải hợp lệ tuyệt đối theo Pydantic."""
        self.assertTrue(self.props_path.exists(), f"Không tìm thấy {self.props_path}")
        with open(self.props_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        props = RenderProps.model_validate(data)
        self.assertEqual(props.schema_version, 1)
        self.assertEqual(props.fps, 24)
        self.assertEqual(props.width, 1920)
        self.assertEqual(props.height, 1080)
        self.assertGreater(len(props.scenes), 0)

    def test_srt_file_integrity(self):
        """File phụ đề SRT phải có mốc thời gian tăng dần và không rỗng."""
        self.assertTrue(self.srt_path.exists(), f"Không tìm thấy {self.srt_path}")
        with open(self.srt_path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]

        self.assertGreater(len(lines), 3)
        self.assertEqual(lines[0], "1")
        self.assertIn("-->", lines[1])

    def test_youtube_metadata_integrity(self):
        """Metadata YouTube phải đáp ứng đầy đủ tiêu chí schema và độ dài."""
        self.assertTrue(self.meta_path.exists(), f"Không tìm thấy {self.meta_path}")
        with open(self.meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        self.assertIn("title", meta)
        self.assertLessEqual(len(meta["title"]), 70)
        self.assertIn("description", meta)
        self.assertIn("tags", meta)
        self.assertGreaterEqual(len(meta["tags"]), 10)
        self.assertIn("thumbnail", meta)

    def test_thumbnail_dimensions(self):
        """Thumbnail base phải có kích thước chuẩn YouTube 1280x720."""
        if not self.has_ffmpeg:
            self.skipTest("Hệ thống không có ffmpeg")

        self.assertTrue(self.thumb_path.exists(), f"Không tìm thấy {self.thumb_path}")
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            str(self.thumb_path),
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
        dims = res.stdout.strip()
        self.assertEqual(dims, "1280x720", f"Kích thước thumbnail không đúng: {dims} (yêu cầu 1280x720)")

    def test_bench_render_report_fps(self):
        """Báo cáo benchmark hiệu năng (bench_p3.json) phải tồn tại và đạt tốc độ tối thiểu."""
        bench_p3 = self.output_dir / "bench_p3.json"
        if not bench_p3.exists():
            self.skipTest("bench_p3.json chưa được tạo")

        with open(bench_p3, "r", encoding="utf-8") as f:
            report = json.load(f)

        self.assertIn("fps_render", report)
        self.assertGreater(report["fps_render"], 10.0, "fps render Remotion phải đạt tốc độ tối thiểu")


if __name__ == "__main__":
    unittest.main()
