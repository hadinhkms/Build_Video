import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from src.render.encoder_probe import (
    clear_encoder_probe_cache,
    compute_max_parallel_nvenc,
    normalize_encoder_request,
    probe_encoder_capability,
)


class TestEncoderProbe(unittest.TestCase):
    def setUp(self):
        clear_encoder_probe_cache()

    def tearDown(self):
        clear_encoder_probe_cache()

    def test_normalize_encoder_request(self):
        self.assertEqual(normalize_encoder_request("auto"), "auto")
        self.assertEqual(normalize_encoder_request("NVENC"), "nvenc")
        self.assertEqual(normalize_encoder_request("h264_nvenc"), "nvenc")
        self.assertEqual(normalize_encoder_request("libx264"), "libx264")
        self.assertEqual(normalize_encoder_request("cpu"), "libx264")
        with self.assertRaises(ValueError):
            normalize_encoder_request("invalid_codec")

    def test_compute_max_parallel_nvenc_respects_vram_limits(self):
        self.assertEqual(compute_max_parallel_nvenc(4096), 3)
        self.assertEqual(compute_max_parallel_nvenc(2048), 3)
        self.assertEqual(compute_max_parallel_nvenc(0), 3)
        self.assertEqual(compute_max_parallel_nvenc(None), 3)
        self.assertEqual(compute_max_parallel_nvenc(8192), 4)
        self.assertEqual(compute_max_parallel_nvenc(24576), 4)

    def test_forced_libx264_skips_nvenc_live_test(self):
        with patch("src.render.encoder_probe._run_nvenc_live_test") as mock_live:
            cap = probe_encoder_capability(requested="libx264", force_refresh=True)
        mock_live.assert_not_called()
        self.assertEqual(cap.selected_encoder, "libx264")
        self.assertFalse(cap.nvenc_available)
        self.assertFalse(cap.supports_bframes)
        self.assertEqual(cap.max_parallel_nvenc, 0)
        self.assertEqual(cap.reason, "forced_libx264")

    def test_auto_selects_nvenc_with_bframes_on_turing(self):
        fake_dir = Path("C:/ffmpeg/bin")
        with patch("src.render.encoder_probe.find_system_ffmpeg_bin_dir", return_value=fake_dir), \
             patch("src.render.encoder_probe._run_nvenc_live_test", return_value=True) as mock_live:
            cap = probe_encoder_capability(requested="auto", vram_mb=4096, force_refresh=True)

        # Chỉ gọi 1 lần với bframes=2
        mock_live.assert_called_once()
        self.assertEqual(mock_live.call_args.kwargs.get("bframes"), 2)
        self.assertEqual(cap.selected_encoder, "h264_nvenc")
        self.assertTrue(cap.is_nvenc)
        self.assertTrue(cap.nvenc_available)
        self.assertTrue(cap.supports_bframes)
        self.assertEqual(cap.ffmpeg_bin_dir, fake_dir)
        self.assertEqual(cap.max_parallel_nvenc, 3)

    def test_auto_selects_nvenc_without_bframes_on_volta(self):
        fake_dir = Path("C:/ffmpeg/bin")

        def fake_live(exe, bframes, timeout_sec=3.0):
            return bframes == 0

        with patch("src.render.encoder_probe.find_system_ffmpeg_bin_dir", return_value=fake_dir), \
             patch("src.render.encoder_probe._run_nvenc_live_test", side_effect=fake_live):
            cap = probe_encoder_capability(requested="auto", vram_mb=4096, force_refresh=True)

        self.assertEqual(cap.selected_encoder, "h264_nvenc")
        self.assertTrue(cap.nvenc_available)
        self.assertFalse(cap.supports_bframes)
        self.assertEqual(cap.max_parallel_nvenc, 3)
        self.assertEqual(cap.reason, "nvenc_no_bframes_ok")

    def test_auto_falls_back_to_libx264_when_no_gpu_or_nvenc_fails(self):
        fake_dir = Path("C:/ffmpeg/bin")
        with patch("src.render.encoder_probe.find_system_ffmpeg_bin_dir", return_value=fake_dir), \
             patch("src.render.encoder_probe._run_nvenc_live_test", return_value=False):
            cap = probe_encoder_capability(requested="auto", vram_mb=0, force_refresh=True)

        self.assertEqual(cap.selected_encoder, "libx264")
        self.assertFalse(cap.is_nvenc)
        self.assertFalse(cap.nvenc_available)
        self.assertEqual(cap.max_parallel_nvenc, 0)
        self.assertEqual(cap.reason, "nvenc_probe_failed")

    def test_auto_falls_back_to_libx264_when_ffmpeg_missing(self):
        with patch("src.render.encoder_probe.find_system_ffmpeg_bin_dir", return_value=None):
            cap = probe_encoder_capability(requested="auto", force_refresh=True)
        self.assertEqual(cap.selected_encoder, "libx264")
        self.assertIsNone(cap.ffmpeg_bin_dir)
        self.assertEqual(cap.reason, "ffmpeg_not_found")

    def test_explicit_nvenc_raises_when_unavailable(self):
        fake_dir = Path("C:/ffmpeg/bin")
        with patch("src.render.encoder_probe.find_system_ffmpeg_bin_dir", return_value=fake_dir), \
             patch("src.render.encoder_probe._run_nvenc_live_test", return_value=False):
            with self.assertRaises(RuntimeError):
                probe_encoder_capability(requested="nvenc", force_refresh=True)

        with patch("src.render.encoder_probe.find_system_ffmpeg_bin_dir", return_value=None):
            with self.assertRaises(RuntimeError):
                probe_encoder_capability(requested="nvenc", force_refresh=True)

    def test_in_process_cache_and_force_refresh(self):
        fake_dir = Path("C:/ffmpeg/bin")
        with patch("src.render.encoder_probe.find_system_ffmpeg_bin_dir", return_value=fake_dir), \
             patch("src.render.encoder_probe._run_nvenc_live_test", return_value=True) as mock_live:
            c1 = probe_encoder_capability(requested="auto", vram_mb=4096)
            c2 = probe_encoder_capability(requested="auto", vram_mb=4096)
            self.assertIs(c1, c2)
            self.assertEqual(mock_live.call_count, 1)

            c3 = probe_encoder_capability(requested="auto", vram_mb=4096, force_refresh=True)
            self.assertEqual(mock_live.call_count, 2)
            self.assertEqual(c3.selected_encoder, "h264_nvenc")

    def test_live_probe_timeout_is_handled_safely(self):
        fake_dir = Path("C:/ffmpeg/bin")
        with patch("src.render.encoder_probe.find_system_ffmpeg_bin_dir", return_value=fake_dir), \
             patch("src.render.encoder_probe.subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 3.0)):
            cap = probe_encoder_capability(requested="auto", force_refresh=True)
        self.assertEqual(cap.selected_encoder, "libx264")
        self.assertFalse(cap.nvenc_available)

    def test_cache_keys_isolate_requested_mode_and_vram(self):
        fake_dir = Path("C:/ffmpeg/bin")
        with patch("src.render.encoder_probe.find_system_ffmpeg_bin_dir", return_value=fake_dir), \
             patch("src.render.encoder_probe._run_nvenc_live_test", return_value=True) as mock_live:
            c_auto_4g = probe_encoder_capability(requested="auto", vram_mb=4096)
            c_cpu_4g = probe_encoder_capability(requested="libx264", vram_mb=4096)
            c_nv_4g = probe_encoder_capability(requested="nvenc", vram_mb=4096)
            c_auto_8g = probe_encoder_capability(requested="auto", vram_mb=8192)
            # Lặp lại từng khóa phải trả đúng object cache riêng biệt, không lẫn nhau
            self.assertIs(probe_encoder_capability(requested="auto", vram_mb=4096), c_auto_4g)
            self.assertIs(probe_encoder_capability(requested="libx264", vram_mb=4096), c_cpu_4g)
            self.assertIs(probe_encoder_capability(requested="nvenc", vram_mb=4096), c_nv_4g)
            self.assertIs(probe_encoder_capability(requested="auto", vram_mb=8192), c_auto_8g)

        self.assertEqual(c_auto_4g.selected_encoder, "h264_nvenc")
        self.assertEqual(c_auto_4g.max_parallel_nvenc, 3)
        self.assertEqual(c_cpu_4g.selected_encoder, "libx264")
        self.assertEqual(c_cpu_4g.max_parallel_nvenc, 0)
        self.assertEqual(c_nv_4g.requested_encoder, "nvenc")
        self.assertEqual(c_auto_8g.max_parallel_nvenc, 4)
        # Chỉ 3 khóa có probe GPU (auto/4G, nvenc/4G, auto/8G); libx264 không gọi live test
        self.assertEqual(mock_live.call_count, 3)


if __name__ == "__main__":
    unittest.main()
