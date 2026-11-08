import math

# Khoảng đệm sau lời thoại để chuyển cảnh mượt
SHOT_TAIL_PAD_SEC = 0.6
# Giữ phụ đề thêm một chút sau từ cuối cùng để người xem kịp đọc hết
SUBTITLE_HOLD_SEC = 0.3
TTS_LABELS = {"edge": "Edge-TTS (miễn phí)", "vbee": "Vbee"}

def plan_shot_frames(
    audio_duration: float,
    fps: int,
    min_duration: float,
    pad_sec: float = SHOT_TAIL_PAD_SEC,
) -> int:
    """Số frame shot = ceil(max(audio + pad_sec, min_duration) * fps - 1e-6)."""
    raw = max(audio_duration + pad_sec, min_duration)
    return math.ceil(raw * fps - 1e-6)

def plan_shot_duration(
    audio_duration: float,
    fps: int,
    min_duration: float,
    pad_sec: float = SHOT_TAIL_PAD_SEC,
) -> float:
    """Thời lượng shot = số frame / fps, làm tròn 4 chữ số thập phân."""
    frames = plan_shot_frames(audio_duration, fps, min_duration, pad_sec)
    return round(frames / fps, 4)
