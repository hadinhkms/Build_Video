import tempfile
import unittest
from pathlib import Path

from src.core.hardware_profile import HardwareProfile
from src.core.scratch_manager import ScratchManager


def _make_profile(
    workspace_disk_type: str = "USB",
    localappdata_disk_type: str = "NVMe",
    localappdata_free_gb: float = 200.0,
    localappdata_path: str = "C:\\Users\\Test\\AppData\\Local",
) -> HardwareProfile:
    return HardwareProfile(
        cpu_name="Xeon",
        cpu_physical_cores=28,
        cpu_logical_threads=56,
        cpu_sockets=2,
        numa_nodes=2,
        ram_total_gb=64.0,
        ram_available_gb=40.0,
        has_nvidia=True,
        gpu_name="GTX 1650",
        vram_mb=4096,
        gpu_driver="610.88",
        workspace_path="D:\\_Short_film",
        workspace_drive="D:",
        workspace_disk_type=workspace_disk_type,
        workspace_disk_detail=workspace_disk_type,
        workspace_free_gb=500.0,
        localappdata_path=localappdata_path,
        localappdata_drive="C:",
        localappdata_disk_type=localappdata_disk_type,
        localappdata_disk_detail=localappdata_disk_type,
        localappdata_free_gb=localappdata_free_gb,
    )


class TestScratchManager(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.fake_project = self.tmp_dir / "repo"
        self.fake_local = self.tmp_dir / "localappdata"
        self.fake_project.mkdir(parents=True, exist_ok=True)
        self.fake_local.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_auto_uses_nvme_when_workspace_usb_and_localappdata_nvme_enough_space(self):
        hw = _make_profile(
            workspace_disk_type="USB",
            localappdata_disk_type="NVMe",
            localappdata_free_gb=120.0,
            localappdata_path=str(self.fake_local),
        )
        mgr = ScratchManager(
            project_root=self.fake_project,
            scratch_dir_setting="auto",
            hardware_profile=hw,
        )
        self.assertTrue(mgr.using_nvme_offload)
        self.assertEqual(mgr.scratch_root, self.fake_local / "CineStory" / "scratch")

    def test_auto_falls_back_to_repo_when_nvme_space_below_15gb(self):
        hw = _make_profile(
            workspace_disk_type="USB",
            localappdata_disk_type="NVMe",
            localappdata_free_gb=12.5,
            localappdata_path=str(self.fake_local),
        )
        mgr = ScratchManager(
            project_root=self.fake_project,
            scratch_dir_setting="auto",
            hardware_profile=hw,
        )
        self.assertFalse(mgr.using_nvme_offload)
        self.assertEqual(mgr.scratch_root, self.fake_project.resolve() / "cache" / "scratch")

    def test_auto_falls_back_to_repo_when_workspace_already_nvme(self):
        hw = _make_profile(
            workspace_disk_type="NVMe",
            localappdata_disk_type="NVMe",
            localappdata_free_gb=250.0,
            localappdata_path=str(self.fake_local),
        )
        mgr = ScratchManager(
            project_root=self.fake_project,
            scratch_dir_setting="auto",
            hardware_profile=hw,
        )
        self.assertFalse(mgr.using_nvme_offload)
        self.assertEqual(mgr.scratch_root, self.fake_project.resolve() / "cache" / "scratch")

    def test_explicit_scratch_dir_override(self):
        custom = self.tmp_dir / "custom_scratch"
        hw = _make_profile(workspace_disk_type="NVMe")
        mgr = ScratchManager(
            project_root=self.fake_project,
            scratch_dir_setting=str(custom),
            hardware_profile=hw,
        )
        self.assertEqual(mgr.scratch_root, custom)

    def test_directory_layout_paths(self):
        custom = self.tmp_dir / "scratch_root"
        mgr = ScratchManager(
            project_root=self.fake_project,
            scratch_dir_setting=str(custom),
            hardware_profile=_make_profile(),
        )
        self.assertEqual(mgr.bundle_cache_dir, custom / "bundle-cache")
        self.assertEqual(mgr.hw_bin_dir, custom / "hw-bin")
        self.assertEqual(mgr.chapter_work_dir("ch_01"), custom / "work" / "ch_01")
        self.assertEqual(mgr.prenorm_mkv_path("ch_01"), custom / "work" / "ch_01" / "video.prenorm.mkv")
        self.assertEqual(mgr.clips_dir("ch_01"), custom / "work" / "ch_01" / "clips")
        self.assertEqual(
            mgr.master_temp_path("ch_01", "video.master.tmp.mp4"),
            custom / "work" / "ch_01" / "video.master.tmp.mp4",
        )

    def test_promote_to_output_atomic_replace_and_source_cleanup(self):
        mgr = ScratchManager(
            project_root=self.fake_project,
            scratch_dir_setting=str(self.tmp_dir / "scratch"),
            hardware_profile=_make_profile(),
        )
        src = mgr.master_temp_path("ch_01", "video.master.tmp.mp4")
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_bytes(b"MASTER_VIDEO_BYTES_V2")

        dst = self.fake_project / "output" / "ch_01" / "final_chapter_video.mp4"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"OLD_VIDEO_BYTES")

        result = mgr.promote_to_output(src, dst, remove_src=True)
        self.assertEqual(result, dst)
        self.assertEqual(dst.read_bytes(), b"MASTER_VIDEO_BYTES_V2")
        self.assertFalse(src.exists())
        self.assertFalse(dst.with_suffix(".tmp").exists())

    def test_promote_to_output_raises_when_source_missing(self):
        mgr = ScratchManager(
            project_root=self.fake_project,
            scratch_dir_setting=str(self.tmp_dir / "scratch"),
            hardware_profile=_make_profile(),
        )
        with self.assertRaises(FileNotFoundError):
            mgr.promote_to_output(self.tmp_dir / "missing.mp4", self.tmp_dir / "out.mp4")

    def test_cleanup_chapter_work(self):
        mgr = ScratchManager(
            project_root=self.fake_project,
            scratch_dir_setting=str(self.tmp_dir / "scratch"),
            hardware_profile=_make_profile(),
        )
        work = mgr.chapter_work_dir("ch_02")
        (work / "clips").mkdir(parents=True, exist_ok=True)
        (work / "video.prenorm.mkv").write_bytes(b"123")
        (work / "clips" / "shot_01.mov").write_bytes(b"456")

        self.assertTrue(mgr.cleanup_chapter_work("ch_02"))
        self.assertFalse(work.exists())
        # Idempotent cleanup
        self.assertTrue(mgr.cleanup_chapter_work("ch_02"))


if __name__ == "__main__":
    unittest.main()
