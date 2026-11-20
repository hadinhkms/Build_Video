from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.audio.mastering import encode_without_mastering, master_loudness
from src.core.models import RenderProps, ShotKind
from src.export.srt import build_srt_entries, build_srt_from_props
from src.packaging.youtube import YouTubePackager
from src.pipeline.context import PipelineContext
from src.render.encoder_probe import probe_encoder_capability
from src.render.remotion_runner import RemotionRunner
from src.tts_service import TTSService
from src.video_composer import VideoComposer


def _count_rendered_frames(props_path: Path, frames_spec: Optional[str]) -> int:
    total_frames = 0
    if props_path.exists():
        try:
            with open(props_path, "r", encoding="utf-8") as pf:
                p_data = json.load(pf)
            total_frames = sum(int(s["durationInFrames"]) for s in p_data.get("scenes", []))
        except Exception:
            pass

    if frames_spec and "-" in frames_spec:
        try:
            f_parts = frames_spec.split("-", 1)
            start_f = int(f_parts[0])
            end_f = int(f_parts[1])
            if total_frames > 0:
                end_f = min(end_f, total_frames - 1)
            return max(1, end_f - start_f + 1)
        except Exception:
            return total_frames
    if frames_spec and frames_spec.isdigit():
        return 1
    return total_frames


def _find_prenorm_path(ctx: PipelineContext) -> Optional[Path]:
    """Tìm file prenorm ưu tiên trên NVMe scratch theo renderer hiện tại rồi fallback về ctx.chapter_dir."""
    scratch_mgr = ctx.scratch_manager
    candidates = []
    prefer_mov = ctx.renderer == "ffmpeg"

    if scratch_mgr is not None:
        mkv_scratch = scratch_mgr.prenorm_mkv_path(ctx.chapter_id)
        mov_scratch = scratch_mgr.prenorm_mov_path(ctx.chapter_id, ctx.output_name)
        candidates.extend([mov_scratch, mkv_scratch] if prefer_mov else [mkv_scratch, mov_scratch])

    mkv_legacy = ctx.chapter_dir / "video.prenorm.mkv"
    mov_legacy = ctx.chapter_dir / (Path(ctx.output_name).stem + ".prenorm.mov")
    candidates.extend([mov_legacy, mkv_legacy] if prefer_mov else [mkv_legacy, mov_legacy])

    for cand in candidates:
        if cand.exists():
            return cand
    return None


def run_stage_video(ctx: PipelineContext) -> bool:
    """Render video bằng Renderer đã chọn (Remotion hoặc FFmpeg)."""
    print(f"\n[Stage: video] 🎬 Render video bằng Renderer: '{ctx.renderer}'...")
    scratch_mgr = ctx.scratch_manager
    assert scratch_mgr is not None

    if ctx.renderer == "remotion":
        render_cfg = ctx.settings.get("render", {})
        crf = int(render_cfg.get("crf", 18))
        concurrency = render_cfg.get("concurrency")
        gl = render_cfg.get("gl", "angle")
        x264_preset = render_cfg.get("x264_preset")
        image_format = render_cfg.get("image_format", "jpeg")
        jpeg_quality = render_cfg.get("jpeg_quality", 85)
        bundle_cache = bool(render_cfg.get("bundle_cache", True))
        encoder_req = str(render_cfg.get("encoder", "auto"))
        nvenc_preset = str(render_cfg.get("nvenc_preset", "p5"))
        nvenc_cq = int(render_cfg.get("nvenc_cq", min(51, crf + 1)))

        ram_total_gb = (
            float(ctx.hardware_profile.ram_total_gb)
            if ctx.hardware_profile is not None and ctx.hardware_profile.ram_total_gb > 0
            else 16.0
        )
        default_media_mb = 2048 if ram_total_gb >= 32.0 else (1024 if ram_total_gb >= 16.0 else 512)
        default_offthread_mb = 1024 if ram_total_gb >= 32.0 else (512 if ram_total_gb >= 16.0 else 256)
        cfg_media_mb = int(render_cfg.get("media_cache_mb", default_media_mb))
        cfg_offthread_mb = int(render_cfg.get("offthread_video_cache_mb", default_offthread_mb))
        # Co theo dung lượng RAM thực tế để không chiếm quá ~10% tổng RAM
        max_safe_media_mb = max(256, int(ram_total_gb * 1024 * 0.10))
        media_cache_bytes = min(cfg_media_mb, max_safe_media_mb) * 1024 * 1024
        offthread_video_cache_bytes = min(cfg_offthread_mb, max(128, max_safe_media_mb // 2)) * 1024 * 1024
        offthread_video_threads = max(1, min(16, int(render_cfg.get("offthread_video_threads", 4))))

        vram_mb = (
            ctx.hardware_profile.vram_mb
            if ctx.hardware_profile is not None and ctx.hardware_profile.has_nvidia
            else None
        )
        enc_cap = probe_encoder_capability(requested=encoder_req, vram_mb=vram_mb)
        resolved_encoder_flag = "nvenc" if enc_cap.is_nvenc else "libx264"

        if ctx.hardware_profile is not None and concurrency is not None:
            warn = ctx.hardware_profile.check_vram_warning(str(gl), int(concurrency))
            if warn:
                print(f" -> [Cảnh báo] {warn}")

        props_path = ctx.chapter_dir / "render_props.json"
        is_bench_mode = bool(ctx.frames or ctx.bench)

        if is_bench_mode:
            out_path = scratch_mgr.chapter_work_dir(ctx.chapter_id) / "video.bench.mkv"
        else:
            out_path = scratch_mgr.prenorm_mkv_path(ctx.chapter_id)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        print(
            f" -> NVMe/Scratch output: {out_path} "
            f"(encoder={enc_cap.selected_encoder}, bframes={enc_cap.supports_bframes})"
        )

        runner = RemotionRunner(project_root=scratch_mgr.project_root)
        t0 = time.time()
        success = runner.render(
            props_path=props_path,
            output_path=out_path,
            concurrency=concurrency,
            crf=crf,
            gl=gl,
            x264_preset=x264_preset,
            image_format=image_format,
            jpeg_quality=jpeg_quality,
            frame_range=ctx.frames,
            scratch_dir=scratch_mgr.scratch_root,
            chapter_id=ctx.chapter_id,
            bundle_cache=bundle_cache,
            encoder=resolved_encoder_flag,
            nvenc_preset=nvenc_preset,
            nvenc_cq=nvenc_cq,
            ffmpeg_bin_dir=enc_cap.ffmpeg_bin_dir if enc_cap.is_nvenc else None,
            supports_bframes=enc_cap.supports_bframes if enc_cap.is_nvenc else None,
            media_cache_bytes=media_cache_bytes,
            offthread_video_cache_bytes=offthread_video_cache_bytes,
            offthread_video_threads=offthread_video_threads,
        )
        wall_sec = time.time() - t0
        if not success:
            return False

        timing = runner.last_timing or {}
        active_encoder = runner.last_encoder or timing.get("encoder") or enc_cap.selected_encoder
        rendered_count = _count_rendered_frames(props_path, ctx.frames)
        render_ms = timing.get("render_ms")
        render_sec = (render_ms / 1000.0) if render_ms and render_ms > 0 else wall_sec
        fps_render = rendered_count / max(0.001, render_sec) if rendered_count > 0 else 0.0
        fps_wall = rendered_count / max(0.001, wall_sec) if rendered_count > 0 else 0.0

        report_data = {
            "frames": rendered_count,
            "seconds": round(wall_sec, 2),
            "render_seconds": round(render_sec, 2),
            "fps_render": round(fps_render, 2),
            "fps_wall": round(fps_wall, 2),
            "encoder": active_encoder,
            "nvenc_preset": nvenc_preset if active_encoder == "h264_nvenc" else None,
            "nvenc_cq": nvenc_cq if active_encoder == "h264_nvenc" else None,
            "concurrency": concurrency,
            "gl": gl,
            "x264_preset": x264_preset,
            "bundle_ms": timing.get("bundle_ms"),
            "select_ms": timing.get("select_ms"),
            "render_ms": timing.get("render_ms"),
            "cache_hit": timing.get("cache_hit"),
            "scratch_dir": str(scratch_mgr.scratch_root),
            "date": datetime.now().isoformat(),
        }

        if ctx.bench:
            bench_path = ctx.chapter_dir / f"bench_{ctx.bench}.json"
            with open(bench_path, "w", encoding="utf-8") as bf:
                json.dump(report_data, bf, indent=2)
            print(f" -> Đã lưu báo cáo benchmark tại: {bench_path}")
        else:
            report_path = ctx.chapter_dir / "render_report.json"
            with open(report_path, "w", encoding="utf-8") as rf:
                json.dump(report_data, rf, indent=2)
            print(f" -> Đã lưu báo cáo render tại: {report_path}")

        if not is_bench_mode:
            try:
                probe_res = runner.probe_media_streams(out_path)
                audio_streams = [
                    s for s in probe_res.get("streams", []) if s.get("codec_type") == "audio"
                ]
                if audio_streams:
                    codec_name = audio_streams[0].get("codec_name")
                    print(f" -> Luồng audio trung gian: {codec_name} (chuẩn bị cho mastering)")
            except Exception:
                pass
        return True
    else:
        sb = ctx.state_mgr.load_state()
        if not sb:
            print("[Lỗi] Không tìm thấy storyboard.")
            return False

        render_cfg = ctx.settings.get("render", {})
        encoder_req = str(render_cfg.get("encoder", "auto"))
        vram_mb = (
            ctx.hardware_profile.vram_mb
            if ctx.hardware_profile is not None and ctx.hardware_profile.has_nvidia
            else None
        )
        phys_cores = (
            ctx.hardware_profile.cpu_physical_cores
            if ctx.hardware_profile is not None
            else None
        )
        enc_cap = probe_encoder_capability(requested=encoder_req, vram_mb=vram_mb)
        composer = VideoComposer(encoder_capability=enc_cap)

        # Đồng bộ cấu hình render từ ctx.settings (hỗ trợ override trong test / runtime)
        composer.encoder_setting = encoder_req
        if "ffmpeg_workers" in render_cfg:
            composer.ffmpeg_workers_setting = render_cfg["ffmpeg_workers"]
        if "nvenc_preset" in render_cfg:
            composer.nvenc_preset = str(render_cfg["nvenc_preset"])
        if "nvenc_cq" in render_cfg:
            composer.nvenc_cq = int(render_cfg["nvenc_cq"])
        if "crf" in render_cfg:
            composer.crf = int(render_cfg["crf"])
        if "x264_preset" in render_cfg and render_cfg["x264_preset"]:
            composer.x264_preset = str(render_cfg["x264_preset"])

        clip_dir = scratch_mgr.clips_dir(ctx.chapter_id)
        clip_dir.mkdir(parents=True, exist_ok=True)
        default_image = "assets/characters/main_char_face.jpg"

        story_shots = [s for s in sb.shots if s.kind == ShotKind.STORY]
        if not story_shots:
            print("[Lỗi] Không có STORY shot nào trong storyboard.")
            return False

        max_workers = min(len(story_shots), composer.get_recommended_workers(physical_cores=phys_cores))
        print(
            f" -> FFmpeg parallel render: {len(story_shots)} shots | "
            f"encoder={composer.active_encoder} | workers={max_workers} | scratch={clip_dir}"
        )

        def _render_one(idx: int, shot: Any) -> Optional[Dict[str, Any]]:
            specific_scene_img = f"assets/images/{shot.shot_id}.jpg"
            chapter_scene_img = ctx.chapter_dir / "images" / f"{shot.shot_id}.jpg"
            if os.path.exists(specific_scene_img):
                source_img = specific_scene_img
            elif chapter_scene_img.exists():
                source_img = str(chapter_scene_img)
            else:
                source_img = default_image

            clip_out = clip_dir / f"{shot.shot_id}.mov"
            ok = composer.render_shot_clip(
                image_path=source_img,
                audio_path=shot.audio_file,
                output_clip_path=str(clip_out),
                motion_type=shot.camera_motion or "zoom_in",
                duration=shot.duration,
            )
            if not ok:
                return None
            clip_dur = VideoComposer.probe_duration(str(clip_out)) or shot.duration
            words = TTSService.load_words(shot.audio_file) if shot.audio_file else []
            return {
                "idx": idx,
                "clip": str(clip_out),
                "text": shot.raw_text,
                "duration": clip_dur,
                "words": words,
            }

        t_ff0 = time.time()
        results_by_idx: Dict[int, Dict[str, Any]] = {}
        failed_shots: List[str] = []
        if max_workers <= 1:
            for idx, shot in enumerate(story_shots):
                try:
                    res = _render_one(idx, shot)
                    if res is not None:
                        results_by_idx[idx] = res
                    else:
                        failed_shots.append(shot.shot_id)
                except Exception as exc:
                    print(f"[Lỗi worker shot {shot.shot_id}]: {exc}")
                    failed_shots.append(shot.shot_id)
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {
                    executor.submit(_render_one, idx, shot): (idx, shot.shot_id)
                    for idx, shot in enumerate(story_shots)
                }
                for fut in as_completed(future_map):
                    idx, shot_id = future_map[fut]
                    try:
                        res = fut.result()
                        if res is not None:
                            results_by_idx[idx] = res
                        else:
                            failed_shots.append(shot_id)
                    except Exception as exc:
                        print(f"[Lỗi worker shot {shot_id}]: {exc}")
                        failed_shots.append(shot_id)

        if failed_shots or len(results_by_idx) != len(story_shots):
            print(
                f"[Lỗi] Render FFmpeg thất bại ở {len(failed_shots)}/{len(story_shots)} shot "
                f"({', '.join(failed_shots)}). Hủy xuất SRT & concat để tránh lệch thời lượng."
            )
            return False

        # Bảo toàn tuyệt đối thứ tự chỉ số idx trước khi xuất SRT và concatenate_shots()
        rendered_clips: List[Dict[str, Any]] = [
            results_by_idx[i] for i in range(len(story_shots))
        ]

        ff_elapsed = round(time.time() - t_ff0, 2)
        print(f" -> Đã render {len(rendered_clips)}/{len(story_shots)} clip trong {ff_elapsed}s.")

        srt_path = ctx.chapter_dir / ctx.output_name.replace(".mp4", ".srt")
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(build_srt_entries(rendered_clips)))
        print(f" -> Đã xuất phụ đề: {srt_path}")

        prenorm_path = scratch_mgr.prenorm_mov_path(ctx.chapter_id, ctx.output_name)
        prenorm_path.parent.mkdir(parents=True, exist_ok=True)
        return composer.concatenate_shots([c["clip"] for c in rendered_clips], str(prenorm_path))


def run_stage_master(ctx: PipelineContext) -> bool:
    """Mastering loudness (-14 LUFS) trên NVMe scratch và promote nguyên tử về output."""
    print(f"\n[Stage: master] 🎚️ Mastering loudness (-14 LUFS) và hoàn thiện video...")
    scratch_mgr = ctx.scratch_manager
    assert scratch_mgr is not None

    prenorm_path = _find_prenorm_path(ctx)
    final_video_path = ctx.chapter_dir / ctx.output_name

    if prenorm_path is None or not prenorm_path.exists():
        expected = scratch_mgr.prenorm_mkv_path(ctx.chapter_id)
        print(f"[Lỗi] Không tìm thấy file video prenorm để master (kiểm tra {expected} và {ctx.chapter_dir})")
        return False

    audio_cfg = ctx.settings.get("audio", {})
    loudness = audio_cfg.get("loudness", {})
    target_i = float(loudness.get("integrated_lufs", -14.0))
    target_tp = float(loudness.get("true_peak_db", -1.5))
    target_lra = float(loudness.get("lra", 11.0))
    sample_rate = int(audio_cfg.get("sample_rate", 44100))

    master_tmp = scratch_mgr.master_temp_path(ctx.chapter_id, "video.master.tmp.mp4")
    master_tmp.parent.mkdir(parents=True, exist_ok=True)

    measured = master_loudness(
        str(prenorm_path),
        str(master_tmp),
        target_i=target_i,
        target_tp=target_tp,
        target_lra=target_lra,
        sample_rate=sample_rate,
    )

    if measured is None:
        print(" -> [Cảnh báo] Mastering loudnorm thất bại, fallback encode_without_mastering...")
        success = encode_without_mastering(str(prenorm_path), str(master_tmp), sample_rate)
    else:
        success = True

    if success and master_tmp.exists():
        alt_video = ctx.chapter_dir / "video.mp4"
        needs_alt = final_video_path.name != "video.mp4"
        scratch_mgr.promote_to_output(master_tmp, final_video_path, remove_src=not needs_alt)

        if needs_alt:
            try:
                scratch_mgr.promote_to_output(master_tmp, alt_video, remove_src=True)
            except Exception:
                try:
                    shutil.copyfile(final_video_path, alt_video)
                except Exception:
                    pass
                if master_tmp.exists():
                    try:
                        master_tmp.unlink()
                    except OSError:
                        pass

        if prenorm_path.exists():
            try:
                os.remove(prenorm_path)
            except OSError:
                pass

        scratch_mgr.cleanup_chapter_work(ctx.chapter_id)
        print(f"🎉 Xuất bản video master thành công: {final_video_path.name}")
        return True
    else:
        print("[Lỗi] Mux và mastering thất bại.")
        return False


def run_stage_package(ctx: PipelineContext) -> bool:
    """Đóng gói tài nguyên YouTube (SRT, metadata, thumbnail)."""
    print(f"\n[Stage: package] 📦 Đóng gói tài nguyên YouTube (SRT, metadata, thumbnail)...")
    props_path = ctx.chapter_dir / "render_props.json"
    if not props_path.exists():
        print(f"[Lỗi] Không tìm thấy {props_path}. Vui lòng chạy stage props trước.")
        return False

    with open(props_path, "r", encoding="utf-8") as pf:
        props_data = json.load(pf)

    srt_path = ctx.chapter_dir / "video.srt"
    srt_content = build_srt_from_props(props_data)
    with open(srt_path, "w", encoding="utf-8") as sf:
        sf.write(srt_content)
    print(f" -> Đã xuất phụ đề chuẩn: {srt_path.name}")

    yt_packager = YouTubePackager(
        project_root=ctx.scratch_manager.project_root if ctx.scratch_manager else Path(".")
    )
    meta_path = ctx.chapter_dir / "youtube_metadata.json"
    props_obj = RenderProps.model_validate(props_data)
    yt_packager.generate_metadata(
        props=props_obj,
        draft_path=ctx.chapter_dir / "youtube_draft.json",
        output_path=meta_path,
    )

    thumb_path = ctx.chapter_dir / "thumbnail_base.png"
    render_cfg = ctx.settings.get("render", {})
    yt_packager.export_thumbnail_base(
        props_path=props_path,
        output_image_path=thumb_path,
        scratch_dir=ctx.scratch_manager.scratch_root if ctx.scratch_manager else None,
        chapter_id=ctx.chapter_id,
        gl=render_cfg.get("gl", "angle"),
    )

    print(f"🎉 Gói tài nguyên YouTube đã sẵn sàng tại: output/{ctx.chapter_id}/")
    return True
