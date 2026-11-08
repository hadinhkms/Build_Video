import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


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
    ) -> bool:
        """Thực thi render.ts và theo dõi tiến độ qua stdout."""
        if not props_path.exists():
            logger.error(f"File props không tồn tại: {props_path}")
            return False

        output_path.parent.mkdir(parents=True, exist_ok=True)

        concurrency_arg = str(concurrency) if concurrency is not None else "auto"
        npx_cmd = "npx.cmd" if sys.platform == "win32" else "npx"

        cmd = [
            npx_cmd,
            "tsx",
            "scripts/render.ts",
            str(props_path.resolve()),
            str(output_path.resolve()),
            concurrency_arg,
            str(crf),
        ]

        logger.info(f"Khởi động Remotion render: {' '.join(cmd)}")
        print(f" -> Khởi động Remotion Node API (concurrency={concurrency_arg}, crf={crf})...")

        t0 = time.time()
        output_lines: List[str] = []

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

            progress_pattern = re.compile(r"^PROGRESS\s+([0-9.]+)")

            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break

                if line:
                    stripped = line.strip()
                    output_lines.append(stripped)

                    match = progress_pattern.match(stripped)
                    if match:
                        prog_val = float(match.group(1))
                        if progress_callback:
                            progress_callback(prog_val)
                        percent = int(prog_val * 100)
                        print(f"\r -> Tiến độ render: {percent}%", end="", flush=True)
                    elif "Bundling" in stripped or "Selecting" in stripped or "Rendering" in stripped:
                        print(f" -> {stripped}")

            returncode = process.wait(timeout=self.timeout_sec)
            print()  # Xuống dòng sau tiến độ

            render_dur = round(time.time() - t0, 2)

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

            print(f"🎉 Render hoàn tất trong {render_dur}s: {output_path.name}")
            return True

        except subprocess.TimeoutExpired:
            process.kill()
            print(f"\n[Lỗi] Remotion render quá thời gian chờ ({self.timeout_sec}s). Đã hủy tiến trình.")
            return False
        except Exception as e:
            print(f"\n[Lỗi] Lỗi không xác định khi chạy Remotion: {e}")
            return False
