import math
import subprocess
import wave
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np


class AudioEnvelopeCalculator:
    """Tính toán biên độ âm thanh (RMS envelope) theo frame cho khẩu hình miệng nhân vật."""

    def __init__(self, fps: int = 24, target_sr: int = 16000):
        self.fps = fps
        self.target_sr = target_sr
        self.attack_ms = 30.0
        self.release_ms = 80.0
        self.threshold = 0.15

    def _decode_to_pcm(self, audio_path: Path) -> Tuple[np.ndarray, int]:
        """Giải mã audio thành mảng numpy float [-1.0, 1.0] mono."""
        # 1. Thử đọc trực tiếp nếu là WAV mono 16-bit
        if audio_path.suffix.lower() == ".wav":
            try:
                with wave.open(str(audio_path), "rb") as wf:
                    n_channels = wf.getnchannels()
                    sampwidth = wf.getsampwidth()
                    sr = wf.getframerate()
                    n_frames = wf.getnframes()
                    if sampwidth == 2:  # 16-bit PCM
                        raw_data = wf.readframes(n_frames)
                        audio_data = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
                        if n_channels > 1:
                            audio_data = audio_data.reshape(-1, n_channels).mean(axis=1)
                        return audio_data, sr
            except Exception:
                pass  # Fallback sang ffmpeg

        # 2. Dùng ffmpeg giải mã sang mono PCM 16kHz
        cmd = [
            "ffmpeg",
            "-y",
            "-v", "error",
            "-i", str(audio_path),
            "-f", "f32le",
            "-ac", "1",
            "-ar", str(self.target_sr),
            "pipe:1",
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        samples = np.frombuffer(proc.stdout, dtype=np.float32)
        return samples, self.target_sr

    def compute_full_envelope(self, audio_path: Path) -> List[float]:
        """Tính envelope cho toàn bộ file audio với 5 bước theo thiết kế kỹ thuật Phase 3."""
        if not audio_path.exists():
            return []

        samples, sr = self._decode_to_pcm(audio_path)
        if len(samples) == 0:
            return []

        # 1. Cửa sổ theo frame (1 / fps)
        samples_per_frame = sr / float(self.fps)
        total_frames = int(math.ceil(len(samples) / samples_per_frame))

        # 2. Tính RMS theo từng khung hình
        rms_values = np.zeros(total_frames, dtype=np.float32)
        for f in range(total_frames):
            start = int(f * samples_per_frame)
            end = min(len(samples), int((f + 1) * samples_per_frame))
            if start < end:
                chunk = samples[start:end]
                rms = np.sqrt(np.mean(chunk**2))
                rms_values[f] = rms

        # 3. Chuẩn hóa theo phân vị 95 (95th percentile)
        p95 = float(np.percentile(rms_values, 95))
        if p95 > 1e-6:
            norm_rms = np.clip(rms_values / p95, 0.0, 1.0)
        else:
            norm_rms = np.zeros_like(rms_values)

        # 4. Làm mượt với attack 30ms và release 80ms
        dt = 1.0 / float(self.fps)
        alpha_attack = 1.0 - math.exp(-dt / (self.attack_ms / 1000.0))
        alpha_release = 1.0 - math.exp(-dt / (self.release_ms / 1000.0))

        smoothed = np.zeros_like(norm_rms)
        current = 0.0
        for i, val in enumerate(norm_rms):
            if val > current:
                current += alpha_attack * (val - current)
            else:
                current += alpha_release * (val - current)
            smoothed[i] = current

        # 5. Áp ngưỡng 0.15 và làm tròn 2 chữ số
        result = []
        for val in smoothed:
            if val < self.threshold:
                result.append(0.0)
            else:
                result.append(round(float(min(1.0, val)), 2))

        return result

    def slice_envelope(
        self,
        full_envelope: List[float],
        start_in_file_sec: float,
        duration_in_frames: int,
    ) -> List[float]:
        """Cắt envelope cho một cảnh/cảnh con và đệm thêm 0 nếu audio ngắn hơn duration_in_frames."""
        start_frame = int(round(start_in_file_sec * self.fps))
        end_frame = start_frame + duration_in_frames

        if start_frame < len(full_envelope):
            sub = full_envelope[start_frame:min(end_frame, len(full_envelope))]
        else:
            sub = []

        # Đệm thêm 0 cho đủ duration_in_frames
        if len(sub) < duration_in_frames:
            sub = sub + [0.0] * (duration_in_frames - len(sub))
        elif len(sub) > duration_in_frames:
            sub = sub[:duration_in_frames]

        return sub


def compute_shot_envelope(
    audio_path: Optional[Path],
    start_in_file_sec: float,
    duration_in_frames: int,
    is_dialogue: bool,
    speaker: str,
    on_screen_character_id: Optional[str] = None,
    character_id: str = "nhan_vat_chinh",
    fps: int = 24,
) -> Optional[List[float]]:
    """Quy tắc miệng: chỉ cử động khi is_dialogue đúng và speaker là nhân vật trên hình."""
    # Quy tắc: chỉ khi là đối thoại và nhân vật đang nói là nhân vật trên màn hình
    speaking_char = on_screen_character_id or character_id
    if not is_dialogue or speaker != speaking_char or not audio_path or not audio_path.exists():
        return None

    calc = AudioEnvelopeCalculator(fps=fps)
    full_env = calc.compute_full_envelope(audio_path)
    return calc.slice_envelope(full_env, start_in_file_sec, duration_in_frames)
