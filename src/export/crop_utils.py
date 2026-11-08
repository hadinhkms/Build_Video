import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from src.core.models import CharacterAnchor, Rect

def copy_file_if_different(src: Path, dst: Path) -> bool:
    """Sao chép tệp nếu đích chưa tồn tại hoặc khác kích thước / thời gian sửa đổi."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.copy2(src, dst)
        return True
    src_stat = src.stat()
    dst_stat = dst.stat()
    if src_stat.st_size != dst_stat.st_size or src_stat.st_mtime > dst_stat.st_mtime:
        shutil.copy2(src, dst)
        return True
    return False

def get_media_duration(path: Path) -> float:
    """Đo thời lượng file media bằng ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(res.stdout.strip())
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
