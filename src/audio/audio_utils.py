import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple


def words_path_for(audio_path: str) -> str:
    return Path(audio_path).with_suffix(".words.json").as_posix()


def meta_path_for(audio_path: str) -> str:
    return Path(audio_path).with_suffix(".meta.json").as_posix()


def load_words(audio_path: str) -> list:
    path = words_path_for(audio_path)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def boundary_events_to_words(events: list) -> list:
    return [
        {
            "text": e["text"],
            "start": round(e["offset"] / 1e7, 4),
            "end": round((e["offset"] + e["duration"]) / 1e7, 4),
        }
        for e in events
    ]


def estimate_words(text: str, speech_start: float, speech_end: float) -> list:
    syllables = re.findall(r"\w+", text)
    total_chars = sum(len(s) for s in syllables)
    if not total_chars:
        return []
    sec_per_char = (speech_end - speech_start) / total_chars
    words, cursor = [], speech_start
    for syllable in syllables:
        end = cursor + len(syllable) * sec_per_char
        words.append({"text": syllable, "start": round(cursor, 4), "end": round(end, 4)})
        cursor = end
    return words


def detect_speech_span(audio_path: str, noise_db: float = -40.0, min_silence_sec: float = 0.1) -> Tuple[float, float]:
    duration = get_audio_duration(audio_path)
    stderr = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", audio_path,
         "-af", f"silencedetect=noise={noise_db}dB:d={min_silence_sec}", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stderr
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: (-?[\d.]+)", stderr)]

    speech_start, speech_end = 0.0, duration
    if starts and ends and starts[0] <= 0.05:
        speech_start = ends[0]
    if starts and (len(ends) < len(starts) or ends[-1] >= duration - 0.05):
        speech_end = starts[-1]
    if speech_end <= speech_start:
        return 0.0, duration
    return round(speech_start, 4), round(speech_end, 4)


def get_audio_duration(file_path: str) -> float:
    """Dùng ffprobe để lấy chính xác thời lượng file audio."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        raise RuntimeError(f"[Lỗi nghiêm trọng] Không thể đo thời lượng audio bằng ffprobe cho '{file_path}': {e}")


def get_audio_stream_props(file_path: str) -> Tuple[int, str]:
    """Lấy sample_rate và channel_layout (mono/stereo) của audio bằng ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=sample_rate,channels",
        "-of", "json",
        file_path,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        info = json.loads(res.stdout)["streams"][0]
        sr = int(info.get("sample_rate", 24000))
        ch = int(info.get("channels", 1))
        cl = "mono" if ch == 1 else "stereo"
        return sr, cl
    except Exception:
        return 24000, "mono"
