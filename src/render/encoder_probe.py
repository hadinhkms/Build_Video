"""Bộ thăm dò encoder phần cứng thực tế (h264_nvenc / B-frames / fallback libx264).

Chạy phép thử mã hóa thật 1 khung hình vào `null` (< 300 ms, cache trong tiến trình)
để xác minh chắc chắn GPU, driver NVIDIA và FFmpeg hệ thống thực sự mã hóa được
`h264_nvenc` (không chỉ dựa vào danh sách `ffmpeg -encoders`).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from src.core.hardware_profile import detect_hardware_profile

_PROBE_CACHE: Dict[Tuple[str, Optional[int]], "EncoderCapability"] = {}

_VALID_ENCODER_ALIASES = {
    "auto": "auto",
    "nvenc": "nvenc",
    "h264_nvenc": "nvenc",
    "libx264": "libx264",
    "cpu": "libx264",
}


@dataclass(frozen=True)
class EncoderCapability:
    selected_encoder: str  # "h264_nvenc" | "libx264"
    requested_encoder: str  # "auto" | "nvenc" | "libx264"
    nvenc_available: bool
    supports_bframes: bool
    ffmpeg_bin_dir: Optional[Path]
    max_parallel_nvenc: int
    probe_ms: int = 0
    reason: str = "ok"

    @property
    def is_nvenc(self) -> bool:
        return self.selected_encoder == "h264_nvenc"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_encoder": self.selected_encoder,
            "requested_encoder": self.requested_encoder,
            "nvenc_available": self.nvenc_available,
            "supports_bframes": self.supports_bframes,
            "ffmpeg_bin_dir": str(self.ffmpeg_bin_dir) if self.ffmpeg_bin_dir else None,
            "max_parallel_nvenc": self.max_parallel_nvenc,
            "probe_ms": self.probe_ms,
            "reason": self.reason,
        }


def clear_encoder_probe_cache() -> None:
    """Xóa cache thăm dò encoder trong tiến trình (chủ yếu cho kiểm thử)."""
    _PROBE_CACHE.clear()


def normalize_encoder_request(requested: Optional[str]) -> str:
    raw = (requested or "auto").strip().lower()
    if raw not in _VALID_ENCODER_ALIASES:
        raise ValueError(
            f"Giá trị render.encoder không hợp lệ: {requested!r}. "
            f"Chỉ chấp nhận 'auto', 'nvenc', hoặc 'libx264'."
        )
    return _VALID_ENCODER_ALIASES[raw]


def find_system_ffmpeg_bin_dir() -> Optional[Path]:
    """Tìm thư mục chứa ffmpeg hệ thống trên PATH."""
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        return None
    resolved = Path(ffmpeg_path).resolve()
    if not resolved.exists():
        return None
    return resolved.parent


def compute_max_parallel_nvenc(vram_mb: Optional[int]) -> int:
    """Giới hạn số phiên NVENC đồng thời theo VRAM (<= 4 GB -> 3, > 4 GB -> tối đa 4)."""
    if vram_mb is None or vram_mb <= 0:
        return 3
    if vram_mb <= 4096:
        return 3
    return 4


def _run_nvenc_live_test(ffmpeg_exe: str, bframes: int, timeout_sec: float = 3.0) -> bool:
    """Chạy phép thử mã hóa sống 1 khung hình bằng h264_nvenc vào null."""
    cmd = [
        ffmpeg_exe,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=black:s=256x256:r=24:d=0.1",
        "-frames:v",
        "1",
        "-c:v",
        "h264_nvenc",
        "-bf",
        str(bframes),
        "-f",
        "null",
        "-",
    ]
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_sec,
        )
        return res.returncode == 0
    except Exception:
        return False


def probe_encoder_capability(
    requested: str = "auto",
    vram_mb: Optional[int] = None,
    force_refresh: bool = False,
) -> EncoderCapability:
    """Thăm dò thực tế khả năng h264_nvenc + B-frames và chọn encoder phù hợp.

    - `requested="libx264"`: ép dùng CPU `libx264` (không chạy probe GPU).
    - `requested="nvenc"`: bắt buộc `h264_nvenc`, báo `RuntimeError` nếu không khả dụng.
    - `requested="auto"`: dùng `h264_nvenc` nếu probe thật PASS, ngược lại fallback êm về `libx264`.
    """
    norm_req = normalize_encoder_request(requested)
    cache_key = (norm_req, vram_mb)
    if not force_refresh and cache_key in _PROBE_CACHE:
        return _PROBE_CACHE[cache_key]

    t0 = time.perf_counter()
    ffmpeg_bin_dir = find_system_ffmpeg_bin_dir()

    if norm_req == "libx264":
        cap = EncoderCapability(
            selected_encoder="libx264",
            requested_encoder="libx264",
            nvenc_available=False,
            supports_bframes=False,
            ffmpeg_bin_dir=ffmpeg_bin_dir,
            max_parallel_nvenc=0,
            probe_ms=int(round((time.perf_counter() - t0) * 1000)),
            reason="forced_libx264",
        )
        _PROBE_CACHE[cache_key] = cap
        return cap

    if ffmpeg_bin_dir is None:
        if norm_req == "nvenc":
            raise RuntimeError(
                "render.encoder='nvenc' nhưng không tìm thấy ffmpeg hệ thống trên PATH."
            )
        cap = EncoderCapability(
            selected_encoder="libx264",
            requested_encoder="auto",
            nvenc_available=False,
            supports_bframes=False,
            ffmpeg_bin_dir=None,
            max_parallel_nvenc=0,
            probe_ms=int(round((time.perf_counter() - t0) * 1000)),
            reason="ffmpeg_not_found",
        )
        _PROBE_CACHE[cache_key] = cap
        return cap

    ffmpeg_exe = str(ffmpeg_bin_dir / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"))
    if not Path(ffmpeg_exe).exists():
        ffmpeg_exe = shutil.which("ffmpeg") or "ffmpeg"

    # Thử -bf 2 trước: trên Turing/Ada (TU106/RTX) chỉ cần đúng 1 lần gọi (~150-250ms)
    supports_bframes = _run_nvenc_live_test(ffmpeg_exe, bframes=2)
    if supports_bframes:
        nvenc_available = True
    else:
        # Thử -bf 0 cho các GPU Volta/GTX 1650 TU117 không hỗ trợ B-frames
        nvenc_available = _run_nvenc_live_test(ffmpeg_exe, bframes=0)

    probe_ms = int(round((time.perf_counter() - t0) * 1000))

    if not nvenc_available:
        if norm_req == "nvenc":
            raise RuntimeError(
                "render.encoder='nvenc' nhưng phép thử mã hóa sống h264_nvenc thất bại "
                "(thiếu GPU NVIDIA, driver cũ, hoặc bản FFmpeg không hỗ trợ NVENC)."
            )
        cap = EncoderCapability(
            selected_encoder="libx264",
            requested_encoder="auto",
            nvenc_available=False,
            supports_bframes=False,
            ffmpeg_bin_dir=ffmpeg_bin_dir,
            max_parallel_nvenc=0,
            probe_ms=probe_ms,
            reason="nvenc_probe_failed",
        )
        _PROBE_CACHE[cache_key] = cap
        return cap

    resolved_vram = vram_mb
    if resolved_vram is None:
        try:
            hw = detect_hardware_profile()
            resolved_vram = hw.vram_mb if hw.has_nvidia else 0
        except Exception:
            resolved_vram = 0

    max_parallel = compute_max_parallel_nvenc(resolved_vram)
    cap = EncoderCapability(
        selected_encoder="h264_nvenc",
        requested_encoder=norm_req,
        nvenc_available=True,
        supports_bframes=supports_bframes,
        ffmpeg_bin_dir=ffmpeg_bin_dir,
        max_parallel_nvenc=max_parallel,
        probe_ms=probe_ms,
        reason="nvenc_bframes_ok" if supports_bframes else "nvenc_no_bframes_ok",
    )
    _PROBE_CACHE[cache_key] = cap
    return cap


def main() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Thăm dò năng lực encoder GPU/CPU CineStory")
    parser.add_argument("--encoder", default="auto", choices=["auto", "nvenc", "libx264"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    cap = probe_encoder_capability(requested=args.encoder, force_refresh=True)
    if args.json:
        print(json.dumps(cap.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(
            f"Encoder: {cap.selected_encoder} | NVENC={cap.nvenc_available} | "
            f"B-frames={cap.supports_bframes} | max_parallel={cap.max_parallel_nvenc} | "
            f"probe={cap.probe_ms}ms | ffmpeg_dir={cap.ffmpeg_bin_dir}"
        )


if __name__ == "__main__":
    main()
