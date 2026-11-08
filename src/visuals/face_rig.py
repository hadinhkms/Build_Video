import json
import logging
import math
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageFilter
from skimage.metrics import structural_similarity as ssim

from src.visuals.image_io import load_cv2_image, save_cv2_image

logger = logging.getLogger(__name__)


class FaceRigProcessor:
    """Xử lý ảnh biến thể nhân vật (mắt nhắm, miệng hé) để tạo patch và tọa độ face_rig."""

    def __init__(self, ssim_threshold: float = 0.95, feather_radius: int = 8):
        self.ssim_threshold = ssim_threshold
        self.feather_radius = feather_radius

    def _load_image(self, path: Path) -> np.ndarray:
        return load_cv2_image(path)

    def _save_image(self, path: Path, img: np.ndarray) -> None:
        save_cv2_image(path, img)

    def _align_images(self, base_gray: np.ndarray, var_gray: np.ndarray) -> np.ndarray:
        """Căn chỉnh variant khớp pixel với base nếu lệch nhẹ vài pixel."""
        if base_gray.shape == var_gray.shape:
            return var_gray
        return cv2.resize(var_gray, (base_gray.shape[1], base_gray.shape[0]), interpolation=cv2.INTER_LINEAR)

    def process_variant(
        self,
        base_path: Path,
        variant_path: Path,
        feature_type: str,  # "eyes" hoặc "mouth"
        output_dir: Path,
        cutout_meta_path: Optional[Path] = None,
    ) -> Optional[Dict[str, Any]]:
        """So ảnh gốc với biến thể, kiểm tra SSIM, cắt patch với mask mờ biên và tính tọa độ cutout."""
        if not base_path.exists() or not variant_path.exists():
            logger.warning(f"File không tồn tại: base={base_path}, variant={variant_path}")
            return None

        base_img = self._load_image(base_path)
        var_img = self._load_image(variant_path)

        # Đảm bảo cùng kích thước
        h, w = base_img.shape[:2]
        if var_img.shape[:2] != (h, w):
            var_img = cv2.resize(var_img, (w, h), interpolation=cv2.INTER_LINEAR)

        # Chuyển về grayscale để so sánh
        base_bgr = base_img[:, :, :3] if len(base_img.shape) == 3 and base_img.shape[2] >= 3 else base_img
        var_bgr = var_img[:, :, :3] if len(var_img.shape) == 3 and var_img.shape[2] >= 3 else var_img

        base_gray = cv2.cvtColor(base_bgr, cv2.COLOR_BGR2GRAY) if len(base_bgr.shape) == 3 else base_bgr
        var_gray = cv2.cvtColor(var_bgr, cv2.COLOR_BGR2GRAY) if len(var_bgr.shape) == 3 else var_bgr

        # 1. Tính ảnh khác biệt tuyệt đối
        diff = cv2.absdiff(base_gray, var_gray)

        # 2. Xác định vùng tìm kiếm cho mắt hoặc miệng
        # Mắt ở nửa trên khuôn mặt (y < 0.55), miệng ở nửa dưới (y >= 0.45)
        mask_search = np.zeros_like(diff, dtype=np.uint8)
        if feature_type == "eyes":
            mask_search[: int(h * 0.55), :] = 255
        elif feature_type == "mouth":
            mask_search[int(h * 0.45) :, :] = 255
        else:
            mask_search[:, :] = 255

        diff_feature = cv2.bitwise_and(diff, diff, mask=mask_search)

        # Ngưỡng phát hiện biến đổi
        _, thresh = cv2.threshold(diff_feature, 15, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            logger.warning(f"Không phát hiện thay đổi cho feature '{feature_type}'")
            return None

        # Bounding box bao quanh tất cả contour của feature
        x_min, y_min = w, h
        x_max, y_max = 0, 0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 20:  # Bỏ nhiễu vi mô
                continue
            x, y, cw, ch = cv2.boundingRect(cnt)
            x_min = min(x_min, x)
            y_min = min(y_min, y)
            x_max = max(x_max, x + cw)
            y_max = max(y_max, y + ch)

        if x_min >= x_max or y_min >= y_max:
            logger.warning(f"Không tìm thấy bounding box hợp lệ cho '{feature_type}'")
            return None

        # Thêm padding xung quanh vùng mắt/miệng
        pad_x = int((x_max - x_min) * 0.25) + 8
        pad_y = int((y_max - y_min) * 0.25) + 8
        x1 = max(0, x_min - pad_x)
        y1 = max(0, y_min - pad_y)
        x2 = min(w, x_max + pad_x)
        y2 = min(h, y_max + pad_y)
        patch_w = x2 - x1
        patch_h = y2 - y1

        # 3. Kiểm tra SSIM ngoài vùng feature (đảm bảo không bị vẽ lại toàn bộ ảnh)
        outer_mask = np.ones((h, w), dtype=bool)
        outer_mask[y1:y2, x1:x2] = False

        if np.any(outer_mask):
            score, _ = ssim(base_gray, var_gray, full=True)
            outer_base = base_gray[outer_mask]
            outer_var = var_gray[outer_mask]
            # Tính correlation / SSIM xấp xỉ ngoài vùng
            outer_diff = np.abs(outer_base.astype(float) - outer_var.astype(float))
            # Nếu phần ngoài vùng thay đổi quá nhiều (trung bình > 8 mức xám hoặc ssim toàn cục < threshold)
            if score < self.ssim_threshold and np.mean(outer_diff) > 8.0:
                logger.warning(
                    f"Từ chối biến thể '{feature_type}': SSIM ngoài vùng mặt thấp ({score:.3f} < {self.ssim_threshold}). "
                    "Công cụ AI có thể đã vẽ lại toàn bộ ảnh thay vì chỉ sửa mắt/miệng."
                )
                return None

        # 4. Cắt patch kèm mask làm mờ biên (feathering)
        patch_bgr = var_bgr[y1:y2, x1:x2].copy()

        # Tạo alpha mask có mờ biên
        alpha_mask = np.ones((patch_h, patch_w), dtype=np.float32) * 255.0
        # Làm mờ biên ngoài bằng feather_radius
        pad_edge = max(2, self.feather_radius)
        cv2.rectangle(
            alpha_mask,
            (0, 0),
            (patch_w - 1, patch_h - 1),
            0.0,
            thickness=pad_edge,
        )
        alpha_mask = cv2.GaussianBlur(alpha_mask, (pad_edge * 2 + 1, pad_edge * 2 + 1), sigmaX=pad_edge / 2.0)

        # Ghép thành RGBA
        b, g, r = cv2.split(patch_bgr)
        patch_rgba = cv2.merge([b, g, r, alpha_mask.astype(np.uint8)])

        # 5. Quy đổi tọa độ về tỉ lệ 0..1 của ảnh cutout
        # Nếu có base_cutout.json (Phase 2)
        crop_box = None
        if cutout_meta_path and cutout_meta_path.exists():
            try:
                with open(cutout_meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    crop_box = meta.get("crop_box")
            except Exception as e:
                logger.warning(f"Lỗi đọc {cutout_meta_path}: {e}")

        if crop_box:
            # x_cutout = (x_gốc − crop_box.x) / crop_box.w
            cb_x = crop_box["x"]
            cb_y = crop_box["y"]
            cb_w = crop_box["w"]
            cb_h = crop_box["h"]
            norm_x = max(0.0, min(1.0, (x1 - cb_x) / float(cb_w)))
            norm_y = max(0.0, min(1.0, (y1 - cb_y) / float(cb_h)))
            norm_w = max(0.0, min(1.0, patch_w / float(cb_w)))
            norm_h = max(0.0, min(1.0, patch_h / float(cb_h)))
        else:
            # Không có crop_box (base chính là cutout)
            norm_x = round(x1 / float(w), 4)
            norm_y = round(y1 / float(h), 4)
            norm_w = round(patch_w / float(w), 4)
            norm_h = round(patch_h / float(h), 4)

        # 6. Lưu file patch
        output_dir.mkdir(parents=True, exist_ok=True)
        patch_filename = f"{feature_type}_patch.png" if feature_type != "eyes" else "eyes_closed_patch.png"
        if feature_type == "mouth":
            patch_filename = "mouth_open_patch.png"
        patch_file = output_dir / patch_filename
        self._save_image(patch_file, patch_rgba)

        rect_data = {
            "x": round(norm_x, 4),
            "y": round(norm_y, 4),
            "w": round(norm_w, 4),
            "h": round(norm_h, 4),
        }

        return {
            "feature": feature_type,
            "patch_path": patch_file,
            "patch_name": patch_filename,
            "rect": rect_data,
        }

    def rig_character(
        self,
        char_dir: Path,
        output_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Tự động tìm kiếm ảnh base và các ảnh biến thể eyes_closed.png, mouth_open.png trong char_dir."""
        target_dir = output_dir or char_dir
        base_path = char_dir / "base.png"
        if not base_path.exists():
            base_path = char_dir / "base_cutout.png"
        if not base_path.exists():
            return {"eyes": None, "mouth": None, "eyesPatchSrc": None, "mouthPatchSrc": None}

        cutout_meta = char_dir / "base_cutout.json"

        rig_result: Dict[str, Any] = {
            "eyes": None,
            "mouth": None,
            "eyesPatchSrc": None,
            "mouthPatchSrc": None,
        }

        # Xử lý mắt
        eyes_var = char_dir / "eyes_closed.png"
        if eyes_var.exists():
            res = self.process_variant(base_path, eyes_var, "eyes", target_dir, cutout_meta)
            if res:
                rig_result["eyes"] = res["rect"]
                rig_result["eyesPatchSrc"] = f"characters/{char_dir.name}/{res['patch_name']}"

        # Xử lý miệng
        mouth_var = char_dir / "mouth_open.png"
        if mouth_var.exists():
            res = self.process_variant(base_path, mouth_var, "mouth", target_dir, cutout_meta)
            if res:
                rig_result["mouth"] = res["rect"]
                rig_result["mouthPatchSrc"] = f"characters/{char_dir.name}/{res['patch_name']}"

        # Lưu face_rig.json
        rig_json = target_dir / "face_rig.json"
        with open(rig_json, "w", encoding="utf-8") as f:
            json.dump(rig_result, f, indent=2, ensure_ascii=False)

        return rig_result
