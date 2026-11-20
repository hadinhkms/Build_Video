from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
import subprocess
import threading
import uuid
import wave
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

from src.core.hardware_profile import detect_hardware_profile


def envelope_cache_path_for(audio_path: Path) -> Path:
    """Đường dẫn tệp cache đĩa `<audio_stem>.envelope.json` nằm cạnh tệp audio."""
    return Path(audio_path).with_suffix(".envelope.json")


def _compute_file_sha1(audio_path: Path) -> str:
    hasher = hashlib.sha1()
    with open(audio_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class AudioEnvelopeCalculator:
    """Tính toán biên độ âm thanh (RMS envelope) theo frame cho khẩu hình miệng nhân vật."""

    def __init__(self, fps: int = 24, target_sr: int = 16000, use_cache: bool = True):
        self.fps = fps
        self.target_sr = target_sr
        self.use_cache = use_cache
        self.attack_ms = 30.0
        self.release_ms = 80.0
        self.threshold = 0.15

    def _load_cached_envelope(self, audio_path: Path, source_sha1: str) -> Optional[List[float]]:
        cache_path = envelope_cache_path_for(audio_path)
        if not cache_path.exists():
            return None
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if (
                isinstance(data, dict)
                and data.get("source_sha1") == source_sha1
                and data.get("fps") == self.fps
                and data.get("target_sr") == self.target_sr
                and isinstance(data.get("envelope"), list)
            ):
                return [float(v) for v in data["envelope"]]
        except Exception:
            return None
        return None

    def _save_cached_envelope(
        self,
        audio_path: Path,
        source_sha1: str,
        envelope: List[float],
    ) -> None:
        cache_path = envelope_cache_path_for(audio_path)
        token = f"{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}"
        tmp_path = cache_path.with_name(f".{cache_path.name}.tmp.{token}")
        payload = {
            "source_sha1": source_sha1,
            "fps": self.fps,
            "target_sr": self.target_sr,
            "envelope": envelope,
        }
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, separators=(",", ":"))
            os.replace(str(tmp_path), str(cache_path))
        except OSError:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass

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

    def compute_full_envelope(
        self,
        audio_path: Path,
        use_cache: Optional[bool] = None,
    ) -> List[float]:
        """Tính envelope cho toàn bộ file audio với 5 bước + cache đĩa `<audio_stem>.envelope.json`."""
        audio_path = Path(audio_path)
        if not audio_path.exists():
            return []

        cache_enabled = self.use_cache if use_cache is None else bool(use_cache)
        source_sha1: Optional[str] = None
        if cache_enabled:
            source_sha1 = _compute_file_sha1(audio_path)
            cached = self._load_cached_envelope(audio_path, source_sha1)
            if cached is not None:
                return cached

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

        if cache_enabled and source_sha1 is not None:
            self._save_cached_envelope(audio_path, source_sha1, result)

        return result

    def slice_envelope(
        self,
        full_envelope: List[float],
        start_in_file_sec: float,
        duration_in_frames: int,
    ) -> List[float]:
        """Cắt envelope cho một cảnh/cảnh con và đệm thêm 0 nếu audio ngắn hơn duration_in_frames."""
        if duration_in_frames <= 0:
            return []
        start_frame = max(0, int(round(start_in_file_sec * self.fps)))
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


def _default_envelope_workers() -> int:
    try:
        cores = int(detect_hardware_profile().cpu_physical_cores)
    except Exception:
        cores = max(1, (os.cpu_count() or 4) // 2)
    return max(1, min(8, cores))


def batch_compute_envelopes(
    audio_paths: Iterable[Path],
    fps: int = 24,
    target_sr: int = 16000,
    max_workers: Optional[int] = None,
    use_cache: bool = True,
) -> Dict[Path, List[float]]:
    """Tính full_envelope cho tập tệp audio duy nhất (tận dụng cache đĩa + ThreadPoolExecutor khi miss).

    Trả về dict ánh xạ từng `Path` đầu vào sang danh sách float full_envelope tương ứng.
    """
    unique_inputs: List[Path] = []
    seen_inputs = set()
    resolved_to_canonical: Dict[Path, Path] = {}

    for raw_p in audio_paths:
        if raw_p is None:
            continue
        p = Path(raw_p)
        if not p.exists():
            continue
        if p not in seen_inputs:
            seen_inputs.add(p)
            unique_inputs.append(p)
        rp = p.resolve()
        if rp not in resolved_to_canonical:
            resolved_to_canonical[rp] = rp

    if not unique_inputs:
        return {}

    calc = AudioEnvelopeCalculator(fps=fps, target_sr=target_sr, use_cache=use_cache)
    env_by_resolved: Dict[Path, List[float]] = {}
    misses: List[Path] = []

    # Lượt 1: đọc nhanh các tệp đã trúng cache đĩa (không cần khởi tạo ThreadPool)
    for rp in resolved_to_canonical:
        if use_cache:
            sha1 = _compute_file_sha1(rp)
            cached = calc._load_cached_envelope(rp, sha1)
            if cached is not None:
                env_by_resolved[rp] = cached
                continue
        misses.append(rp)

    # Lượt 2: tính song song các tệp cache miss
    if misses:
        workers = max(1, int(max_workers)) if max_workers is not None else _default_envelope_workers()
        workers = min(workers, len(misses))
        if workers <= 1:
            for rp in misses:
                env_by_resolved[rp] = calc.compute_full_envelope(rp, use_cache=use_cache)
        else:
            def _worker(path_item: Path) -> Tuple[Path, List[float]]:
                worker_calc = AudioEnvelopeCalculator(fps=fps, target_sr=target_sr, use_cache=use_cache)
                return path_item, worker_calc.compute_full_envelope(path_item, use_cache=use_cache)

            with ThreadPoolExecutor(max_workers=workers) as executor:
                for rp, env in executor.map(_worker, misses):
                    env_by_resolved[rp] = env

    return {p: env_by_resolved[p.resolve()] for p in unique_inputs if p.resolve() in env_by_resolved}


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
