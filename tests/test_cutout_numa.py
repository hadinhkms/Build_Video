import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from src.core.hardware_profile import HardwareProfile
from src.visuals.cutout import (
    CutoutProcessor,
    build_onnx_session_options,
    compute_cutout_worker_count,
    process_all_characters,
    resolve_rembg_threads,
    select_onnx_providers,
)


def _make_hw(cores: int, sockets: int, vram_mb: int = 4096, has_nvidia: bool = True) -> HardwareProfile:
    return HardwareProfile(
        cpu_name="Test Xeon",
        cpu_physical_cores=cores,
        cpu_logical_threads=cores * 2,
        cpu_sockets=sockets,
        numa_nodes=sockets,
        ram_total_gb=64.0,
        ram_available_gb=48.0,
        has_nvidia=has_nvidia,
        gpu_name="GTX 1650" if has_nvidia else None,
        vram_mb=vram_mb if has_nvidia else 0,
        gpu_driver="610.88" if has_nvidia else None,
        workspace_path="D:/_Short_film",
        workspace_drive="D:",
        workspace_disk_type="USB",
        workspace_disk_detail="USB HDD",
        workspace_free_gb=500.0,
        localappdata_path="C:/Users/Admin/AppData/Local",
        localappdata_drive="C:",
        localappdata_disk_type="NVMe",
        localappdata_disk_detail="NVMe SSD",
        localappdata_free_gb=500.0,
    )


class TestCutoutNumaAndProviders(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_resolve_rembg_threads_pins_within_single_numa_socket(self):
        # Dual Xeon 28C / 2 sockets -> 14 cores/socket -> 14 threads
        hw_xeon = _make_hw(cores=28, sockets=2)
        self.assertEqual(resolve_rembg_threads("auto", hw_xeon), 14)

        # Máy 64C / 2 sockets -> 32 cores/socket -> kẹp trần 14
        hw_epyc = _make_hw(cores=64, sockets=2)
        self.assertEqual(resolve_rembg_threads("auto", hw_epyc), 14)

        # Máy 8C / 1 socket -> 8
        hw_mid = _make_hw(cores=8, sockets=1)
        self.assertEqual(resolve_rembg_threads("auto", hw_mid), 8)

        # Máy 2C / 1 socket -> sàn tối thiểu 4
        hw_low = _make_hw(cores=2, sockets=1)
        self.assertEqual(resolve_rembg_threads("auto", hw_low), 4)

        # Giá trị tường minh ưu tiên cao nhất
        self.assertEqual(resolve_rembg_threads(6, hw_xeon), 6)
        self.assertEqual(resolve_rembg_threads("10", hw_xeon), 10)

    def test_onnx_session_options_enforce_sequential_and_numa_threads(self):
        import onnxruntime as ort

        sess_opts = build_onnx_session_options(14)
        self.assertEqual(sess_opts.intra_op_num_threads, 14)
        self.assertEqual(sess_opts.inter_op_num_threads, 1)
        self.assertEqual(sess_opts.execution_mode, ort.ExecutionMode.ORT_SEQUENTIAL)
        self.assertEqual(
            sess_opts.graph_optimization_level,
            ort.GraphOptimizationLevel.ORT_ENABLE_ALL,
        )

    def test_select_onnx_providers_handles_cpu_cuda_dml_and_low_vram_fallback(self):
        # 1. Môi trường chỉ có rembg[cpu]
        prov, gpu = select_onnx_providers(
            device="auto",
            available_providers=["AzureExecutionProvider", "CPUExecutionProvider"],
        )
        self.assertEqual(prov, ["CPUExecutionProvider"])
        self.assertFalse(gpu)

        # 2. Có CUDA + VRAM trống >= 1.5 GB -> bật CUDA + fallback CPU
        prov, gpu = select_onnx_providers(
            device="auto",
            available_providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            free_vram_mb=2400,
        )
        self.assertEqual(prov, ["CUDAExecutionProvider", "CPUExecutionProvider"])
        self.assertTrue(gpu)

        # 3. Có CUDA nhưng VRAM trống < 1.5 GB -> hạ cấp CPU an toàn
        prov, gpu = select_onnx_providers(
            device="auto",
            available_providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            free_vram_mb=1024,
        )
        self.assertEqual(prov, ["CPUExecutionProvider"])
        self.assertFalse(gpu)

        # 4. Có DirectML + VRAM đủ -> chọn DirectML
        prov, gpu = select_onnx_providers(
            device="auto",
            available_providers=["DmlExecutionProvider", "CPUExecutionProvider"],
            free_vram_mb=2048,
        )
        self.assertEqual(prov, ["DmlExecutionProvider", "CPUExecutionProvider"])
        self.assertTrue(gpu)

        # 5. Chỉ định tường minh device="cpu" -> luôn CPU dù có CUDA
        prov, gpu = select_onnx_providers(
            device="cpu",
            available_providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            free_vram_mb=4096,
        )
        self.assertEqual(prov, ["CPUExecutionProvider"])
        self.assertFalse(gpu)

        # 6. Chỉ định device="cuda" trên máy không cài onnxruntime-gpu -> fallback CPU không crash
        prov, gpu = select_onnx_providers(
            device="cuda",
            available_providers=["CPUExecutionProvider"],
        )
        self.assertEqual(prov, ["CPUExecutionProvider"])
        self.assertFalse(gpu)

    def test_worker_count_and_parallel_process_all_characters(self):
        hw_2s = _make_hw(cores=28, sockets=2)
        hw_1s = _make_hw(cores=8, sockets=1)

        # CPU 2 socket -> 2 worker; CPU 1 socket -> 1; GPU 4GB -> luôn 1
        self.assertEqual(compute_cutout_worker_count(3, using_gpu=False, hardware_profile=hw_2s), 2)
        self.assertEqual(compute_cutout_worker_count(3, using_gpu=False, hardware_profile=hw_1s), 1)
        self.assertEqual(compute_cutout_worker_count(3, using_gpu=True, hardware_profile=hw_2s), 1)

        # Tạo 3 nhân vật với ảnh RGBA hợp lệ (nhân vật 0 đã có cache, 1 & 2 chưa có cache)
        chars_dir = self.tmp / "characters"
        for i in range(3):
            cdir = chars_dir / f"char_{i}"
            cdir.mkdir(parents=True, exist_ok=True)
            img = Image.new("RGBA", (120, 200), (0, 0, 0, 0))
            for y in range(20, 180):
                for x in range(30, 90):
                    img.putpixel((x, y), (100 + i * 30, 80, 60, 255))
            img.save(cdir / "base.png")

        # Chạy trước cho char_0 để tạo cache hợp lệ
        base_proc = CutoutProcessor(rembg_threads=14, rembg_device="cpu", hardware_profile=hw_2s)
        base_proc.process_image(
            chars_dir / "char_0" / "base.png",
            chars_dir / "char_0" / "base_cutout.png",
            chars_dir / "char_0" / "base_cutout.json",
        )

        # Theo dõi độ song song thực tế khi xử lý 2 nhân vật chưa cache trên CPU 2 socket
        lock = threading.Lock()
        active = 0
        peak = 0
        processed_names = []
        orig_process = CutoutProcessor.process_image

        def slow_process(self_p, in_p, out_png, out_json, force=False):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
                processed_names.append(in_p.parent.name)
            time.sleep(0.06)
            try:
                return orig_process(self_p, in_p, out_png, out_json, force=force)
            finally:
                with lock:
                    active -= 1

        with mock.patch.object(CutoutProcessor, "process_image", autospec=True, side_effect=slow_process):
            res = process_all_characters(
                self.tmp,
                processor=base_proc,
                hardware_profile=hw_2s,
            )

        self.assertEqual(set(res.keys()), {"char_0", "char_1", "char_2"})
        # char_0 trúng cache -> KHÔNG bị gọi lại process_image
        self.assertEqual(set(processed_names), {"char_1", "char_2"})
        # 2 worker song song trên 2 socket CPU
        self.assertEqual(peak, 2)

    def test_get_session_thread_safe_validates_rembg_signature_and_gpu_fallback(self):
        import inspect
        import rembg
        from concurrent.futures import ThreadPoolExecutor

        # Xác nhận chữ ký rembg.new_session hỗ trợ sess_opts và **kwargs (providers)
        sig = inspect.signature(rembg.new_session)
        self.assertIn("sess_opts", sig.parameters)
        self.assertTrue(
            any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            or "providers" in sig.parameters
        )

        # 1. Shared CutoutProcessor gọi _get_session đồng thời từ 4 luồng -> chỉ tạo đúng 1 session
        hw_2s = _make_hw(cores=28, sockets=2)
        proc = CutoutProcessor(rembg_threads=14, rembg_device="cpu", hardware_profile=hw_2s)
        calls = []

        def fake_new_session(model_name, sess_opts=None, providers=None):
            time.sleep(0.03)
            calls.append((model_name, sess_opts.intra_op_num_threads, list(providers or [])))
            return object()

        with mock.patch("rembg.new_session", side_effect=fake_new_session):
            with ThreadPoolExecutor(max_workers=4) as pool:
                sessions = list(pool.map(lambda _: proc._get_session(), range(4)))

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], ("isnet-general-use", 14, ["CPUExecutionProvider"]))
        self.assertTrue(all(s is sessions[0] for s in sessions))

        # 2. Khi GPU provider ném lỗi lúc khởi tạo session -> tự fallback êm ái sang CPUExecutionProvider
        gpu_proc = CutoutProcessor(rembg_threads=14, rembg_device="cuda", hardware_profile=hw_2s)
        gpu_calls = []

        def flaky_gpu_session(model_name, sess_opts=None, providers=None):
            gpu_calls.append(list(providers or []))
            if providers and providers[0] == "CUDAExecutionProvider":
                raise RuntimeError("CUDA DLL missing")
            return "CPU_FALLBACK_SESSION"

        with mock.patch(
            "src.visuals.cutout.select_onnx_providers",
            return_value=(["CUDAExecutionProvider", "CPUExecutionProvider"], True),
        ), mock.patch("rembg.new_session", side_effect=flaky_gpu_session):
            sess = gpu_proc._get_session()

        self.assertEqual(sess, "CPU_FALLBACK_SESSION")
        self.assertEqual(
            gpu_calls,
            [["CUDAExecutionProvider", "CPUExecutionProvider"], ["CPUExecutionProvider"]],
        )
        self.assertFalse(gpu_proc.using_gpu)


if __name__ == "__main__":
    unittest.main()
