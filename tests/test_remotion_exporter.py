import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from src.core.models import NarrativeAct, RenderProps, Shot, ShotKind, Storyboard
from src.export.remotion_props import RemotionPropsExporter
from src.visuals.visual_splitter import split_long_shot

class TestRemotionExporter(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent
        self.fixtures_dir = self.root / "tests" / "fixtures" / "sample_chapter"
        self.temp_out = Path(tempfile.mkdtemp())
        self.exporter = RemotionPropsExporter(project_root=str(self.root))

    def tearDown(self):
        if self.temp_out.exists():
            shutil.rmtree(self.temp_out)

    def test_exporter_generates_valid_props_from_sample_fixtures(self):
        # Tạo storyboard mẫu với 1 title_card, 1 shot thường, 2 shot con do visual split, 1 end_screen
        fps = 24
        shots = [
            Shot(
                shot_id="title_card",
                kind=ShotKind.TITLE_CARD,
                narrative_act=NarrativeAct.HOOK,
                raw_text="Chương 1: Đêm mưa",
                voice_text="",
                duration_frames=60,
                duration=2.5,
                shot_type="wide",
                camera_motion="static",
            ),
            Shot(
                shot_id="shot_01",
                kind=ShotKind.STORY,
                narrative_act=NarrativeAct.SETUP,
                raw_text="Cơn mưa cuối tháng Mười trút xuống mái hiên rầm rập.",
                voice_text="Cơn mưa cuối tháng Mười trút xuống mái hiên rầm rập.",
                duration_frames=130,
                duration=round(130 / 24, 4),
                audio_file=str(self.fixtures_dir / "shot_01.mp3"),
                shot_type="wide",
                camera_motion="zoom_out",
            ),
            Shot(
                shot_id="shot_03a",
                kind=ShotKind.STORY,
                parent_id="shot_03",
                narrative_act=NarrativeAct.RISING,
                raw_text="Ánh đèn vàng từ cây đèn góc phòng hắt lên nửa khuôn mặt trầm mặc của anh,",
                voice_text="Ánh đèn vàng từ cây đèn góc phòng hắt lên nửa khuôn mặt trầm mặc của anh,",
                duration_frames=89,
                duration=round(89 / 24, 4),
                audio_file=str(self.fixtures_dir / "shot_03.mp3"),
                audio_start_in_file_sec=0.0,
                shot_type="medium",
                camera_motion="zoom_in",
            ),
            Shot(
                shot_id="shot_03b",
                kind=ShotKind.STORY,
                parent_id="shot_03",
                narrative_act=NarrativeAct.RISING,
                raw_text="để lộ vết sẹo mờ nơi đuôi mắt phải.",
                voice_text="để lộ vết sẹo mờ nơi đuôi mắt phải.",
                duration_frames=88,
                duration=round(88 / 24, 4),
                audio_file=str(self.fixtures_dir / "shot_03.mp3"),
                audio_start_in_file_sec=round(89 / 24, 4),
                shot_type="over_shoulder",
                camera_motion="zoom_out",
            ),
            Shot(
                shot_id="end_screen",
                kind=ShotKind.END_SCREEN,
                narrative_act=NarrativeAct.CLIFFHANGER,
                raw_text="",
                voice_text="",
                duration_frames=240,
                duration=10.0,
                shot_type="wide",
                camera_motion="static",
            ),
        ]

        sb = Storyboard(chapter_id="test_chapter", title="Chương 1: Đêm mưa", shots=shots)
        settings = {
            "video": {"fps": 24, "width": 1920, "height": 1080},
            "visuals": {"title_card_sec": 2.5, "end_screen_sec": 10.0},
        }

        with open(self.fixtures_dir / "shot_01.words.json", "r", encoding="utf-8") as f:
            words_01 = json.load(f)
        with open(self.fixtures_dir / "shot_03.words.json", "r", encoding="utf-8") as f:
            words_03 = json.load(f)

        words_map = {
            "shot_01": words_01,
            "shot_03a": words_03[:17],
            "shot_03b": words_03[17:],
        }

        props = self.exporter.export(
            storyboard=sb,
            settings=settings,
            output_dir=self.temp_out,
            words_map=words_map,
        )

        # File json được sinh ra
        json_file = self.temp_out / "render_props.json"
        self.assertTrue(json_file.exists())

        # Validate lại file json
        with open(json_file, "r", encoding="utf-8") as f:
            content = f.read()
        validated = RenderProps.model_validate_json(content, by_name=False)
        self.assertEqual(validated.chapter_id, "test_chapter")
        self.assertEqual(len(validated.scenes), 5)

        # Kiểm tra frame nguyên và durationInFrames
        for sc in validated.scenes:
            self.assertIsInstance(sc.duration_in_frames, int)
            self.assertGreater(sc.duration_in_frames, 0)

        # Kiểm tra audio startInFileSec
        sc_03a = next(s for s in validated.scenes if s.id == "shot_03a")
        sc_03b = next(s for s in validated.scenes if s.id == "shot_03b")
        self.assertEqual(sc_03a.audio.start_in_file_sec, 0.0)
        self.assertEqual(sc_03b.audio.start_in_file_sec, round(89 / 24, 4))
        self.assertEqual(sc_03a.audio.src, sc_03b.audio.src)

if __name__ == "__main__":
    unittest.main()
