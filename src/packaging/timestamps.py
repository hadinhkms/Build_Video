import logging
from typing import Any, Dict, List, Optional
from src.core.models import Scene

logger = logging.getLogger(__name__)


def format_timestamp_min_sec(seconds: float) -> str:
    """Đổi số giây sang định dạng mm:ss hoặc hh:mm:ss cho YouTube chapters."""
    total_sec = int(round(seconds))
    hrs = total_sec // 3600
    mins = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def generate_youtube_timestamps(scenes: List[Scene], fps: int = 24) -> Optional[str]:
    """
    Sinh danh sách mốc thời gian (chapters) YouTube từ các hồi kịch bản.
    Quy định của YouTube:
    - Mốc đầu tiên bắt buộc phải là 00:00.
    - Cần ít nhất 3 mốc thời gian.
    - Mỗi mốc/chương phải dài tối thiểu 10 giây.
    Nếu không đủ điều kiện (video quá ngắn), trả về None để bỏ timestamps và tránh lỗi YouTube.
    """
    if not scenes:
        return None

    act_names = {
        "HOOK": "Mở đầu kịch tính (Hook)",
        "SETUP": "Thiết lập bối cảnh (Setup)",
        "RISING": "Mâu thuẫn leo thang (Rising)",
        "CLIMAX": "Cao trào nút thắt (Climax)",
        "CLIFFHANGER": "Đoạn kết bỏ ngỏ (Cliffhanger)",
    }

    # 1. Thu thập thời gian bắt đầu và thời lượng của từng hồi
    act_segments: List[Dict[str, Any]] = []
    current_frame = 0
    current_act = None
    act_start_frame = 0
    act_frames = 0

    for s in scenes:
        act = s.act
        if act != current_act:
            if current_act is not None:
                act_segments.append({
                    "act": current_act,
                    "name": act_names.get(current_act, current_act),
                    "start_sec": act_start_frame / float(fps),
                    "duration_sec": act_frames / float(fps),
                })
            current_act = act
            act_start_frame = current_frame
            act_frames = s.duration_in_frames
        else:
            act_frames += s.duration_in_frames

        current_frame += s.duration_in_frames

    if current_act is not None:
        act_segments.append({
            "act": current_act,
            "name": act_names.get(current_act, current_act),
            "start_sec": act_start_frame / float(fps),
            "duration_sec": act_frames / float(fps),
        })

    if not act_segments:
        return None

    # Mốc đầu tiên luôn là 0.0s
    act_segments[0]["start_sec"] = 0.0

    # 2. Gộp các hồi ngắn hơn 10 giây vào hồi trước hoặc hồi sau
    merged_segments: List[Dict[str, Any]] = []
    for seg in act_segments:
        if not merged_segments:
            merged_segments.append(seg)
        else:
            if merged_segments[-1]["duration_sec"] < 10.0:
                prev = merged_segments.pop()
                seg["start_sec"] = prev["start_sec"]
                seg["duration_sec"] += prev["duration_sec"]
                seg["name"] = f"{prev['name']} & {seg['name']}"
                merged_segments.append(seg)
            elif seg["duration_sec"] < 10.0:
                merged_segments[-1]["duration_sec"] += seg["duration_sec"]
                merged_segments[-1]["name"] += f" & {seg['name']}"
            else:
                merged_segments.append(seg)

    # 3. Kiểm tra điều kiện YouTube: ít nhất 3 đoạn và mỗi đoạn >= 10s
    valid_count = len(merged_segments)
    all_ge_10s = all(s["duration_sec"] >= 10.0 for s in merged_segments)

    if valid_count < 3 or not all_ge_10s:
        logger.warning(
            f"Không tạo timestamps YouTube: video chỉ có {valid_count} đoạn (yêu cầu >= 3 đoạn mỗi đoạn >= 10s)."
        )
        return None

    lines = ["⏳ MỐC THỜI GIAN (CHAPTERS):"]
    for seg in merged_segments:
        ts_str = format_timestamp_min_sec(seg["start_sec"])
        lines.append(f"{ts_str} - {seg['name']}")

    return "\n".join(lines)
