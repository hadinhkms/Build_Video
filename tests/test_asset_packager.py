import json
import shutil
import tempfile
import unittest
from pathlib import Path

from src.visuals.asset_packager import AssetPackager


class TestAssetPackager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_dir = self.temp_dir / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Mock environments.json
        env_data = {
            "environments": {
                "test_room": {
                    "id": "env_01",
                    "name": "Phòng thử nghiệm",
                    "spatial_anchors": {
                        "left": "big glass window with rainy drops",
                        "center": "wooden table",
                        "right": "tall floor lamp",
                        "background": "dark wall with vintage books",
                    },
                    "lighting": "dramatic tungsten contrast with blue ambient",
                    "camera_profile": "35mm anamorphic, Arri Alexa",
                    "weather": "midnight rain",
                }
            }
        }
        with open(self.config_dir / "environments.json", "w", encoding="utf-8") as f:
            json.dump(env_data, f)

        # Mock characters.json
        char_data = {
            "characters": {
                "nam_chinh": {
                    "id": "char_01",
                    "name": "Nam",
                    "role": "Nhân vật chính",
                    "dna_prompt": "Vietnamese man in his 20s, sharp jawline, short black hair",
                    "fixed_wardrobe": "dark olive jacket over black t-shirt",
                    "forbidden_traits": "no anime, no plastic smooth skin",
                    "face_reference_image": "assets/characters/ref.jpg",
                }
            }
        }
        with open(self.config_dir / "characters.json", "w", encoding="utf-8") as f:
            json.dump(char_data, f)

        self.packager = AssetPackager(config_dir=self.config_dir, base_dir=self.temp_dir)

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_export_package_structure_and_prompts(self):
        pkg_dir = self.packager.export_package("test_chapter", output_root=self.temp_dir / "packages")
        self.assertTrue(pkg_dir.exists())

        # 1. README.md
        readme_file = pkg_dir / "README.md"
        self.assertTrue(readme_file.exists())
        with open(readme_file, "r", encoding="utf-8") as f:
            readme_text = f.read()
        self.assertIn("GÓI TẠO TÀI SẢN HÌNH ẢNH", readme_text)
        self.assertIn("test_chapter", readme_text)

        # 2. Plate prompt
        plate_prompt_file = pkg_dir / "environments" / "test_room" / "plate_prompt.txt"
        self.assertTrue(plate_prompt_file.exists())
        with open(plate_prompt_file, "r", encoding="utf-8") as f:
            plate_prompt = f.read().lower()

        # Bắt buộc: có đủ anchors và có "no people"
        self.assertIn("left: big glass window with rainy drops", plate_prompt)
        self.assertIn("center: wooden table", plate_prompt)
        self.assertIn("right: tall floor lamp", plate_prompt)
        self.assertIn("background: dark wall with vintage books", plate_prompt)
        self.assertIn("no people", plate_prompt)
        self.assertIn("empty room", plate_prompt)

        # 3. Character prompt
        char_prompt_file = pkg_dir / "characters" / "nam_chinh" / "base_prompt.txt"
        self.assertTrue(char_prompt_file.exists())
        with open(char_prompt_file, "r", encoding="utf-8") as f:
            char_prompt = f.read()

        self.assertIn("Vietnamese man in his 20s", char_prompt)
        self.assertIn("dark olive jacket over black t-shirt", char_prompt)
        self.assertIn("half-body, front-facing, neutral expression", char_prompt)
        self.assertIn("no anime, no plastic smooth skin", char_prompt)
        self.assertIn("assets/characters/ref.jpg", char_prompt)


if __name__ == "__main__":
    unittest.main()
