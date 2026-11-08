import argparse
import sys
from typing import Optional

# Đảm bảo in tiếng Việt và emoji mượt mà trên console Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.export.srt import build_srt_entries, format_srt_time
from src.pipeline.runner import execute_pipeline
from src.pipeline.timing import plan_shot_duration, plan_shot_frames
from src.tts_service import TTS_PROVIDERS

__all__ = [
    "build_srt_entries",
    "format_srt_time",
    "plan_shot_frames",
    "plan_shot_duration",
    "run_pipeline",
]

def run_pipeline(
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
    return execute_pipeline(
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline tạo video truyện audio YouTube chuẩn điện ảnh")
    parser.add_argument("--input", default="input/sample_chapter.txt", help="Đường dẫn file văn bản chương truyện")
    parser.add_argument("--output", default="final_chapter_video.mp4", help="Tên file video đầu ra (.mp4)")
    parser.add_argument(
        "--tts",
        choices=TTS_PROVIDERS,
        default=None,
        help="Dịch vụ giọng đọc: edge (miễn phí) hoặc vbee (cần khóa trong .env)",
    )
    parser.add_argument(
        "--renderer",
        choices=["ffmpeg", "remotion"],
        default=None,
        help="Công nghệ render: remotion hoặc ffmpeg (mặc định lấy từ settings.json)",
    )
    parser.add_argument(
        "--stage",
        choices=["script", "audio", "assets", "props", "video", "master", "package", "stills", "prepare", "render", "all"],
        default="all",
        help="Giai đoạn thực thi: script, audio, assets, props, video, master, package, stills, prepare, render, all",
    )
    parser.add_argument("--title", default=None, help="Tiêu đề chương truyện")
    parser.add_argument("--env", default=None, help="Bối cảnh mặc định")
    parser.add_argument("--frames", default=None, help="Dải frame render cho Remotion, ví dụ 0-239")
    parser.add_argument("--bench", default=None, help="Nhãn đo hiệu năng benchmark, ví dụ p2")
    args = parser.parse_args()

    run_pipeline(
        chapter_file=args.input,
        output_name=args.output,
        tts_provider=args.tts,
        renderer=args.renderer,
        stage=args.stage,
        title=args.title,
        env=args.env,
        frames=args.frames,
        bench=args.bench,
    )
