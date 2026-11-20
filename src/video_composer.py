import json
import os
import subprocess
import threading
from pathlib import Path
from typing import List, Optional

from src.render.encoder_probe import EncoderCapability, probe_encoder_capability


class VideoComposer:
    def __init__(
        self,
        settings_path: str = "config/settings.json",
        encoder_capability: Optional[EncoderCapability] = None,
        vram_mb: Optional[int] = None,
    ):
        with open(settings_path, "r", encoding="utf-8") as f:
            self.settings = json.load(f)
        self.v_cfg = self.settings.get("video", {})
        self.r_cfg = self.settings.get("render", {})
        self.width = int(self.v_cfg.get("width", 1920))
        self.height = int(self.v_cfg.get("height", 1080))
        self.fps = int(self.v_cfg.get("fps", 24))

        self.encoder_setting = str(self.r_cfg.get("encoder", "auto"))
        self.crf = int(self.r_cfg.get("crf", self.v_cfg.get("crf", 18)))
        self.x264_preset = str(
            self.r_cfg.get("x264_preset")
            or self.v_cfg.get("preset")
            or "faster"
        )
        self.nvenc_preset = str(self.r_cfg.get("nvenc_preset", "p5"))
        self.nvenc_cq = int(self.r_cfg.get("nvenc_cq", min(51, self.crf + 1)))
        self.ffmpeg_workers_setting = self.r_cfg.get("ffmpeg_workers", "auto")

        self.encoder_capability: EncoderCapability = (
            encoder_capability
            if encoder_capability is not None
            else probe_encoder_capability(
                requested=self.encoder_setting,
                vram_mb=vram_mb,
            )
        )
        self.active_encoder = self.encoder_capability.selected_encoder
        self._nvenc_semaphore: Optional[threading.BoundedSemaphore] = (
            threading.BoundedSemaphore(min(4, max(1, self.encoder_capability.max_parallel_nvenc)))
            if self.encoder_capability.is_nvenc
            else None
        )

    def get_recommended_workers(self, physical_cores: Optional[int] = None) -> int:
        """Tính số worker song song tối ưu cho render_shot_clip()."""
        explicit: Optional[int] = None
        if isinstance(self.ffmpeg_workers_setting, int) and not isinstance(self.ffmpeg_workers_setting, bool):
            explicit = self.ffmpeg_workers_setting
        elif isinstance(self.ffmpeg_workers_setting, str) and self.ffmpeg_workers_setting.strip().isdigit():
            explicit = int(self.ffmpeg_workers_setting.strip())

        if self.encoder_capability.is_nvenc:
            nvenc_cap = min(4, max(1, self.encoder_capability.max_parallel_nvenc))
            if explicit is not None and explicit > 0:
                return min(explicit, nvenc_cap)
            return nvenc_cap

        cores = physical_cores if physical_cores and physical_cores > 0 else max(2, (os.cpu_count() or 4) // 2)
        if explicit is not None and explicit > 0:
            return max(1, explicit)
        return min(12, max(2, cores // 2))

    def _get_ken_burns_filter(self, motion_type: str, duration: float) -> str:
        """Sinh chuỗi filter FFmpeg zoompan mô phỏng chuyển động máy quay điện ảnh.

        Độ phân giải tiền phóng (scale) được tối ưu sát biên độ zoom thực tế:
        - zoom_in / zoom_out (max_zoom 1.18): 2304:-2 ở 1080p (thay vì 2560:-1)
        - pan_left / pan_right (zoom 1.12): 2160:-2 ở 1080p
        """
        # round() thay vì int(): duration đã căn theo frame, int() có thể hụt 1 frame do sai số float
        frames = round(duration * self.fps)
        zoom_scale_w = ((int(round(self.width * 1.20)) + 15) // 16) * 16
        pan_scale_w = ((int(round(self.width * 1.125)) + 7) // 8) * 8

        if motion_type == "zoom_out":
            # Bắt đầu từ 1.18 thu nhỏ dần về 1.0
            return (
                f"scale={zoom_scale_w}:-2,zoompan=z='if(lte(zoom,1.0),1.18,max(1.001,zoom-0.0010))':"
                f"d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={self.width}x{self.height}:fps={self.fps}"
            )
        elif motion_type == "pan_left":
            return (
                f"scale={pan_scale_w}:-2,zoompan=z=1.12:x='if(lte(on,1),0,min(iw-iw/zoom,x+1.2))':"
                f"y='ih/2-(ih/zoom/2)':d={frames}:s={self.width}x{self.height}:fps={self.fps}"
            )
        elif motion_type == "pan_right":
            return (
                f"scale={pan_scale_w}:-2,zoompan=z=1.12:x='if(lte(on,1),iw-iw/zoom,max(0,x-1.2))':"
                f"y='ih/2-(ih/zoom/2)':d={frames}:s={self.width}x{self.height}:fps={self.fps}"
            )
        else:  # default: zoom_in
            return (
                f"scale={zoom_scale_w}:-2,zoompan=z='min(zoom+0.0010,1.18)':"
                f"d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={self.width}x{self.height}:fps={self.fps}"
            )

    def _build_video_encoder_args(self, use_nvenc: bool, x264_threads: int = 4) -> List[str]:
        if use_nvenc:
            bf = "2" if self.encoder_capability.supports_bframes else "0"
            return [
                "-c:v", "h264_nvenc",
                "-preset", self.nvenc_preset,
                "-tune", "hq",
                "-rc", "vbr",
                "-cq", str(self.nvenc_cq),
                "-b:v", "0",
                "-bf", bf,
                "-spatial-aq", "1",
                "-aq-strength", "8",
            ]
        return [
            "-c:v", "libx264",
            "-preset", self.x264_preset,
            "-crf", str(self.crf),
            "-threads", str(max(1, int(x264_threads))),
        ]

    def build_render_shot_command(
        self,
        image_path: str,
        audio_path: str,
        output_clip_path: str,
        motion_type: str = "zoom_in",
        duration: float = 5.0,
        use_nvenc: Optional[bool] = None,
        x264_threads: int = 4,
    ) -> List[str]:
        vf_filter = self._get_ken_burns_filter(motion_type, duration)
        nvenc_flag = self.encoder_capability.is_nvenc if use_nvenc is None else bool(use_nvenc)
        enc_args = self._build_video_encoder_args(use_nvenc=nvenc_flag, x264_threads=x264_threads)
        return [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_path,
            "-i", audio_path,
            "-vf", vf_filter,
            "-af", "apad",
            *enc_args,
            "-t", f"{duration:.3f}",
            "-pix_fmt", "yuv420p",
            "-c:a", "pcm_s16le",
            output_clip_path,
        ]

    def render_shot_clip(
        self,
        image_path: str,
        audio_path: str,
        output_clip_path: str,
        motion_type: str = "zoom_in",
        duration: float = 5.0,
        x264_threads: int = 4,
    ) -> bool:
        """
        Ghép 1 ảnh + 1 file audio thành 1 đoạn video clip với chuyển động Ken Burns.
        Clip dài đúng `duration`: audio được đệm im lặng (apad) thay vì cắt theo -shortest,
        nếu không clip sẽ chỉ dài bằng file mp3 và lệch khỏi storyboard/SRT.
        Audio để PCM (clip phải là .mov): mỗi clip AAC mang ~21ms priming, ghép -c copy sẽ
        cộng dồn làm giọng trễ dần so với hình. AAC chỉ được mã hóa 1 lần ở bước mastering.
        Không dùng .mkv: Matroska làm tròn timestamp về 1ms, video ra không còn đúng 24fps (CFR).
        """
        out_dir = os.path.dirname(output_clip_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        use_nvenc = self.encoder_capability.is_nvenc
        cmd = self.build_render_shot_command(
            image_path=image_path,
            audio_path=audio_path,
            output_clip_path=output_clip_path,
            motion_type=motion_type,
            duration=duration,
            use_nvenc=use_nvenc,
            x264_threads=x264_threads,
        )

        try:
            if use_nvenc and self._nvenc_semaphore is not None:
                with self._nvenc_semaphore:
                    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            else:
                subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return True
        except subprocess.CalledProcessError as e:
            err_snippet = e.stderr.decode("utf-8", errors="ignore")[:300]
            if use_nvenc and self.encoder_setting.strip().lower() == "auto":
                print(
                    f"[Cảnh báo NVENC shot {Path(output_clip_path).name}] "
                    f"Lỗi NVENC ({err_snippet.strip()[:120]}), tự động fallback sang libx264..."
                )
                fallback_cmd = self.build_render_shot_command(
                    image_path=image_path,
                    audio_path=audio_path,
                    output_clip_path=output_clip_path,
                    motion_type=motion_type,
                    duration=duration,
                    use_nvenc=False,
                    x264_threads=x264_threads,
                )
                try:
                    subprocess.run(fallback_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                    return True
                except subprocess.CalledProcessError as fe:
                    print(
                        f"[Lỗi render shot {output_clip_path} (fallback libx264)]: "
                        f"{fe.stderr.decode('utf-8', errors='ignore')[:300]}"
                    )
                    return False
            print(f"[Lỗi render shot {output_clip_path}]: {err_snippet}")
            return False

    @staticmethod
    def probe_duration(media_path: str):
        """Thời lượng thực của file (giây) theo ffprobe, None nếu không đo được."""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            media_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError):
            return None

    def concatenate_shots(self, clip_paths: list, output_video_path: str) -> bool:
        """
        Ghép danh sách các clip con thành 1 video hoàn chỉnh bằng stream copy.
        """
        out_dir = os.path.dirname(output_video_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        concat_txt = os.path.join(out_dir or ".", "concat_list.txt")

        with open(concat_txt, "w", encoding="utf-8") as f:
            for clip in clip_paths:
                # Chuẩn hóa đường dẫn cho ffmpeg
                abs_path = os.path.abspath(clip).replace("\\", "/")
                f.write(f"file '{abs_path}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_txt,
            "-c", "copy",
            output_video_path,
        ]

        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            if os.path.exists(concat_txt):
                os.remove(concat_txt)
            return True
        except subprocess.CalledProcessError as e:
            print(f"[Lỗi ghép video tổng hợp]: {e.stderr.decode('utf-8', errors='ignore')[:300]}")
            return False
