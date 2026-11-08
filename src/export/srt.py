import math
from typing import Any, Dict, List, Union

from src.core.models import RenderProps, Scene


def format_srt_time(seconds: float) -> str:
    """Đổi số giây sang định dạng chuẩn SRT (HH:MM:SS,mmm), làm tròn tới mili giây."""
    total_ms = int(round(max(seconds, 0.0) * 1000))
    hrs, rem = divmod(total_ms, 3_600_000)
    mins, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def build_srt_from_props(props: Union[RenderProps, Dict[str, Any]]) -> str:
    """Xuất nội dung SRT hoàn chỉnh từ captions trong RenderProps (khớp 100% với phụ đề trên hình)."""
    if isinstance(props, dict):
        props_obj = RenderProps.model_validate(props)
    else:
        props_obj = props

    fps = props_obj.fps
    entries: List[str] = []
    entry_idx = 1

    current_frame_offset = 0

    for scene in props_obj.scenes:
        scene_start_sec = current_frame_offset / float(fps)

        # TitleCard và EndScreen không có phụ đề thoại SRT
        if scene.kind == "story":
            for cap in scene.captions:
                abs_start = scene_start_sec + cap.start
                abs_end = scene_start_sec + cap.end

                start_str = format_srt_time(abs_start)
                end_str = format_srt_time(abs_end)

                entries.append(f"{entry_idx}\n{start_str} --> {end_str}\n{cap.text}\n")
                entry_idx += 1

        current_frame_offset += scene.duration_in_frames

    return "\n".join(entries).strip() + "\n" if entries else ""


def build_srt_entries(clips: list) -> list:
    """Hàm tương thích ngược với renderer ffmpeg cũ."""
    entries = []
    clip_start = 0.0
    subtitle_hold_sec = 0.3
    for idx, clip in enumerate(clips, start=1):
        words = clip.get("words") or []
        if words:
            start = clip_start + max(words[0]["start"], 0.0)
            end = clip_start + min(words[-1]["end"] + subtitle_hold_sec, clip["duration"])
        else:
            start, end = clip_start, clip_start + clip["duration"]
        entries.append(f"{idx}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{clip['text']}\n")
        clip_start += clip["duration"]
    return entries
