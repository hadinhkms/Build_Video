"""Quản lý thư mục scratch & cache tốc độ cao trên ổ NVMe/SSD (C:) và di chuyển nguyên tử.

Khi repo nằm trên ổ USB/HDD chậm (ví dụ D:) và %LOCALAPPDATA% nằm trên NVMe/SSD
còn trống >= 15 GB, tự động chuyển toàn bộ bundle-cache, hw-bin và work/<chapter_id>
sang %LOCALAPPDATA%\\CineStory\\scratch\\.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Optional, Union

from src.core.hardware_profile import HardwareProfile, detect_disk_type, detect_hardware_profile

logger = logging.getLogger(__name__)

_SLOW_DISK_TYPES = {"USB", "HDD"}
_FAST_DISK_TYPES = {"NVMe", "SSD"}


class ScratchManager:
    """Điều phối đường dẫn scratch/cache và promote file an toàn xuyên phân vùng."""

    def __init__(
        self,
        project_root: Optional[Union[Path, str]] = None,
        scratch_dir_setting: Optional[Union[str, Path]] = "auto",
        hardware_profile: Optional[HardwareProfile] = None,
        min_free_gb: float = 15.0,
        localappdata_override: Optional[Union[Path, str]] = None,
    ):
        self.project_root = (
            Path(project_root).resolve() if project_root is not None else Path.cwd().resolve()
        )
        self.min_free_gb = float(min_free_gb)
        self.scratch_dir_setting = str(scratch_dir_setting) if scratch_dir_setting is not None else "auto"
        self.hardware_profile = hardware_profile or detect_hardware_profile(self.project_root)

        self.using_nvme_offload = False
        self.scratch_root = self._resolve_scratch_root(
            setting=self.scratch_dir_setting,
            localappdata_override=Path(localappdata_override) if localappdata_override is not None else None,
        )

    def _resolve_scratch_root(
        self,
        setting: str,
        localappdata_override: Optional[Path] = None,
    ) -> Path:
        normalized = setting.strip() if setting else "auto"
        if normalized.lower() == "auto":
            hw = self.hardware_profile
            ws_is_slow = hw.workspace_disk_type in _SLOW_DISK_TYPES
            local_is_fast = hw.localappdata_disk_type in _FAST_DISK_TYPES
            has_enough_space = hw.localappdata_free_gb >= self.min_free_gb

            local_base = localappdata_override or Path(hw.localappdata_path)
            if ws_is_slow and local_is_fast and has_enough_space and str(local_base).strip():
                self.using_nvme_offload = True
                return local_base / "CineStory" / "scratch"

            self.using_nvme_offload = False
            return self.project_root / "cache" / "scratch"

        expanded = Path(os.path.expandvars(normalized)).expanduser()
        if not expanded.is_absolute():
            expanded = (self.project_root / expanded).resolve()
        disk_t = detect_disk_type(expanded)
        if disk_t != "UNKNOWN":
            self.using_nvme_offload = disk_t in _FAST_DISK_TYPES
        else:
            self.using_nvme_offload = expanded != (self.project_root / "cache" / "scratch").resolve()
        return expanded

    @property
    def bundle_cache_dir(self) -> Path:
        return self.scratch_root / "bundle-cache"

    @property
    def hw_bin_dir(self) -> Path:
        return self.scratch_root / "hw-bin"

    @property
    def work_root(self) -> Path:
        return self.scratch_root / "work"

    def chapter_work_dir(self, chapter_id: str) -> Path:
        return self.work_root / chapter_id

    def prenorm_mkv_path(self, chapter_id: str) -> Path:
        return self.chapter_work_dir(chapter_id) / "video.prenorm.mkv"

    def prenorm_mov_path(self, chapter_id: str, output_name: str = "final_chapter_video.mp4") -> Path:
        return self.chapter_work_dir(chapter_id) / f"{Path(output_name).stem}.prenorm.mov"

    def clips_dir(self, chapter_id: str) -> Path:
        return self.chapter_work_dir(chapter_id) / "clips"

    def master_temp_path(self, chapter_id: str, filename: str = "video.master.tmp.mp4") -> Path:
        return self.chapter_work_dir(chapter_id) / filename

    def promote_to_output(
        self,
        src_path: Union[Path, str],
        dst_path: Union[Path, str],
        remove_src: bool = True,
    ) -> Path:
        """Di chuyển an toàn xuyên ổ đĩa (ví dụ C: -> D:) qua file .tmp + os.replace() nguyên tử."""
        src = Path(src_path)
        dst = Path(dst_path)

        if not src.exists():
            raise FileNotFoundError(f"File nguồn không tồn tại để promote: {src}")

        dst.parent.mkdir(parents=True, exist_ok=True)

        try:
            if src.resolve() == dst.resolve():
                return dst
        except Exception:
            pass

        tmp_dst = (
            dst.with_suffix(".tmp")
            if dst.suffix
            else dst.with_name(f"{dst.name}.tmp")
        )

        try:
            shutil.copy2(str(src), str(tmp_dst))
            os.replace(str(tmp_dst), str(dst))
        except Exception:
            if tmp_dst.exists():
                try:
                    tmp_dst.unlink()
                except OSError:
                    pass
            raise

        if remove_src and src.exists():
            try:
                src.unlink()
            except OSError as exc:
                logger.warning(f"Không thể xóa file nguồn sau promote ({src}): {exc}")

        return dst

    def cleanup_chapter_work(self, chapter_id: str) -> bool:
        """Dọn toàn bộ thư mục tạm work/<chapter_id>/ sau khi hoàn tất mastering."""
        work_dir = self.chapter_work_dir(chapter_id)
        if not work_dir.exists():
            return True
        try:
            shutil.rmtree(str(work_dir))
            return not work_dir.exists()
        except OSError as exc:
            logger.warning(f"Không thể dọn thư mục scratch {work_dir}: {exc}")
            return False
