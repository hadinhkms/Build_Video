from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from src.audio.envelope import compute_shot_envelope
from src.audio.foley_planner import FoleyPlanner
from src.core.models import (
    Caption,
    Effects,
    Grade,
    Scene,
    SceneAudio,
    Sfx,
    Shot,
    ShotKind,
    Storyboard,
    Visual,
    Word,
)
from src.export.crop_utils import copy_file_if_different
from src.text.alignment import create_captions

def build_scenes(
    storyboard: Storyboard,
    story_visuals: Dict[str, Visual],
    story_effects: Dict[str, Effects],
    story_grades: Dict[str, Optional[Grade]],
    foley_planner: FoleyPlanner,
    words_map: Dict[str, List[Dict[str, Any]]],
    emotion_keywords: List[str],
    root: Path,
    pub_chapter_dir: Path,
    chapter_id: str,
    fps: int,
) -> Tuple[List[Scene], Set[str]]:
    """Xây dựng danh sách Scene hoàn chỉnh cho RenderProps."""
    pub_audio_dir = pub_chapter_dir / "audio"
    copied_audio_rel_paths: Set[str] = set()

    story_shots = [s for s in storyboard.shots if s.kind == ShotKind.STORY]
    first_story_visual = story_visuals.get(story_shots[0].shot_id) if story_shots else None
    last_story_visual = story_visuals.get(story_shots[-1].shot_id) if story_shots else None

    seen_acts: Set[str] = set()
    first_of_act_shot_ids: Set[str] = set()
    for s in story_shots:
        act_val = s.narrative_act.value if hasattr(s.narrative_act, "value") else str(s.narrative_act)
        if act_val not in seen_acts:
            seen_acts.add(act_val)
            first_of_act_shot_ids.add(s.shot_id)

    scenes: List[Scene] = []

    for shot in storyboard.shots:
        # 1. Visual, Effects, Grade
        if shot.kind == ShotKind.TITLE_CARD:
            visual = first_story_visual or Visual(
                mode="full_image",
                image_src=None,
                background_src=None,
                character_src=None,
                clip_src=None,
                character_anchor=None,
                crop_rect=None,
                clip_duration_sec=None,
                clip_fit=None,
                face_rig=None,
            )
            effects = Effects(rain="off", rain_region=None, flicker=False)
            grade = None
        elif shot.kind == ShotKind.END_SCREEN:
            visual = last_story_visual or Visual(
                mode="full_image",
                image_src=None,
                background_src=None,
                character_src=None,
                clip_src=None,
                character_anchor=None,
                crop_rect=None,
                clip_duration_sec=None,
                clip_fit=None,
                face_rig=None,
            )
            effects = Effects(rain="off", rain_region=None, flicker=False)
            grade = None
        else:
            visual = story_visuals.get(shot.shot_id)
            effects = story_effects.get(shot.shot_id)
            grade = story_grades.get(shot.shot_id)

        # 2. Audio
        scene_audio = None
        if shot.kind == ShotKind.STORY and shot.audio_file:
            audio_src_path = Path(shot.audio_file)
            if not audio_src_path.is_absolute():
                audio_src_path = root / shot.audio_file

            if audio_src_path.exists():
                dst_audio = pub_audio_dir / audio_src_path.name
                copy_file_if_different(audio_src_path, dst_audio)
                copied_audio_rel_paths.add(dst_audio.relative_to(pub_audio_dir).as_posix())

                rel_src = f"chapters/{chapter_id}/audio/{audio_src_path.name}"
                duration_sec = shot.duration_frames / fps
                scene_audio = SceneAudio(
                    src=rel_src,
                    start_in_file_sec=round(float(getattr(shot, "audio_start_in_file_sec", 0.0) or 0.0), 4),
                    duration_sec=round(float(duration_sec), 4),
                )

        # 3. Words & Captions
        shot_words: List[Word] = []
        shot_captions: List[Caption] = []

        key = shot.parent_id or shot.shot_id
        if shot.kind == ShotKind.STORY and key in words_map:
            all_words = words_map[key]
            offset_start = float(getattr(shot, "audio_start_in_file_sec", 0.0) or 0.0)
            offset_end = offset_start + (shot.duration_frames / fps)

            for w in all_words:
                w_start = float(w["start"])
                w_end = float(w["end"])
                if w_start >= (offset_start - 0.001) and w_end <= (offset_end + 0.05):
                    local_start = max(0.0, w_start - offset_start)
                    local_end = max(0.0, w_end - offset_start)
                    shot_words.append(
                        Word(
                            text=w["text"],
                            start=round(local_start, 4),
                            end=round(local_end, 4),
                        )
                    )

            if shot_words:
                shot_dur_sec = shot.duration_frames / fps
                shot_captions_dict = create_captions(
                    [w.model_dump() for w in shot_words],
                    shot_duration=shot_dur_sec,
                    emotion_keywords=emotion_keywords,
                )
                for c in shot_captions_dict:
                    shot_captions.append(
                        Caption(
                            text=c["text"],
                            start=c["start"],
                            end=c["end"],
                            highlight=c["highlight"],
                        )
                    )

        # 4. SFX
        shot_sfx: List[Sfx] = []
        if shot.kind == ShotKind.STORY:
            is_first_of_act = shot.shot_id in first_of_act_shot_ids
            planned_sfx = foley_planner.plan_sfx_for_scene(
                shot=shot,
                words=[w.model_dump() for w in shot_words],
                is_first_of_act=is_first_of_act,
            )
            for s in planned_sfx:
                src_f = root / "assets" / s.src
                dst_f = pub_chapter_dir / s.src
                if src_f.exists():
                    copy_file_if_different(src_f, dst_f)
                    copied_audio_rel_paths.add(dst_f.relative_to(pub_audio_dir).as_posix())
                    shot_sfx.append(
                        Sfx(
                            src=f"chapters/{chapter_id}/{s.src}",
                            start_sec=s.start_sec,
                            volume=s.volume,
                            duration_sec=s.duration_sec,
                            fade_in_sec=s.fade_in_sec,
                            fade_out_sec=s.fade_out_sec,
                        )
                    )

        # 5. Mouth envelope
        mouth_envelope = None
        if shot.kind == ShotKind.STORY and shot.audio_file:
            audio_src_p = Path(shot.audio_file)
            if not audio_src_p.is_absolute():
                audio_src_p = root / shot.audio_file
            mouth_envelope = compute_shot_envelope(
                audio_path=audio_src_p if audio_src_p.exists() else None,
                start_in_file_sec=float(getattr(shot, "audio_start_in_file_sec", 0.0) or 0.0),
                duration_in_frames=int(shot.duration_frames),
                is_dialogue=shot.is_dialogue,
                speaker=shot.speaker,
                on_screen_character_id=shot.on_screen_character_id,
                character_id=shot.character_id,
                fps=fps,
            )

        # 6. Scene object
        kind_val = shot.kind.value if hasattr(shot.kind, "value") else str(shot.kind)
        act_val = shot.narrative_act.value if hasattr(shot.narrative_act, "value") else str(shot.narrative_act)
        st_val = shot.shot_type.value if hasattr(shot.shot_type, "value") else str(shot.shot_type)
        cm_val = shot.camera_motion.value if hasattr(shot.camera_motion, "value") else str(shot.camera_motion)

        scene = Scene(
            id=shot.shot_id,
            kind=kind_val,
            act=act_val,
            raw_text=shot.raw_text,
            voice_text=shot.voice_text or shot.raw_text,
            speaker=shot.speaker,
            is_dialogue=shot.is_dialogue,
            on_screen_character_id=shot.on_screen_character_id,
            environment_id=shot.environment_id,
            shot_type=st_val,
            camera_motion=cm_val,
            duration_in_frames=int(shot.duration_frames),
            audio=scene_audio,
            words=shot_words,
            captions=shot_captions,
            sfx=shot_sfx,
            visual=visual,
            effects=effects,
            grade=grade,
            mouth_envelope=mouth_envelope,
        )
        scenes.append(scene)

    return scenes, copied_audio_rel_paths
