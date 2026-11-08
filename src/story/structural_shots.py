from typing import List
from src.core.models import CameraMotion, NarrativeAct, Shot, ShotKind, ShotType

def insert_structural_shots(
    story_shots: List[Shot],
    chapter_title: str,
    fps: int,
    title_card_sec: float,
    end_screen_sec: float,
) -> List[Shot]:
    """Chèn title_card ngay sau Hook và end_screen ở cuối storyboard."""
    final_shots: List[Shot] = []
    final_shots.append(story_shots[0])

    next_story_shot = story_shots[1] if len(story_shots) > 1 else story_shots[0]

    title_card_frames = round(title_card_sec * fps)
    title_card = Shot(
        shot_id="title_card",
        kind=ShotKind.TITLE_CARD,
        narrative_act=NarrativeAct.HOOK,
        raw_text=chapter_title,
        voice_text="",
        voiceover="",
        speaker="narrator",
        is_dialogue=False,
        on_screen_character_id=None,
        character_id="nhan_vat_chinh",
        environment_id=next_story_shot.environment_id,
        shot_type=ShotType.WIDE.value,
        camera_motion=CameraMotion.STATIC.value,
        duration=round(title_card_frames / fps, 4),
        duration_frames=title_card_frames,
        action="title card display",
    )
    final_shots.append(title_card)

    for shot in story_shots[1:]:
        final_shots.append(shot)

    if end_screen_sec > 0:
        last_story_shot = story_shots[-1]
        end_frames = round(end_screen_sec * fps)
        end_screen = Shot(
            shot_id="end_screen",
            kind=ShotKind.END_SCREEN,
            narrative_act=NarrativeAct.CLIFFHANGER,
            raw_text="",
            voice_text="",
            voiceover="",
            speaker="narrator",
            is_dialogue=False,
            on_screen_character_id=None,
            character_id=last_story_shot.character_id,
            environment_id=last_story_shot.environment_id,
            shot_type=ShotType.WIDE.value,
            camera_motion=CameraMotion.STATIC.value,
            duration=round(end_frames / fps, 4),
            duration_frames=end_frames,
            action="end screen outro",
        )
        final_shots.append(end_screen)

    return final_shots
