import json
import shutil
import tempfile
import unittest
from pathlib import Path

from src.core.models import NarrativeAct, RenderProps, Scene, Style, Visual, Effects
from src.packaging.youtube import YouTubePackager, generate_youtube_timestamps


class TestYouTubePackaging(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.packager = YouTubePackager(project_root=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_dummy_scene(self, scene_id: str, act: str, duration_frames: int) -> Scene:
        return Scene(
            id=scene_id,
            kind="story",
            act=act,
            raw_text="Câu thoại mẫu cho cảnh này.",
            voice_text="Câu thoại mẫu cho cảnh này.",
            speaker="narrator",
            is_dialogue=False,
            on_screen_character_id=None,
            environment_id="phong_khach",
            shot_type="medium",
            camera_motion="static",
            duration_in_frames=duration_frames,
            audio=None,
            words=[],
            captions=[],
            sfx=[],
            visual=Visual(
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
            ),
            effects=Effects(rain="off", rain_region=None, flicker=False),
            grade=None,
            mouth_envelope=None,
        )

    def test_short_video_returns_no_timestamps(self):
        # Video 25s: Hook 5s (120f), Setup 10s (240f), Climax 10s (240f) -> chỉ có 2 đoạn >= 10s sau khi gộp Hook
        scenes = [
            self._create_dummy_scene("s1", "HOOK", 120),    # 5s
            self._create_dummy_scene("s2", "SETUP", 240),   # 10s
            self._create_dummy_scene("s3", "CLIMAX", 240),  # 10s
        ]
        # Sau khi gộp: Hook(5s) + Setup(10s) = 15s; Climax = 10s -> chỉ có 2 đoạn -> Không đủ 3 đoạn -> Trả về None
        ts = generate_youtube_timestamps(scenes, fps=24)
        self.assertIsNone(ts, "Video không đủ 3 chapters >= 10s phải trả về None")

    def test_valid_video_generates_correct_timestamps(self):
        # Video 60s: Hook 15s, Setup 15s, Rising 15s, Climax 15s
        scenes = [
            self._create_dummy_scene("s1", "HOOK", 360),    # 15s
            self._create_dummy_scene("s2", "SETUP", 360),   # 15s
            self._create_dummy_scene("s3", "RISING", 360),  # 15s
            self._create_dummy_scene("s4", "CLIMAX", 360),  # 15s
        ]
        ts = generate_youtube_timestamps(scenes, fps=24)
        self.assertIsNotNone(ts)
        self.assertIn("00:00", ts)
        lines = ts.strip().split("\n")
        # Dòng đầu là tiêu đề mốc, sau đó có ít nhất 3 dòng timestamps
        self.assertGreaterEqual(len(lines), 4)

    def test_generate_metadata_structure(self):
        scenes = [
            self._create_dummy_scene("s1", "HOOK", 360),
            self._create_dummy_scene("s2", "SETUP", 360),
            self._create_dummy_scene("s3", "CLIMAX", 360),
        ]
        props = RenderProps(
            schema_version=1,
            chapter_id="chap_01",
            title="Đêm Mưa Kinh Hoàng",
            fps=24,
            width=1920,
            height=1080,
            scenes=scenes,
            ambience=[],
            bgm=None,
            style=Style(subtitles=True, letterbox_ratio=2.39, grain=True),
        )

        out_json = self.test_dir / "youtube_metadata.json"
        meta = self.packager.generate_metadata(props, output_path=out_json)

        self.assertTrue(out_json.exists())
        self.assertLessEqual(len(meta["title"]), 70)
        self.assertGreaterEqual(len(meta["tags"]), 10)
        self.assertIn("thumbnail", meta)
        self.assertTrue(meta["has_timestamps"])


if __name__ == "__main__":
    unittest.main()
