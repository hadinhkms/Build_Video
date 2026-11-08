import re
from typing import Callable, Dict, List, Optional, Tuple

from src.core.models import (
    CameraMotion,
    NarrativeAct,
    Shot,
    ShotKind,
    ShotType,
)
from src.story.structural_shots import insert_structural_shots
from src.story.text_utils import normalize_text_nfc

__all__ = [
    "build_initial_shots",
    "assign_narrative_acts",
    "assign_on_screen_characters",
    "assign_camera_and_shot_types",
    "insert_structural_shots",
]

def build_initial_shots(parsed_units: List[Dict]) -> Tuple[List[Shot], bool]:
    """Xác định Hook và tạo danh sách Shot cơ bản (bao gồm cold-open nếu cần)."""
    hook_unit_idx = None
    for i, u in enumerate(parsed_units):
        if u["is_explicit_hook"]:
            hook_unit_idx = i
            break

    if hook_unit_idx is None:
        max_score = -1
        best_idx = 0
        for i, u in enumerate(parsed_units):
            score = u["tension_score"]
            if score >= max_score:
                max_score = score
                best_idx = i
        hook_unit_idx = best_idx

    story_shots: List[Shot] = []
    is_cold_open = (hook_unit_idx > 0)

    if is_cold_open:
        hook_unit = parsed_units[hook_unit_idx]
        cold_open_shot = Shot(
            shot_id="shot_hook",
            kind=ShotKind.STORY,
            narrative_act=NarrativeAct.HOOK,
            raw_text=hook_unit["raw_text"],
            voice_text=hook_unit["voice_text"],
            voiceover=hook_unit["voice_text"],
            speaker=hook_unit["speaker"],
            is_dialogue=hook_unit["is_dialogue"],
            environment_id=hook_unit["environment_id"],
            action="intense hook moment, suspenseful revelation",
        )
        cold_open_shot._on_char_tag = hook_unit["on_screen_char"]
        cold_open_shot._tension_score = hook_unit["tension_score"]
        cold_open_shot._syllables = hook_unit["syllables"]
        story_shots.append(cold_open_shot)

    for i, u in enumerate(parsed_units):
        s_id = f"shot_{i:02d}"
        act = NarrativeAct.HOOK if (not is_cold_open and i == 0) else NarrativeAct.SETUP
        shot = Shot(
            shot_id=s_id,
            kind=ShotKind.STORY,
            narrative_act=act,
            raw_text=u["raw_text"],
            voice_text=u["voice_text"],
            voiceover=u["voice_text"],
            speaker=u["speaker"],
            is_dialogue=u["is_dialogue"],
            environment_id=u["environment_id"],
            action=f"narrating: {u['raw_text'][:40]}...",
        )
        shot._on_char_tag = u["on_screen_char"]
        shot._tension_score = u["tension_score"]
        shot._syllables = u["syllables"]
        story_shots.append(shot)

    return story_shots, is_cold_open

def assign_narrative_acts(story_shots: List[Shot], is_cold_open: bool) -> None:
    """Gán 4 hồi cho các cảnh story sau Hook theo tỉ lệ âm tiết cộng dồn."""
    post_hook_shots = story_shots[1:]
    total_syllables = sum(getattr(s, "_syllables", 1) for s in post_hook_shots) or 1

    cum_syllables = 0
    for idx, shot in enumerate(post_hook_shots):
        s_syl = getattr(shot, "_syllables", 1)
        mid = cum_syllables + s_syl / 2.0
        ratio = mid / total_syllables
        cum_syllables += s_syl

        if idx == len(post_hook_shots) - 1:
            shot.narrative_act = NarrativeAct.CLIFFHANGER
        elif ratio < 0.20:
            shot.narrative_act = NarrativeAct.SETUP
        elif ratio < 0.60:
            shot.narrative_act = NarrativeAct.RISING
        elif ratio < 0.90:
            shot.narrative_act = NarrativeAct.CLIMAX
        else:
            shot.narrative_act = NarrativeAct.CLIFFHANGER

def assign_on_screen_characters(
    story_shots: List[Shot],
    char_name_to_key: Dict[str, str],
) -> None:
    """Gán on_screen_character_id theo thứ tự ưu tiên."""
    prev_char_id = None
    prev_env_id = None

    for shot in story_shots:
        tag_char = getattr(shot, "_on_char_tag", None)
        if tag_char == "none":
            chosen_char = None
        elif tag_char:
            chosen_char = tag_char
        elif shot.is_dialogue and shot.speaker != "narrator":
            chosen_char = shot.speaker
        else:
            found_char = None
            first_pos = 999999
            text_norm = normalize_text_nfc(shot.raw_text).lower()
            for name_norm, char_k in char_name_to_key.items():
                pos = text_norm.find(name_norm)
                if pos != -1 and pos < first_pos:
                    first_pos = pos
                    found_char = char_k
            if found_char:
                chosen_char = found_char
            elif prev_char_id and shot.environment_id == prev_env_id:
                chosen_char = prev_char_id
            else:
                chosen_char = None

        shot.on_screen_character_id = chosen_char
        shot.character_id = chosen_char or "nhan_vat_chinh"
        prev_char_id = chosen_char
        prev_env_id = shot.environment_id

def assign_camera_and_shot_types(
    story_shots: List[Shot],
    rules: Dict,
    build_prompt_fn: Callable[[str, str, str, str], str],
) -> None:
    """Gán cỡ cảnh (shot_type) và camera motion theo luật không trùng."""
    shot_priority_by_act = {
        NarrativeAct.HOOK: [ShotType.CLOSEUP, ShotType.EXTREME_CLOSEUP],
        NarrativeAct.SETUP: [ShotType.WIDE, ShotType.MEDIUM],
        NarrativeAct.RISING: [ShotType.MEDIUM, ShotType.OVER_SHOULDER],
        NarrativeAct.CLIMAX: [ShotType.CLOSEUP, ShotType.EXTREME_CLOSEUP],
        NarrativeAct.CLIFFHANGER: [ShotType.EXTREME_CLOSEUP, ShotType.CLOSEUP, ShotType.MEDIUM],
    }

    last_shot_of_act = {}
    for idx, shot in enumerate(story_shots):
        last_shot_of_act[shot.narrative_act] = idx

    movement_verbs = rules.get("movement_verbs", [])
    pan_direction = "pan_left"
    prev_shot_type: Optional[ShotType] = None

    for idx, shot in enumerate(story_shots):
        priorities = shot_priority_by_act.get(shot.narrative_act, [ShotType.MEDIUM, ShotType.CLOSEUP])
        chosen_type = priorities[0]
        if prev_shot_type and chosen_type == prev_shot_type:
            for candidate in priorities[1:]:
                if candidate != prev_shot_type:
                    chosen_type = candidate
                    break
        shot.shot_type = chosen_type.value
        prev_shot_type = chosen_type

        text_norm = normalize_text_nfc(shot.raw_text).lower()
        has_movement = any(re.search(r'(?<!\w)' + re.escape(normalize_text_nfc(v).lower()) + r'(?!\w)', text_norm) for v in movement_verbs)

        if shot.narrative_act == NarrativeAct.HOOK:
            shot.camera_motion = CameraMotion.RAPID_ZOOM_IN.value
        elif idx == last_shot_of_act.get(shot.narrative_act):
            shot.camera_motion = CameraMotion.ZOOM_OUT.value
        elif has_movement:
            shot.camera_motion = pan_direction
            pan_direction = "pan_right" if pan_direction == "pan_left" else "pan_left"
        elif getattr(shot, "_tension_score", 0) > 0:
            shot.camera_motion = CameraMotion.ZOOM_IN.value
        else:
            shot.camera_motion = CameraMotion.ZOOM_IN.value

        shot.prompt = build_prompt_fn(
            shot.shot_type,
            f"moment: {shot.raw_text[:30]}",
            shot.character_id,
            shot.environment_id,
        )
