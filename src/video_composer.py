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
        # round() thay vì int(): duration đã căn theo frame, int() có thể hụt 1 frame do sai số float
        frames = round(duration * self.fps)
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
        Clip dài đúng `duration`: audio được đệm im lặng (apad) thay vì cắt theo -shortest,
        nếu không clip sẽ chỉ dài bằng file mp3 và lệch khỏi storyboard/SRT.
        Audio để PCM (clip phải là .mov): mỗi clip AAC mang ~21ms priming, ghép -c copy sẽ
        cộng dồn làm giọng trễ dần so với hình. AAC chỉ được mã hóa 1 lần ở bước mastering.
        Không dùng .mkv: Matroska làm tròn timestamp về 1ms, video ra không còn đúng 24fps (CFR).
        """
        os.makedirs(os.path.dirname(output_clip_path), exist_ok=True)
        vf_filter = self._get_ken_burns_filter(motion_type, duration)

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_path,
            "-i", audio_path,
            "-vf", vf_filter,
            "-af", "apad",
            "-c:v", "libx264",
            "-t", f"{duration:.3f}",
            "-pix_fmt", "yuv420p",
            "-c:a", "pcm_s16le",
            output_clip_path
        ]
        
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"[Lỗi render shot {output_clip_path}]: {e.stderr.decode('utf-8', errors='ignore')[:300]}")
            return False

    @staticmethod
    def probe_duration(media_path: str):
        """Thời lượng thực của file (giây) theo ffprobe, None nếu không đo được."""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            media_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError):
            return None

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
