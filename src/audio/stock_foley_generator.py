import os
import sys
import subprocess

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def generate_stock_foley_assets():
    """Tự động tạo bộ âm thanh Foley chuẩn bằng FFmpeg nếu chưa có."""
    foley_dir = "assets/audio/foley"
    bgm_dir = "assets/audio/bgm"
    os.makedirs(foley_dir, exist_ok=True)
    os.makedirs(bgm_dir, exist_ok=True)

    effects = {
        os.path.join(foley_dir, "rain_ambient.mp3"): [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "anoisesrc=c=pink:r=44100:a=0.08",
            "-t", "8", "-af", "lowpass=f=700",
            os.path.join(foley_dir, "rain_ambient.mp3")
        ],
        os.path.join(foley_dir, "wind_ambient.mp3"): [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "anoisesrc=c=brown:r=44100:a=0.06",
            "-t", "8", "-af", "bandpass=f=350:width_type=h:w=200",
            os.path.join(foley_dir, "wind_ambient.mp3")
        ],
        os.path.join(foley_dir, "heartbeat_suspense.mp3"): [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "sine=f=55:r=44100",
            "-t", "6", "-af", "volume='if(lt(mod(t,1.2),0.18),1.0,0.0)':eval=frame,lowpass=f=120",
            os.path.join(foley_dir, "heartbeat_suspense.mp3")
        ],
        os.path.join(foley_dir, "thunder_rumble.mp3"): [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "anoisesrc=c=brown:r=44100:a=0.15",
            "-t", "5", "-af", "lowpass=f=180,afade=t=in:ss=0:d=0.5,afade=t=out:st=3:d=2.0",
            os.path.join(foley_dir, "thunder_rumble.mp3")
        ],
        os.path.join(bgm_dir, "dark_ambient_drone.mp3"): [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "sine=f=65:r=44100",
            "-t", "60", "-af", "volume=0.3,lowpass=f=200",
            os.path.join(bgm_dir, "dark_ambient_drone.mp3")
        ]
    }

    for path, cmd in effects.items():
        if not os.path.exists(path):
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                print(f"[Audio Generator] Đã khởi tạo âm thanh: {path}")
            except Exception as e:
                print(f"[Lỗi tạo audio {path}]: {e}")

if __name__ == "__main__":
    generate_stock_foley_assets()
