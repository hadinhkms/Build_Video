import json
import logging
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

_PROGRESS_RE = re.compile(r"^PROGRESS\s+([0-9.]+)")
_TIMING_KV_RE = re.compile(r"\b(bundle_ms|select_ms|render_ms)=(\d+)")
_BUNDLE_CACHE_RE = re.compile(
    r"^BUNDLE_CACHE\s+hit=(\d+)\s+hash=(\S+)\s+sync_ms=(\d+)\s+synced_files=(\d+)"
)
_ENCODER_ACTIVE_RE = re.compile(r"^ENCODER_ACTIVE\s+(\S+)")


class RemotionRunner:
    """Điều phối render video bằng Remotion Node API qua scripts/render.ts."""

    def __init__(
        self,
        project_root: Optional[Path] = None,
        remotion_dir: Optional[Path] = None,
        timeout_sec: int = 600,
    ):
        self.root = project_root or Path(__file__).resolve().parent.parent.parent
        self.remotion_dir = remotion_dir or (self.root / "remotion")
        self.timeout_sec = timeout_sec
        self.last_timing: Dict[str, Any] = {}
        self.last_output_lines: List[str] = []
        self.last_encoder: Optional[str] = None

    @staticmethod
    def parse_timing_line(line: str) -> Dict[str, int]:
        """Phân tích dòng `TIMING bundle_ms=... select_ms=... render_ms=...` từ stdout."""
        if not line.startswith("TIMING"):
            return {}
        return {k: int(v) for k, v in _TIMING_KV_RE.findall(line)}

    @staticmethod
    def parse_bundle_cache_line(line: str) -> Dict[str, Any]:
        """Phân tích dòng `BUNDLE_CACHE hit=... hash=... sync_ms=... synced_files=...`."""
        m = _BUNDLE_CACHE_RE.match(line)
        if not m:
            return {}
        return {
            "cache_hit": bool(int(m.group(1))),
            "source_hash": m.group(2),
            "sync_ms": int(m.group(3)),
            "synced_files": int(m.group(4)),
        }

    @staticmethod
    def parse_encoder_active_line(line: str) -> Optional[str]:
        """Phân tích dòng `ENCODER_ACTIVE <h264_nvenc|libx264> ...` từ stdout."""
        m = _ENCODER_ACTIVE_RE.match(line)
        if not m:
            return None
        return m.group(1)

    def build_command(
        self,
        props_path: Path,
        output_path: Path,
        concurrency: Optional[int] = None,
        crf: int = 18,
        gl: Optional[str] = None,
        x264_preset: Optional[str] = None,
        image_format: Optional[str] = None,
        jpeg_quality: Optional[int] = None,
        frame_range: Optional[str] = None,
        scratch_dir: Optional[Union[Path, str]] = None,
        chapter_id: Optional[str] = None,
        bundle_cache: bool = True,
        encoder: Optional[str] = None,
        nvenc_preset: Optional[str] = None,
        nvenc_cq: Optional[int] = None,
        ffmpeg_bin_dir: Optional[Union[Path, str]] = None,
        supports_bframes: Optional[bool] = None,
        media_cache_bytes: Optional[int] = None,
        offthread_video_cache_bytes: Optional[int] = None,
        offthread_video_threads: Optional[int] = None,
    ) -> List[str]:
        """Tạo danh sách đối số CLI gọi scripts/render.ts (tương thích ngược vị trí cũ)."""
        concurrency_arg = str(concurrency) if concurrency is not None else "auto"
        npx_cmd = "npx.cmd" if sys.platform == "win32" else "npx"

        cmd = [
            npx_cmd,
            "tsx",
            "scripts/render.ts",
            str(Path(props_path).resolve()),
            str(Path(output_path).resolve()),
            concurrency_arg,
            str(crf),
        ]

        if gl:
            cmd.extend(["--gl", str(gl)])
        if x264_preset:
            cmd.extend(["--x264-preset", str(x264_preset)])
        if image_format:
            cmd.extend(["--image-format", str(image_format)])
        if jpeg_quality is not None:
            cmd.extend(["--jpeg-quality", str(int(jpeg_quality))])
        if frame_range:
            cmd.extend(["--frames", str(frame_range)])
        if scratch_dir is not None:
            cmd.extend(["--scratch-dir", str(Path(scratch_dir).resolve())])
        if chapter_id:
            cmd.extend(["--chapter-id", str(chapter_id)])
        if not bundle_cache:
            cmd.append("--no-bundle-cache")
        if encoder:
            cmd.extend(["--encoder", str(encoder)])
        if nvenc_preset:
            cmd.extend(["--nvenc-preset", str(nvenc_preset)])
        if nvenc_cq is not None:
            cmd.extend(["--nvenc-cq", str(int(nvenc_cq))])
        if ffmpeg_bin_dir is not None:
            cmd.extend(["--ffmpeg-bin-dir", str(Path(ffmpeg_bin_dir).resolve())])
        if supports_bframes is not None:
            cmd.extend(["--nvenc-bframes", "1" if supports_bframes else "0"])
        if media_cache_bytes is not None and media_cache_bytes > 0:
            cmd.extend(["--media-cache-bytes", str(int(media_cache_bytes))])
        if offthread_video_cache_bytes is not None and offthread_video_cache_bytes > 0:
            cmd.extend(["--offthread-video-cache-bytes", str(int(offthread_video_cache_bytes))])
        if offthread_video_threads is not None and offthread_video_threads > 0:
            cmd.extend(["--offthread-video-threads", str(int(offthread_video_threads))])

        return cmd

    def probe_media_streams(self, file_path: Path) -> Dict[str, Any]:
        """Kiểm tra codec video và audio bằng ffprobe."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "stream=index,codec_type,codec_name,duration",
            "-of", "json",
            str(file_path),
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return json.loads(res.stdout)

    def render(
        self,
        props_path: Path,
        output_path: Path,
        concurrency: Optional[int] = None,
        crf: int = 18,
        progress_callback: Optional[Callable[[float], None]] = None,
        gl: Optional[str] = None,
        x264_preset: Optional[str] = None,
        image_format: Optional[str] = None,
        jpeg_quality: Optional[int] = None,
        frame_range: Optional[str] = None,
        scratch_dir: Optional[Union[Path, str]] = None,
        chapter_id: Optional[str] = None,
        bundle_cache: bool = True,
        encoder: Optional[str] = None,
        nvenc_preset: Optional[str] = None,
        nvenc_cq: Optional[int] = None,
        ffmpeg_bin_dir: Optional[Union[Path, str]] = None,
        supports_bframes: Optional[bool] = None,
        media_cache_bytes: Optional[int] = None,
        offthread_video_cache_bytes: Optional[int] = None,
        offthread_video_threads: Optional[int] = None,
    ) -> bool:
        """Thực thi render.ts và theo dõi tiến độ + mốc TIMING + ENCODER_ACTIVE qua stdout."""
        props_path = Path(props_path)
        output_path = Path(output_path)
        self.last_timing = {}
        self.last_output_lines = []
        self.last_encoder = None

        if not props_path.exists():
            logger.error(f"File props không tồn tại: {props_path}")
            return False

        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = self.build_command(
            props_path=props_path,
            output_path=output_path,
            concurrency=concurrency,
            crf=crf,
            gl=gl,
            x264_preset=x264_preset,
            image_format=image_format,
            jpeg_quality=jpeg_quality,
            frame_range=frame_range,
            scratch_dir=scratch_dir,
            chapter_id=chapter_id,
            bundle_cache=bundle_cache,
            encoder=encoder,
            nvenc_preset=nvenc_preset,
            nvenc_cq=nvenc_cq,
            ffmpeg_bin_dir=ffmpeg_bin_dir,
            supports_bframes=supports_bframes,
            media_cache_bytes=media_cache_bytes,
            offthread_video_cache_bytes=offthread_video_cache_bytes,
            offthread_video_threads=offthread_video_threads,
        )

        concurrency_arg = str(concurrency) if concurrency is not None else "auto"
        logger.info(f"Khởi động Remotion render: {' '.join(cmd)}")
        print(
            f" -> Khởi động Remotion Node API (encoder={encoder or 'auto'}, concurrency={concurrency_arg}, "
            f"gl={gl or 'angle'}, preset={x264_preset or 'default'}, crf={crf}"
            f"{f', frames={frame_range}' if frame_range else ''})..."
        )

        t0 = time.time()
        output_lines: List[str] = []
        timing: Dict[str, Any] = {}
        process: Optional[subprocess.Popen] = None
        timed_out = threading.Event()
        watchdog: Optional[threading.Timer] = None

        def _terminate_process_tree(proc: subprocess.Popen) -> None:
            timed_out.set()
            try:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=5,
                    )
                else:
                    proc.kill()
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        try:
            process = subprocess.Popen(
                cmd,
                cwd=str(self.remotion_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            if self.timeout_sec and self.timeout_sec > 0:
                watchdog = threading.Timer(self.timeout_sec, _terminate_process_tree, args=(process,))
                watchdog.daemon = True
                watchdog.start()

            assert process.stdout is not None
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break

                if line:
                    stripped = line.strip()
                    output_lines.append(stripped)

                    match = _PROGRESS_RE.match(stripped)
                    if match:
                        prog_val = float(match.group(1))
                        if progress_callback:
                            progress_callback(prog_val)
                        percent = int(prog_val * 100)
                        print(f"\r -> Tiến độ render: {percent}%", end="", flush=True)
                        continue

                    parsed_timing = self.parse_timing_line(stripped)
                    if parsed_timing:
                        timing.update(parsed_timing)
                        continue

                    parsed_cache = self.parse_bundle_cache_line(stripped)
                    if parsed_cache:
                        timing.update(parsed_cache)
                        continue

                    active_enc = self.parse_encoder_active_line(stripped)
                    if active_enc:
                        self.last_encoder = active_enc
                        timing["encoder"] = active_enc
                        print(f" -> {stripped}")
                        continue

                    if (
                        "Bundling" in stripped
                        or "Selecting" in stripped
                        or "Rendering" in stripped
                        or "NVENC_BRIDGE_DISABLED" in stripped
                    ):
                        print(f" -> {stripped}")

            returncode = process.wait(timeout=max(5, self.timeout_sec))
            if watchdog is not None:
                watchdog.cancel()
            print()  # Xuống dòng sau tiến độ

            if timed_out.is_set():
                self.last_output_lines = output_lines
                print(f"\n[Lỗi] Remotion render quá thời gian chờ ({self.timeout_sec}s). Đã hủy tiến trình.")
                return False

            render_dur = round(time.time() - t0, 2)
            timing["total_ms"] = int(round((time.time() - t0) * 1000))
            self.last_timing = timing
            self.last_output_lines = output_lines

            if returncode != 0:
                print(f"[Lỗi] Remotion render thất bại với mã lỗi {returncode}.")
                print("--- 30 dòng nhật ký cuối cùng ---")
                for err_line in output_lines[-30:]:
                    print(f"   {err_line}")
                print("---------------------------------")
                return False

            if not output_path.exists():
                print(f"[Lỗi] File đầu ra không xuất hiện: {output_path}")
                return False

            timing_summary = ""
            if "bundle_ms" in timing and "render_ms" in timing:
                timing_summary = (
                    f" [bundle={timing['bundle_ms']}ms"
                    f", select={timing.get('select_ms', 0)}ms"
                    f", render={timing['render_ms']}ms]"
                )
            print(f"🎉 Render hoàn tất trong {render_dur}s{timing_summary}: {output_path.name}")
            return True

        except subprocess.TimeoutExpired:
            if process is not None:
                _terminate_process_tree(process)
            self.last_output_lines = output_lines
            print(f"\n[Lỗi] Remotion render quá thời gian chờ ({self.timeout_sec}s). Đã hủy tiến trình.")
            return False
        except Exception as e:
            self.last_output_lines = output_lines
            print(f"\n[Lỗi] Lỗi không xác định khi chạy Remotion: {e}")
            return False
        finally:
            if watchdog is not None:
                watchdog.cancel()
            if process is not None and process.stdout is not None:
                try:
                    process.stdout.close()
                except Exception:
                    pass
