import os
from typing import Optional

from src.pipeline.context import PipelineContext
from src.pipeline.stage_assets_props import run_stage_assets, run_stage_props, run_stage_stills
from src.pipeline.stage_script_audio import run_stage_audio, run_stage_script
from src.pipeline.stage_video_master import run_stage_master, run_stage_package, run_stage_video

def execute_pipeline(
    chapter_file: str = "input/sample_chapter.txt",
    output_name: str = "final_chapter_video.mp4",
    tts_provider: Optional[str] = None,
    renderer: Optional[str] = None,
    stage: str = "all",
    title: Optional[str] = None,
    env: Optional[str] = None,
    frames: Optional[str] = None,
    bench: Optional[str] = None,
) -> bool:
    print("=" * 65)
    print("🎬 KHỞI ĐỘNG HỆ THỐNG BIẾN CHƯƠNG TRUYỆN THÀNH VIDEO ĐIỆN ẢNH")
    print("=" * 65)

    if not os.path.exists(chapter_file):
        print(f"[Lỗi] Không tìm thấy file đầu vào: {chapter_file}")
        return False

    ctx = PipelineContext.create(
        chapter_file=chapter_file,
        output_name=output_name,
        tts_provider=tts_provider,
        renderer=renderer,
        stage=stage,
        title=title,
        env=env,
        frames=frames,
        bench=bench,
    )

    if stage == "script":
        return run_stage_script(ctx) is not None
    elif stage == "audio":
        return run_stage_audio(ctx) is not None
    elif stage == "assets":
        return run_stage_assets(ctx)
    elif stage == "props":
        return run_stage_props(ctx)
    elif stage == "video":
        return run_stage_video(ctx)
    elif stage == "master":
        return run_stage_master(ctx)
    elif stage == "package":
        return run_stage_package(ctx)
    elif stage == "stills":
        return run_stage_stills(ctx)
    elif stage == "prepare":
        if not run_stage_script(ctx):
            return False
        if not run_stage_audio(ctx):
            return False
        if not run_stage_assets(ctx):
            return False
        if not run_stage_props(ctx):
            return False
        print(f"\n✨ Stage [prepare] hoàn tất thành công!")
        print(f"👉 Vui lòng kiểm tra gói prompt tại: packages/{ctx.chapter_id}/")
        print(f"👉 Sau khi tạo ảnh, chạy tiếp: python run_pipeline.py --renderer remotion --stage render --input {ctx.chapter_file}")
        return True
    elif stage == "render":
        if not run_stage_assets(ctx):
            return False
        if not run_stage_props(ctx):
            return False
        if not run_stage_video(ctx):
            return False
        if not run_stage_master(ctx):
            return False
        if not run_stage_package(ctx):
            return False
        return True
    elif stage == "all":
        if not run_stage_script(ctx):
            return False
        if not run_stage_audio(ctx):
            return False
        if not run_stage_assets(ctx):
            return False
        if not run_stage_props(ctx):
            return False
        if not run_stage_video(ctx):
            return False
        if ctx.renderer == "remotion":
            if not run_stage_master(ctx):
                return False
            if not run_stage_package(ctx):
                return False
        return True
    else:
        print(f"[Lỗi] Stage không hợp lệ: {stage}")
        return False
