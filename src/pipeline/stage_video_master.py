import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from src.audio.mastering import encode_without_mastering, master_loudness
from src.core.models import RenderProps, ShotKind
from src.export.srt import build_srt_entries, build_srt_from_props
from src.packaging.youtube import YouTubePackager
from src.pipeline.context import PipelineContext
from src.render.remotion_runner import RemotionRunner
from src.tts_service import TTSService
from src.video_composer import VideoComposer

def run_stage_video(ctx: PipelineContext) -> bool:
    """Render video bằng Renderer đã chọn (Remotion hoặc FFmpeg)."""
    print(f"\n[Stage: video] 🎬 Render video bằng Renderer: '{ctx.renderer}'...")
    if ctx.renderer == "remotion":
        props_file_rel = f"../output/{ctx.chapter_id}/render_props.json"
        if ctx.frames:
            out_mp4_rel = f"../output/{ctx.chapter_id}/video.bench.mp4"
        else:
            out_mp4_rel = f"../output/{ctx.chapter_id}/video.remotion.mp4"

        crf = ctx.settings.get("render", {}).get("crf", 18)
        concurrency = ctx.settings.get("render", {}).get("concurrency")

        cmd = [
            "npx.cmd" if sys.platform == "win32" else "npx",
            "remotion",
            "render",
            "src/index.ts",
            "StoryComposition",
            out_mp4_rel,
            f"--props={props_file_rel}",
            f"--crf={crf}",
        ]
        if concurrency is not None:
            cmd.append(f"--concurrency={concurrency}")
        if ctx.frames:
            cmd.append(f"--frames={ctx.frames}")

        if ctx.frames or ctx.bench:
            t0 = time.time()
            print(f" -> Chạy lệnh: {' '.join(cmd)}")
            res = subprocess.run(cmd, cwd="remotion", shell=True)
            render_sec = time.time() - t0

            if res.returncode == 0:
                print(f"🎉 Render Remotion thành công: {out_mp4_rel}")
                props_path = ctx.chapter_dir / "render_props.json"
                total_frames = 0
                if props_path.exists():
                    try:
                        with open(props_path, "r", encoding="utf-8") as pf:
                            p_data = json.load(pf)
                        total_frames = sum(s["durationInFrames"] for s in p_data.get("scenes", []))
                    except Exception:
                        pass

                if ctx.frames and "-" in ctx.frames:
                    try:
                        f_parts = ctx.frames.split("-")
                        rendered_count = int(f_parts[1]) - int(f_parts[0]) + 1
                    except Exception:
                        rendered_count = total_frames
                else:
                    rendered_count = total_frames

                fps_render = rendered_count / max(0.001, render_sec)
                report_data = {
                    "frames": rendered_count,
                    "seconds": round(render_sec, 2),
                    "fps_render": round(fps_render, 2),
                    "concurrency": concurrency,
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
                return True
            else:
                print(f"[Lỗi] Remotion render thất bại với mã lỗi {res.returncode}")
                return False
        else:
            props_path = ctx.chapter_dir / "render_props.json"
            prenorm_mkv = ctx.chapter_dir / "video.prenorm.mkv"
            runner = RemotionRunner(project_root=Path("."))
            success = runner.render(
                props_path=props_path,
                output_path=prenorm_mkv,
                concurrency=concurrency,
                crf=crf,
            )
            if not success:
                return False

            try:
                probe_res = runner.probe_media_streams(prenorm_mkv)
                audio_streams = [s for s in probe_res.get("streams", []) if s.get("codec_type") == "audio"]
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

        composer = VideoComposer()
        clip_dir = ctx.chapter_dir / "clips"
        clip_dir.mkdir(parents=True, exist_ok=True)
        rendered_clips = []
        default_image = "assets/characters/main_char_face.jpg"

        story_shots = [s for s in sb.shots if s.kind == ShotKind.STORY]
        for idx, shot in enumerate(story_shots):
            specific_scene_img = f"assets/images/{shot.shot_id}.jpg"
            source_img = specific_scene_img if os.path.exists(specific_scene_img) else default_image

            clip_out = clip_dir / f"{shot.shot_id}.mov"
            success = composer.render_shot_clip(
                image_path=source_img,
                audio_path=shot.audio_file,
                output_clip_path=str(clip_out),
                motion_type=shot.camera_motion or "zoom_in",
                duration=shot.duration,
            )
            if success:
                clip_dur = VideoComposer.probe_duration(str(clip_out)) or shot.duration
                words = TTSService.load_words(shot.audio_file) if shot.audio_file else []
                rendered_clips.append({
                    "clip": str(clip_out),
                    "text": shot.raw_text,
                    "duration": clip_dur,
                    "words": words,
                })

        srt_path = ctx.chapter_dir / ctx.output_name.replace(".mp4", ".srt")
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(build_srt_entries(rendered_clips)))
        print(f" -> Đã xuất phụ đề: {srt_path}")

        prenorm_path = ctx.chapter_dir / (Path(ctx.output_name).stem + ".prenorm.mov")
        return composer.concatenate_shots([c["clip"] for c in rendered_clips], str(prenorm_path))

def run_stage_master(ctx: PipelineContext) -> bool:
    """Mastering loudness (-14 LUFS) và hoàn thiện video."""
    print(f"\n[Stage: master] 🎚️ Mastering loudness (-14 LUFS) và hoàn thiện video...")
    prenorm_mkv = ctx.chapter_dir / "video.prenorm.mkv"
    prenorm_mov = ctx.chapter_dir / (Path(ctx.output_name).stem + ".prenorm.mov")
    final_video_path = ctx.chapter_dir / ctx.output_name

    prenorm_path = prenorm_mkv if prenorm_mkv.exists() else prenorm_mov
    if not prenorm_path.exists():
        print(f"[Lỗi] Không tìm thấy file video prenorm để master: {prenorm_path}")
        return False

    audio_cfg = ctx.settings.get("audio", {})
    loudness = audio_cfg.get("loudness", {})
    target_i = float(loudness.get("integrated_lufs", -14.0))
    target_tp = float(loudness.get("true_peak_db", -1.5))
    target_lra = float(loudness.get("lra", 11.0))
    sample_rate = int(audio_cfg.get("sample_rate", 44100))

    measured = master_loudness(
        str(prenorm_path),
        str(final_video_path),
        target_i=target_i,
        target_tp=target_tp,
        target_lra=target_lra,
        sample_rate=sample_rate,
    )

    if measured is None:
        print(" -> [Cảnh báo] Mastering loudnorm thất bại, fallback encode_without_mastering...")
        success = encode_without_mastering(str(prenorm_path), str(final_video_path), sample_rate)
    else:
        success = True

    if success and final_video_path.exists():
        if prenorm_path.exists():
            os.remove(prenorm_path)
        alt_video = ctx.chapter_dir / "video.mp4"
        if final_video_path.name != "video.mp4":
            try:
                shutil.copyfile(final_video_path, alt_video)
            except Exception:
                pass
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

    yt_packager = YouTubePackager(project_root=Path("."))
    meta_path = ctx.chapter_dir / "youtube_metadata.json"
    props_obj = RenderProps.model_validate(props_data)
    yt_packager.generate_metadata(
        props=props_obj,
        draft_path=ctx.chapter_dir / "youtube_draft.json",
        output_path=meta_path,
    )

    thumb_path = ctx.chapter_dir / "thumbnail_base.png"
    yt_packager.export_thumbnail_base(
        props_path=props_path,
        output_image_path=thumb_path,
    )

    print(f"🎉 Gói tài nguyên YouTube đã sẵn sàng tại: output/{ctx.chapter_id}/")
    return True
