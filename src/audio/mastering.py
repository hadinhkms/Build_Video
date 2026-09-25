"""
Chuẩn hóa độ lớn âm thanh (loudness) 2 lượt cho video master, chạy 1 lần duy nhất sau khi ghép.

Chuyển thể từ helpers/render.py (measure_loudness, apply_loudnorm_two_pass) của
browser-use/video-use — https://github.com/browser-use/video-use
MIT License, Copyright (c) 2026 Browser Use.

Thay đổi so với bản gốc: subprocess đọc stderr bằng utf-8 (console Windows), sample rate
lấy từ config thay vì cố định 48000, trả về số đo để log thay vì chỉ True/False, và đây là
lần DUY NHẤT audio được mã hóa AAC (clip trung gian giữ PCM).
"""
import json
import subprocess
from typing import Optional


def _run(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def parse_loudnorm_json(stderr: str) -> Optional[dict]:
    """loudnorm in khối JSON ở cuối stderr; trả về dict hoặc None nếu không đọc được."""
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(stderr[start:end + 1])
    except json.JSONDecodeError:
        return None


def _loudnorm_filter(target_i: float, target_tp: float, target_lra: float) -> str:
    return f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}"


def measure_loudness(input_path: str, target_i: float, target_tp: float, target_lra: float) -> Optional[dict]:
    """Lượt 1: đo input_i / input_tp / input_lra / input_thresh / target_offset."""
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats",
        "-i", input_path,
        "-af", _loudnorm_filter(target_i, target_tp, target_lra) + ":print_format=json",
        "-vn", "-f", "null", "-",
    ]
    data = parse_loudnorm_json(_run(cmd).stderr)
    needed = {"input_i", "input_tp", "input_lra", "input_thresh", "target_offset"}
    if data is None or not needed.issubset(data.keys()):
        return None
    return data


def master_loudness(
    input_path: str,
    output_path: str,
    target_i: float = -14.0,
    target_tp: float = -1.0,
    target_lra: float = 11.0,
    sample_rate: int = 44100,
) -> Optional[dict]:
    """
    Lượt 2: chuẩn hóa audio theo số đo lượt 1, copy nguyên luồng video.
    Trả về số đo lượt 2 (output_i, output_tp, normalization_type...) hoặc None nếu thất bại.
    """
    filter_str = _loudnorm_filter(target_i, target_tp, target_lra)
    measurement = measure_loudness(input_path, target_i, target_tp, target_lra)
    if measurement is None:
        print("   [Cảnh báo] Không đo được loudness, chuyển sang chuẩn hóa 1 lượt")
    else:
        print(f"   Lượt 1 đo được: I={measurement['input_i']} LUFS, "
              f"TP={measurement['input_tp']} dBTP, LRA={measurement['input_lra']} LU")
        filter_str += (
            f":measured_I={measurement['input_i']}"
            f":measured_TP={measurement['input_tp']}"
            f":measured_LRA={measurement['input_lra']}"
            f":measured_thresh={measurement['input_thresh']}"
            f":offset={measurement['target_offset']}"
            f":linear=true"
        )

    # Khi không đạt được chế độ linear (thường gặp với giọng đọc), loudnorm chạy dynamic và gắn
    # timestamp khối cuối lệch tới 100ms -> audio dài hơn video. asetpts đánh lại timestamp liền mạch.
    audio_filter = filter_str + ":print_format=json,asetpts=N/SR/TB"
    result = _encode_final(input_path, output_path, sample_rate, audio_filter)
    if result.returncode != 0:
        print(f"   [Lỗi chuẩn hóa loudness]: {result.stderr[-300:]}")
        return None
    return parse_loudnorm_json(result.stderr) or {}


def encode_without_mastering(input_path: str, output_path: str, sample_rate: int = 44100) -> bool:
    """Phương án dự phòng: chỉ mã hóa audio sang AAC, không chuẩn hóa loudness."""
    result = _encode_final(input_path, output_path, sample_rate)
    if result.returncode != 0:
        print(f"   [Lỗi mã hóa audio]: {result.stderr[-300:]}")
    return result.returncode == 0


def _encode_final(input_path: str, output_path: str, sample_rate: int, audio_filter: Optional[str] = None) -> subprocess.CompletedProcess:
    """Copy nguyên luồng video, mã hóa audio AAC 1 lần duy nhất cho file MP4 cuối."""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-nostats", "-i", input_path, "-c:v", "copy"]
    if audio_filter:
        cmd += ["-af", audio_filter]
    cmd += [
        # loudnorm nội suy lên 192kHz, phải ép lại sample rate đầu ra
        "-c:a", "aac", "-b:a", "192k", "-ar", str(sample_rate),
        "-movflags", "+faststart",
        output_path,
    ]
    return _run(cmd)
