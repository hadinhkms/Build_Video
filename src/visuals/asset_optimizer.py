"""Chuẩn hóa độ phân giải proxy cho ảnh plate / full_image / cutout trước khi đưa vào Remotion.

Tránh để Chromium giải mã lặp lại ảnh AI độ phân giải quá lớn (4K–8K) ở 16–24 tab song song,
giúp giảm mạnh mức tiêu thụ RAM/VRAM và thời gian decode trong khi vẫn dư độ nét cho 1080p.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Tuple

from PIL import Image, ImageOps

from src.export.crop_utils import copy_file_if_different

AssetKind = Literal["plate", "cutout", "full_image"]

# (trục giới hạn, kích thước tối đa tính theo pixel)
ASSET_LIMITS: Dict[AssetKind, Tuple[Literal["width", "height"], int]] = {
    "plate": ("width", 2560),
    "full_image": ("width", 2304),
    "cutout": ("height", 1920),
}

CACHE_FILENAME = ".asset_opt_cache.json"


@dataclass(frozen=True)
class AssetOptimizeInfo:
    dst_path: Path
    kind: AssetKind
    cache_hit: bool
    resized: bool
    original_size: Optional[Tuple[int, int]]
    output_size: Optional[Tuple[int, int]]


def _load_cache(cache_path: Path) -> Dict[str, Any]:
    if not cache_path.exists():
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _unique_tmp_path(dst: Path, suffix: Optional[str] = None) -> Path:
    ext = suffix if suffix is not None else dst.suffix
    token = f"{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}"
    return dst.with_name(f".{dst.stem}.opt.{token}{ext}")


def _atomic_copy_file(src: Path, dst: Path) -> None:
    """Sao chép qua tệp tạm rồi os.replace() — tuyệt đối không ghi đè trực tiếp lên hardlink đích."""
    try:
        if dst.exists() and os.path.samefile(src, dst):
            return
    except OSError:
        pass
    tmp_path = _unique_tmp_path(dst, dst.suffix or src.suffix or ".tmp")
    try:
        shutil.copy2(src, tmp_path)
        os.replace(str(tmp_path), str(dst))
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise


def _save_cache(cache_path: Path, data: Dict[str, Any]) -> None:
    tmp_path = _unique_tmp_path(cache_path, ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(str(tmp_path), str(cache_path))
    except OSError:
        # Lỗi ghi cache không được làm hỏng quá trình chuẩn hóa tài sản
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


def _compute_target_size(
    width: int,
    height: int,
    axis: Literal["width", "height"],
    max_dim: int,
) -> Optional[Tuple[int, int]]:
    """Trả về `(new_w, new_h)` nếu ảnh vượt ngưỡng; trả về `None` nếu đã <= ngưỡng."""
    if width <= 0 or height <= 0:
        return None
    if axis == "width":
        if width <= max_dim:
            return None
        new_w = max_dim
        new_h = max(1, int(round(height * (max_dim / float(width)))))
        return (new_w, new_h)
    else:
        if height <= max_dim:
            return None
        new_h = max_dim
        new_w = max(1, int(round(width * (max_dim / float(height)))))
        return (new_w, new_h)


def optimize_render_asset(
    src_path: Path,
    dst_path: Path,
    kind: AssetKind = "full_image",
) -> AssetOptimizeInfo:
    """Chuẩn hóa kích thước ảnh theo `kind` với cache `(src_path, src_size, src_mtime_ns, target_max_dim)`.

    - `plate`: thu chiều rộng tối đa `2560px` (LANCZOS, JPEG/WebP quality=92).
    - `full_image`: thu chiều rộng tối đa `2304px` (đủ cho zoom 1.18x ở 1080p).
    - `cutout`: thu chiều cao tối đa `1920px`, bảo toàn kênh alpha RGBA (`PNG`, `compress_level=1`).
    - Nếu ảnh gốc đã <= ngưỡng → bỏ qua resize, copy/hardlink trực tiếp để không mất chất lượng.
    - Khi cần resize hoặc fallback → luôn ghi ra tệp tạm rồi `os.replace()` (tuyệt đối không ghi đè hardlink gốc).
    """
    if kind not in ASSET_LIMITS:
        raise ValueError(
            f"Loại asset không hợp lệ: {kind!r}. Chỉ hỗ trợ 'plate', 'cutout', hoặc 'full_image'."
        )

    src = Path(src_path)
    dst = Path(dst_path)
    if not src.exists():
        raise FileNotFoundError(f"Không tìm thấy tệp nguồn ảnh: {src}")

    axis, max_dim = ASSET_LIMITS[kind]
    dst.parent.mkdir(parents=True, exist_ok=True)

    src_stat = src.stat()
    src_sig = {
        "src_path": str(src.resolve()),
        "src_size": src_stat.st_size,
        "src_mtime_ns": src_stat.st_mtime_ns,
        "target_max_dim": max_dim,
        "kind": kind,
    }

    cache_path = dst.parent / CACHE_FILENAME
    cache_data = _load_cache(cache_path)
    cached_entry = cache_data.get(dst.name)

    if (
        isinstance(cached_entry, dict)
        and dst.exists()
        and dst.stat().st_size > 0
        and cached_entry.get("src_path") == src_sig["src_path"]
        and cached_entry.get("src_size") == src_sig["src_size"]
        and cached_entry.get("src_mtime_ns") == src_sig["src_mtime_ns"]
        and cached_entry.get("target_max_dim") == src_sig["target_max_dim"]
        and cached_entry.get("kind") == src_sig["kind"]
    ):
        orig_sz = tuple(cached_entry["original_size"]) if cached_entry.get("original_size") else None
        out_sz = tuple(cached_entry["output_size"]) if cached_entry.get("output_size") else None
        return AssetOptimizeInfo(
            dst_path=dst,
            kind=kind,
            cache_hit=True,
            resized=bool(cached_entry.get("resized", False)),
            original_size=orig_sz,
            output_size=out_sz,
        )

    tmp_out: Optional[Path] = None
    orig_w = 0
    orig_h = 0
    target_size: Optional[Tuple[int, int]] = None

    # Nếu tệp nguồn không phải ảnh hợp lệ (ví dụ fixture giả trong unit test) → copy nguyên tử an toàn
    try:
        with Image.open(src) as raw_img:
            img = ImageOps.exif_transpose(raw_img)
            orig_w, orig_h = img.size
            target_size = _compute_target_size(orig_w, orig_h, axis, max_dim)

            if target_size is not None:
                new_w, new_h = target_size
                suffix = dst.suffix.lower()
                has_alpha = (
                    img.mode in ("RGBA", "LA", "PA")
                    or (img.mode == "P" and "transparency" in img.info)
                )

                if kind == "cutout" or suffix == ".png":
                    work_img = img.convert("RGBA") if (kind == "cutout" or has_alpha) else img.convert("RGB")
                    resized_img = work_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    tmp_out = _unique_tmp_path(dst, dst.suffix or ".png")
                    resized_img.save(tmp_out, format="PNG", compress_level=1)
                elif suffix == ".webp":
                    work_img = img.convert("RGBA") if has_alpha else img.convert("RGB")
                    resized_img = work_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    tmp_out = _unique_tmp_path(dst, dst.suffix)
                    resized_img.save(tmp_out, format="WEBP", quality=92, method=4)
                else:
                    # JPEG mặc định cho plate / full_image
                    work_img = img.convert("RGB")
                    resized_img = work_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    tmp_out = _unique_tmp_path(dst, dst.suffix or ".jpg")
                    resized_img.save(tmp_out, format="JPEG", quality=92, optimize=True)

        # Đã đóng handle tệp nguồn `src` trước khi thao tác trên `dst` (tránh khóa NTFS trên Windows khi dst hardlink tới src)
        if target_size is None:
            if src.resolve() != dst.resolve():
                copy_file_if_different(src, dst)
            cache_data[dst.name] = {
                **src_sig,
                "resized": False,
                "original_size": [orig_w, orig_h],
                "output_size": [orig_w, orig_h],
            }
            _save_cache(cache_path, cache_data)
            return AssetOptimizeInfo(
                dst_path=dst,
                kind=kind,
                cache_hit=False,
                resized=False,
                original_size=(orig_w, orig_h),
                output_size=(orig_w, orig_h),
            )

        assert tmp_out is not None
        new_w, new_h = target_size
        os.replace(str(tmp_out), str(dst))
        cache_data[dst.name] = {
            **src_sig,
            "resized": True,
            "original_size": [orig_w, orig_h],
            "output_size": [new_w, new_h],
        }
        _save_cache(cache_path, cache_data)
        return AssetOptimizeInfo(
            dst_path=dst,
            kind=kind,
            cache_hit=False,
            resized=True,
            original_size=(orig_w, orig_h),
            output_size=(new_w, new_h),
        )
    except Exception:
        if tmp_out is not None:
            try:
                if tmp_out.exists():
                    tmp_out.unlink()
            except OSError:
                pass
        if src.resolve() != dst.resolve():
            _atomic_copy_file(src, dst)
        return AssetOptimizeInfo(
            dst_path=dst,
            kind=kind,
            cache_hit=False,
            resized=False,
            original_size=None,
            output_size=None,
        )


def prepare_render_asset(
    src_path: Path,
    dst_path: Path,
    kind: AssetKind = "full_image",
) -> Path:
    """API công khai chuẩn hóa tài sản ảnh vào thư mục render, trả về đường dẫn đích."""
    return optimize_render_asset(src_path=src_path, dst_path=dst_path, kind=kind).dst_path
