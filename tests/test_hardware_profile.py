import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from src.core.hardware_profile import (
    HardwareProfile,
    classify_bus_and_seek,
    clear_hardware_profile_cache,
    compute_recommended_concurrency,
    detect_hardware_profile,
)


class TestHardwareProfile(unittest.TestCase):
    def setUp(self):
        clear_hardware_profile_cache()

    def tearDown(self):
        clear_hardware_profile_cache()

    def test_detect_real_hardware_profile_schema_and_report(self):
        profile = detect_hardware_profile(Path.cwd(), force_refresh=True)
        self.assertGreaterEqual(profile.cpu_physical_cores, 1)
        self.assertGreaterEqual(profile.cpu_logical_threads, profile.cpu_physical_cores)
        self.assertGreaterEqual(profile.cpu_sockets, 1)
        self.assertGreaterEqual(profile.numa_nodes, 1)
        self.assertGreater(profile.ram_total_gb, 0.0)
        self.assertIn(profile.workspace_disk_type, {"NVMe", "SSD", "USB", "HDD", "UNKNOWN"})
        self.assertIn(profile.localappdata_disk_type, {"NVMe", "SSD", "USB", "HDD", "UNKNOWN"})

        report = profile.format_report()
        self.assertIn("CINESTORY HARDWARE PROFILE", report)
        self.assertIn("cores /", report)

        serialized = json.dumps(profile.to_dict(), ensure_ascii=False)
        self.assertIn("cpu_physical_cores", serialized)

    def test_profile_in_process_cache_and_force_refresh(self):
        p1 = detect_hardware_profile(Path.cwd())
        p2 = detect_hardware_profile(Path.cwd())
        self.assertIs(p1, p2)

        p3 = detect_hardware_profile(Path.cwd(), force_refresh=True)
        self.assertIsNot(p1, p3)

    def test_gpu_fallback_when_nvidia_smi_missing(self):
        with patch("src.core.hardware_profile.subprocess.run", side_effect=FileNotFoundError("no nvidia-smi")):
            profile = detect_hardware_profile(Path.cwd(), force_refresh=True)
        self.assertFalse(profile.has_nvidia)
        self.assertIsNone(profile.gpu_name)
        self.assertEqual(profile.vram_mb, 0)
        self.assertIsNone(profile.gpu_driver)
        self.assertFalse(profile.has_nvenc)

    def test_gpu_detection_parses_nvidia_smi_csv(self):
        def fake_run(cmd, **kwargs):
            if cmd[0] == "nvidia-smi":
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="NVIDIA GeForce GTX 1650, 4096, 610.88\n", stderr=""
                )
            return subprocess.CompletedProcess(
                cmd, 0, stdout=" V..... h264_nvenc\n V..... libx264\n", stderr=""
            )

        with patch("src.core.hardware_profile.subprocess.run", side_effect=fake_run):
            profile = detect_hardware_profile(Path.cwd(), force_refresh=True)

        self.assertTrue(profile.has_nvidia)
        self.assertEqual(profile.gpu_name, "NVIDIA GeForce GTX 1650")
        self.assertEqual(profile.vram_mb, 4096)
        self.assertEqual(profile.gpu_driver, "610.88")
        self.assertTrue(profile.has_nvenc)
        self.assertIn("h264_nvenc", profile.ffmpeg_encoders)

    def test_classify_bus_and_seek_all_types(self):
        self.assertEqual(classify_bus_and_seek(17, False), ("NVMe", "NVMe SSD"))
        self.assertEqual(classify_bus_and_seek(7, True), ("USB", "USB HDD"))
        self.assertEqual(classify_bus_and_seek(7, False), ("USB", "USB SSD"))
        self.assertEqual(classify_bus_and_seek(11, False), ("SSD", "SSD"))
        self.assertEqual(classify_bus_and_seek(11, True), ("HDD", "HDD"))
        self.assertEqual(classify_bus_and_seek(None, None), ("UNKNOWN", "UNKNOWN"))

    def test_vram_warning_for_4gb_gpu(self):
        profile = HardwareProfile(
            cpu_name="Xeon",
            cpu_physical_cores=28,
            cpu_logical_threads=56,
            cpu_sockets=2,
            numa_nodes=2,
            ram_total_gb=64.0,
            ram_available_gb=40.0,
            has_nvidia=True,
            gpu_name="NVIDIA GeForce GTX 1650",
            vram_mb=4096,
            gpu_driver="610.88",
            workspace_path="D:\\_Short_film",
            workspace_drive="D:",
            workspace_disk_type="USB",
            workspace_disk_detail="USB HDD",
            workspace_free_gb=500.0,
            localappdata_path="C:\\Users\\Test\\AppData\\Local",
            localappdata_drive="C:",
            localappdata_disk_type="NVMe",
            localappdata_disk_detail="NVMe SSD",
            localappdata_free_gb=300.0,
        )
        self.assertIsNone(profile.check_vram_warning("angle", 24))
        self.assertIsNotNone(profile.check_vram_warning("angle", 28))
        self.assertIsNone(profile.check_vram_warning("swangle", 28))

    def test_recommended_concurrency_heuristics(self):
        rec, sweep = compute_recommended_concurrency(28, 64.0, True, 4096)
        self.assertEqual(rec, 16)
        self.assertEqual(sweep, [8, 12, 16, 20, 24, 28, 32])

        rec_small, sweep_small = compute_recommended_concurrency(4, 8.0, False, 0)
        self.assertLessEqual(rec_small, 4)
        self.assertTrue(all(c <= 4 for c in sweep_small))

    def test_cli_module_execution(self):
        res = subprocess.run(
            [sys.executable, "-m", "src.core.hardware_profile", "--json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            check=True,
        )
        data = json.loads(res.stdout)
        self.assertIn("cpu_physical_cores", data)
        self.assertIn("workspace_disk_type", data)
        self.assertIn("localappdata_disk_type", data)


if __name__ == "__main__":
    unittest.main()
