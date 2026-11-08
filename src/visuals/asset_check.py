import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from PIL import Image

from src.core.models import NarrativeAct, Shot, ShotKind, ShotType, Storyboard
from src.visuals.raccord import downgrade_over_shoulder_shots


class AssetChecker:
    """Kiểm tra tài sản hình ảnh, hạ cấp over_shoulder, chọn visual.mode và in checklist."""

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        config_dir: Optional[Path] = None,
    ):
        self.base_dir = base_dir or Path(__file__).resolve().parent.parent.parent
        self.config_dir = config_dir or (self.base_dir / "config")
        self.assets_dir = self.base_dir / "assets"
        self.environments_config = self._load_json(self.config_dir / "environments.json").get("environments", {})
        self.characters_config = self._load_json(self.config_dir / "characters.json").get("characters", {})

    def _load_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def find_shot_image(self, shot_id: str, parent_id: Optional[str] = None) -> Optional[Path]:
        """Tìm ảnh tĩnh full_image trong assets/images/ theo shot_id hoặc parent_id."""
        images_dir = self.assets_dir / "images"
        if not images_dir.exists():
            return None

        # 1. Tìm theo shot_id
        for ext in [".jpg", ".jpeg", ".png", ".webp"]:
            candidate = images_dir / f"{shot_id}{ext}"
            if candidate.exists():
                return candidate

        # 2. Nếu là cảnh con, fallback tìm theo parent_id
        if parent_id:
            for ext in [".jpg", ".jpeg", ".png", ".webp"]:
                candidate = images_dir / f"{parent_id}{ext}"
                if candidate.exists():
                    return candidate

        return None

    def find_environment_plate(self, env_key: str) -> Optional[Path]:
        """Tìm ảnh plate của bối cảnh trong assets/environments/<env_key>/plate.(png|jpg)."""
        env_dir = self.assets_dir / "environments" / env_key
        if not env_dir.exists():
            return None
        for ext in [".png", ".jpg", ".jpeg", ".webp"]:
            candidate = env_dir / f"plate{ext}"
            if candidate.exists():
                return candidate
        return None

    def find_character_cutout(self, char_key: str) -> Tuple[Optional[Path], Optional[Dict[str, Any]]]:
        """Tìm ảnh nhân vật đã tách nền base_cutout.png và base_cutout.json."""
        char_dir = self.assets_dir / "characters" / char_key
        if not char_dir.exists():
            return None, None

        cutout_img = char_dir / "base_cutout.png"
        cutout_json = char_dir / "base_cutout.json"

        meta = None
        if cutout_json.exists():
            try:
                with open(cutout_json, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                meta = None

        if cutout_img.exists():
            return cutout_img, meta

        # Nếu chưa có base_cutout.png, kiểm tra xem có base.png đã có alpha không
        for ext in [".png", ".webp"]:
            base_cand = char_dir / f"base{ext}"
            if base_cand.exists():
                return base_cand, meta

        return None, meta

    def downgrade_over_shoulder_shots(self, storyboard: Storyboard) -> List[str]:
        """Hạ cấp cỡ cảnh over_shoulder theo quy tắc raccord."""
        return downgrade_over_shoulder_shots(
            storyboard,
            has_custom_image_fn=lambda s_id, p_id: self.find_shot_image(s_id, p_id) is not None,
        )

    def check_and_assign_visuals(self, storyboard: Storyboard) -> Dict[str, Any]:
        """Kiểm tra tài sản cho từng cảnh, gán visual mode và tạo báo cáo checklist."""
        # 1. Hạ cấp over_shoulder trước
        downgraded_log = self.downgrade_over_shoulder_shots(storyboard)

        checklist: Dict[str, Any] = {
            "downgraded_shots": downgraded_log,
            "missing_plates": set(),
            "missing_cutouts": set(),
            "warnings": [],
            "shot_visual_modes": {},
            "stats": {"layered": 0, "full_image": 0, "fallback_default": 0},
        }

        # Ảnh dự phòng baseline mặc định
        default_fallback_img = self.assets_dir / "characters" / "main_char_face.jpg"

        for shot in storyboard.shots:
            if shot.kind != ShotKind.STORY:
                continue

            shot_img = self.find_shot_image(shot.shot_id, shot.parent_id)
            plate_img = self.find_environment_plate(shot.environment_id)

            char_img, cutout_meta = None, None
            if shot.on_screen_character_id:
                char_img, cutout_meta = self.find_character_cutout(shot.on_screen_character_id)

            # Ưu tiên 1: Có ảnh riêng trong assets/images/
            if shot_img:
                mode = "full_image"
                checklist["stats"]["full_image"] += 1
                checklist["shot_visual_modes"][shot.shot_id] = {
                    "mode": mode,
                    "image_path": str(shot_img),
                }
                continue

            # Ưu tiên 2: Có plate và có nhân vật trên hình + có ảnh cutout
            if plate_img and shot.on_screen_character_id and char_img:
                mode = "layered"
                checklist["stats"]["layered"] += 1

                # Kiểm tra slot cut_bottom
                env_info = self.environments_config.get(shot.environment_id, {})
                slots = env_info.get("character_slots", {})
                default_slot_name = env_info.get("default_character_slot", "center")
                slot = slots.get(default_slot_name, {"x": 0.5, "y": 1.02, "height": 0.62})

                if cutout_meta and cutout_meta.get("cut_bottom", False):
                    slot_y = slot.get("y", 1.0)
                    if slot_y < 1.0:
                        warn = (
                            f"[LỖI SLOT] Cảnh {shot.shot_id} ({shot.environment_id}): "
                            f"Nhân vật '{shot.on_screen_character_id}' có cut_bottom=True "
                            f"nhưng slot.y={slot_y} < 1.0 (mép cắt sẽ bị lơ lửng trong khung hình!)."
                        )
                        checklist["warnings"].append(warn)

                # Kiểm tra zoom ratio > 1.5x
                self._check_crop_softness(plate_img, shot, checklist)

                checklist["shot_visual_modes"][shot.shot_id] = {
                    "mode": mode,
                    "plate_path": str(plate_img),
                    "character_path": str(char_img),
                }
                continue

            # Ưu tiên 3: Có plate nhưng không có nhân vật (hoặc thiếu cutout)
            if plate_img:
                mode = "layered"
                checklist["stats"]["layered"] += 1
                if shot.on_screen_character_id and not char_img:
                    checklist["missing_cutouts"].add(shot.on_screen_character_id)

                self._check_crop_softness(plate_img, shot, checklist)

                checklist["shot_visual_modes"][shot.shot_id] = {
                    "mode": mode,
                    "plate_path": str(plate_img),
                    "character_path": None,
                }
                continue

            # Ưu tiên 4: Không có plate -> Fallback về ảnh mặc định full_image
            checklist["missing_plates"].add(shot.environment_id)
            checklist["stats"]["fallback_default"] += 1
            checklist["shot_visual_modes"][shot.shot_id] = {
                "mode": "full_image",
                "image_path": str(default_fallback_img) if default_fallback_img.exists() else None,
            }

        # Convert set to list for JSON serialization
        checklist["missing_plates"] = sorted(list(checklist["missing_plates"]))
        checklist["missing_cutouts"] = sorted(list(checklist["missing_cutouts"]))
        return checklist

    def _check_crop_softness(self, plate_path: Path, shot: Shot, checklist: Dict[str, Any]) -> None:
        """Cảnh báo khi độ phân giải vùng crop bị phóng > 1.5x so với khung 1920x1080."""
        try:
            with Image.open(plate_path) as im:
                plate_w, plate_h = im.size
        except Exception:
            return

        # Tỉ lệ crop theo cỡ cảnh:
        crop_ratios = {
            "wide": 1.0,
            "medium": 0.70,
            "closeup": 0.45,
            "extreme_closeup": 0.30,
            "over_shoulder": 0.55,
        }
        st_val = shot.shot_type.value if hasattr(shot.shot_type, "value") else str(shot.shot_type)
        ratio = crop_ratios.get(st_val, 1.0)
        crop_effective_w = plate_w * ratio

        # Nếu vùng crop nhỏ hơn 1920 / 1.5 = 1280px thì phóng lên sẽ bị vỡ/mềm
        if crop_effective_w < (1920 / 1.5):
            scale_factor = round(1920 / max(1, crop_effective_w), 2)
            warn = (
                f"[CẢNH BÁO MỀM ẢNH] Cảnh {shot.shot_id} ({st_val}): "
                f"Plate {plate_w}x{plate_h} crop {int(ratio*100)}% ({int(crop_effective_w)}px) "
                f"bị phóng {scale_factor}x (> 1.5x) để lấp khung 1080p. Khuyến nghị dùng plate 4K (>=3840px) hoặc ảnh riêng."
            )
            checklist["warnings"].append(warn)
