import json
import shutil
import tempfile
import unittest
from pathlib import Path

from src.audio.envelope import AudioEnvelopeCalculator, compute_shot_envelope
from src.core.models import NarrativeAct, RenderProps, Shot, ShotKind, Storyboard
from src.export.clip_fit import plan_clip_fit
from src.export.remotion_props import RemotionPropsExporter
from src.visuals.face_rig import FaceRigProcessor


class TestGate3Acceptance(unittest.TestCase):
    """Bộ kiểm thử nghiệm thu Gate 3: Diễn xuất 2.5D & Khe cắm Hybrid Video."""

    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent
        self.temp_dir = Path(tempfile.mkdtemp())
        self.sample_props_path = self.root / "output" / "sample_chapter" / "render_props.json"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_criterion_1_character_life_parameters(self):
        """Tiêu chí 1: Nhịp thở và chuyển động đầu tất định, biên độ an toàn."""
        # Life system đã được kiểm thử chi tiết trong vitest (life.test.ts).
        # Tại đây kiểm tra tính sẵn sàng của schema và cấu trúc component
        life_ts = self.root / "remotion" / "src" / "lib" / "life.ts"
        self.assertTrue(life_ts.exists())
        with open(life_ts, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("breathScale", content)
            self.assertIn("blinkAmount", content)
            self.assertIn("headDrift", content)
            self.assertIn("0.008", content)  # Biên độ thở <= 0.8%

    def test_criterion_2_no_uncanny_simulation(self):
        """Tiêu chí 2: Không có biến thể thì không vẽ patch giả lập nào, không lỗi."""
        # Trong chương mẫu, nhân vật chính không có ảnh eyes_closed.png / mouth_open.png
        self.assertTrue(self.sample_props_path.exists())
        with open(self.sample_props_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        props = RenderProps.model_validate(data)
        for scene in props.scenes:
            if scene.kind == "story" and scene.visual.mode == "layered":
                # Nếu không có file biến thể, face_rig phải là None hoặc có các patch null
                if scene.visual.face_rig:
                    self.assertIsNone(scene.visual.face_rig.eyes_patch_src)
                    self.assertIsNone(scene.visual.face_rig.mouth_patch_src)

    def test_criterion_3_mouth_envelope_rules(self):
        """Tiêu chí 3: Cảnh lời dẫn không có envelope. Cảnh thoại có envelope chuẩn hóa."""
        self.assertTrue(self.sample_props_path.exists())
        with open(self.sample_props_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        props = RenderProps.model_validate(data)
        # Toàn bộ chương mẫu là lời dẫn -> 0 cảnh có mouthEnvelope
        for scene in props.scenes:
            self.assertIsNone(scene.mouth_envelope, f"Scene {scene.id} là lời dẫn nhưng lại có mouth_envelope")

        # Kiểm tra giả lập cảnh thoại
        dummy_audio = self.root / "tests" / "fixtures" / "sample_chapter" / "shot_01.mp3"
        if dummy_audio.exists():
            env = compute_shot_envelope(
                audio_path=dummy_audio,
                start_in_file_sec=0.0,
                duration_in_frames=48,
                is_dialogue=True,
                speaker="nhan_vat_chinh",
                on_screen_character_id="nhan_vat_chinh",
                fps=24,
            )
            self.assertIsNotNone(env)
            self.assertEqual(len(env), 48)
            self.assertTrue(all(0.0 <= v <= 1.0 for v in env))

    def test_criterion_4_hybrid_clip_fit_policy(self):
        """Tiêu chí 4: Khớp thời lượng clip 5s vào cảnh 6s -> chậm lại hoặc freeze, không đổi thời lượng."""
        # 1. Clip 5s vào cảnh 6s (5.0 / 6.0 = 0.833 >= 0.8) -> Làm chậm lại
        fit_slow = plan_clip_fit(clip_duration_sec=5.0, scene_duration_sec=6.0, min_ratio=0.8)
        self.assertEqual(fit_slow.playback_rate, 0.8333)
        self.assertIsNone(fit_slow.freeze_at_frame)
        self.assertFalse(fit_slow.loop)

        # 2. Clip 3s vào cảnh 6s (3.0 / 6.0 = 0.5 < 0.8), file thường -> Freeze frame cuối
        fit_freeze = plan_clip_fit(clip_duration_sec=3.0, scene_duration_sec=6.0, min_ratio=0.8, is_loop=False, fps=24)
        self.assertEqual(fit_freeze.playback_rate, 1.0)
        self.assertEqual(fit_freeze.freeze_at_frame, 71)

        # 3. Clip 3s vào cảnh 6s, file .loop.mp4 -> Loop
        fit_loop = plan_clip_fit(clip_duration_sec=3.0, scene_duration_sec=6.0, min_ratio=0.8, is_loop=True, fps=24)
        self.assertEqual(fit_loop.playback_rate, 1.0)
        self.assertTrue(fit_loop.loop)

    def test_criterion_5_performance_regression_gate(self):
        """Tiêu chí 5: So sánh bench_p3.json với bench_p2.json, fps_render giảm không quá 20%."""
        bench_p2_path = self.root / "output" / "sample_chapter" / "bench_p2.json"
        bench_p3_path = self.root / "output" / "sample_chapter" / "bench_p3.json"

        if not bench_p2_path.exists():
            self.skipTest("bench_p2.json chưa tồn tại (chưa chạy benchmark Phase 2)")

        if not bench_p3_path.exists():
            # Nếu chưa chạy bench p3 thì chỉ log thông tin
            return

        with open(bench_p2_path, "r", encoding="utf-8") as f:
            b2 = json.load(f)
        with open(bench_p3_path, "r", encoding="utf-8") as f:
            b3 = json.load(f)

        fps_p2 = b2.get("fps_render", 5.0)
        fps_p3 = b3.get("fps_render", 5.0)

        # fps_p3 >= 0.8 * fps_p2 (không giảm quá 20%)
        min_allowed_fps = 0.8 * fps_p2
        self.assertGreaterEqual(
            fps_p3,
            min_allowed_fps,
            f"Hiệu năng Phase 3 giảm quá 20%: P2={fps_p2:.2f} fps, P3={fps_p3:.2f} fps (Tối thiểu={min_allowed_fps:.2f} fps)",
        )


if __name__ == "__main__":
    unittest.main()
