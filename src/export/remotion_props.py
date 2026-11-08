import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.audio.foley_planner import FoleyPlanner
from src.core.models import (
    Ambience,
    Bgm,
    CharacterAnchor,
    Rect,
    RenderProps,
    Shot,
    Storyboard,
    Style,
)
from src.export.crop_utils import calculate_crop_rect, copy_file_if_different, get_media_duration
from src.export.scene_builder import build_scenes
from src.export.visual_builder import build_shot_visuals, resolve_shot_image
from src.visuals.asset_check import AssetChecker

__all__ = [
    "copy_file_if_different",
    "calculate_crop_rect",
    "RemotionPropsExporter",
]

class RemotionPropsExporter:
    def __init__(
        self,
        project_root: Optional[str] = None,
        remotion_dir: Optional[str] = None,
    ):
        self.root = Path(project_root) if project_root else Path(__file__).resolve().parent.parent.parent
        self.remotion_dir = Path(remotion_dir) if remotion_dir else (self.root / "remotion")
        self.public_dir = self.remotion_dir / "public"
        self.settings = self._load_json(self.root / "config" / "settings.json")
        self.environments = self._load_json(self.root / "config" / "environments.json").get("environments", {})
        self.asset_checker = AssetChecker(base_dir=self.root, config_dir=self.root / "config")

    def _load_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _get_media_duration(self, path: Path) -> float:
        return get_media_duration(path)

    def resolve_shot_image(self, shot: Shot, chapter_id: str) -> Path:
        return resolve_shot_image(shot, chapter_id, self.root)

    def calculate_crop_rect(
        self,
        shot_type: Any,
        char_anchor: Optional[CharacterAnchor],
        cutout_meta: Optional[Dict[str, Any]],
    ) -> Rect:
        return calculate_crop_rect(shot_type, char_anchor, cutout_meta)

    def export_props(
        self,
        storyboard: Storyboard,
        chapter_id: str,
        output_dir: Path,
        words_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        audio_files_map: Optional[Dict[str, Path]] = None,
        story_rules_path: str = "config/story_rules.json",
    ) -> RenderProps:
        video_cfg = self.settings.get("video", {})
        fps = video_cfg.get("fps", 24)
        width = video_cfg.get("width", 1920)
        height = video_cfg.get("height", 1080)

        pub_chapter_dir = self.public_dir / "chapters" / chapter_id
        pub_audio_dir = pub_chapter_dir / "audio"
        for sub in ["audio", "images", "environments", "characters", "clips"]:
            (pub_chapter_dir / sub).mkdir(parents=True, exist_ok=True)

        words_map = words_map or {}
        audio_files_map = audio_files_map or {}

        # 1. Đọc emotion_keywords
        emotion_keywords = ["kinh hoàng", "bất ngờ", "bí mật", "không hề", "kỳ lạ"]
        rules_p = self.root / story_rules_path
        if rules_p.exists():
            with open(rules_p, "r", encoding="utf-8") as rf:
                rules_data = json.load(rf)
                emotion_keywords = rules_data.get("emotion_keywords", emotion_keywords)

        for shot in storyboard.shots:
            if shot.raw_text:
                emo_match = re.search(r'\[EMO:\s*([^\]]+)\]', shot.raw_text, flags=re.IGNORECASE)
                if emo_match:
                    extras = [e.strip().lower() for e in emo_match.group(1).split(",") if e.strip()]
                    emotion_keywords.extend(extras)

        # 2. Khởi tạo FoleyPlanner
        foley_planner = FoleyPlanner(
            foley_rules_path=str(self.root / "config" / "foley_rules.json"),
            environments_path=str(self.root / "config" / "environments.json"),
            settings_path=str(self.root / "config" / "settings.json"),
            assets_dir=str(self.root / "assets" / "audio"),
        )

        # 3. Phân tích tài sản hình ảnh và tạo visuals
        asset_checklist = self.asset_checker.check_and_assign_visuals(storyboard)
        visual_modes = asset_checklist["shot_visual_modes"]
        story_visuals, story_effects, story_grades, _ = build_shot_visuals(
            storyboard=storyboard,
            visual_modes=visual_modes,
            environments=self.environments,
            root=self.root,
            pub_chapter_dir=pub_chapter_dir,
            chapter_id=chapter_id,
            fps=fps,
            asset_checker=self.asset_checker,
        )

        # 4. Xây dựng các Scenes
        scenes, _ = build_scenes(
            storyboard=storyboard,
            story_visuals=story_visuals,
            story_effects=story_effects,
            story_grades=story_grades,
            foley_planner=foley_planner,
            words_map=words_map,
            emotion_keywords=emotion_keywords,
            root=self.root,
            pub_chapter_dir=pub_chapter_dir,
            chapter_id=chapter_id,
            fps=fps,
        )

        # 5. Ambience & BGM
        planned_amb = foley_planner.plan_ambience(storyboard, fps=fps)
        ambience_props: List[Ambience] = []
        for amb in planned_amb:
            src_f = self.root / "assets" / amb.src
            dst_f = pub_chapter_dir / amb.src
            if src_f.exists():
                copy_file_if_different(src_f, dst_f)
                ambience_props.append(
                    Ambience(
                        src=f"chapters/{chapter_id}/{amb.src}",
                        start_sec=amb.start_sec,
                        end_sec=amb.end_sec,
                        volume=amb.volume,
                        fade_sec=amb.fade_sec,
                    )
                )

        planned_bgm = foley_planner.plan_bgm(storyboard, words_map, fps=fps)
        bgm_prop: Optional[Bgm] = None
        if planned_bgm:
            src_f = self.root / "assets" / planned_bgm.src
            dst_f = pub_chapter_dir / planned_bgm.src
            if src_f.exists():
                copy_file_if_different(src_f, dst_f)
                bgm_prop = Bgm(
                    src=f"chapters/{chapter_id}/{planned_bgm.src}",
                    volume=planned_bgm.volume,
                    ducked_volume=planned_bgm.ducked_volume,
                    duck_intervals=planned_bgm.duck_intervals,
                    cut_at_sec=planned_bgm.cut_at_sec,
                )

        # 6. Style & RenderProps
        visuals_cfg = self.settings.get("visuals", {})
        letterbox_ratio = visuals_cfg.get("letterbox_ratio", 2.39)
        if abs(width / max(1, height) - 16 / 9) > 0.05:
            letterbox_ratio = None

        style_prop = Style(
            subtitles=bool(visuals_cfg.get("enable_subtitles", True)),
            letterbox_ratio=letterbox_ratio,
            grain=bool(visuals_cfg.get("film_grain", True)),
        )

        props = RenderProps(
            schema_version=1,
            chapter_id=chapter_id,
            title=storyboard.title,
            fps=fps,
            width=width,
            height=height,
            scenes=scenes,
            ambience=ambience_props,
            bgm=bgm_prop,
            style=style_prop,
        )

        props_dict = props.model_dump(mode="json", by_alias=True)
        json_str = json.dumps(props_dict, ensure_ascii=False, indent=2)
        RenderProps.model_validate_json(json_str, by_name=False)

        output_dir.mkdir(parents=True, exist_ok=True)
        props_file = output_dir / "render_props.json"
        with open(props_file, "w", encoding="utf-8") as f:
            f.write(json_str)

        return props

    def export(
        self,
        storyboard: Storyboard,
        output_dir: Path,
        chapter_id: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None,
        words_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        audio_files_map: Optional[Dict[str, Path]] = None,
        story_rules_path: str = "config/story_rules.json",
    ) -> RenderProps:
        if settings:
            self.settings = settings
        cid = chapter_id or storyboard.chapter_id or "sample_chapter"
        return self.export_props(
            storyboard=storyboard,
            chapter_id=cid,
            output_dir=Path(output_dir),
            words_map=words_map,
            audio_files_map=audio_files_map,
            story_rules_path=story_rules_path,
        )
