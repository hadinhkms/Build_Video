import json
import os
import subprocess
from pathlib import Path

class VideoComposer:
    def __init__(self, settings_path="config/settings.json"):
        with open(settings_path, "r", encoding="utf-8") as f:
            self.settings = json.load(f)
        self.v_cfg = self.settings.get("video", {})
        self.width = self.v_cfg.get("width", 1920)
        self.height = self.v_cfg.get("height", 1080)
        self.fps = self.v_cfg.get("fps", 24)

    def _get_ken_burns_filter(self, motion_type: str, duration: float) -> str:
        """Sinh chuỗi filter FFmpeg zoompan mô phỏng chuyển động máy quay điện ảnh."""
        frames = int(duration * self.fps)
        if motion_type == "zoom_out":
            # Bắt đầu từ 1.15 thu nhỏ dần về 1.0
            return (
                f"scale=4000:-1,zoompan=z='if(lte(zoom,1.0),1.18,max(1.001,zoom-0.0010))':"
                f"d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={self.width}x{self.height}:fps={self.fps}"
            )
        elif motion_type == "pan_left":
            return (
                f"scale=4000:-1,zoompan=z=1.12:x='if(lte(on,1),0,min(iw-iw/zoom,x+1.2))':"
                f"y='ih/2-(ih/zoom/2)':d={frames}:s={self.width}x{self.height}:fps={self.fps}"
            )
        elif motion_type == "pan_right":
            return (
                f"scale=4000:-1,zoompan=z=1.12:x='if(lte(on,1),iw-iw/zoom,max(0,x-1.2))':"
                f"y='ih/2-(ih/zoom/2)':d={frames}:s={self.width}x{self.height}:fps={self.fps}"
            )
        else: # default: zoom_in
            return (
                f"scale=4000:-1,zoompan=z='min(zoom+0.0010,1.18)':"
                f"d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={self.width}x{self.height}:fps={self.fps}"
            )

    def render_shot_clip(self, image_path: str, audio_path: str, output_clip_path: str, motion_type: str = "zoom_in", duration: float = 5.0) -> bool:
        """
        Ghép 1 ảnh + 1 file audio thành 1 đoạn video clip với chuyển động Ken Burns.
        """
        os.makedirs(os.path.dirname(output_clip_path), exist_ok=True)
        vf_filter = self._get_ken_burns_filter(motion_type, duration)

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_path,
            "-i", audio_path,
            "-vf", vf_filter,
            "-c:v", "libx264",
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            output_clip_path
        ]
        
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"[Lỗi render shot {output_clip_path}]: {e.stderr.decode('utf-8', errors='ignore')[:300]}")
            return False

    def concatenate_shots(self, clip_paths: list, output_video_path: str) -> bool:
        """
        Ghép danh sách các clip con thành 1 video mp4 hoàn chỉnh.
        """
        os.makedirs(os.path.dirname(output_video_path), exist_ok=True)
        concat_txt = os.path.join(os.path.dirname(output_video_path), "concat_list.txt")
        
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
            output_video_path
        ]

        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            if os.path.exists(concat_txt):
                os.remove(concat_txt)
            return True
        except subprocess.CalledProcessError as e:
            print(f"[Lỗi ghép video tổng hợp]: {e.stderr.decode('utf-8', errors='ignore')[:300]}")
            return False
