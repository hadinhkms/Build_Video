import shutil
import tempfile
import unittest
import wave
from pathlib import Path
import numpy as np

from src.core.models import Shot, ShotKind, Storyboard
from src.visuals.asset_packager import AssetPackager


class TestHybridPackager(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.packager = AssetPackager(base_dir=self.test_dir)

        # Tạo file audio mẫu
        self.audio_dir = self.test_dir / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.audio_file = self.audio_dir / "sample.wav"
        samples = (np.sin(np.linspace(0, 10, 16000)) * 32767).astype(np.int16)
        with wave.open(str(self.audio_file), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(samples.tobytes())

        # Tạo ảnh mẫu
        self.images_dir = self.test_dir / "assets" / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        with open(self.images_dir / "shot_01.jpg", "wb") as f:
            f.write(b"\xFF\xD8\xFF\xE0\x00\x10JFIF")

        self.storyboard = Storyboard(
            chapter_id="test_chapter",
            title="Chương test",
            shots=[
                Shot(
                    shot_id="shot_01",
                    kind=ShotKind.STORY,
                    action="Nhân vật nhìn ra cửa sổ trong đêm mưa",
                    camera_motion="zoom_in",
                    duration_frames=72,
                    audio_file=str(self.audio_file),
                    audio_start_in_file_sec=0.0,
                ),
                Shot(
                    shot_id="title_shot",
                    kind=ShotKind.TITLE_CARD,
                    action="Hiển thị tiêu đề",
                    duration_frames=48,
                ),
            ],
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_export_hybrid_package(self):
        pkg_dir = self.packager.export_hybrid_package(
            storyboard=self.storyboard,
            chapter_id="test_chapter",
            output_root=self.test_dir / "packages",
            fps=24,
        )

        shot_dir = pkg_dir / "shot_01"
        self.assertTrue(shot_dir.exists())

        # 1. image.png
        self.assertTrue((shot_dir / "image.png").exists())

        # 2. voice.wav
        self.assertTrue((shot_dir / "voice.wav").exists())

        # 3. motion_prompt.txt
        motion_p = shot_dir / "motion_prompt.txt"
        self.assertTrue(motion_p.exists())
        with open(motion_p, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Nhân vật nhìn ra cửa sổ", content)
            self.assertIn("zoom_in", content)

        # 4. README.txt
        readme_p = shot_dir / "README.txt"
        self.assertTrue(readme_p.exists())
        with open(readme_p, "r", encoding="utf-8") as f:
            readme_text = f.read()
            self.assertIn("3.0 giây", readme_text)  # 72 frames @ 24 fps = 3.0s
            self.assertIn("16:9", readme_text)
            self.assertIn("input/rendered_clips/shot_01.mp4", readme_text)

        # Title card không được xuất trong shots/
        self.assertFalse((pkg_dir / "title_shot").exists())


if __name__ == "__main__":
    unittest.main()
