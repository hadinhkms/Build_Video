import json
import shutil
import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np

from src.core.models import FaceRig
from src.visuals.face_rig import FaceRigProcessor


class TestFaceRig(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.processor = FaceRigProcessor(ssim_threshold=0.95, feather_radius=4)

        # Tạo ảnh base tổng hợp (200x200)
        # Nền xám, có hình tròn đầu (tâm 100, 100, r=60)
        self.base_img = np.ones((200, 200, 3), dtype=np.uint8) * 180
        # Khuôn mặt
        cv2.circle(self.base_img, (100, 100), 60, (220, 200, 180), -1)
        # Mắt mở (vẽ 2 điểm đen ở y=85, x=80 và x=120)
        cv2.circle(self.base_img, (80, 85), 6, (30, 30, 30), -1)
        cv2.circle(self.base_img, (120, 85), 6, (30, 30, 30), -1)
        # Miệng ngậm (đường kẻ ngang ở y=130, x=85..115)
        cv2.line(self.base_img, (85, 130), (115, 130), (50, 50, 150), 2)

        self.base_path = self.test_dir / "base.png"
        cv2.imwrite(str(self.base_path), self.base_img)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_eyes_closed_variant_success(self):
        # Tạo ảnh biến thể: chỉ vùng mắt đổi thành đường cong nhắm mắt
        var_img = self.base_img.copy()
        # Xóa mắt mở
        cv2.circle(var_img, (80, 85), 6, (220, 200, 180), -1)
        cv2.circle(var_img, (120, 85), 6, (220, 200, 180), -1)
        # Vẽ mắt nhắm (2 cung cong)
        cv2.ellipse(var_img, (80, 87), (6, 3), 0, 0, 180, (40, 40, 40), 2)
        cv2.ellipse(var_img, (120, 87), (6, 3), 0, 0, 180, (40, 40, 40), 2)

        var_path = self.test_dir / "eyes_closed.png"
        cv2.imwrite(str(var_path), var_img)

        res = self.processor.process_variant(
            base_path=self.base_path,
            variant_path=var_path,
            feature_type="eyes",
            output_dir=self.test_dir,
        )

        self.assertIsNotNone(res, "Eyes variant should be accepted")
        self.assertEqual(res["feature"], "eyes")
        self.assertTrue(Path(res["patch_path"]).exists())

        # Kiểm tra mask alpha mờ biên (4 kênh RGBA)
        patch_rgba = cv2.imread(str(res["patch_path"]), cv2.IMREAD_UNCHANGED)
        self.assertEqual(patch_rgba.shape[2], 4, "Patch must be RGBA")
        # Biên ngoài cùng của patch phải có alpha thấp/bằng 0 do mờ biên
        self.assertLess(patch_rgba[0, 0, 3], 200)

        # Kiểm tra tọa độ rect
        rect = res["rect"]
        self.assertGreaterEqual(rect["x"], 0.0)
        self.assertLessEqual(rect["x"] + rect["w"], 1.0)
        self.assertGreaterEqual(rect["y"], 0.0)
        self.assertLessEqual(rect["y"] + rect["h"], 1.0)

    def test_repainted_variant_rejected_by_ssim(self):
        # Biến thể bị AI vẽ lại toàn bộ ảnh (thêm nhiễu ngẫu nhiên khắp nơi)
        noisy_var = self.base_img.copy().astype(np.int16)
        noise = np.random.randint(-30, 30, noisy_var.shape)
        noisy_var = np.clip(noisy_var + noise, 0, 255).astype(np.uint8)

        var_path = self.test_dir / "eyes_repainted.png"
        cv2.imwrite(str(var_path), noisy_var)

        res = self.processor.process_variant(
            base_path=self.base_path,
            variant_path=var_path,
            feature_type="eyes",
            output_dir=self.test_dir,
        )

        self.assertIsNone(res, "Repainted variant must be rejected due to low SSIM")

    def test_rig_character_pipeline(self):
        # Đặt eyes_closed và mouth_open vào thư mục nhân vật
        var_eyes = self.base_img.copy()
        cv2.circle(var_eyes, (80, 85), 6, (220, 200, 180), -1)
        cv2.circle(var_eyes, (120, 85), 6, (220, 200, 180), -1)
        cv2.imwrite(str(self.test_dir / "eyes_closed.png"), var_eyes)

        var_mouth = self.base_img.copy()
        cv2.circle(var_mouth, (100, 130), 8, (60, 20, 20), -1)  # Miệng mở tròn
        cv2.imwrite(str(self.test_dir / "mouth_open.png"), var_mouth)

        # Viết base_cutout.json
        with open(self.test_dir / "base_cutout.json", "w", encoding="utf-8") as f:
            json.dump({"crop_box": {"x": 20, "y": 20, "w": 160, "h": 160}}, f)

        rig = self.processor.rig_character(self.test_dir)
        self.assertIsNotNone(rig["eyes"])
        self.assertIsNotNone(rig["mouth"])
        self.assertIsNotNone(rig["eyesPatchSrc"])
        self.assertIsNotNone(rig["mouthPatchSrc"])

        # Kiểm tra tương thích với Pydantic FaceRig model
        model = FaceRig.model_validate(rig)
        self.assertIsNotNone(model.eyes)
        self.assertIsNotNone(model.mouth)


if __name__ == "__main__":
    unittest.main()
