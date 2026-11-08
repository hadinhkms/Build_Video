import json
import unittest
from pathlib import Path

from src.audio.foley_planner import FoleyPlanner, db_to_linear
from src.core.models import NarrativeAct, Shot, ShotKind, Storyboard


class TestFoleyPlanner(unittest.TestCase):
    def setUp(self):
        self.planner = FoleyPlanner()

    def test_thunder_detected_on_tia_chop(self):
        # Câu 1 có "tia chớp": phải sinh SFX thunder
        shot = Shot(
            shot_id="shot_01",
            kind=ShotKind.STORY,
            narrative_act=NarrativeAct.SETUP,
            raw_text="Cơn mưa trút xuống mái hiên. Từng tia chớp xé toang bầu trời đêm.",
            duration_frames=130,
        )
        words = [
            {"text": "Cơn", "start": 0.1, "end": 0.3},
            {"text": "tia", "start": 1.5, "end": 1.8},
            {"text": "chớp", "start": 1.8, "end": 2.1},
        ]
        sfx_list = self.planner.plan_sfx_for_scene(shot, words)
        self.assertGreater(len(sfx_list), 0)
        self.assertIn("thunder", sfx_list[0].src)
        self.assertGreaterEqual(sfx_list[0].start_sec, 0.0)

    def test_chop_mat_excluded_no_thunder(self):
        # Câu 4 có "chớp mắt": bị exclude nên KHÔNG ĐƯỢC sinh SFX thunder
        shot = Shot(
            shot_id="shot_04",
            kind=ShotKind.STORY,
            narrative_act=NarrativeAct.CLIMAX,
            raw_text="Anh không hề chớp mắt, đôi con ngươi đen thẳm chỉ nhìn chằm chằm.",
            duration_frames=150,
        )
        words = [
            {"text": "Anh", "start": 0.1, "end": 0.3},
            {"text": "không", "start": 0.3, "end": 0.5},
            {"text": "hề", "start": 0.5, "end": 0.7},
            {"text": "chớp", "start": 0.7, "end": 0.9},
            {"text": "mắt,", "start": 0.9, "end": 1.1},
        ]
        sfx_list = self.planner.plan_sfx_for_scene(shot, words)
        # Không có SFX thunder nào
        thunder_sfx = [s for s in sfx_list if "thunder" in s.src]
        self.assertEqual(len(thunder_sfx), 0, "Câu có 'chớp mắt' không được sinh sấm!")

    def test_stable_file_selection_hash(self):
        # Kiểm tra hai lần gọi khác nhau luôn chọn cùng 1 file cho cùng 1 seed
        f1 = self.planner.select_file_stable(self.planner.foley_dir / "rain", "test_seed_123")
        f2 = self.planner.select_file_stable(self.planner.foley_dir / "rain", "test_seed_123")
        self.assertEqual(f1, f2)
        self.assertIsNotNone(f1)

    def test_ambience_continuous_for_same_environment(self):
        # 3 cảnh liên tiếp cùng bối cảnh phong_khach_dem_mua (weather: heavy midnight rain)
        shots = [
            Shot(
                shot_id="s1",
                kind=ShotKind.STORY,
                narrative_act=NarrativeAct.SETUP,
                environment_id="phong_khach_dem_mua",
                duration_frames=72,  # 3s
            ),
            Shot(
                shot_id="s2",
                kind=ShotKind.STORY,
                narrative_act=NarrativeAct.RISING,
                environment_id="phong_khach_dem_mua",
                duration_frames=96,  # 4s
            ),
            Shot(
                shot_id="s3",
                kind=ShotKind.STORY,
                narrative_act=NarrativeAct.CLIMAX,
                environment_id="phong_khach_dem_mua",
                duration_frames=120,  # 5s
            ),
        ]
        sb = Storyboard(chapter_id="test_amb", title="Test", shots=shots)
        amb_list = self.planner.plan_ambience(sb, fps=24)

        self.assertEqual(len(amb_list), 1, "Phải gộp thành 1 dải ambience duy nhất phủ cả 3 cảnh")
        amb = amb_list[0]
        self.assertIn("rain", amb.src)
        self.assertEqual(amb.start_sec, 0.0)
        self.assertEqual(amb.end_sec, 12.0)  # 3s + 4s + 5s = 12s
        self.assertEqual(amb.fade_sec, 1.5)

    def test_bgm_ducking_and_cliffhanger_cut(self):
        shots = [
            Shot(
                shot_id="s1",
                kind=ShotKind.STORY,
                narrative_act=NarrativeAct.SETUP,
                duration_frames=96,  # 4s (0s - 4s)
            ),
            Shot(
                shot_id="s2",
                kind=ShotKind.STORY,
                narrative_act=NarrativeAct.RISING,
                duration_frames=120,  # 5s (4s - 9s)
            ),
            Shot(
                shot_id="s3",
                kind=ShotKind.STORY,
                narrative_act=NarrativeAct.CLIFFHANGER,
                duration_frames=96,  # 4s (9s - 13s)
            ),
        ]
        words_map = {
            "s1": [{"text": "Alo", "start": 0.2, "end": 3.5}],
            "s2": [{"text": "Balo", "start": 0.5, "end": 4.2}],
            "s3": [{"text": "Hết", "start": 0.1, "end": 2.0}],
        }
        sb = Storyboard(chapter_id="test_bgm", title="Test", shots=shots)
        bgm = self.planner.plan_bgm(sb, words_map, fps=24)

        self.assertIsNotNone(bgm)
        self.assertIn("dark_ambient_drone", bgm.src)

        # cut_at_sec phải đúng thời điểm bắt đầu CLIFFHANGER (4s + 5s = 9.0s)
        self.assertEqual(bgm.cut_at_sec, 9.0)

        # duck_intervals phải bao gồm khoảng giọng nói
        self.assertGreater(len(bgm.duck_intervals), 0)
        # s1: voice 0.2s - 3.5s
        self.assertAlmostEqual(bgm.duck_intervals[0][0], 0.2, delta=0.01)

    def test_explicit_sfx_and_bgm_tags(self):
        shot_sfx = Shot(
            shot_id="s_tag",
            kind=ShotKind.STORY,
            narrative_act=NarrativeAct.RISING,
            raw_text="[SFX: thunder_rumble.mp3] Tiếng sấm vang lên.",
            duration_frames=100,
        )
        sfx_res = self.planner.plan_sfx_for_scene(shot_sfx, [])
        self.assertEqual(len(sfx_res), 1)
        self.assertIn("thunder_rumble.mp3", sfx_res[0].src)

        # [SFX: none]
        shot_none = Shot(
            shot_id="s_none",
            kind=ShotKind.STORY,
            narrative_act=NarrativeAct.RISING,
            raw_text="[SFX: none] Tia chớp xé toang bầu trời.",
            duration_frames=100,
        )
        sfx_none = self.planner.plan_sfx_for_scene(shot_none, [])
        self.assertEqual(len(sfx_none), 0)


if __name__ == "__main__":
    unittest.main()
