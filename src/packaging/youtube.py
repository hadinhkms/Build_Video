import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core.models import RenderProps, Scene

logger = logging.getLogger(__name__)


def safe_print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


from src.packaging.timestamps import format_timestamp_min_sec, generate_youtube_timestamps


class YouTubePackager:
    """Đóng gói siêu dữ liệu YouTube (tiêu đề, mô tả, tags, thumbnail) theo chuẩn RULES."""

    def __init__(
        self,
        project_root: Optional[Path] = None,
        config_dir: Optional[Path] = None,
    ):
        self.root = project_root or Path(__file__).resolve().parent.parent.parent
        self.config_dir = config_dir or (self.root / "config")
        self.template_path = self.config_dir / "youtube_template.json"

    def _load_template(self) -> Dict[str, Any]:
        if self.template_path.exists():
            with open(self.template_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "title_template": "{title} | Phim Ngắn Điện Ảnh",
            "default_tags": [
                "phim ngắn",
                "truyện trinh thám",
                "kịch tính",
                "điện ảnh 2.5d",
                "cinestory",
                "truyện audio",
                "phim trinh thám",
                "audio book",
                "nghẹt thở",
                "plot twist",
            ],
            "description_template": "{content_summary}\n\n{timestamps}",
        }

    def generate_metadata(
        self,
        props: RenderProps,
        draft_path: Optional[Path] = None,
        output_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Tạo metadata đầy đủ và lưu ra youtube_metadata.json."""
        template = self._load_template()

        # Kiểm tra bản nháp do Agent viết nếu có
        draft = {}
        if draft_path and draft_path.exists():
            try:
                with open(draft_path, "r", encoding="utf-8") as df:
                    draft = json.load(df)
            except Exception as e:
                logger.warning(f"Lỗi đọc {draft_path}: {e}")

        # 1. Tiêu đề
        if draft.get("titles"):
            titles = draft["titles"][:3]
        else:
            base_t = template.get("title_template", "{title}").replace("{title}", props.title)
            titles = [
                base_t[:70],
                f"Sự Thật Đằng Sau: {props.title}"[:70],
                f"{props.title} - Cái Kết Bất Ngờ"[:70],
            ]

        selected_title = titles[0]

        # 2. Timestamps từ hồi kịch bản
        timestamps_str = generate_youtube_timestamps(props.scenes, fps=props.fps) or ""

        # 3. Mô tả
        story_scenes = [s for s in props.scenes if s.kind == "story"]
        hook_text = story_scenes[0].raw_text if story_scenes else ""
        content_summary = "\n".join([f"- {s.raw_text}" for s in story_scenes[:4]])

        desc_template = template.get("description_template", "{content_summary}\n\n{timestamps}")
        description = desc_template.format(
            title=props.title,
            hook_summary=hook_text,
            content_summary=content_summary,
            timestamps=timestamps_str,
        ).strip()

        # 4. Tags (đảm bảo 10-15 tags theo quy chuẩn)
        tags = list(draft.get("tags") or template.get("default_tags", []))
        extra_pool = [
            "phim ngắn", "truyện trinh thám", "kịch tính", "điện ảnh 2.5d",
            "cinestory", "truyện audio", "phim trinh thám", "audio book",
            "nghẹt thở", "plot twist", "phim ngắn 2026", "review truyện",
            "truyện kinh dị", "điện ảnh việt", "audio truyện"
        ]
        for et in extra_pool:
            if et not in tags and len(tags) < 15:
                tags.append(et)
            if len(tags) >= 12:
                break

        # 5. Thumbnail info
        thumb_text = draft.get("thumbnail_text", props.title[:25])
        thumb_prompt = draft.get(
            "thumbnail_prompt",
            f"Cinematic YouTube thumbnail for {props.title}, dramatic moody lighting, mystery atmosphere, 16:9, hyperrealistic.",
        )

        metadata = {
            "title": selected_title,
            "alternative_titles": titles,
            "description": description,
            "tags": tags,
            "thumbnail": {
                "base_image": "thumbnail_base.png",
                "suggested_text": thumb_text,
                "prompt": thumb_prompt,
            },
            "has_timestamps": bool(timestamps_str),
        }

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as out_f:
                json.dump(metadata, out_f, indent=2, ensure_ascii=False)
            safe_print(f" -> Đã lưu YouTube metadata tại: {output_path}")

        return metadata

    def export_thumbnail_base(
        self,
        props_path: Path,
        output_image_path: Path,
        remotion_dir: Optional[Path] = None,
    ) -> bool:
        """Render khung hình still ở 1920x1080 và thu nhỏ bằng ffmpeg sang 1280x720."""
        r_dir = remotion_dir or (self.root / "remotion")
        temp_still = output_image_path.parent / "temp_still_1080p.png"
        temp_still.parent.mkdir(parents=True, exist_ok=True)

        npx_cmd = "npx.cmd" if sys.platform == "win32" else "npx"

        # Frame 30 thường nằm trong đoạn Hook
        cmd_still = [
            npx_cmd,
            "remotion",
            "still",
            "src/index.ts",
            "StoryComposition",
            str(temp_still.resolve()),
            f"--props={str(props_path.resolve())}",
            "--frame=30",
        ]

        try:
            subprocess.run(cmd_still, cwd=str(r_dir), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if not temp_still.exists():
                return False

            # Dùng ffmpeg lanczos scale về đúng chuẩn YouTube thumbnail 1280x720
            cmd_scale = [
                "ffmpeg",
                "-y",
                "-v", "error",
                "-i", str(temp_still),
                "-vf", "scale=1280:720:flags=lanczos",
                str(output_image_path),
            ]
            subprocess.run(cmd_scale, check=True)

            if temp_still.exists():
                os.remove(temp_still)

            safe_print(f" -> Đã xuất ảnh nền thumbnail (1280x720): {output_image_path.name}")
            return output_image_path.exists()
        except Exception as e:
            logger.warning(f"Lỗi tạo thumbnail base: {e}")
            if temp_still.exists():
                os.remove(temp_still)
            return False
