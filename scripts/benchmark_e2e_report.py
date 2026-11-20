"""Bộ đo hiệu năng & nghiệm thu E2E toàn chuỗi 7 stage cho CineStory Engine (OPT Phase 4).

Chạy tuần tự 7 stage (script -> audio -> assets -> props -> video -> master -> package)
trên từng chương truyện đầu vào, đo thời gian từng bước, Peak RAM/VRAM/CPU, kiểm chứng đủ
5 bất biến kỹ thuật + danh sách tệp xuất bản, và lưu `output/<chapterId>/e2e_perf_report.json`
kèm bảng tổng hợp Markdown.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.benchmark_hardware import ResourceMonitor
from src.audio.mastering import measure_loudness
from src.pipeline.context import PipelineContext
from src.pipeline.stage_assets_props import run_stage_assets, run_stage_props
from src.pipeline.stage_script_audio import run_stage_audio, run_stage_script
from src.pipeline.stage_video_master import run_stage_master, run_stage_package, run_stage_video

_SRT_TIME_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})"
)


def _srt_hms_to_sec(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600.0 + int(m) * 60.0 + int(s) + int(ms) / 1000.0


def parse_srt_timestamps(srt_path: Path) -> List[Tuple[float, float]]:
    """Đọc toàn bộ khoảng thời gian (start_sec, end_sec) trong tệp phụ đề SRT."""
    if not srt_path.exists():
        return []
    text = srt_path.read_text(encoding="utf-8", errors="replace")
    spans: List[Tuple[float, float]] = []
    for match in _SRT_TIME_RE.finditer(text):
        start = _srt_hms_to_sec(match.group(1), match.group(2), match.group(3), match.group(4))
        end = _srt_hms_to_sec(match.group(5), match.group(6), match.group(7), match.group(8))
        spans.append((round(start, 4), round(end, 4)))
    return spans


def probe_media_info(video_path: Path) -> Dict[str, Any]:
    """Đọc thông số container, video stream và audio stream bằng ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-of", "json",
        str(video_path),
    ]
    res = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    data = json.loads(res.stdout)
    streams = data.get("streams", [])
    fmt = data.get("format", {})

    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    v0 = video_streams[0] if video_streams else {}
    a0 = audio_streams[0] if audio_streams else {}

    duration_sec = 0.0
    for raw_dur in (fmt.get("duration"), v0.get("duration"), a0.get("duration")):
        if raw_dur is not None:
            try:
                duration_sec = float(raw_dur)
                break
            except (TypeError, ValueError):
                pass

    sample_rate = 0
    if a0.get("sample_rate") is not None:
        try:
            sample_rate = int(a0["sample_rate"])
        except (TypeError, ValueError):
            sample_rate = 0

    return {
        "duration_sec": round(duration_sec, 4),
        "video_codec": v0.get("codec_name"),
        "video_width": int(v0.get("width", 0) or 0),
        "video_height": int(v0.get("height", 0) or 0),
        "video_stream_count": len(video_streams),
        "audio_codec": a0.get("codec_name"),
        "audio_sample_rate": sample_rate,
        "audio_channels": int(a0.get("channels", 0) or 0),
        "audio_stream_count": len(audio_streams),
        "size_mb": round(video_path.stat().st_size / (1024 * 1024), 2) if video_path.exists() else 0.0,
    }


def verify_e2e_invariants(
    chapter_dir: Path,
    props_path: Path,
    video_path: Path,
    srt_path: Path,
    scratch_work_dir: Path,
) -> Dict[str, Any]:
    """Kiểm chứng đủ 5 bất biến kỹ thuật & tính đầy đủ tài sản xuất bản."""
    props_data: Dict[str, Any] = {}
    if props_path.exists():
        props_data = json.loads(props_path.read_text(encoding="utf-8"))

    fps = int(props_data.get("fps", 24) or 24)
    scenes = props_data.get("scenes", [])
    total_frames = sum(int(s.get("durationInFrames", 0)) for s in scenes)
    expected_duration_sec = round(total_frames / float(fps), 4) if fps > 0 else 0.0

    # 1 & 2. Probe media (frame delta ±1 & AAC 44.1 kHz)
    media_info: Dict[str, Any] = {}
    frame_delta: Optional[float] = None
    frame_ok = False
    aac_ok = False
    if video_path.exists():
        try:
            media_info = probe_media_info(video_path)
            actual_dur = float(media_info.get("duration_sec", 0.0))
            frame_delta = round(abs(actual_dur - expected_duration_sec) * fps, 3)
            frame_ok = total_frames > 0 and frame_delta <= 1.0
            aac_ok = (
                media_info.get("audio_codec") == "aac"
                and int(media_info.get("audio_sample_rate", 0)) == 44100
                and int(media_info.get("audio_stream_count", 0)) == 1
            )
        except Exception as exc:
            media_info = {"error": str(exc)}

    # 3. Loudness EBU R128 (-14.0 ± 1.0 LUFS, True Peak <= -1.5 dBTP)
    loudness_info: Dict[str, Any] = {
        "integrated_lufs": None,
        "true_peak_db": None,
        "lra": None,
        "passed": False,
    }
    if video_path.exists():
        measured = measure_loudness(str(video_path), target_i=-14.0, target_tp=-1.5, target_lra=11.0)
        if measured:
            try:
                lufs = round(float(measured["input_i"]), 2)
                tp = round(float(measured["input_tp"]), 2)
                lra = round(float(measured["input_lra"]), 2)
                loudness_info = {
                    "integrated_lufs": lufs,
                    "true_peak_db": tp,
                    "lra": lra,
                    "passed": (-15.0 <= lufs <= -13.0) and (tp <= -1.5),
                }
            except (KeyError, TypeError, ValueError):
                pass

    # 4. SRT sync & cấu trúc hợp lệ
    srt_spans = parse_srt_timestamps(srt_path)
    monotonic = all(
        srt_spans[i][0] <= srt_spans[i][1] + 1e-4
        and (i == 0 or srt_spans[i][0] >= srt_spans[i - 1][0] - 0.05)
        for i in range(len(srt_spans))
    )
    last_srt_end = srt_spans[-1][1] if srt_spans else 0.0
    srt_within_video = last_srt_end <= (expected_duration_sec + 0.5) if expected_duration_sec > 0 else False
    srt_ok = len(srt_spans) > 0 and monotonic and srt_within_video

    # 5. Dọn sạch NVMe scratch work/<chapterId>/
    leftover_files: List[str] = []
    if scratch_work_dir.exists():
        leftover_files = [
            str(p.relative_to(scratch_work_dir))
            for p in scratch_work_dir.rglob("*")
            if p.is_file()
        ]
    scratch_clean_ok = len(leftover_files) == 0

    artifacts = {
        "video_mp4": (chapter_dir / "video.mp4").exists(),
        "video_srt": (chapter_dir / "video.srt").exists(),
        "youtube_metadata_json": (chapter_dir / "youtube_metadata.json").exists(),
        "thumbnail_base_png": (chapter_dir / "thumbnail_base.png").exists(),
        "render_report_json": (chapter_dir / "render_report.json").exists(),
    }

    invariants = {
        "frame_duration": {
            "expected_frames": total_frames,
            "fps": fps,
            "expected_sec": expected_duration_sec,
            "actual_sec": media_info.get("duration_sec"),
            "frame_delta": frame_delta,
            "passed": frame_ok,
        },
        "audio_stream": {
            "codec": media_info.get("audio_codec"),
            "sample_rate": media_info.get("audio_sample_rate"),
            "stream_count": media_info.get("audio_stream_count"),
            "passed": aac_ok,
        },
        "loudness": loudness_info,
        "srt_sync": {
            "entries": len(srt_spans),
            "monotonic": monotonic,
            "last_end_sec": last_srt_end,
            "expected_sec": expected_duration_sec,
            "passed": srt_ok,
        },
        "nvme_scratch_clean": {
            "work_dir": str(scratch_work_dir),
            "leftover_files": leftover_files,
            "passed": scratch_clean_ok,
        },
        "artifacts": artifacts,
    }
    invariants["all_passed"] = bool(
        frame_ok
        and aac_ok
        and loudness_info["passed"]
        and srt_ok
        and scratch_clean_ok
        and all(artifacts.values())
    )
    return invariants


def run_chapter_e2e_benchmark(
    chapter_file: str,
    renderer: str = "remotion",
    tts_provider: Optional[str] = None,
    output_name: str = "final_chapter_video.mp4",
    check_warm_props: bool = True,
) -> Dict[str, Any]:
    """Chạy đủ 7 stage E2E trên 1 chương truyện và xuất `e2e_perf_report.json`."""
    ctx = PipelineContext.create(
        chapter_file=chapter_file,
        output_name=output_name,
        tts_provider=tts_provider,
        renderer=renderer,
        stage="all",
        title=None,
        env=None,
        frames=None,
        bench=None,
    )
    hw = ctx.hardware_profile
    scratch_mgr = ctx.scratch_manager
    assert hw is not None and scratch_mgr is not None

    stage_timings: Dict[str, Optional[float]] = {}
    stage_status: Dict[str, bool] = {}

    overall_monitor = ResourceMonitor(has_nvidia=hw.has_nvidia, interval_sec=0.25)
    overall_monitor.start()
    t_total0 = time.perf_counter()

    stages = [
        ("script", lambda: run_stage_script(ctx) is not None),
        ("audio", lambda: run_stage_audio(ctx) is not None),
        ("assets", lambda: bool(run_stage_assets(ctx))),
        ("props", lambda: bool(run_stage_props(ctx))),
        ("video", lambda: bool(run_stage_video(ctx))),
        ("master", lambda: bool(run_stage_master(ctx))),
        ("package", lambda: bool(run_stage_package(ctx))),
    ]

    pipeline_ok = True
    video_monitor_stats: Dict[str, Any] = {}

    for stage_name, fn in stages:
        t0 = time.perf_counter()
        v_mon = ResourceMonitor(has_nvidia=hw.has_nvidia, interval_sec=0.25) if stage_name == "video" else None
        if v_mon is not None:
            v_mon.start()
        try:
            ok = fn()
        except Exception as exc:
            print(f"[Lỗi E2E stage '{stage_name}']: {exc}")
            ok = False
        if v_mon is not None:
            video_monitor_stats = v_mon.stop()
        elapsed = round(time.perf_counter() - t0, 3)
        stage_timings[stage_name] = elapsed
        stage_status[stage_name] = ok

        if not ok:
            pipeline_ok = False
            break

        # Đo thêm warm cache cho stage props (< 1s check của Gate 4)
        if stage_name == "props" and check_warm_props:
            t_warm0 = time.perf_counter()
            warm_ok = bool(run_stage_props(ctx))
            stage_timings["props_warm"] = round(time.perf_counter() - t_warm0, 3)
            stage_status["props_warm"] = warm_ok

    total_sec = round(time.perf_counter() - t_total0, 3)
    overall_stats = overall_monitor.stop()
    stage_timings["total"] = total_sec

    # Đọc render_report.json & baseline bench_p2.json (nếu có)
    render_report_path = ctx.chapter_dir / "render_report.json"
    render_report: Dict[str, Any] = {}
    if render_report_path.exists():
        try:
            render_report = json.loads(render_report_path.read_text(encoding="utf-8"))
        except Exception:
            render_report = {}

    baseline_p2: Optional[Dict[str, Any]] = None
    bench_p2_path = ctx.chapter_dir / "bench_p2.json"
    if bench_p2_path.exists():
        try:
            p2 = json.loads(bench_p2_path.read_text(encoding="utf-8"))
            baseline_p2 = {
                "source": "bench_p2.json",
                "fps_render": p2.get("fps_render"),
                "seconds": p2.get("seconds"),
                "concurrency": p2.get("concurrency"),
            }
        except Exception:
            baseline_p2 = None

    video_mp4 = ctx.chapter_dir / "video.mp4"
    if not video_mp4.exists():
        video_mp4 = ctx.chapter_dir / output_name

    invariants = verify_e2e_invariants(
        chapter_dir=ctx.chapter_dir,
        props_path=ctx.chapter_dir / "render_props.json",
        video_path=video_mp4,
        srt_path=ctx.chapter_dir / "video.srt",
        scratch_work_dir=scratch_mgr.chapter_work_dir(ctx.chapter_id),
    )

    fps_render = render_report.get("fps_render")
    speedup_vs_p2 = None
    if baseline_p2 and baseline_p2.get("fps_render") and fps_render:
        try:
            speedup_vs_p2 = round(float(fps_render) / float(baseline_p2["fps_render"]), 2)
        except (TypeError, ValueError, ZeroDivisionError):
            speedup_vs_p2 = None

    scratch_drive = os.path.splitdrive(str(scratch_mgr.scratch_root))[0].upper() or str(scratch_mgr.scratch_root)
    report: Dict[str, Any] = {
        "generated_at": datetime.now().isoformat(),
        "chapter_id": ctx.chapter_id,
        "input": chapter_file,
        "renderer": renderer,
        "pipeline_ok": pipeline_ok,
        "stage_status": stage_status,
        "stage_timings_sec": stage_timings,
        "render_metrics": {
            "frames": render_report.get("frames"),
            "fps_render": fps_render,
            "fps_wall": render_report.get("fps_wall"),
            "encoder": render_report.get("encoder"),
            "nvenc_preset": render_report.get("nvenc_preset"),
            "nvenc_cq": render_report.get("nvenc_cq"),
            "concurrency": render_report.get("concurrency"),
            "gl": render_report.get("gl"),
            "bundle_ms": render_report.get("bundle_ms"),
            "select_ms": render_report.get("select_ms"),
            "render_ms": render_report.get("render_ms"),
            "cache_hit": render_report.get("cache_hit"),
            "scratch_dir": str(scratch_mgr.scratch_root),
            "scratch_drive": scratch_drive,
            "using_nvme_offload": scratch_mgr.using_nvme_offload,
            "peak_ram_gb": max(
                float(overall_stats.get("peak_ram_gb", 0.0)),
                float(video_monitor_stats.get("peak_ram_gb", 0.0)),
            ),
            "peak_vram_mb": max(
                float(overall_stats.get("peak_vram_mb", 0.0)),
                float(video_monitor_stats.get("peak_vram_mb", 0.0)),
            ),
            "avg_cpu_pct": video_monitor_stats.get("avg_cpu_pct", overall_stats.get("avg_cpu_pct", 0.0)),
            "peak_cpu_pct": max(
                float(overall_stats.get("peak_cpu_pct", 0.0)),
                float(video_monitor_stats.get("peak_cpu_pct", 0.0)),
            ),
        },
        "baseline_comparison": {
            "baseline": baseline_p2,
            "speedup_vs_p2": speedup_vs_p2,
        },
        "hardware_summary": {
            "cpu_name": hw.cpu_name,
            "cpu_physical_cores": hw.cpu_physical_cores,
            "cpu_logical_threads": hw.cpu_logical_threads,
            "cpu_sockets": hw.cpu_sockets,
            "ram_total_gb": hw.ram_total_gb,
            "gpu_name": hw.gpu_name,
            "vram_mb": hw.vram_mb,
            "workspace_disk_detail": hw.workspace_disk_detail,
            "localappdata_disk_detail": hw.localappdata_disk_detail,
        },
        "invariants": invariants,
    }

    report_path = ctx.chapter_dir / "e2e_perf_report.json"
    tmp_path = report_path.with_name(f".{report_path.name}.tmp.{os.getpid()}")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(str(tmp_path), str(report_path))
    report["invariants"]["artifacts"]["e2e_perf_report_json"] = report_path.exists()
    # Cập nhật lại tệp với trường e2e_perf_report_json = True
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(str(tmp_path), str(report_path))

    print(f" -> Đã lưu báo cáo E2E tại: {report_path}")
    return report


def format_markdown_report(reports: List[Dict[str, Any]]) -> str:
    """Định dạng bảng Markdown tổng hợp thời gian 7 stage & 5 bất biến kỹ thuật."""
    lines: List[str] = []
    lines.append("## BÁO CÁO NGHIỆM THU E2E — OPT PHASE 4 (7 STAGES)")
    lines.append("")
    lines.append("### 1. Thời gian từng stage (giây) & thông số render")
    lines.append("")
    lines.append(
        "| Chapter | script | audio | assets | props | props (warm) | video | master | package | Total | fps_render | Encoder | Conc | GL | Scratch | Peak RAM | Peak VRAM |"
    )
    lines.append(
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- | ---: | :--- | :--- | ---: | ---: |"
    )
    for r in reports:
        t = r.get("stage_timings_sec", {})
        m = r.get("render_metrics", {})

        def _fmt(val: Any, suffix: str = "s") -> str:
            if val is None:
                return "—"
            return f"{float(val):.2f}{suffix}"

        lines.append(
            f"| `{r['chapter_id']}` "
            f"| {_fmt(t.get('script'))} "
            f"| {_fmt(t.get('audio'))} "
            f"| {_fmt(t.get('assets'))} "
            f"| {_fmt(t.get('props'))} "
            f"| {_fmt(t.get('props_warm'))} "
            f"| {_fmt(t.get('video'))} "
            f"| {_fmt(t.get('master'))} "
            f"| {_fmt(t.get('package'))} "
            f"| **{_fmt(t.get('total'))}** "
            f"| {_fmt(m.get('fps_render'), '')} "
            f"| `{m.get('encoder') or 'N/A'}` "
            f"| {m.get('concurrency') or 'auto'} "
            f"| `{m.get('gl') or 'N/A'}` "
            f"| `{m.get('scratch_drive') or 'N/A'}` "
            f"| {_fmt(m.get('peak_ram_gb'), ' GB')} "
            f"| {_fmt(m.get('peak_vram_mb'), ' MB')} |"
        )

    lines.append("")
    lines.append("### 2. Kiểm chứng 5 bất biến kỹ thuật & gói xuất bản")
    lines.append("")
    lines.append(
        "| Chapter | Frame Delta (≤1f) | Loudness (-14±1 LUFS / TP ≤ -1.5) | Audio AAC 44.1kHz | SRT Sync | NVMe Scratch Clean | Artifacts | Verdict |"
    )
    lines.append(
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |"
    )
    for r in reports:
        inv = r.get("invariants", {})
        fd = inv.get("frame_duration", {})
        ld = inv.get("loudness", {})
        au = inv.get("audio_stream", {})
        sr = inv.get("srt_sync", {})
        sc = inv.get("nvme_scratch_clean", {})
        arts = inv.get("artifacts", {})
        all_arts = bool(arts) and all(arts.values())

        fd_txt = f"{'PASS' if fd.get('passed') else 'FAIL'} (Δ={fd.get('frame_delta')}f)"
        ld_txt = (
            f"{'PASS' if ld.get('passed') else 'FAIL'} "
            f"({ld.get('integrated_lufs')} LUFS / {ld.get('true_peak_db')} dBTP)"
        )
        au_txt = f"{'PASS' if au.get('passed') else 'FAIL'} ({au.get('codec')} {au.get('sample_rate')}Hz)"
        sr_txt = f"{'PASS' if sr.get('passed') else 'FAIL'} ({sr.get('entries')} cues)"
        sc_txt = f"{'PASS' if sc.get('passed') else 'FAIL'} ({len(sc.get('leftover_files', []))} files)"
        ar_txt = f"{'PASS' if all_arts else 'FAIL'} ({sum(1 for v in arts.values() if v)}/{len(arts)})"
        verdict = "**PASS**" if (r.get("pipeline_ok") and inv.get("all_passed")) else "**FAIL**"

        lines.append(
            f"| `{r['chapter_id']}` | {fd_txt} | {ld_txt} | {au_txt} | {sr_txt} | {sc_txt} | {ar_txt} | {verdict} |"
        )

    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Chạy benchmark & nghiệm thu E2E 7 stage cho CineStory Engine (OPT Phase 4)"
    )
    parser.add_argument(
        "--inputs",
        nargs="+",
        default=["input/sample_chapter.txt", "input/chapter_02.txt"],
        help="Danh sách tệp chương truyện đầu vào",
    )
    parser.add_argument(
        "--renderer",
        choices=["remotion", "ffmpeg"],
        default="remotion",
        help="Bộ dựng video sử dụng (mặc định: remotion)",
    )
    parser.add_argument(
        "--tts",
        choices=["edge", "vbee"],
        default=None,
        help="Nhà cung cấp giọng đọc TTS",
    )
    parser.add_argument(
        "--output-name",
        default="final_chapter_video.mp4",
        help="Tên tệp video master đầu ra",
    )
    parser.add_argument(
        "--no-warm-props",
        action="store_true",
        help="Bỏ qua lượt đo stage props warm cache thứ 2",
    )
    parser.add_argument(
        "--markdown-out",
        default=None,
        help="Đường dẫn tùy chọn để lưu bảng tổng hợp Markdown",
    )
    args = parser.parse_args(argv)

    reports: List[Dict[str, Any]] = []
    for inp in args.inputs:
        print("\n" + "=" * 72)
        print(f"  E2E BENCHMARK: {inp} (renderer={args.renderer})")
        print("=" * 72)
        rep = run_chapter_e2e_benchmark(
            chapter_file=inp,
            renderer=args.renderer,
            tts_provider=args.tts,
            output_name=args.output_name,
            check_warm_props=not args.no_warm_props,
        )
        reports.append(rep)

    md = format_markdown_report(reports)
    print("\n" + md)

    if args.markdown_out:
        md_path = Path(args.markdown_out)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md, encoding="utf-8")
        print(f" -> Đã lưu báo cáo Markdown tại: {md_path}")

    all_ok = all(r.get("pipeline_ok") and r.get("invariants", {}).get("all_passed") for r in reports)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
