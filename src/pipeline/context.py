import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from src.core.state_manager import StateManager
from src.story_parser import slugify_chapter_id

@dataclass
class PipelineContext:
    chapter_file: str
    output_name: str
    tts_provider: Optional[str]
    renderer: str
    stage: str
    title: Optional[str]
    env: Optional[str]
    frames: Optional[str]
    bench: Optional[str]
    settings: Dict[str, Any]
    story_rules: Dict[str, Any]
    fps: int
    shot_min: float
    shot_max: float
    split_min: float
    chapter_id: str
    chapter_dir: Path
    audio_dir: Path
    storyboard_path: Path
    state_mgr: StateManager

    @classmethod
    def create(
        cls,
        chapter_file: str,
        output_name: str,
        tts_provider: Optional[str],
        renderer: Optional[str],
        stage: str,
        title: Optional[str],
        env: Optional[str],
        frames: Optional[str],
        bench: Optional[str],
    ) -> "PipelineContext":
        with open("config/settings.json", "r", encoding="utf-8") as f:
            settings = json.load(f)
        with open("config/story_rules.json", "r", encoding="utf-8") as f:
            story_rules = json.load(f)

        fps = settings["video"]["fps"]
        shot_min = settings["visuals"]["shot_min_duration"]
        shot_max = settings["visuals"]["shot_max_duration"]
        split_min = settings["visuals"].get("split_min_duration", 2.5)

        chosen_renderer = renderer or settings.get("render", {}).get("renderer", "ffmpeg")
        chapter_id = slugify_chapter_id(chapter_file)
        chapter_dir = Path("output") / chapter_id
        chapter_dir.mkdir(parents=True, exist_ok=True)
        audio_dir = chapter_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        storyboard_path = chapter_dir / "storyboard.json"
        state_mgr = StateManager(state_file_path=str(storyboard_path))

        return cls(
            chapter_file=chapter_file,
            output_name=output_name,
            tts_provider=tts_provider,
            renderer=chosen_renderer,
            stage=stage,
            title=title,
            env=env,
            frames=frames,
            bench=bench,
            settings=settings,
            story_rules=story_rules,
            fps=fps,
            shot_min=shot_min,
            shot_max=shot_max,
            split_min=split_min,
            chapter_id=chapter_id,
            chapter_dir=chapter_dir,
            audio_dir=audio_dir,
            storyboard_path=storyboard_path,
            state_mgr=state_mgr,
        )
