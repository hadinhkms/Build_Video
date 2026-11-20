"""Bộ nhận diện cấu hình phần cứng thực tế (CPU/NUMA, RAM, GPU, Disk, FFmpeg).

Dùng Win32 API qua ctypes (chạy < 10 ms) kết hợp nvidia-smi / ffmpeg với timeout ngắn
và tự động fallback an toàn trên mọi nền tảng (không bao giờ crash).
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Windows STORAGE_BUS_TYPE constants
_BUS_TYPE_USB = 7
_BUS_TYPE_NVME = 17

# Windows IOCTL & CreateFile constants
_IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_OPEN_EXISTING = 3
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

# Windows GetLogicalProcessorInformationEx Relation constants
_RELATION_PROCESSOR_CORE = 0
_RELATION_NUMA_NODE = 1
_RELATION_PROCESSOR_PACKAGE = 3
_RELATION_ALL = 0xFFFF

_NOTABLE_ENCODERS = ("h264_nvenc", "hevc_nvenc", "libx264", "libx265", "aac")

_PROFILE_CACHE: Dict[str, "HardwareProfile"] = {}


@dataclass
class HardwareProfile:
    cpu_name: str
    cpu_physical_cores: int
    cpu_logical_threads: int
    cpu_sockets: int
    numa_nodes: int
    ram_total_gb: float
    ram_available_gb: float
    has_nvidia: bool
    gpu_name: Optional[str]
    vram_mb: int
    gpu_driver: Optional[str]
    workspace_path: str
    workspace_drive: str
    workspace_disk_type: str
    workspace_disk_detail: str
    workspace_free_gb: float
    localappdata_path: str
    localappdata_drive: str
    localappdata_disk_type: str
    localappdata_disk_detail: str
    localappdata_free_gb: float
    ffmpeg_encoders: List[str] = field(default_factory=list)
    has_nvenc: bool = False
    recommended_concurrency: int = 8
    recommended_concurrency_sweep: List[int] = field(default_factory=lambda: [4, 8])

    def check_vram_warning(self, gl: str, concurrency: int) -> Optional[str]:
        """Cảnh báo khi concurrency vượt ngưỡng an toàn VRAM 4 GB với ANGLE."""
        if (
            gl == "angle"
            and self.has_nvidia
            and 0 < self.vram_mb <= 4096
            and concurrency > 24
        ):
            return (
                f"Cảnh báo VRAM: GPU {self.gpu_name} chỉ có {self.vram_mb} MB VRAM; "
                f"gl='angle' với concurrency={concurrency} (>24) có nguy cơ tràn VRAM."
            )
        return None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def format_report(self) -> str:
        ram_nominal_gb = round(self.ram_total_gb)
        gpu_line = (
            f"{self.gpu_name} ({self.vram_mb} MB VRAM, Driver {self.gpu_driver or 'N/A'})"
            if self.has_nvidia and self.gpu_name
            else "Không phát hiện GPU NVIDIA (CPU fallback)"
        )
        encoders_str = ", ".join(self.ffmpeg_encoders) if self.ffmpeg_encoders else "N/A"
        lines = [
            "=" * 68,
            "  CINESTORY HARDWARE PROFILE",
            "=" * 68,
            f"  CPU          : {self.cpu_name}",
            f"                 {self.cpu_physical_cores} cores / {self.cpu_logical_threads} threads "
            f"({self.cpu_sockets} socket(s), {self.numa_nodes} NUMA node(s))",
            f"  RAM          : {self.ram_total_gb:.2f} GB (~{ram_nominal_gb} GB RAM) | "
            f"Trống: {self.ram_available_gb:.2f} GB",
            f"  GPU          : {gpu_line}",
            f"  Workspace    : {self.workspace_drive or self.workspace_path} "
            f"[{self.workspace_disk_detail}] — trống {self.workspace_free_gb:.1f} GB",
            f"  LOCALAPPDATA : {self.localappdata_drive or self.localappdata_path} "
            f"[{self.localappdata_disk_detail}] — trống {self.localappdata_free_gb:.1f} GB",
            f"  FFmpeg Enc.  : {encoders_str} (NVENC={'Có' if self.has_nvenc else 'Không'})",
            f"  Gợi ý Render : concurrency={self.recommended_concurrency}, "
            f"sweep={self.recommended_concurrency_sweep}",
        ]
        if self.has_nvidia and 0 < self.vram_mb <= 4096:
            lines.append(
                f"  Lưu ý VRAM   : GPU <= 4 GB ({self.vram_mb} MB) -> khuyến nghị concurrency <= 24 khi dùng gl='angle'."
            )
        lines.append("=" * 68)
        return "\n".join(lines)


def _detect_cpu_name() -> str:
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            ) as key:
                name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
                if name and str(name).strip():
                    return str(name).strip()
        except Exception:
            pass
    return platform.processor() or platform.machine() or "Unknown CPU"


def _detect_cpu_topology_windows() -> Tuple[int, int, int, int]:
    """Đọc (physical_cores, logical_threads, sockets, numa_nodes) qua Win32 API."""
    logical = os.cpu_count() or 1
    try:
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetLogicalProcessorInformationEx.argtypes = [
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.DWORD),
        ]
        k32.GetLogicalProcessorInformationEx.restype = wintypes.BOOL

        buf_len = wintypes.DWORD(0)
        k32.GetLogicalProcessorInformationEx(
            _RELATION_ALL, None, ctypes.byref(buf_len)
        )
        if buf_len.value == 0:
            return (max(1, logical // 2), logical, 1, 1)

        buf = (ctypes.c_byte * buf_len.value)()
        ok = k32.GetLogicalProcessorInformationEx(
            _RELATION_ALL, ctypes.byref(buf), ctypes.byref(buf_len)
        )
        if not ok:
            return (max(1, logical // 2), logical, 1, 1)

        offset = 0
        cores = 0
        numa = 0
        packages = 0
        while offset + 8 <= buf_len.value:
            rel = ctypes.c_uint32.from_buffer(buf, offset).value
            size = ctypes.c_uint32.from_buffer(buf, offset + 4).value
            if size == 0:
                break
            if rel == _RELATION_PROCESSOR_CORE:
                cores += 1
            elif rel == _RELATION_NUMA_NODE:
                numa += 1
            elif rel == _RELATION_PROCESSOR_PACKAGE:
                packages += 1
            offset += size

        return (
            cores if cores > 0 else max(1, logical // 2),
            logical,
            packages if packages > 0 else 1,
            numa if numa > 0 else 1,
        )
    except Exception:
        return (max(1, logical // 2), logical, 1, 1)


def _detect_cpu_info() -> Tuple[str, int, int, int, int]:
    cpu_name = _detect_cpu_name()
    if sys.platform == "win32":
        cores, logical, sockets, numa = _detect_cpu_topology_windows()
        return (cpu_name, cores, logical, sockets, numa)

    logical = os.cpu_count() or 1
    cores = max(1, logical // 2)
    sockets = 1
    numa = 1
    try:
        cpuinfo = Path("/proc/cpuinfo")
        if cpuinfo.exists():
            text = cpuinfo.read_text(encoding="utf-8", errors="ignore")
            phys_ids = set()
            core_pairs = set()
            cur_phys = "0"
            for line in text.splitlines():
                if line.startswith("physical id"):
                    cur_phys = line.split(":", 1)[1].strip()
                    phys_ids.add(cur_phys)
                elif line.startswith("core id"):
                    core_pairs.add((cur_phys, line.split(":", 1)[1].strip()))
            if core_pairs:
                cores = len(core_pairs)
            if phys_ids:
                sockets = len(phys_ids)
                numa = sockets
    except Exception:
        pass
    return (cpu_name, cores, logical, sockets, numa)


def _detect_ram_info() -> Tuple[float, float]:
    """Trả về (ram_total_gb, ram_available_gb)."""
    if sys.platform == "win32":
        try:
            from ctypes import wintypes

            class _MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", wintypes.DWORD),
                    ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_uint64),
                    ("ullAvailPhys", ctypes.c_uint64),
                    ("ullTotalPageFile", ctypes.c_uint64),
                    ("ullAvailPageFile", ctypes.c_uint64),
                    ("ullTotalVirtual", ctypes.c_uint64),
                    ("ullAvailVirtual", ctypes.c_uint64),
                    ("ullAvailExtendedVirtual", ctypes.c_uint64),
                ]

            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(_MEMORYSTATUSEX)]
            k32.GlobalMemoryStatusEx.restype = wintypes.BOOL

            mem = _MEMORYSTATUSEX()
            mem.dwLength = ctypes.sizeof(mem)
            if k32.GlobalMemoryStatusEx(ctypes.byref(mem)):
                gb = 1024 ** 3
                return (round(mem.ullTotalPhys / gb, 2), round(mem.ullAvailPhys / gb, 2))
        except Exception:
            pass

    try:
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            total_kb = 0
            avail_kb = 0
            for line in meminfo.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    avail_kb = int(line.split()[1])
            if total_kb > 0:
                return (round(total_kb / (1024 ** 2), 2), round(avail_kb / (1024 ** 2), 2))
    except Exception:
        pass

    return (0.0, 0.0)


def _detect_gpu_info(timeout_sec: float = 2.5) -> Tuple[bool, Optional[str], int, Optional[str]]:
    """Trả về (has_nvidia, gpu_name, vram_mb, driver_version)."""
    try:
        res = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_sec,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return (False, None, 0, None)
        first_line = res.stdout.strip().splitlines()[0]
        parts = [p.strip() for p in first_line.split(",")]
        if len(parts) < 2:
            return (False, None, 0, None)
        name = parts[0] or None
        vram_mb = int(float(parts[1])) if parts[1] else 0
        driver = parts[2] if len(parts) >= 3 and parts[2] else None
        return (True, name, vram_mb, driver)
    except Exception:
        return (False, None, 0, None)


def _extract_drive_letter(path: Path) -> str:
    resolved = str(path.resolve())
    drive, _ = os.path.splitdrive(resolved)
    if drive and len(drive) >= 2 and drive[1] == ":":
        return drive[:2].upper()
    return ""


def _query_windows_disk_ioctl(drive_letter: str) -> Tuple[Optional[int], Optional[bool]]:
    """Truy vấn (BusType, IncursSeekPenalty) không cần quyền Admin qua DeviceIoControl."""
    from ctypes import wintypes

    class _STORAGE_PROPERTY_QUERY(ctypes.Structure):
        _fields_ = [
            ("PropertyId", wintypes.DWORD),
            ("QueryType", wintypes.DWORD),
            ("AdditionalParameters", ctypes.c_byte * 1),
        ]

    class _STORAGE_DEVICE_DESCRIPTOR(ctypes.Structure):
        _fields_ = [
            ("Version", wintypes.DWORD),
            ("Size", wintypes.DWORD),
            ("DeviceType", ctypes.c_byte),
            ("DeviceTypeModifier", ctypes.c_byte),
            ("RemovableMedia", ctypes.c_byte),
            ("CommandQueueing", ctypes.c_byte),
            ("VendorIdOffset", wintypes.DWORD),
            ("ProductIdOffset", wintypes.DWORD),
            ("ProductRevisionOffset", wintypes.DWORD),
            ("SerialNumberOffset", wintypes.DWORD),
            ("BusType", wintypes.DWORD),
            ("RawPropertiesLength", wintypes.DWORD),
            ("RawDeviceProperties", ctypes.c_byte * 1),
        ]

    class _DEVICE_SEEK_PENALTY_DESCRIPTOR(ctypes.Structure):
        _fields_ = [
            ("Version", wintypes.DWORD),
            ("Size", wintypes.DWORD),
            ("IncursSeekPenalty", ctypes.c_byte),
        ]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    k32.CreateFileW.restype = ctypes.c_void_p

    k32.DeviceIoControl.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    k32.DeviceIoControl.restype = wintypes.BOOL

    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    k32.CloseHandle.restype = wintypes.BOOL

    vol_path = f"\\\\.\\{drive_letter}"
    handle = k32.CreateFileW(
        vol_path,
        0,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE,
        None,
        _OPEN_EXISTING,
        0,
        None,
    )
    if not handle or handle == _INVALID_HANDLE_VALUE:
        return (None, None)

    bus_type: Optional[int] = None
    seek_penalty: Optional[bool] = None
    try:
        ret = wintypes.DWORD(0)

        # StorageDeviceProperty (PropertyId=0)
        q_dev = _STORAGE_PROPERTY_QUERY(0, 0)
        out_dev = (ctypes.c_byte * 1024)()
        if k32.DeviceIoControl(
            handle,
            _IOCTL_STORAGE_QUERY_PROPERTY,
            ctypes.byref(q_dev),
            ctypes.sizeof(q_dev),
            out_dev,
            len(out_dev),
            ctypes.byref(ret),
            None,
        ):
            bus_type = int(_STORAGE_DEVICE_DESCRIPTOR.from_buffer(out_dev).BusType)

        # StorageDeviceSeekPenaltyProperty (PropertyId=7)
        q_seek = _STORAGE_PROPERTY_QUERY(7, 0)
        out_seek = _DEVICE_SEEK_PENALTY_DESCRIPTOR()
        if k32.DeviceIoControl(
            handle,
            _IOCTL_STORAGE_QUERY_PROPERTY,
            ctypes.byref(q_seek),
            ctypes.sizeof(q_seek),
            ctypes.byref(out_seek),
            ctypes.sizeof(out_seek),
            ctypes.byref(ret),
            None,
        ):
            seek_penalty = bool(out_seek.IncursSeekPenalty)
    finally:
        k32.CloseHandle(handle)

    return (bus_type, seek_penalty)


def classify_bus_and_seek(bus_type: Optional[int], seek_penalty: Optional[bool]) -> Tuple[str, str]:
    """Phân loại ổ đĩa thành (disk_type, disk_detail)."""
    if bus_type == _BUS_TYPE_NVME:
        return ("NVMe", "NVMe SSD")
    if bus_type == _BUS_TYPE_USB:
        if seek_penalty is True:
            return ("USB", "USB HDD")
        if seek_penalty is False:
            return ("USB", "USB SSD")
        return ("USB", "USB")
    if seek_penalty is False:
        return ("SSD", "SSD")
    if seek_penalty is True:
        return ("HDD", "HDD")
    return ("UNKNOWN", "UNKNOWN")


def detect_disk_info(path: Path) -> Tuple[str, str]:
    """Phát hiện loại ổ đĩa chứa `path`, trả về `(disk_type, disk_detail)`."""
    if sys.platform == "win32":
        drive = _extract_drive_letter(path)
        if drive:
            try:
                bus_type, seek_penalty = _query_windows_disk_ioctl(drive)
                disk_type, detail = classify_bus_and_seek(bus_type, seek_penalty)
                if disk_type != "UNKNOWN":
                    return (disk_type, detail)
            except Exception:
                pass
    return ("UNKNOWN", "UNKNOWN")


def detect_disk_type(path: Path) -> str:
    """Trả về loại ổ đĩa: 'NVMe', 'SSD', 'USB', 'HDD', hoặc 'UNKNOWN'."""
    return detect_disk_info(path)[0]


def get_disk_free_gb(path: Path) -> float:
    """Trả về dung lượng trống (GB) tại đường dẫn (tự lùi về thư mục cha gần nhất)."""
    target = path
    try:
        while not target.exists() and target != target.parent:
            target = target.parent
        usage = shutil.disk_usage(str(target))
        return round(usage.free / (1024 ** 3), 2)
    except Exception:
        return 0.0


def _detect_ffmpeg_encoders(timeout_sec: float = 2.5) -> List[str]:
    """Quét nhanh các bộ mã hóa chính mà FFmpeg hệ thống hỗ trợ."""
    try:
        res = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_sec,
        )
        if res.returncode != 0:
            return []
        stdout = res.stdout
        return [enc for enc in _NOTABLE_ENCODERS if enc in stdout]
    except Exception:
        return []


def compute_recommended_concurrency(
    cpu_physical_cores: int,
    ram_total_gb: float,
    has_nvidia: bool,
    vram_mb: int,
) -> Tuple[int, List[int]]:
    """Tính cấu hình concurrency khuyến nghị và dải benchmark sweep."""
    if cpu_physical_cores >= 24 and ram_total_gb >= 32.0:
        sweep = [8, 12, 16, 20, 24, 28, 32]
        rec = 16
        if has_nvidia and 0 < vram_mb <= 4096:
            rec = min(rec, 24)
        return (rec, sweep)

    if cpu_physical_cores >= 12 and ram_total_gb >= 16.0:
        return (min(12, cpu_physical_cores), [4, 8, 12, 16])

    if cpu_physical_cores >= 6 and ram_total_gb >= 8.0:
        return (min(8, cpu_physical_cores), [4, 6, 8])

    rec = max(2, min(4, cpu_physical_cores))
    return (rec, sorted({2, rec}))


def clear_hardware_profile_cache() -> None:
    """Xóa cache hồ sơ phần cứng trong tiến trình (chủ yếu cho kiểm thử)."""
    _PROFILE_CACHE.clear()


def detect_hardware_profile(
    workspace_dir: Optional[Path] = None,
    force_refresh: bool = False,
) -> HardwareProfile:
    """Quét và cache hồ sơ phần cứng hiện tại của máy."""
    ws_path = (workspace_dir or Path.cwd()).resolve()
    cache_key = str(ws_path).lower() if sys.platform == "win32" else str(ws_path)
    if not force_refresh and cache_key in _PROFILE_CACHE:
        return _PROFILE_CACHE[cache_key]

    cpu_name, cores, logical, sockets, numa = _detect_cpu_info()
    ram_total_gb, ram_avail_gb = _detect_ram_info()
    has_nvidia, gpu_name, vram_mb, gpu_driver = _detect_gpu_info()

    ws_drive = _extract_drive_letter(ws_path)
    ws_disk_type, ws_disk_detail = detect_disk_info(ws_path)
    ws_free_gb = get_disk_free_gb(ws_path)

    localappdata_env = os.environ.get("LOCALAPPDATA")
    if localappdata_env:
        local_path = Path(localappdata_env)
    else:
        local_path = Path.home() / ".cache"

    local_drive = _extract_drive_letter(local_path)
    local_disk_type, local_disk_detail = detect_disk_info(local_path)
    local_free_gb = get_disk_free_gb(local_path)

    encoders = _detect_ffmpeg_encoders()
    has_nvenc = "h264_nvenc" in encoders

    rec_conc, rec_sweep = compute_recommended_concurrency(
        cpu_physical_cores=cores,
        ram_total_gb=ram_total_gb,
        has_nvidia=has_nvidia,
        vram_mb=vram_mb,
    )

    profile = HardwareProfile(
        cpu_name=cpu_name,
        cpu_physical_cores=cores,
        cpu_logical_threads=logical,
        cpu_sockets=sockets,
        numa_nodes=numa,
        ram_total_gb=ram_total_gb,
        ram_available_gb=ram_avail_gb,
        has_nvidia=has_nvidia,
        gpu_name=gpu_name,
        vram_mb=vram_mb,
        gpu_driver=gpu_driver,
        workspace_path=str(ws_path),
        workspace_drive=ws_drive,
        workspace_disk_type=ws_disk_type,
        workspace_disk_detail=ws_disk_detail,
        workspace_free_gb=ws_free_gb,
        localappdata_path=str(local_path),
        localappdata_drive=local_drive,
        localappdata_disk_type=local_disk_type,
        localappdata_disk_detail=local_disk_detail,
        localappdata_free_gb=local_free_gb,
        ffmpeg_encoders=encoders,
        has_nvenc=has_nvenc,
        recommended_concurrency=rec_conc,
        recommended_concurrency_sweep=rec_sweep,
    )
    _PROFILE_CACHE[cache_key] = profile
    return profile


def main() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Quét và in hồ sơ phần cứng CineStory")
    parser.add_argument("--workspace", default=None, help="Đường dẫn thư mục workspace")
    parser.add_argument("--json", action="store_true", help="Xuất kết quả dạng JSON")
    args = parser.parse_args()

    ws = Path(args.workspace) if args.workspace else None
    profile = detect_hardware_profile(workspace_dir=ws, force_refresh=True)
    if args.json:
        print(json.dumps(profile.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(profile.format_report())


if __name__ == "__main__":
    main()
