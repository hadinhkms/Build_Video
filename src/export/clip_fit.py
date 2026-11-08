import math
from typing import Optional

from src.core.models import ClipFit


def plan_clip_fit(
    clip_duration_sec: float,
    scene_duration_sec: float,
    min_ratio: float = 0.8,
    is_loop: bool = False,
    fps: int = 24,
) -> ClipFit:
    """Tính toán chiến lược khớp thời lượng clip với cảnh theo bảng quyết định Phase 3."""
    if scene_duration_sec <= 0:
        raise ValueError("scene_duration_sec phải lớn hơn 0")
    if clip_duration_sec <= 0:
        raise ValueError("clip_duration_sec phải lớn hơn 0")

    # Trường hợp 1: Clip dài hơn hoặc bằng cảnh
    if clip_duration_sec >= scene_duration_sec:
        return ClipFit(
            playback_rate=1.0,
            freeze_at_frame=None,
            loop=False,
        )

    # Trường hợp 2: Clip ngắn hơn nhưng trong ngưỡng làm chậm (>= min_ratio * cảnh)
    threshold = min_ratio * scene_duration_sec
    if clip_duration_sec >= threshold:
        rate = round(clip_duration_sec / scene_duration_sec, 4)
        # Giới hạn an toàn trong (0, 1.0]
        rate = min(1.0, max(0.1, rate))
        return ClipFit(
            playback_rate=rate,
            freeze_at_frame=None,
            loop=False,
        )

    # Trường hợp 3 & 4: Clip ngắn hơn min_ratio * cảnh
    if is_loop:
        # Trường hợp 4: Clip idle loop (.loop.mp4)
        return ClipFit(
            playback_rate=1.0,
            freeze_at_frame=None,
            loop=True,
        )
    else:
        # Trường hợp 3: Clip thường -> phát hết rồi freeze tại frame cuối
        freeze_frame = max(0, math.floor(clip_duration_sec * fps) - 1)
        return ClipFit(
            playback_rate=1.0,
            freeze_at_frame=freeze_frame,
            loop=False,
        )
