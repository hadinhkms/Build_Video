import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.models import CharacterDNA, EnvironmentAnchor, SpatialAnchors, Shot, Storyboard, ShotStatus, NarrativeAct
from src.core.state_manager import StateManager

class TestPhase0Contracts(unittest.TestCase):
    def test_character_dna_contract(self):
        char = CharacterDNA(
            id="char_01",
            name="Nam",
            dna_prompt="28yo Vietnamese man",
            fixed_wardrobe="olive canvas jacket"
        )
        self.assertEqual(char.name, "Nam")
        self.assertEqual(char.fixed_wardrobe, "olive canvas jacket")

    def test_environment_anchor_contract(self):
        env = EnvironmentAnchor(
            id="env_01",
            name="Living Room",
            spatial_anchors=SpatialAnchors(left="window", center="sofa"),
            lighting="Rembrandt",
            weather="rainy",
            camera_profile="Arri Alexa"
        )
        self.assertEqual(env.spatial_anchors.left, "window")

    def test_storyboard_state_manager(self):
        test_state_file = "output/test_state.json"
        mgr = StateManager(state_file_path=test_state_file)

        shot1 = Shot(
            shot_id="shot_00_hook",
            narrative_act=NarrativeAct.HOOK,
            voiceover="Câu thoại mở đầu bí ẩn",
            action="looking shocked",
            duration=5.0
        )
        sb = Storyboard(chapter_id="chap_test", shots=[shot1], total_duration=5.0)

        mgr.save_state(sb)
        loaded = mgr.load_state()

        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded.shots), 1)
        self.assertEqual(loaded.shots[0].shot_id, "shot_00_hook")

        # Test status update
        mgr.update_shot_status("shot_00_hook", ShotStatus.AUDIO_READY, audio_file="test.mp3")
        reloaded = mgr.load_state()
        self.assertEqual(reloaded.shots[0].status, ShotStatus.AUDIO_READY)
        self.assertEqual(reloaded.shots[0].audio_file, "test.mp3")

        if os.path.exists(test_state_file):
            os.remove(test_state_file)

if __name__ == "__main__":
    unittest.main()
