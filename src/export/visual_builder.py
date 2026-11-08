import json
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

from src.core.models import (
    CharacterAnchor,
    Effects,
    FaceRig,
    Grade,
    Rect,
    Shot,
    ShotKind,
    Storyboard,
    Visual,
)
from src.export.clip_fit import plan_clip_fit
from src.export.crop_utils import calculate_crop_rect, copy_file_if_different, get_media_duration
from src.visuals.asset_check import AssetChecker
from src.visuals.face_rig import FaceRigProcessor

def resolve_shot_image(shot: Shot, chapter_id: str, root: Path) -> Path:
    """Tìm đường dẫn ảnh của cảnh theo thứ tự ưu tiên."""
    img_p = root / "assets" / "images" / f"{shot.shot_id}.jpg"
    if img_p.exists():
        return img_p
    if shot.parent_id:
        parent_img = root / "assets" / "images" / f"{shot.parent_id}.jpg"
        if parent_img.exists():
            return parent_img

    default_char_img = root / "assets" / "characters" / "main_char_face.jpg"
    if default_char_img.exists():
        return default_char_img

    return img_p

def build_shot_visuals(
    storyboard: Storyboard,
    visual_modes: Dict[str, Any],
    environments: Dict[str, Any],
    root: Path,
    pub_chapter_dir: Path,
    chapter_id: str,
    fps: int,
    asset_checker: AssetChecker,
) -> Tuple[Dict[str, Visual], Dict[str, Effects], Dict[str, Optional[Grade]], Set[str]]:
    """Tạo Visual, Effects & Grade cho từng cảnh story trong Storyboard."""
    pub_images_dir = pub_chapter_dir / "images"
    pub_env_dir = pub_chapter_dir / "environments"
    pub_char_dir = pub_chapter_dir / "characters"
    pub_clips_dir = pub_chapter_dir / "clips"

    copied_image_rel_paths: Set[str] = set()
    story_visuals: Dict[str, Visual] = {}
    story_effects: Dict[str, Effects] = {}
    story_grades: Dict[str, Optional[Grade]] = {}

    for shot in storyboard.shots:
        if shot.kind != ShotKind.STORY:
            continue

        v_info = visual_modes.get(shot.shot_id, {})
        mode = v_info.get("mode", "full_image")

        env_info = environments.get(shot.environment_id, {})
        slots = env_info.get("character_slots", {})
        default_slot_name = env_info.get("default_character_slot", "center")
        slot = slots.get(default_slot_name, {"x": 0.5, "y": 1.02, "height": 0.62})

        # 1. Grade
        grade_data = env_info.get("grade")
        if grade_data:
            grade = Grade(
                css_filter=grade_data.get("css_filter", "none"),
                overlay_gradient=grade_data.get("overlay_gradient"),
                overlay_blend=grade_data.get("overlay_blend", "soft-light"),
                contact_shadow_opacity=float(grade_data.get("contact_shadow_opacity", 0.45)),
            )
        else:
            grade = None
        story_grades[shot.shot_id] = grade

        # 2. Effects
        rain_mode = env_info.get("rain_mode", "off")
        rain_reg_data = env_info.get("rain_region")
        if rain_mode == "window" and rain_reg_data:
            rain_region = Rect(
                x=float(rain_reg_data["x"]),
                y=float(rain_reg_data["y"]),
                w=float(rain_reg_data["w"]),
                h=float(rain_reg_data["h"]),
            )
        else:
            if rain_mode == "window":
                rain_mode = "full"
            rain_region = None

        effects = Effects(
            rain=rain_mode,
            rain_region=rain_region,
            flicker=bool(env_info.get("flicker", False)),
        )
        story_effects[shot.shot_id] = effects

        # 3. Visual
        clips_input_dir = root / "input" / "rendered_clips"
        clip_file = None
        is_loop = False
        if clips_input_dir.exists():
            reg_clip = clips_input_dir / f"{shot.shot_id}.mp4"
            loop_clip = clips_input_dir / f"{shot.shot_id}.loop.mp4"
            if reg_clip.exists() and loop_clip.exists():
                print(f"Cảnh báo: Cả {reg_clip.name} và {loop_clip.name} đều tồn tại. Ưu tiên clip thường.")
                clip_file = reg_clip
                is_loop = False
            elif reg_clip.exists():
                clip_file = reg_clip
                is_loop = False
            elif loop_clip.exists():
                clip_file = loop_clip
                is_loop = True

        if clip_file:
            clip_dur = get_media_duration(clip_file)
            dst_clip = pub_clips_dir / clip_file.name
            copy_file_if_different(clip_file, dst_clip)
            clip_rel = f"chapters/{chapter_id}/clips/{clip_file.name}"
            scene_dur_sec = shot.duration_frames / fps
            clip_fit = plan_clip_fit(
                clip_duration_sec=clip_dur,
                scene_duration_sec=scene_dur_sec,
                is_loop=is_loop,
                fps=fps,
            )
            visual = Visual(
                mode="clip",
                image_src=None,
                background_src=None,
                character_src=None,
                clip_src=clip_rel,
                character_anchor=None,
                crop_rect=None,
                clip_duration_sec=round(clip_dur, 4),
                clip_fit=clip_fit,
                face_rig=None,
            )
        elif mode == "layered":
            plate_path = Path(v_info["plate_path"])
            dst_plate = pub_env_dir / shot.environment_id / plate_path.name
            copy_file_if_different(plate_path, dst_plate)
            bg_rel = f"chapters/{chapter_id}/environments/{shot.environment_id}/{plate_path.name}"

            char_rel = None
            char_anchor = None
            cutout_meta = None
            face_rig = None

            char_key = shot.on_screen_character_id or shot.character_id or "default"
            if v_info.get("character_path"):
                char_path = Path(v_info["character_path"])
                dst_char = pub_char_dir / char_key / char_path.name
                copy_file_if_different(char_path, dst_char)
                char_rel = f"chapters/{chapter_id}/characters/{char_key}/{char_path.name}"

                char_anchor = CharacterAnchor(
                    x=float(slot.get("x", 0.5)),
                    y=float(slot.get("y", 1.02)),
                    height=float(slot.get("height", 0.62)),
                )
                _, cutout_meta = asset_checker.find_character_cutout(char_key)

                char_dir = root / "assets" / "characters" / char_key
                face_rig_json = char_dir / "face_rig.json"
                if not face_rig_json.exists() and (char_dir / "eyes_closed.png").exists():
                    FaceRigProcessor().rig_character(char_dir)
                if face_rig_json.exists():
                    try:
                        with open(face_rig_json, "r", encoding="utf-8") as frf:
                            fr_data = json.load(frf)
                        for fname in ["eyes_closed_patch.png", "mouth_open_patch.png"]:
                            p_src = char_dir / fname
                            if p_src.exists():
                                copy_file_if_different(p_src, pub_char_dir / char_key / fname)
                        face_rig = FaceRig(
                            eyes_patch_src=f"chapters/{chapter_id}/characters/{char_key}/eyes_closed_patch.png" if (char_dir / "eyes_closed_patch.png").exists() else None,
                            mouth_patch_src=f"chapters/{chapter_id}/characters/{char_key}/mouth_open_patch.png" if (char_dir / "mouth_open_patch.png").exists() else None,
                            eyes=Rect(**fr_data["eyes"]) if fr_data.get("eyes") else None,
                            mouth=Rect(**fr_data["mouth"]) if fr_data.get("mouth") else None,
                        )
                    except Exception:
                        face_rig = None

            crop_rect = calculate_crop_rect(shot.shot_type, char_anchor, cutout_meta)
            visual = Visual(
                mode="layered",
                image_src=None,
                background_src=bg_rel,
                character_src=char_rel,
                clip_src=None,
                character_anchor=char_anchor,
                crop_rect=crop_rect,
                clip_duration_sec=None,
                clip_fit=None,
                face_rig=face_rig,
            )
        else:
            img_path_str = v_info.get("image_path")
            if img_path_str:
                src_p = Path(img_path_str)
                dst_p = pub_images_dir / f"{shot.shot_id}.jpg"
                if src_p.exists():
                    copy_file_if_different(src_p, dst_p)
                    copied_image_rel_paths.add(dst_p.relative_to(pub_images_dir).as_posix())
                img_rel = f"chapters/{chapter_id}/images/{shot.shot_id}.jpg"
            else:
                src_img = resolve_shot_image(shot, chapter_id, root)
                dst_img = pub_images_dir / f"{shot.shot_id}.jpg"
                if src_img.exists():
                    copy_file_if_different(src_img, dst_img)
                    copied_image_rel_paths.add(dst_img.relative_to(pub_images_dir).as_posix())
                img_rel = f"chapters/{chapter_id}/images/{shot.shot_id}.jpg"

            visual = Visual(
                mode="full_image",
                image_src=img_rel,
                background_src=None,
                character_src=None,
                clip_src=None,
                character_anchor=None,
                crop_rect=None,
                clip_duration_sec=None,
                clip_fit=None,
                face_rig=None,
            )
        story_visuals[shot.shot_id] = visual

    return story_visuals, story_effects, story_grades, copied_image_rel_paths
