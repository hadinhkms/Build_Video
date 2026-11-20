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
        frame: int = 30,
        scratch_dir: Optional[Path] = None,
        chapter_id: Optional[str] = None,
        gl: Optional[str] = None,
    ) -> bool:
        """Render khung hình still ở 1920x1080 (tái sử dụng NVMe bundle-cache) và thu nhỏ sang 1280x720."""
        from src.core.scratch_manager import ScratchManager

        props_path = Path(props_path)
        output_image_path = Path(output_image_path)
        r_dir = Path(remotion_dir) if remotion_dir else (self.root / "remotion")
        temp_still = output_image_path.parent / "temp_still_1080p.png"
        temp_still.parent.mkdir(parents=True, exist_ok=True)

        resolved_chapter_id = chapter_id
        if not resolved_chapter_id and props_path.exists():
            try:
                resolved_chapter_id = json.loads(props_path.read_text(encoding="utf-8")).get("chapterId")
            except Exception:
                resolved_chapter_id = None

        render_cfg: Dict[str, Any] = {}
        settings_path = self.config_dir / "settings.json"
        if settings_path.exists():
            try:
                render_cfg = json.loads(settings_path.read_text(encoding="utf-8")).get("render", {})
            except Exception:
                render_cfg = {}

        resolved_gl = gl or str(render_cfg.get("gl") or "angle")
        resolved_scratch: Optional[Path] = Path(scratch_dir).resolve() if scratch_dir is not None else None
        if resolved_scratch is None:
            try:
                mgr = ScratchManager(
                    project_root=self.root,
                    scratch_dir_setting=str(render_cfg.get("scratch_dir", "auto")),
                )
                resolved_scratch = mgr.scratch_root
            except Exception:
                resolved_scratch = None

        npx_cmd = "npx.cmd" if sys.platform == "win32" else "npx"

        # Frame 30 thường nằm trong đoạn Hook; gọi render_stills.ts tái dùng NVMe bundle-cache
        cmd_still = [
            npx_cmd,
            "tsx",
            "scripts/render_stills.ts",
            "--props",
            str(props_path.resolve()),
            "--composition",
            "StoryComposition",
            "--frame",
            str(max(0, int(frame))),
            "--out",
            str(temp_still.resolve()),
            "--gl",
            resolved_gl,
        ]
        if resolved_scratch is not None:
            cmd_still.extend(["--scratch-dir", str(resolved_scratch)])
        if resolved_chapter_id:
            cmd_still.extend(["--chapter-id", str(resolved_chapter_id)])

        try:
            subprocess.run(
                cmd_still,
                cwd=str(r_dir),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
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
