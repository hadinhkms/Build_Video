import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PIL import Image


def is_rembg_available() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("rembg") is not None
    except Exception:
        return False


REMBG_AVAILABLE = is_rembg_available()


def compute_file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class CutoutProcessor:
    """Tách nền tự động bằng rembg, crop viền sát và tính ma trận base_cutout.json."""

    def __init__(self, model_name: str = "isnet-general-use"):
        self.model_name = model_name
        self._session = None

    def _get_session(self):
        if not REMBG_AVAILABLE:
            raise RuntimeError("Thư viện 'rembg' chưa được cài đặt.")
        if self._session is None:
            self._session = rembg.new_session(self.model_name)
        return self._session

    def process_image(
        self,
        input_path: Path,
        output_png_path: Path,
        output_json_path: Path,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Tách nền 1 file ảnh, xuất PNG có alpha và file JSON tọa độ."""
        if not input_path.exists():
            raise FileNotFoundError(f"Không tìm thấy ảnh đầu vào: {input_path}")

        current_hash = compute_file_hash(input_path)

        # Kiểm tra cache
        if (
            not force
            and output_png_path.exists()
            and output_json_path.exists()
        ):
            try:
                with open(output_json_path, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                if cached_data.get("source_hash") == current_hash:
                    return cached_data
            except Exception:
                pass

        orig_img = Image.open(input_path)
        orig_w, orig_h = orig_img.size

        # Kiểm tra xem ảnh gốc đã có alpha tách nền hay chưa
        has_alpha = orig_img.mode in ("RGBA", "LA") or (
            orig_img.mode == "P" and "transparency" in orig_img.info
        )

        rgba_img: Image.Image
        if has_alpha:
            rgba_candidate = orig_img.convert("RGBA")
            # Kiểm tra xem alpha có thực sự trong suốt không
            alpha_extrema = rgba_candidate.getchannel("A").getextrema()
            if alpha_extrema[0] < 250:
                rgba_img = rgba_candidate
            else:
                session = self._get_session()
                rgba_img = rembg.remove(orig_img, session=session)
        else:
            session = self._get_session()
            rgba_img = rembg.remove(orig_img, session=session)

        # Tìm bounding box của kênh alpha
        alpha_channel = rgba_img.getchannel("A")
        bbox = alpha_channel.getbbox()  # (left, upper, right, lower)
        if bbox is None:
            # Ảnh rỗng hoặc hoàn toàn trong suốt -> giữ nguyên kích thước
            bbox = (0, 0, orig_w, orig_h)

        left, upper, right, lower = bbox
        # Thêm 1-2px padding nhẹ nếu còn nằm trong khung
        pad = 2
        left = max(0, left - pad)
        upper = max(0, upper - pad)
        right = min(orig_w, right + pad)
        lower = min(orig_h, lower + pad)

        cropped_img = rgba_img.crop((left, upper, right, lower))
        crop_w = right - left
        crop_h = lower - upper
        aspect = round(crop_w / max(1, crop_h), 4)

        # Kiểm tra xem có bị cắt ngang người ở đáy (cut_bottom) không:
        # Nếu các pixel ở hàng cuối cùng (hoặc 2 hàng cuối) của ảnh crop có alpha > 30
        cropped_alpha = cropped_img.getchannel("A")
        bottom_row_y = crop_h - 1
        cut_bottom = False
        opaque_count = 0
        for x in range(crop_w):
            if cropped_alpha.getpixel((x, bottom_row_y)) > 30:
                opaque_count += 1

        # Nếu có trên 15% số pixel ở đáy không trong suốt -> nhân vật bị cắt ngang người
        if opaque_count > max(2, int(crop_w * 0.15)):
            cut_bottom = True

        # Tọa độ face và chest mặc định theo chuẩn ảnh bán thân nhìn thẳng
        # face: 0.5 ngang, 0.16 cao
        # chest: 0.5 ngang, 0.42 cao
        metadata: Dict[str, Any] = {
            "aspect": aspect,
            "crop_box": {
                "x": left,
                "y": upper,
                "w": crop_w,
                "h": crop_h,
            },
            "face": {"x": 0.50, "y": 0.16},
            "chest": {"x": 0.50, "y": 0.42},
            "cut_bottom": cut_bottom,
            "source_hash": current_hash,
        }

        output_png_path.parent.mkdir(parents=True, exist_ok=True)
        cropped_img.save(output_png_path, "PNG")

        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        return metadata


def process_all_characters(
    assets_dir: Path,
    processor: Optional[CutoutProcessor] = None,
) -> Dict[str, Dict[str, Any]]:
    """Duyệt qua tất cả thư mục characters trong assets/ và chạy tách nền nếu có base.png / base.jpg."""
    characters_dir = assets_dir / "characters"
    results = {}
    if not characters_dir.exists():
        return results

    if processor is None and REMBG_AVAILABLE:
        processor = CutoutProcessor()

    for char_folder in characters_dir.iterdir():
        if not char_folder.is_dir():
            continue
        base_img = None
        for ext in [".png", ".jpg", ".jpeg", ".webp"]:
            candidate = char_folder / f"base{ext}"
            if candidate.exists():
                base_img = candidate
                break

        if base_img and processor:
            out_png = char_folder / "base_cutout.png"
            out_json = char_folder / "base_cutout.json"
            try:
                meta = processor.process_image(base_img, out_png, out_json)
                results[char_folder.name] = meta
            except Exception as e:
                print(f"[CẢNH BÁO] Lỗi khi tách nền nhân vật {char_folder.name}: {e}")

    return results
