from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from PIL import Image

from src.core.hardware_profile import HardwareProfile, detect_hardware_profile

MIN_GPU_FREE_VRAM_MB = 1536  # >= 1.5 GB VRAM trống mới bật GPU provider cho rembg
# Bảo vệ rembg.new_session() (pooch.retrieve tải model .onnx) không đụng độ giữa nhiều worker thread
_REMBG_NEW_SESSION_LOCK = threading.Lock()


def is_rembg_available() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("rembg") is not None
    except Exception:
        return False


REMBG_AVAILABLE = is_rembg_available()


def compute_file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _load_rembg_visuals_config(settings_path: Optional[Path] = None) -> Tuple[Any, str]:
    """Đọc (rembg_threads, rembg_device) từ config/settings.json -> visuals."""
    path = settings_path or (Path(__file__).resolve().parent.parent.parent / "config" / "settings.json")
    if not path.exists():
        return ("auto", "auto")
    try:
        with open(path, "r", encoding="utf-8") as f:
            visuals = json.load(f).get("visuals", {})
        return (
            visuals.get("rembg_threads", "auto"),
            str(visuals.get("rembg_device", "auto") or "auto"),
        )
    except Exception:
        return ("auto", "auto")


def resolve_rembg_threads(
    rembg_threads: Any = "auto",
    hardware_profile: Optional[HardwareProfile] = None,
) -> int:
    """Tính `intra_op_num_threads` gọn trong 1 socket NUMA: `min(14, max(4, cores_per_socket))`."""
    if rembg_threads is not None and str(rembg_threads).strip().lower() != "auto":
        try:
            explicit = int(rembg_threads)
            if explicit > 0:
                return explicit
        except (TypeError, ValueError):
            pass

    hw = hardware_profile
    if hw is None:
        try:
            hw = detect_hardware_profile()
        except Exception:
            hw = None

    if hw is not None and hw.cpu_physical_cores > 0:
        sockets = max(1, int(hw.cpu_sockets or 1))
        cores_per_socket = max(1, int(hw.cpu_physical_cores) // sockets)
    else:
        logical = os.cpu_count() or 4
        cores_per_socket = max(1, logical // 2)

    return min(14, max(4, cores_per_socket))


def query_free_vram_mb(timeout_sec: float = 2.0) -> Optional[int]:
    """Đọc dung lượng VRAM đang trống (MB) từ nvidia-smi; trả về None nếu không khả dụng."""
    try:
        res = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_sec,
        )
        if res.returncode == 0 and res.stdout.strip():
            first = res.stdout.strip().splitlines()[0].strip()
            return int(float(first))
    except Exception:
        pass
    return None


def select_onnx_providers(
    device: str = "auto",
    available_providers: Optional[Sequence[str]] = None,
    free_vram_mb: Optional[int] = None,
    min_gpu_vram_mb: int = MIN_GPU_FREE_VRAM_MB,
) -> Tuple[List[str], bool]:
    """Chọn danh sách ONNX ExecutionProvider theo `visuals.rembg_device` và VRAM trống thực tế.

    Trả về `(providers, using_gpu)`. Không làm gãy môi trường chỉ cài `rembg[cpu]`.
    """
    dev = (device or "auto").strip().lower()
    if available_providers is None:
        try:
            import onnxruntime as ort
            avail = list(ort.get_available_providers())
        except Exception:
            avail = ["CPUExecutionProvider"]
    else:
        avail = list(available_providers)

    if dev == "cpu":
        return (["CPUExecutionProvider"], False)

    if dev == "cuda":
        if "CUDAExecutionProvider" in avail:
            free = free_vram_mb if free_vram_mb is not None else query_free_vram_mb()
            if free is None or free >= min_gpu_vram_mb:
                return (["CUDAExecutionProvider", "CPUExecutionProvider"], True)
        return (["CPUExecutionProvider"], False)

    if dev == "dml":
        if "DmlExecutionProvider" in avail:
            free = free_vram_mb if free_vram_mb is not None else query_free_vram_mb()
            if free is None or free >= min_gpu_vram_mb:
                return (["DmlExecutionProvider", "CPUExecutionProvider"], True)
        return (["CPUExecutionProvider"], False)

    # Chế độ "auto": chỉ kiểm tra VRAM và dùng GPU nếu provider GPU thực sự được cài đặt
    gpu_candidates = [
        p for p in ("CUDAExecutionProvider", "DmlExecutionProvider") if p in avail
    ]
    if gpu_candidates:
        free = free_vram_mb if free_vram_mb is not None else query_free_vram_mb()
        if free is not None and free >= min_gpu_vram_mb:
            return ([gpu_candidates[0], "CPUExecutionProvider"], True)

    return (["CPUExecutionProvider"], False)


def build_onnx_session_options(intra_op_threads: int) -> Any:
    """Khởi tạo `onnxruntime.SessionOptions` ghim luồng gọn trong 1 socket NUMA."""
    import onnxruntime as ort

    sess_opts = ort.SessionOptions()
    sess_opts.intra_op_num_threads = max(1, int(intra_op_threads))
    sess_opts.inter_op_num_threads = 1
    sess_opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return sess_opts


class CutoutProcessor:
    """Tách nền tự động bằng rembg (tối ưu NUMA ONNX Runtime), crop viền sát và tính ma trận base_cutout.json."""

    def __init__(
        self,
        model_name: str = "isnet-general-use",
        rembg_threads: Any = None,
        rembg_device: Optional[str] = None,
        hardware_profile: Optional[HardwareProfile] = None,
        settings_path: Optional[Path] = None,
    ):
        cfg_threads, cfg_device = _load_rembg_visuals_config(settings_path)
        self.model_name = model_name
        self.hardware_profile = hardware_profile
        self.rembg_threads_setting = cfg_threads if rembg_threads is None else rembg_threads
        self.rembg_device = str(cfg_device if rembg_device is None else rembg_device).strip().lower()
        self.intra_op_threads = resolve_rembg_threads(
            self.rembg_threads_setting,
            hardware_profile=self.hardware_profile,
        )
        self._providers: Optional[List[str]] = None
        self._using_gpu: Optional[bool] = None
        self._session = None
        self._session_lock = threading.Lock()

    def _resolve_providers_unlocked(self) -> Tuple[List[str], bool]:
        if self._providers is None or self._using_gpu is None:
            self._providers, self._using_gpu = select_onnx_providers(device=self.rembg_device)
        return list(self._providers), bool(self._using_gpu)

    def resolve_providers(self) -> Tuple[List[str], bool]:
        with self._session_lock:
            return self._resolve_providers_unlocked()

    @property
    def using_gpu(self) -> bool:
        _, gpu = self.resolve_providers()
        return gpu

    def build_session_options(self) -> Any:
        return build_onnx_session_options(self.intra_op_threads)

    def _get_session(self):
        if not REMBG_AVAILABLE:
            raise RuntimeError("Thư viện 'rembg' chưa được cài đặt.")
        with self._session_lock:
            if self._session is None:
                import rembg

                providers, using_gpu = self._resolve_providers_unlocked()
                sess_opts = self.build_session_options()
                with _REMBG_NEW_SESSION_LOCK:
                    try:
                        self._session = rembg.new_session(
                            self.model_name,
                            sess_opts=sess_opts,
                            providers=providers,
                        )
                    except Exception:
                        if not using_gpu:
                            raise
                        # Fallback êm ái về CPUExecutionProvider nếu khởi tạo GPU provider lỗi (thiếu cuDNN / OOM)
                        self._providers = ["CPUExecutionProvider"]
                        self._using_gpu = False
                        fallback_opts = self.build_session_options()
                        self._session = rembg.new_session(
                            self.model_name,
                            sess_opts=fallback_opts,
                            providers=["CPUExecutionProvider"],
                        )
            return self._session

    def is_cached(self, input_path: Path, output_png_path: Path, output_json_path: Path) -> Optional[Dict[str, Any]]:
        """Kiểm tra cache theo SHA-256 ảnh gốc; trả về metadata nếu hợp lệ, ngược lại None."""
        if not (input_path.exists() and output_png_path.exists() and output_json_path.exists()):
            return None
        try:
            current_hash = compute_file_hash(input_path)
            with open(output_json_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
            if isinstance(cached_data, dict) and cached_data.get("source_hash") == current_hash:
                return cached_data
        except Exception:
            return None
        return None

    def process_image(
        self,
        input_path: Path,
        output_png_path: Path,
        output_json_path: Path,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Tách nền 1 file ảnh, xuất PNG có alpha và file JSON tọa độ."""
        if not input_path.exists():
            raise FileNotFoundError(f"Không tìm thấy ảnh đầu vào: {input_path}")

        current_hash = compute_file_hash(input_path)

        # Kiểm tra cache
        if (
            not force
            and output_png_path.exists()
            and output_json_path.exists()
        ):
            try:
                with open(output_json_path, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                if cached_data.get("source_hash") == current_hash:
                    return cached_data
            except Exception:
                pass

        with Image.open(input_path) as orig_img:
            orig_w, orig_h = orig_img.size

            # Kiểm tra xem ảnh gốc đã có alpha tách nền hay chưa
            has_alpha = orig_img.mode in ("RGBA", "LA") or (
                orig_img.mode == "P" and "transparency" in orig_img.info
            )

            rgba_img: Image.Image
            if has_alpha:
                rgba_candidate = orig_img.convert("RGBA")
                # Kiểm tra xem alpha có thực sự trong suốt không
                alpha_extrema = rgba_candidate.getchannel("A").getextrema()
                if alpha_extrema[0] < 250:
                    rgba_img = rgba_candidate
                else:
                    import rembg

                    session = self._get_session()
                    rgba_img = rembg.remove(orig_img, session=session)
            else:
                import rembg

                session = self._get_session()
                rgba_img = rembg.remove(orig_img, session=session)

        # Tìm bounding box của kênh alpha
        alpha_channel = rgba_img.getchannel("A")
        bbox = alpha_channel.getbbox()  # (left, upper, right, lower)
        if bbox is None:
            # Ảnh rỗng hoặc hoàn toàn trong suốt -> giữ nguyên kích thước
            bbox = (0, 0, orig_w, orig_h)

        left, upper, right, lower = bbox
        # Thêm 1-2px padding nhẹ nếu còn nằm trong khung
        pad = 2
        left = max(0, left - pad)
        upper = max(0, upper - pad)
        right = min(orig_w, right + pad)
        lower = min(orig_h, lower + pad)

        cropped_img = rgba_img.crop((left, upper, right, lower))
        crop_w = right - left
        crop_h = lower - upper
        aspect = round(crop_w / max(1, crop_h), 4)

        # Kiểm tra xem có bị cắt ngang người ở đáy (cut_bottom) không:
        # Nếu các pixel ở hàng cuối cùng (hoặc 2 hàng cuối) của ảnh crop có alpha > 30
        cropped_alpha = cropped_img.getchannel("A")
        bottom_row_y = crop_h - 1
        cut_bottom = False
        opaque_count = 0
        for x in range(crop_w):
            if cropped_alpha.getpixel((x, bottom_row_y)) > 30:
                opaque_count += 1

        # Nếu có trên 15% số pixel ở đáy không trong suốt -> nhân vật bị cắt ngang người
        if opaque_count > max(2, int(crop_w * 0.15)):
            cut_bottom = True

        # Tọa độ face và chest mặc định theo chuẩn ảnh bán thân nhìn thẳng
        # face: 0.5 ngang, 0.16 cao
        # chest: 0.5 ngang, 0.42 cao
        metadata: Dict[str, Any] = {
            "aspect": aspect,
            "crop_box": {
                "x": left,
                "y": upper,
                "w": crop_w,
                "h": crop_h,
            },
            "face": {"x": 0.50, "y": 0.16},
            "chest": {"x": 0.50, "y": 0.42},
            "cut_bottom": cut_bottom,
            "source_hash": current_hash,
        }

        output_png_path.parent.mkdir(parents=True, exist_ok=True)
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        token = f"{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}"
        tmp_png = output_png_path.with_name(f".{output_png_path.name}.tmp.{token}.png")
        tmp_json = output_json_path.with_name(f".{output_json_path.name}.tmp.{token}")
        try:
            cropped_img.save(tmp_png, "PNG")
            os.replace(str(tmp_png), str(output_png_path))
            with open(tmp_json, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            os.replace(str(tmp_json), str(output_json_path))
        except Exception:
            for p in (tmp_png, tmp_json):
                try:
                    if p.exists():
                        p.unlink()
                except OSError:
                    pass
            raise

        return metadata


def compute_cutout_worker_count(
    uncached_count: int,
    using_gpu: bool,
    hardware_profile: Optional[HardwareProfile] = None,
) -> int:
    """Tính số worker tách nền an toàn: GPU 4GB luôn = 1; CPU đa socket = min(2, sockets)."""
    if uncached_count <= 1 or using_gpu:
        return 1
    hw = hardware_profile
    if hw is None:
        try:
            hw = detect_hardware_profile()
        except Exception:
            hw = None
    sockets = max(1, int(hw.cpu_sockets or 1)) if hw is not None else 1
    return max(1, min(2, sockets, uncached_count))


def process_all_characters(
    assets_dir: Path,
    processor: Optional[CutoutProcessor] = None,
    settings: Optional[Dict[str, Any]] = None,
    hardware_profile: Optional[HardwareProfile] = None,
) -> Dict[str, Dict[str, Any]]:
    """Duyệt tất cả thư mục characters trong assets/ và tách nền song song theo NUMA socket (hoặc tuần tự trên GPU)."""
    characters_dir = Path(assets_dir) / "characters"
    results: Dict[str, Dict[str, Any]] = {}
    if not characters_dir.exists():
        return results

    visuals_cfg = (settings or {}).get("visuals", {})
    cfg_threads = visuals_cfg.get("rembg_threads")
    cfg_device = visuals_cfg.get("rembg_device")

    candidates: List[Tuple[str, Path, Path, Path]] = []
    for char_folder in sorted(characters_dir.iterdir(), key=lambda p: p.name):
        if not char_folder.is_dir():
            continue
        base_img = None
        for ext in [".png", ".jpg", ".jpeg", ".webp"]:
            candidate = char_folder / f"base{ext}"
            if candidate.exists():
                base_img = candidate
                break
        if base_img is not None:
            candidates.append(
                (
                    char_folder.name,
                    base_img,
                    char_folder / "base_cutout.png",
                    char_folder / "base_cutout.json",
                )
            )

    if not candidates:
        return results

    if processor is None and not REMBG_AVAILABLE:
        return results

    probe_processor = processor or CutoutProcessor(
        rembg_threads=cfg_threads,
        rembg_device=cfg_device,
        hardware_profile=hardware_profile,
    )

    # Tách nhân vật đã có cache (đọc ngay không khởi tạo session ONNX) với nhân vật cần tách nền mới
    uncached: List[Tuple[str, Path, Path, Path]] = []
    for name, base_img, out_png, out_json in candidates:
        cached = probe_processor.is_cached(base_img, out_png, out_json)
        if cached is not None:
            results[name] = cached
        else:
            uncached.append((name, base_img, out_png, out_json))

    if not uncached:
        return results

    max_workers = compute_cutout_worker_count(
        uncached_count=len(uncached),
        using_gpu=probe_processor.using_gpu,
        hardware_profile=hardware_profile or probe_processor.hardware_profile,
    )

    if max_workers <= 1:
        for name, base_img, out_png, out_json in uncached:
            try:
                results[name] = probe_processor.process_image(base_img, out_png, out_json)
            except Exception as e:
                print(f"[CẢNH BÁO] Lỗi khi tách nền nhân vật {name}: {e}")
    else:
        # Mỗi worker trên CPU đa socket tạo session 14T riêng (1 worker / socket) nếu không truyền processor ngoài
        thread_local = threading.local()

        def _get_worker_processor() -> CutoutProcessor:
            if processor is not None:
                return processor
            proc = getattr(thread_local, "proc", None)
            if proc is None:
                proc = CutoutProcessor(
                    model_name=probe_processor.model_name,
                    rembg_threads=probe_processor.rembg_threads_setting,
                    rembg_device=probe_processor.rembg_device,
                    hardware_profile=hardware_profile or probe_processor.hardware_profile,
                )
                thread_local.proc = proc
            return proc

        def _run_one(item: Tuple[str, Path, Path, Path]) -> Tuple[str, Optional[Dict[str, Any]]]:
            name, base_img, out_png, out_json = item
            try:
                meta = _get_worker_processor().process_image(base_img, out_png, out_json)
                return (name, meta)
            except Exception as e:
                print(f"[CẢNH BÁO] Lỗi khi tách nền nhân vật {name}: {e}")
                return (name, None)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for name, meta in executor.map(_run_one, uncached):
                if meta is not None:
                    results[name] = meta

    return results
