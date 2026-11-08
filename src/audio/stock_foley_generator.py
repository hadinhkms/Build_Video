import os
import sys
import subprocess
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def generate_stock_foley_assets():
    """Tự động tạo bộ âm thanh Foley chuẩn theo nhóm bằng FFmpeg nếu chưa có."""
    base_foley_dir = Path("assets/audio/foley")
    bgm_dir = Path("assets/audio/bgm")

    # Tạo các thư mục nhóm
    categories = ["rain", "wind", "thunder", "heartbeat", "door", "footsteps"]
    for cat in categories:
        (base_foley_dir / cat).mkdir(parents=True, exist_ok=True)
    bgm_dir.mkdir(parents=True, exist_ok=True)

    # Di chuyển file cũ từ thư mục phẳng foley/ nếu có
    legacy_moves = [
        ("rain_ambient.mp3", "rain/rain_ambient.mp3"),
        ("wind_ambient.mp3", "wind/wind_ambient.mp3"),
        ("thunder_rumble.mp3", "thunder/thunder_rumble.mp3"),
        ("heartbeat_suspense.mp3", "heartbeat/heartbeat_suspense.mp3"),
    ]
    for old_name, new_rel in legacy_moves:
        old_path = base_foley_dir / old_name
        new_path = base_foley_dir / new_rel
        if old_path.exists() and not new_path.exists():
            old_path.rename(new_path)
            print(f"[Foley] Đã chuyển {old_name} -> {new_rel}")
        elif old_path.exists() and new_path.exists():
            old_path.unlink()

    effects = {
        str(base_foley_dir / "rain" / "rain_ambient.mp3"): [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "anoisesrc=c=pink:r=44100:a=0.08",
            "-t", "8", "-af", "lowpass=f=700",
            str(base_foley_dir / "rain" / "rain_ambient.mp3")
        ],
        str(base_foley_dir / "wind" / "wind_ambient.mp3"): [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "anoisesrc=c=brown:r=44100:a=0.06",
            "-t", "8", "-af", "bandpass=f=350:width_type=h:w=200",
            str(base_foley_dir / "wind" / "wind_ambient.mp3")
        ],
        str(base_foley_dir / "heartbeat" / "heartbeat_suspense.mp3"): [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "sine=f=55:r=44100",
            "-t", "6", "-af", "volume='if(lt(mod(t,1.2),0.18),1.0,0.0)':eval=frame,lowpass=f=120",
            str(base_foley_dir / "heartbeat" / "heartbeat_suspense.mp3")
        ],
        str(base_foley_dir / "thunder" / "thunder_rumble.mp3"): [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "anoisesrc=c=brown:r=44100:a=0.15",
            "-t", "5", "-af", "lowpass=f=180,afade=t=in:ss=0:d=0.5,afade=t=out:st=3:d=2.0",
            str(base_foley_dir / "thunder" / "thunder_rumble.mp3")
        ],
        str(base_foley_dir / "door" / "door_placeholder.mp3"): [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "sine=f=180:r=44100",
            "-t", "1.5", "-af", "volume='if(lt(t,0.8),0.6*sin(2*PI*5*t),0.0)':eval=frame,lowpass=f=300,afade=t=out:st=1.0:d=0.5",
            str(base_foley_dir / "door" / "door_placeholder.mp3")
        ],
        str(base_foley_dir / "footsteps" / "footsteps_placeholder.mp3"): [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "anoisesrc=c=pink:r=44100:a=0.1",
            "-t", "2.0", "-af", "volume='if(lt(mod(t,0.6),0.15),0.8,0.0)':eval=frame,bandpass=f=800:width_type=h:w=400",
            str(base_foley_dir / "footsteps" / "footsteps_placeholder.mp3")
        ],
        str(bgm_dir / "dark_ambient_drone.mp3"): [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "sine=f=65:r=44100",
            "-t", "60", "-af", "volume=0.3,lowpass=f=200",
            str(bgm_dir / "dark_ambient_drone.mp3")
        ],
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

