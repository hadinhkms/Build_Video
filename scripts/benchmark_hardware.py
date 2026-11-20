"""Công cụ Benchmark Sweep tự động cho CineStory Engine (OPT Phase 1).

Quét ma trận (gl × concurrency × x264_preset), theo dõi Peak RAM / Peak VRAM / CPU%,
lưu báo cáo chi tiết vào output/<chapterId>/bench_hw_matrix.json và (khi có --apply)
cập nhật cấu hình tối ưu thỏa ngưỡng an toàn vào config/settings.json -> render.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.hardware_profile import HardwareProfile, detect_hardware_profile
from src.core.scratch_manager import ScratchManager
from src.render.encoder_probe import EncoderCapability, probe_encoder_capability
from src.render.remotion_runner import RemotionRunner
from src.story_parser import slugify_chapter_id


ANGLE_CONCURRENCY_SWEEP = [8, 12, 16, 20, 24]
SWANGLE_CONCURRENCY_SWEEP = [16, 24, 28, 32]
X264_PRESETS_COMPARE = ["medium", "faster", "veryfast"]
NVENC_PRESETS_COMPARE = ["p4", "p5", "p6"]


def _read_ram_used_gb() -> float:
    if sys.platform == "win32":
        try:
            from ctypes import wintypes

            class _MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", wintypes.DWORD),
                    ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_uint64),
                    ("ullAvailPhys", ctypes.c_uint64),
                    ("ullTotalPageFile", ctypes.c_uint64),
                    ("ullAvailPageFile", ctypes.c_uint64),
                    ("ullTotalVirtual", ctypes.c_uint64),
                    ("ullAvailVirtual", ctypes.c_uint64),
                    ("ullAvailExtendedVirtual", ctypes.c_uint64),
                ]

            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(_MEMORYSTATUSEX)]
            k32.GlobalMemoryStatusEx.restype = wintypes.BOOL
            mem = _MEMORYSTATUSEX()
            mem.dwLength = ctypes.sizeof(mem)
            if k32.GlobalMemoryStatusEx(ctypes.byref(mem)):
                used = max(0, mem.ullTotalPhys - mem.ullAvailPhys)
                return round(used / (1024 ** 3), 2)
        except Exception:
            return 0.0
    return 0.0


def _read_system_times() -> Optional[Tuple[int, int, int]]:
    if sys.platform != "win32":
        return None
    try:
        from ctypes import wintypes

        class _FILETIME(ctypes.Structure):
            _fields_ = [
                ("dwLowDateTime", wintypes.DWORD),
                ("dwHighDateTime", wintypes.DWORD),
            ]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetSystemTimes.argtypes = [
            ctypes.POINTER(_FILETIME),
            ctypes.POINTER(_FILETIME),
            ctypes.POINTER(_FILETIME),
        ]
        k32.GetSystemTimes.restype = wintypes.BOOL

        idle = _FILETIME()
        kernel = _FILETIME()
        user = _FILETIME()
        if not k32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            return None

        def _ft_to_int(ft: _FILETIME) -> int:
            return (int(ft.dwHighDateTime) << 32) | int(ft.dwLowDateTime)

        return (_ft_to_int(idle), _ft_to_int(kernel), _ft_to_int(user))
    except Exception:
        return None


def _read_vram_used_mb(timeout_sec: float = 1.5) -> float:
    try:
        res = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_sec,
        )
        if res.returncode == 0 and res.stdout.strip():
            first = res.stdout.strip().splitlines()[0].strip()
            return round(float(first), 1)
    except Exception:
        pass
    return 0.0


class ResourceMonitor:
    """Luồng nền ghi nhận Peak RAM (GB), Peak VRAM (MB) và CPU utilization (%) khi render."""

    def __init__(self, has_nvidia: bool = True, interval_sec: float = 0.25):
        self.has_nvidia = has_nvidia
        self.interval_sec = interval_sec
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.peak_ram_gb: float = 0.0
        self.peak_vram_mb: float = 0.0
        self.peak_cpu_pct: float = 0.0
        self._cpu_samples: List[float] = []
        self.samples: int = 0

    def _sample_once(self, prev_times: Optional[Tuple[int, int, int]]) -> Optional[Tuple[int, int, int]]:
        ram_gb = _read_ram_used_gb()
        if ram_gb > self.peak_ram_gb:
            self.peak_ram_gb = ram_gb

        if self.has_nvidia:
            vram_mb = _read_vram_used_mb()
            if vram_mb > self.peak_vram_mb:
                self.peak_vram_mb = vram_mb

        curr_times = _read_system_times()
        if prev_times is not None and curr_times is not None:
            d_idle = curr_times[0] - prev_times[0]
            d_kernel = curr_times[1] - prev_times[1]
            d_user = curr_times[2] - prev_times[2]
            total = d_kernel + d_user
            if total > 0:
                busy = max(0, total - d_idle)
                cpu_pct = round(min(100.0, (busy / total) * 100.0), 1)
                self._cpu_samples.append(cpu_pct)
                if cpu_pct > self.peak_cpu_pct:
                    self.peak_cpu_pct = cpu_pct

        self.samples += 1
        return curr_times

    def _loop(self) -> None:
        prev_times = _read_system_times()
        while not self._stop_event.is_set():
            prev_times = self._sample_once(prev_times)
            self._stop_event.wait(self.interval_sec)

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> Dict[str, Any]:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        avg_cpu = (
            round(sum(self._cpu_samples) / len(self._cpu_samples), 1)
            if self._cpu_samples
            else 0.0
        )
        return {
            "peak_ram_gb": round(self.peak_ram_gb, 2),
            "peak_vram_mb": round(self.peak_vram_mb, 1),
            "avg_cpu_pct": avg_cpu,
            "peak_cpu_pct": round(self.peak_cpu_pct, 1),
            "samples": self.samples,
        }


def parse_frame_count(frames_spec: str, props_path: Path) -> int:
    total_frames = 0
    if props_path.exists():
        try:
            with open(props_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            total_frames = sum(int(s["durationInFrames"]) for s in data.get("scenes", []))
        except Exception:
            pass
    if frames_spec and "-" in frames_spec:
        start_s, end_s = frames_spec.split("-", 1)
        start_f = int(start_s)
        end_f = int(end_s)
        if total_frames > 0:
            end_f = min(end_f, total_frames - 1)
        return max(1, end_f - start_f + 1)
    if frames_spec and frames_spec.isdigit():
        return 1
    return total_frames


def select_best_config(
    runs: List[Dict[str, Any]],
    max_vram_mb: float = 3400.0,
    max_ram_gb: float = 48.0,
) -> Optional[Dict[str, Any]]:
    """Chọn tổ hợp đạt fps_render cao nhất thỏa ngưỡng an toàn VRAM & RAM."""
    safe_runs = [
        r
        for r in runs
        if r.get("success")
        and float(r.get("fps_render", 0.0)) > 0.0
        and float(r.get("peak_vram_mb", 0.0)) <= max_vram_mb
        and float(r.get("peak_ram_gb", 0.0)) <= max_ram_gb
    ]
    if not safe_runs:
        return None
    safe_runs.sort(
        key=lambda r: (
            float(r.get("fps_render", 0.0)),
            -float(r.get("peak_vram_mb", 0.0)),
            -int(r.get("concurrency", 0)),
        ),
        reverse=True,
    )
    return safe_runs[0]


def apply_config_to_settings(
    settings_path: Path,
    best_run: Dict[str, Any],
) -> Dict[str, Any]:
    """Cập nhật nguyên tử mục `render` trong config/settings.json."""
    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    render_cfg = settings.setdefault("render", {})
    render_cfg["concurrency"] = int(best_run["concurrency"])
    render_cfg["gl"] = str(best_run["gl"])
    if best_run.get("x264_preset"):
        render_cfg["x264_preset"] = str(best_run["x264_preset"])
    if best_run.get("nvenc_preset"):
        render_cfg["nvenc_preset"] = str(best_run["nvenc_preset"])
    if best_run.get("nvenc_cq") is not None:
        render_cfg["nvenc_cq"] = int(best_run["nvenc_cq"])
    if best_run.get("image_format"):
        render_cfg["image_format"] = str(best_run["image_format"])
    if best_run.get("jpeg_quality") is not None:
        render_cfg["jpeg_quality"] = int(best_run["jpeg_quality"])
    render_cfg.setdefault("encoder", "auto")
    render_cfg.setdefault("scratch_dir", "auto")
    render_cfg.setdefault("bundle_cache", True)

    tmp_path = settings_path.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(str(tmp_path), str(settings_path))
    return render_cfg


def run_single_benchmark(
    runner: RemotionRunner,
    scratch_mgr: ScratchManager,
    hw: HardwareProfile,
    props_path: Path,
    chapter_id: str,
    frames_spec: str,
    frame_count: int,
    gl: str,
    concurrency: int,
    x264_preset: str,
    crf: int,
    image_format: str,
    jpeg_quality: int,
    phase_label: str,
    max_vram_mb: float,
    max_ram_gb: float,
    encoder: str = "auto",
    nvenc_preset: str = "p5",
    nvenc_cq: Optional[int] = None,
    ffmpeg_bin_dir: Optional[Path] = None,
    supports_bframes: Optional[bool] = None,
) -> Dict[str, Any]:
    preset_tag = nvenc_preset if encoder == "nvenc" else x264_preset
    out_file = (
        scratch_mgr.chapter_work_dir(chapter_id)
        / f"bench_{encoder}_{gl}_c{concurrency}_{preset_tag}.mkv"
    )
    out_file.parent.mkdir(parents=True, exist_ok=True)
    if out_file.exists():
        try:
            out_file.unlink()
        except OSError:
            pass

    print(
        f"\n[{phase_label}] encoder={encoder}, gl={gl}, concurrency={concurrency}, "
        f"preset={preset_tag}, frames={frames_spec}"
    )
    monitor = ResourceMonitor(has_nvidia=hw.has_nvidia, interval_sec=0.25)
    monitor.start()
    t0 = time.perf_counter()
    success = runner.render(
        props_path=props_path,
        output_path=out_file,
        concurrency=concurrency,
        crf=crf,
        gl=gl,
        x264_preset=x264_preset,
        image_format=image_format,
        jpeg_quality=jpeg_quality,
        frame_range=frames_spec,
        scratch_dir=scratch_mgr.scratch_root,
        chapter_id=chapter_id,
        bundle_cache=True,
        encoder=encoder,
        nvenc_preset=nvenc_preset if encoder != "libx264" else None,
        nvenc_cq=nvenc_cq if encoder != "libx264" else None,
        ffmpeg_bin_dir=ffmpeg_bin_dir if encoder != "libx264" else None,
        supports_bframes=supports_bframes if encoder != "libx264" else None,
    )
    wall_sec = round(time.perf_counter() - t0, 2)
    stats = monitor.stop()

    file_size_mb = 0.0
    if out_file.exists():
        file_size_mb = round(out_file.stat().st_size / (1024 * 1024), 2)
        try:
            out_file.unlink()
        except OSError:
            pass

    timing = dict(runner.last_timing or {})
    active_encoder = (
        runner.last_encoder
        or timing.get("encoder")
        or ("h264_nvenc" if encoder == "nvenc" else "libx264")
    )
    bundle_ms = int(timing.get("bundle_ms", 0))
    select_ms = int(timing.get("select_ms", 0))
    render_ms = int(timing.get("render_ms", 0))
    cache_hit = bool(timing.get("cache_hit", False))

    render_sec = render_ms / 1000.0 if render_ms > 0 else wall_sec
    fps_render = round(frame_count / max(0.001, render_sec), 2) if success else 0.0
    fps_wall = round(frame_count / max(0.001, wall_sec), 2) if success else 0.0

    within_safety = (
        success
        and stats["peak_vram_mb"] <= max_vram_mb
        and stats["peak_ram_gb"] <= max_ram_gb
    )

    result = {
        "phase": phase_label,
        "encoder": active_encoder,
        "gl": gl,
        "concurrency": concurrency,
        "x264_preset": x264_preset,
        "nvenc_preset": nvenc_preset if active_encoder == "h264_nvenc" else None,
        "nvenc_cq": nvenc_cq if active_encoder == "h264_nvenc" else None,
        "crf": crf,
        "image_format": image_format,
        "jpeg_quality": jpeg_quality,
        "frames": frame_count,
        "success": success,
        "within_safety": within_safety,
        "bundle_ms": bundle_ms,
        "select_ms": select_ms,
        "render_ms": render_ms,
        "wall_seconds": wall_sec,
        "fps_render": fps_render,
        "fps_wall": fps_wall,
        "peak_ram_gb": stats["peak_ram_gb"],
        "peak_vram_mb": stats["peak_vram_mb"],
        "avg_cpu_pct": stats["avg_cpu_pct"],
        "peak_cpu_pct": stats["peak_cpu_pct"],
        "cache_hit": cache_hit,
        "output_size_mb": file_size_mb,
    }

    print(
        f"   => enc={active_encoder} fps_render={fps_render:.2f} (wall={fps_wall:.2f}) | "
        f"bundle={bundle_ms}ms select={select_ms}ms render={render_ms}ms | "
        f"RAM={stats['peak_ram_gb']}GB VRAM={stats['peak_vram_mb']}MB CPU={stats['avg_cpu_pct']}% | "
        f"{'SAFE' if within_safety else 'UNSAFE/FAIL'}"
    )
    return result


def print_summary_table(
    runs: List[Dict[str, Any]],
    best: Optional[Dict[str, Any]],
    baseline_fps: Optional[float],
) -> None:
    print("\n" + "=" * 120)
    print("  KẾT QUẢ BENCHMARK PHẦN CỨNG CINESTORY")
    print("=" * 120)
    header = (
        f"  {'Phase':<14} {'Encoder':<10} {'GL':<8} {'Conc':>4} {'Preset':<9} "
        f"{'Bundle':>7} {'Render':>7} {'FPS':>7} {'WallFPS':>7} "
        f"{'RAM(GB)':>7} {'VRAM':>6} {'CPU%':>5} {'Safe':>5}"
    )
    print(header)
    print("  " + "-" * 116)
    for r in runs:
        enc_label = str(r.get("encoder", "libx264"))
        preset_label = str(r.get("nvenc_preset") or r.get("x264_preset") or "")
        print(
            f"  {r['phase']:<14} {enc_label:<10} {r['gl']:<8} {r['concurrency']:>4} {preset_label:<9} "
            f"{r['bundle_ms']:>5}ms {r['render_ms']:>5}ms "
            f"{r['fps_render']:>7.2f} {r['fps_wall']:>7.2f} "
            f"{r['peak_ram_gb']:>7.2f} {r['peak_vram_mb']:>6.0f} "
            f"{r['avg_cpu_pct']:>5.1f} {'OK' if r['within_safety'] else 'NO':>5}"
        )
    print("=" * 120)
    if best:
        speedup = (
            f" ({best['fps_render'] / baseline_fps:.2f}x so với baseline {baseline_fps:.2f} fps)"
            if baseline_fps and baseline_fps > 0
            else ""
        )
        best_enc = best.get("encoder", "libx264")
        best_preset = best.get("nvenc_preset") or best.get("x264_preset")
        print(
            f"  CẤU HÌNH TỐI ƯU: encoder={best_enc}, gl={best['gl']}, concurrency={best['concurrency']}, "
            f"preset={best_preset} -> {best['fps_render']:.2f} fps{speedup}"
        )
    else:
        print("  [Cảnh báo] Không tìm thấy cấu hình thỏa ngưỡng an toàn.")
    print("=" * 120)


def main() -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Benchmark sweep concurrency × gl × x264_preset cho CineStory Remotion"
    )
    parser.add_argument("--input", default="input/sample_chapter.txt", help="File chương truyện")
    parser.add_argument("--frames", default="0-239", help="Dải frame benchmark (ví dụ 0-239)")
    parser.add_argument("--crf", type=int, default=18, help="Chất lượng CRF")
    parser.add_argument("--encoder", choices=["auto", "nvenc", "libx264"], default=None, help="Chế độ encoder (mặc định đọc từ settings.json)")
    parser.add_argument("--nvenc-preset", default=None, help="Preset NVENC (p1..p7)")
    parser.add_argument("--nvenc-cq", type=int, default=None, help="Constant Quality cho NVENC")
    parser.add_argument("--image-format", choices=["jpeg", "png"], default="jpeg")
    parser.add_argument("--jpeg-quality", type=int, default=85)
    parser.add_argument("--vram-limit-mb", type=float, default=3400.0)
    parser.add_argument("--ram-limit-gb", type=float, default=48.0)
    parser.add_argument("--settings", default="config/settings.json")
    parser.add_argument("--output", default=None, help="Đường dẫn file JSON đầu ra")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Tự động ghi cấu hình thắng cuộc vào config/settings.json -> render",
    )
    args = parser.parse_args()

    chapter_id = slugify_chapter_id(args.input)
    chapter_dir = PROJECT_ROOT / "output" / chapter_id
    props_path = chapter_dir / "render_props.json"

    if not props_path.exists():
        print(
            f"[Lỗi] Không tìm thấy {props_path}.\n"
            f"Hãy chạy trước: python run_pipeline.py --stage props --input {args.input}"
        )
        return 1

    settings_path = (PROJECT_ROOT / args.settings).resolve()
    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    render_cfg = settings.get("render", {})
    hw = detect_hardware_profile(PROJECT_ROOT, force_refresh=True)
    print(hw.format_report())

    encoder_req = args.encoder or str(render_cfg.get("encoder", "auto"))
    nvenc_preset = args.nvenc_preset or str(render_cfg.get("nvenc_preset", "p5"))
    nvenc_cq = (
        args.nvenc_cq
        if args.nvenc_cq is not None
        else int(render_cfg.get("nvenc_cq", min(51, args.crf + 1)))
    )
    default_x264_preset = str(render_cfg.get("x264_preset") or "faster")
    enc_cap: EncoderCapability = probe_encoder_capability(
        requested=encoder_req,
        vram_mb=hw.vram_mb if hw.has_nvidia else None,
    )
    resolved_enc_flag = "nvenc" if enc_cap.is_nvenc else "libx264"
    print(
        f" -> Encoder capability: {enc_cap.selected_encoder} "
        f"(requested={encoder_req}, bframes={enc_cap.supports_bframes}, "
        f"nvenc_preset={nvenc_preset}, nvenc_cq={nvenc_cq})"
    )

    scratch_setting = render_cfg.get("scratch_dir", "auto")
    scratch_mgr = ScratchManager(
        project_root=PROJECT_ROOT,
        scratch_dir_setting=scratch_setting,
        hardware_profile=hw,
    )
    print(f" -> Scratch root: {scratch_mgr.scratch_root} (NVMe offload={scratch_mgr.using_nvme_offload})")

    frame_count = parse_frame_count(args.frames, props_path)
    runner = RemotionRunner(project_root=PROJECT_ROOT, timeout_sec=300)

    all_runs: List[Dict[str, Any]] = []

    # 1. Sweep gl="angle" × [8, 12, 16, 20, 24]
    for conc in ANGLE_CONCURRENCY_SWEEP:
        res = run_single_benchmark(
            runner=runner,
            scratch_mgr=scratch_mgr,
            hw=hw,
            props_path=props_path,
            chapter_id=chapter_id,
            frames_spec=args.frames,
            frame_count=frame_count,
            gl="angle",
            concurrency=conc,
            x264_preset=default_x264_preset,
            crf=args.crf,
            image_format=args.image_format,
            jpeg_quality=args.jpeg_quality,
            phase_label="sweep_angle",
            max_vram_mb=args.vram_limit_mb,
            max_ram_gb=args.ram_limit_gb,
            encoder=resolved_enc_flag,
            nvenc_preset=nvenc_preset,
            nvenc_cq=nvenc_cq,
            ffmpeg_bin_dir=enc_cap.ffmpeg_bin_dir if enc_cap.is_nvenc else None,
            supports_bframes=enc_cap.supports_bframes if enc_cap.is_nvenc else None,
        )
        all_runs.append(res)

    # 2. Sweep gl="swangle" × [16, 24, 28, 32]
    for conc in SWANGLE_CONCURRENCY_SWEEP:
        res = run_single_benchmark(
            runner=runner,
            scratch_mgr=scratch_mgr,
            hw=hw,
            props_path=props_path,
            chapter_id=chapter_id,
            frames_spec=args.frames,
            frame_count=frame_count,
            gl="swangle",
            concurrency=conc,
            x264_preset=default_x264_preset,
            crf=args.crf,
            image_format=args.image_format,
            jpeg_quality=args.jpeg_quality,
            phase_label="sweep_swangle",
            max_vram_mb=args.vram_limit_mb,
            max_ram_gb=args.ram_limit_gb,
            encoder=resolved_enc_flag,
            nvenc_preset=nvenc_preset,
            nvenc_cq=nvenc_cq,
            ffmpeg_bin_dir=enc_cap.ffmpeg_bin_dir if enc_cap.is_nvenc else None,
            supports_bframes=enc_cap.supports_bframes if enc_cap.is_nvenc else None,
        )
        all_runs.append(res)

    # 3. So sánh preset phù hợp với encoder đang chạy tại (gl, concurrency) thắng cuộc
    sweep_winner = select_best_config(
        all_runs,
        max_vram_mb=args.vram_limit_mb,
        max_ram_gb=args.ram_limit_gb,
    )
    if sweep_winner is None:
        successful = [r for r in all_runs if r.get("success")]
        sweep_winner = max(successful, key=lambda r: r.get("fps_render", 0.0)) if successful else None

    preset_comparison: List[Dict[str, Any]] = []
    if sweep_winner is not None:
        win_gl = str(sweep_winner["gl"])
        win_conc = int(sweep_winner["concurrency"])
        if enc_cap.is_nvenc:
            print(
                f"\n[Preset Comparison] So sánh nvenc_preset tại cấu hình tốt nhất: gl={win_gl}, concurrency={win_conc}"
            )
            for p in NVENC_PRESETS_COMPARE:
                if p == sweep_winner.get("nvenc_preset"):
                    copied = dict(sweep_winner)
                    copied["phase"] = "preset_compare"
                    preset_comparison.append(copied)
                    continue
                res = run_single_benchmark(
                    runner=runner,
                    scratch_mgr=scratch_mgr,
                    hw=hw,
                    props_path=props_path,
                    chapter_id=chapter_id,
                    frames_spec=args.frames,
                    frame_count=frame_count,
                    gl=win_gl,
                    concurrency=win_conc,
                    x264_preset=default_x264_preset,
                    crf=args.crf,
                    image_format=args.image_format,
                    jpeg_quality=args.jpeg_quality,
                    phase_label="preset_compare",
                    max_vram_mb=args.vram_limit_mb,
                    max_ram_gb=args.ram_limit_gb,
                    encoder="nvenc",
                    nvenc_preset=p,
                    nvenc_cq=nvenc_cq,
                    ffmpeg_bin_dir=enc_cap.ffmpeg_bin_dir,
                    supports_bframes=enc_cap.supports_bframes,
                )
                all_runs.append(res)
                preset_comparison.append(res)
        else:
            print(
                f"\n[Preset Comparison] So sánh x264_preset tại cấu hình tốt nhất: gl={win_gl}, concurrency={win_conc}"
            )
            for preset in X264_PRESETS_COMPARE:
                if preset == sweep_winner["x264_preset"]:
                    copied = dict(sweep_winner)
                    copied["phase"] = "preset_compare"
                    preset_comparison.append(copied)
                    continue
                res = run_single_benchmark(
                    runner=runner,
                    scratch_mgr=scratch_mgr,
                    hw=hw,
                    props_path=props_path,
                    chapter_id=chapter_id,
                    frames_spec=args.frames,
                    frame_count=frame_count,
                    gl=win_gl,
                    concurrency=win_conc,
                    x264_preset=preset,
                    crf=args.crf,
                    image_format=args.image_format,
                    jpeg_quality=args.jpeg_quality,
                    phase_label="preset_compare",
                    max_vram_mb=args.vram_limit_mb,
                    max_ram_gb=args.ram_limit_gb,
                    encoder="libx264",
                )
                all_runs.append(res)
                preset_comparison.append(res)

    best_overall = select_best_config(
        all_runs,
        max_vram_mb=args.vram_limit_mb,
        max_ram_gb=args.ram_limit_gb,
    )

    # Đọc baseline bench_p2.json nếu có
    baseline: Optional[Dict[str, Any]] = None
    bench_p2_path = chapter_dir / "bench_p2.json"
    if bench_p2_path.exists():
        try:
            with open(bench_p2_path, "r", encoding="utf-8") as bf:
                p2 = json.load(bf)
            baseline = {
                "source": "bench_p2.json",
                "fps_render": p2.get("fps_render"),
                "seconds": p2.get("seconds"),
                "concurrency": p2.get("concurrency"),
            }
        except Exception:
            baseline = None

    baseline_fps = float(baseline["fps_render"]) if baseline and baseline.get("fps_render") else None
    print_summary_table(all_runs, best_overall, baseline_fps)

    applied = False
    if args.apply and best_overall is not None:
        updated = apply_config_to_settings(settings_path, best_overall)
        applied = True
        print(f" -> Đã áp dụng cấu hình tối ưu vào {settings_path}: {json.dumps(updated, ensure_ascii=False)}")

    matrix_path = Path(args.output) if args.output else (chapter_dir / "bench_hw_matrix.json")
    matrix_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now().isoformat(),
        "chapter_id": chapter_id,
        "input": args.input,
        "frames": args.frames,
        "frame_count": frame_count,
        "scratch_dir": str(scratch_mgr.scratch_root),
        "using_nvme_offload": scratch_mgr.using_nvme_offload,
        "baseline": baseline,
        "hardware_profile": hw.to_dict(),
        "safety_limits": {
            "max_vram_mb": args.vram_limit_mb,
            "max_ram_gb": args.ram_limit_gb,
        },
        "runs": all_runs,
        "preset_comparison": preset_comparison,
        "best": best_overall,
        "applied": applied,
    }
    with open(matrix_path, "w", encoding="utf-8") as mf:
        json.dump(report, mf, indent=2, ensure_ascii=False)
    print(f" -> Đã lưu bảng benchmark chi tiết tại: {matrix_path}")

    # Chỉ xóa thư mục work tạm của benchmark nếu thực sự rỗng (tránh xóa nhầm prenorm đang chờ master)
    work_dir = scratch_mgr.chapter_work_dir(chapter_id)
    if work_dir.exists():
        try:
            if not any(work_dir.iterdir()):
                work_dir.rmdir()
        except OSError:
            pass
    return 0 if best_overall is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
