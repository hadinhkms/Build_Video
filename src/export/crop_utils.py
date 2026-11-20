from collections import OrderedDict
import os
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from src.core.models import CharacterAnchor, Rect

_MEDIA_DURATION_CACHE: "OrderedDict[Tuple[str, int, int], float]" = OrderedDict()
_MEDIA_DURATION_LOCK = threading.Lock()
_MEDIA_DURATION_CACHE_MAX = 4096


def clear_media_duration_cache() -> None:
    """Xóa bộ nhớ đệm thời lượng media (chủ yếu cho kiểm thử)."""
    with _MEDIA_DURATION_LOCK:
        _MEDIA_DURATION_CACHE.clear()


def _atomic_copy2(src: Path, dst: Path) -> None:
    """Sao chép qua tệp tạm rồi os.replace() để không bao giờ ghi đè in-place lên hardlink đích."""
    token = f"{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}"
    tmp = dst.with_name(f".{dst.name}.copy.{token}")
    try:
        shutil.copy2(src, tmp)
        os.replace(str(tmp), str(dst))
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


def copy_file_if_different(src: Path, dst: Path) -> bool:
    """Ưu tiên hardlink NTFS (os.link) khi cùng thiết bị `st_dev`; fallback sạch về copy nguyên tử."""
    src = Path(src)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    src_stat = src.stat()
    dst_exists = dst.exists()
    dst_stat = dst.stat() if dst_exists else None

    # 1. Nếu đích đã tồn tại và cùng inode -> bỏ qua tức thì (0 I/O)
    if dst_stat is not None:
        if (
            src_stat.st_ino != 0
            and dst_stat.st_ino == src_stat.st_ino
            and dst_stat.st_dev == src_stat.st_dev
        ):
            return False
        try:
            if os.path.samefile(src, dst):
                return False
        except OSError:
            pass

    # 2. Cùng thiết bị (cùng phân vùng NTFS) -> hardlink-first qua os.link()
    parent_stat = dst.parent.stat()
    if src_stat.st_dev == parent_stat.st_dev:
        token = f"{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}"
        tmp_link = dst.with_name(f".{dst.name}.lnk.{token}")
        try:
            os.link(src, tmp_link)
            os.replace(str(tmp_link), str(dst))
            return True
        except OSError:
            try:
                if tmp_link.exists():
                    tmp_link.unlink()
            except OSError:
                pass
            # Fallback sạch sang copy nếu filesystem không hỗ trợ hardlink hoặc bị chặn quyền

    # 3. Khác ổ đĩa hoặc fallback copy: bỏ qua nếu đích đã cùng kích thước & không cũ hơn
    if (
        dst_stat is not None
        and src_stat.st_size == dst_stat.st_size
        and src_stat.st_mtime <= dst_stat.st_mtime
    ):
        return False

    _atomic_copy2(src, dst)
    return True


def get_media_duration(path: Path) -> float:
    """Đo thời lượng file media bằng ffprobe có cache theo (resolved_path, mtime_ns, size)."""
    p = Path(path)
    cache_key: Optional[Tuple[str, int, int]] = None
    try:
        st = p.stat()
        cache_key = (str(p.resolve()), st.st_mtime_ns, st.st_size)
        with _MEDIA_DURATION_LOCK:
            cached = _MEDIA_DURATION_CACHE.get(cache_key)
            if cached is not None:
                _MEDIA_DURATION_CACHE.move_to_end(cache_key)
        if cached is not None:
            return cached
    except OSError:
        cache_key = None

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(p),
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        duration = float(res.stdout.strip())
        if cache_key is not None:
            with _MEDIA_DURATION_LOCK:
                _MEDIA_DURATION_CACHE[cache_key] = duration
                _MEDIA_DURATION_CACHE.move_to_end(cache_key)
                while len(_MEDIA_DURATION_CACHE) > _MEDIA_DURATION_CACHE_MAX:
                    _MEDIA_DURATION_CACHE.popitem(last=False)
        return duration
    except Exception:
        return 5.0

def calculate_crop_rect(
    shot_type: Any,
    char_anchor: Optional[CharacterAnchor],
    cutout_meta: Optional[Dict[str, Any]],
) -> Rect:
    """Tính cropRect chuẩn điện ảnh kẹp trong biên plate [0..1]."""
    st_val = shot_type.value if hasattr(shot_type, "value") else str(shot_type)
    crop_w_map = {
        "wide": 1.0,
        "medium": 0.70,
        "closeup": 0.45,
        "extreme_closeup": 0.30,
        "over_shoulder": 0.55,
    }
    cw = crop_w_map.get(st_val, 0.70)
    ch = cw  # 16:9 plate -> khung crop tương đối tỉ lệ 1:1

    if not char_anchor:
        cx = (1.0 - cw) / 2.0
        cy = (1.0 - ch) / 2.0
        return Rect(x=round(cx, 4), y=round(cy, 4), w=round(cw, 4), h=round(ch, 4))

    aspect = cutout_meta.get("aspect", 0.72) if cutout_meta else 0.72
    face = cutout_meta.get("face", {"x": 0.5, "y": 0.16}) if cutout_meta else {"x": 0.5, "y": 0.16}
    chest = cutout_meta.get("chest", {"x": 0.5, "y": 0.42}) if cutout_meta else {"x": 0.5, "y": 0.42}

    slot_h = char_anchor.height
    cutout_w = slot_h * aspect
    anchor_top_y = char_anchor.y - slot_h

    if st_val in ("closeup", "extreme_closeup", "over_shoulder"):
        target_x = (char_anchor.x - cutout_w / 2.0) + face.get("x", 0.5) * cutout_w
        target_y = anchor_top_y + face.get("y", 0.16) * slot_h
    elif st_val == "medium":
        target_x = (char_anchor.x - cutout_w / 2.0) + chest.get("x", 0.5) * cutout_w
        target_y = anchor_top_y + chest.get("y", 0.42) * slot_h
    else:
        target_x = char_anchor.x
        target_y = anchor_top_y + slot_h / 2.0

    cx = max(0.0, min(1.0 - cw, target_x - cw / 2.0))
    cy = max(0.0, min(1.0 - ch, target_y - ch / 2.0))
    return Rect(x=round(cx, 4), y=round(cy, 4), w=round(cw, 4), h=round(ch, 4))
