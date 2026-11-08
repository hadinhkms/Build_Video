import unittest
from src.export.clip_fit import plan_clip_fit


class TestClipFit(unittest.TestCase):
    def test_case_1_clip_longer_or_equal(self):
        # Clip 6s, cảnh 5s -> playbackRate = 1.0, freeze = None, loop = False
        fit = plan_clip_fit(clip_duration_sec=6.0, scene_duration_sec=5.0)
        self.assertEqual(fit.playback_rate, 1.0)
        self.assertIsNone(fit.freeze_at_frame)
        self.assertFalse(fit.loop)

        # Clip bằng cảnh
        fit_equal = plan_clip_fit(clip_duration_sec=5.0, scene_duration_sec=5.0)
        self.assertEqual(fit_equal.playback_rate, 1.0)
        self.assertIsNone(fit_equal.freeze_at_frame)
        self.assertFalse(fit_equal.loop)

    def test_case_2_clip_slowdown_within_threshold(self):
        # Cảnh 5s, clip 4.5s (4.5 / 5 = 0.9 >= 0.8) -> chậm lại
        fit = plan_clip_fit(clip_duration_sec=4.5, scene_duration_sec=5.0, min_ratio=0.8)
        self.assertAlmostEqual(fit.playback_rate, 0.9, places=4)
        self.assertIsNone(fit.freeze_at_frame)
        self.assertFalse(fit.loop)

        # Đúng ngưỡng 0.8 (4.0s / 5.0s = 0.8)
        fit_exact = plan_clip_fit(clip_duration_sec=4.0, scene_duration_sec=5.0, min_ratio=0.8)
        self.assertAlmostEqual(fit_exact.playback_rate, 0.8, places=4)
        self.assertIsNone(fit_exact.freeze_at_frame)
        self.assertFalse(fit_exact.loop)

    def test_case_3_clip_short_freeze_last_frame(self):
        # Cảnh 6s, clip 3s (3.0 / 6.0 = 0.5 < 0.8), file thường -> freeze ở frame cuối
        # Ở 24 fps: 3.0 * 24 = 72 khung hình (0..71), frame cuối là 71
        fit = plan_clip_fit(clip_duration_sec=3.0, scene_duration_sec=6.0, min_ratio=0.8, is_loop=False, fps=24)
        self.assertEqual(fit.playback_rate, 1.0)
        self.assertEqual(fit.freeze_at_frame, 71)
        self.assertFalse(fit.loop)

    def test_case_4_clip_short_idle_loop(self):
        # Cảnh 6s, clip 3s, is_loop = True -> loop = True
        fit = plan_clip_fit(clip_duration_sec=3.0, scene_duration_sec=6.0, min_ratio=0.8, is_loop=True, fps=24)
        self.assertEqual(fit.playback_rate, 1.0)
        self.assertIsNone(fit.freeze_at_frame)
        self.assertTrue(fit.loop)

    def test_invalid_durations_raise(self):
        with self.assertRaises(ValueError):
            plan_clip_fit(clip_duration_sec=-1.0, scene_duration_sec=5.0)
        with self.assertRaises(ValueError):
            plan_clip_fit(clip_duration_sec=5.0, scene_duration_sec=0.0)


if __name__ == "__main__":
    unittest.main()
