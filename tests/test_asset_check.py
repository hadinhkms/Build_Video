import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from src.core.models import NarrativeAct, Shot, ShotKind, ShotType, Storyboard
from src.visuals.asset_check import AssetChecker


class TestAssetCheck(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_dir = self.temp_dir / "config"
        self.assets_dir = self.temp_dir / "assets"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)

        # Mock environments.json
        env_data = {
            "environments": {
                "room_01": {
                    "id": "env_01",
                    "default_character_slot": "center",
                    "character_slots": {
                        "center": {"x": 0.5, "y": 0.90, "height": 0.62}  # y < 1.0 cố tình lỗi slot
                    },
                }
            }
        }
        with open(self.config_dir / "environments.json", "w", encoding="utf-8") as f:
            json.dump(env_data, f)

        # Mock characters.json
        char_data = {
            "characters": {
                "nam_01": {"id": "char_01", "name": "Nam"}
            }
        }
        with open(self.config_dir / "characters.json", "w", encoding="utf-8") as f:
            json.dump(char_data, f)

        self.checker = AssetChecker(base_dir=self.temp_dir, config_dir=self.config_dir)

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_downgrade_over_shoulder_raccord(self):
        # Case 1: medium -> over_shoulder -> medium  => hạ thành closeup
        sb1 = Storyboard(
            chapter_id="test",
            title="Test",
            shots=[
                Shot(shot_id="s1", kind=ShotKind.STORY, narrative_act=NarrativeAct.SETUP, shot_type="medium"),
                Shot(shot_id="s2", kind=ShotKind.STORY, narrative_act=NarrativeAct.SETUP, shot_type="over_shoulder"),
                Shot(shot_id="s3", kind=ShotKind.STORY, narrative_act=NarrativeAct.SETUP, shot_type="medium"),
            ],
        )
        logs = self.checker.downgrade_over_shoulder_shots(sb1)
        self.assertEqual(len(logs), 1)
        self.assertEqual(sb1.shots[1].shot_type, "closeup")

        # Case 2: medium -> over_shoulder -> closeup => hạ thành wide
        sb2 = Storyboard(
            chapter_id="test",
            title="Test",
            shots=[
                Shot(shot_id="s1", kind=ShotKind.STORY, narrative_act=NarrativeAct.SETUP, shot_type="medium"),
                Shot(shot_id="s2", kind=ShotKind.STORY, narrative_act=NarrativeAct.SETUP, shot_type="over_shoulder"),
                Shot(shot_id="s3", kind=ShotKind.STORY, narrative_act=NarrativeAct.SETUP, shot_type="closeup"),
            ],
        )
        self.checker.downgrade_over_shoulder_shots(sb2)
        self.assertEqual(sb2.shots[1].shot_type, "wide")

    def test_slot_cut_bottom_warning(self):
        # Tạo plate và cutout có cut_bottom = True
        plate_dir = self.assets_dir / "environments" / "room_01"
        plate_dir.mkdir(parents=True, exist_ok=True)
        img_plate = Image.new("RGB", (1920, 1080), (30, 30, 30))
        img_plate.save(plate_dir / "plate.png")

        char_dir = self.assets_dir / "characters" / "nam_01"
        char_dir.mkdir(parents=True, exist_ok=True)
        img_cut = Image.new("RGBA", (100, 200), (100, 100, 100, 255))
        img_cut.save(char_dir / "base_cutout.png")
        with open(char_dir / "base_cutout.json", "w", encoding="utf-8") as f:
            json.dump({"cut_bottom": True, "aspect": 0.5}, f)

        sb = Storyboard(
            chapter_id="test",
            title="Test",
            shots=[
                Shot(
                    shot_id="s1",
                    kind=ShotKind.STORY,
                    narrative_act=NarrativeAct.SETUP,
                    environment_id="room_01",
                    on_screen_character_id="nam_01",
                    shot_type="medium",
                )
            ],
        )

        res = self.checker.check_and_assign_visuals(sb)
        self.assertEqual(res["stats"]["layered"], 1)
        # Vì slot.y = 0.90 < 1.0 nên phải có warning [LỖI SLOT]
        slot_warnings = [w for w in res["warnings"] if "[LỖI SLOT]" in w]
        self.assertGreater(len(slot_warnings), 0)


if __name__ == "__main__":
    unittest.main()
