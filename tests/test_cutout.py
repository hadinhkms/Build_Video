import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from src.visuals.cutout import CutoutProcessor, REMBG_AVAILABLE


class TestCutout(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.processor = CutoutProcessor()

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_cutout_metadata_and_bottom_detection_synthetic(self):
        # 1. Tạo ảnh RGBA tổng hợp bị cắt ngang ở đáy (cut_bottom = True)
        # Kích thước 200x400: nửa trên là vòng tròn, nửa dưới là thân kéo dài chạm đáy
        w, h = 200, 400
        img_cut = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for y in range(100, h):
            for x in range(50, 150):
                img_cut.putpixel((x, y), (120, 100, 80, 255))

        cut_img_path = self.temp_dir / "test_cut.png"
        img_cut.save(cut_img_path)

        out_png = self.temp_dir / "out_cut.png"
        out_json = self.temp_dir / "out_cut.json"

        meta = self.processor.process_image(cut_img_path, out_png, out_json)

        self.assertTrue(out_png.exists())
        self.assertTrue(out_json.exists())
        self.assertTrue(meta["cut_bottom"], "Ảnh chạm đáy khung phải có cut_bottom = True")
        self.assertAlmostEqual(meta["face"]["x"], 0.50, places=2)
        self.assertAlmostEqual(meta["chest"]["y"], 0.42, places=2)
        self.assertIn("crop_box", meta)
        self.assertGreater(meta["crop_box"]["w"], 0)
        self.assertGreater(meta["crop_box"]["h"], 0)

        # 2. Tạo ảnh RGBA lơ lửng không chạm đáy (cut_bottom = False)
        img_float = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for y in range(100, 300):  # Không chạm đáy 400
            for x in range(50, 150):
                img_float.putpixel((x, y), (120, 100, 80, 255))

        float_img_path = self.temp_dir / "test_float.png"
        img_float.save(float_img_path)

        out_float_png = self.temp_dir / "out_float.png"
        out_float_json = self.temp_dir / "out_float.json"

        meta_float = self.processor.process_image(float_img_path, out_float_png, out_float_json)
        self.assertFalse(meta_float["cut_bottom"], "Ảnh không chạm đáy phải có cut_bottom = False")


if __name__ == "__main__":
    unittest.main()
