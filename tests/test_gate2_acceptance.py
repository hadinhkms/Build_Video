import json
import os
import unittest
from pathlib import Path

from src.core.models import NarrativeAct, RenderProps, ShotKind, ShotType, Storyboard


class TestGate2Acceptance(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent
        self.output_dir = self.root / "output" / "sample_chapter"
        self.props_path = self.output_dir / "render_props.json"
        self.storyboard_path = self.output_dir / "storyboard.json"

    def test_gate2_data_contract_and_props_configuration(self):
        """Tiêu chí 1 & 3: Props tuân thủ schema và chứa đầy đủ style, effects, grade."""
        self.assertTrue(self.props_path.exists(), f"Props file does not exist: {self.props_path}")
        with open(self.props_path, "r", encoding="utf-8") as f:
            content = f.read()

        props = RenderProps.model_validate_json(content, by_name=False)
        self.assertEqual(props.schema_version, 1)

        # Style cấp gốc
        self.assertIsNotNone(props.style)
        self.assertIsInstance(props.style.subtitles, bool)
        self.assertIsInstance(props.style.grain, bool)
        if props.style.letterbox_ratio is not None:
            self.assertGreater(props.style.letterbox_ratio, 0)

        # Effects & Grade cấp cảnh
        for sc in props.scenes:
            self.assertIsNotNone(sc.effects)
            self.assertIn(sc.effects.rain, ["window", "full", "off"])
            if sc.effects.rain == "window":
                self.assertIsNotNone(sc.effects.rain_region)
                self.assertGreater(sc.effects.rain_region.w, 0)
                self.assertGreater(sc.effects.rain_region.h, 0)
            else:
                self.assertIsNone(sc.effects.rain_region)

            self.assertIsInstance(sc.effects.flicker, bool)

    def test_gate2_raccord_plate_consistency(self):
        """Tiêu chí: Mọi cảnh layered cùng environmentId phải dùng cùng backgroundSrc."""
        with open(self.props_path, "r", encoding="utf-8") as f:
            props_data = json.load(f)

        env_to_plate = {}
        for sc in props_data["scenes"]:
            visual = sc.get("visual", {})
            if visual.get("mode") == "layered":
                env_id = sc["environmentId"]
                bg_src = visual.get("backgroundSrc")
                self.assertIsNotNone(bg_src, f"Cảnh layered {sc['id']} không được có backgroundSrc null")
                if env_id in env_to_plate:
                    self.assertEqual(
                        env_to_plate[env_id],
                        bg_src,
                        f"Raccord vi phạm: cảnh {sc['id']} có plate khác với các cảnh cùng bối cảnh {env_id}",
                    )
                else:
                    env_to_plate[env_id] = bg_src

    def test_gate2_no_consecutive_same_shot_types_after_downgrade(self):
        """Tiêu chí 2: Sau khi asset_check và exporter chạy, không có 2 cảnh story liền nhau cùng cỡ cảnh."""
        with open(self.props_path, "r", encoding="utf-8") as f:
            props_data = json.load(f)

        story_scenes = [sc for sc in props_data["scenes"] if sc.get("kind") == "story"]
        for i in range(len(story_scenes) - 1):
            s1 = story_scenes[i]
            s2 = story_scenes[i + 1]
            self.assertNotEqual(
                s1["shotType"],
                s2["shotType"],
                f"Trùng cỡ cảnh liên tiếp: cảnh {s1['id']} ({s1['shotType']}) và {s2['id']} ({s2['shotType']})",
            )

    def test_gate2_captions_invariants(self):
        """Tiêu chí 4: Phụ đề tối đa 6 từ, tối đa 42 ký tự, highlight đúng cấu trúc."""
        with open(self.props_path, "r", encoding="utf-8") as f:
            props_data = json.load(f)

        for sc in props_data["scenes"]:
            captions = sc.get("captions", [])
            for cap in captions:
                words = cap["text"].split()
                self.assertLessEqual(len(words), 6, f"Phụ đề vượt quá 6 từ: {cap['text']}")
                self.assertLessEqual(len(cap["text"]), 42, f"Phụ đề vượt quá 42 ký tự: {cap['text']}")
                self.assertLessEqual(cap["start"], cap["end"])
                self.assertIsInstance(cap.get("highlight", []), list)

    def test_gate2_no_slow_css_filters(self):
        """Tiêu chí 9: Code Remotion không dùng backdrop-blur hay backdrop-filter vì làm chậm render."""
        remotion_src = self.root / "remotion" / "src"
        for tsx_file in remotion_src.rglob("*.tsx"):
            with open(tsx_file, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertNotIn("backdrop-blur", content, f"File {tsx_file.name} chứa backdrop-blur (cấm ở Gate 2)")
            self.assertNotIn("backdrop-filter", content, f"File {tsx_file.name} chứa backdrop-filter (cấm ở Gate 2)")


if __name__ == "__main__":
    unittest.main()
