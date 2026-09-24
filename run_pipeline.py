import argparse
import json
import os
import sys
from pathlib import Path

# Đảm bảo in tiếng Việt và emoji mượt mà trên console Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.story_parser import StoryParser
from src.tts_service import TTSService
from src.video_composer import VideoComposer

def format_srt_time(seconds: float) -> str:
    """Đổi số giây sang định dạng chuẩn SRT (HH:MM:SS,mmm)."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

def run_pipeline(chapter_file="input/sample_chapter.txt", output_name="final_chapter_video.mp4"):
    print("=" * 65)
    print("🎬 KHỞI ĐỘNG HỆ THỐNG BIẾN CHƯƠNG TRUYỆN THÀNH VIDEO ĐIỆN ẢNH")
    print("=" * 65)

    if not os.path.exists(chapter_file):
        print(f"[Lỗi] Không tìm thấy file đầu vào: {chapter_file}")
        return

    with open(chapter_file, "r", encoding="utf-8") as f:
        chapter_content = f.read().strip()

    # 1. BÓC TÁCH KỊCH BẢN PHÂN CẢNH (STORYBOARD)
    print("\n[Bước 1/4] 📜 Đang bóc tách kịch bản phân cảnh (Storyboard) & Khóa Raccord...")
    parser = StoryParser()
    storyboard = parser.parse_chapter_to_storyboard(chapter_content)
    
    storyboard_path = "output/storyboard.json"
    os.makedirs("output", exist_ok=True)
    with open(storyboard_path, "w", encoding="utf-8") as f:
        json.dump(storyboard, f, ensure_ascii=False, indent=2)
    print(f" -> Đã tạo {len(storyboard)} phân cảnh chuẩn raccord lưu tại: {storyboard_path}")

    # 2. TẠO GIỌNG ĐỌC AI & TÍNH THỜI LƯỢNG CHUẨN TỪNG SHOT
    print("\n[Bước 2/4] 🎙️ Đang tạo giọng đọc Edge-TTS tiếng Việt & đo thời lượng...")
    tts = TTSService()
    audio_dir = "assets/audio/shots"
    os.makedirs(audio_dir, exist_ok=True)

    current_time = 0.0
    srt_entries = []

    for idx, shot in enumerate(storyboard):
        audio_file = os.path.join(audio_dir, f"{shot['shot_id']}.mp3")
        duration = tts.generate_audio(shot["voiceover"], audio_file)
        
        # Thêm khoảng đệm nhỏ để chuyển cảnh mượt
        shot_duration = max(duration + 0.6, 4.0)
        shot["audio_file"] = audio_file
        shot["duration"] = shot_duration
        print(f"   Shot {idx+1}/{len(storyboard)} [{shot['narrative_act']}]: '{shot['voiceover'][:30]}...' -> {shot_duration:.1f}s")

        # Tạo mục phụ đề SRT
        start_srt = format_srt_time(current_time)
        end_srt = format_srt_time(current_time + shot_duration)
        srt_entries.append(f"{idx+1}\n{start_srt} --> {end_srt}\n{shot['voiceover']}\n")
        current_time += shot_duration

    # Cập nhật lại storyboard với thông số thời lượng thật
    with open(storyboard_path, "w", encoding="utf-8") as f:
        json.dump(storyboard, f, ensure_ascii=False, indent=2)

    # Xuất file phụ đề SRT
    srt_path = os.path.join("output", output_name.replace(".mp4", ".srt"))
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_entries))
    print(f" -> Đã xuất file phụ đề YouTube tự động: {srt_path}")

    # 3. RENDER TỪNG CLIP VỚI HIỆU ỨNG MÁY QUAY KEN BURNS
    print("\n[Bước 3/4] 🎥 Đang render chuyển động máy quay (Ken Burns Motion) cho từng shot...")
    composer = VideoComposer()
    clip_dir = "output/clips"
    os.makedirs(clip_dir, exist_ok=True)

    rendered_clips = []
    default_image = "assets/characters/main_char_face.jpg"

    for idx, shot in enumerate(storyboard):
        # Ưu tiên ảnh theo từng scene nếu có, nếu chưa có thì dùng ảnh anchor
        specific_scene_img = f"assets/images/{shot['shot_id']}.jpg"
        source_img = specific_scene_img if os.path.exists(specific_scene_img) else default_image

        clip_out = os.path.join(clip_dir, f"{shot['shot_id']}.mp4")
        success = composer.render_shot_clip(
            image_path=source_img,
            audio_path=shot["audio_file"],
            output_clip_path=clip_out,
            motion_type=shot.get("camera_motion", "zoom_in"),
            duration=shot["duration"]
        )
        if success:
            rendered_clips.append(clip_out)
            print(f"   ✓ Đã render clip {shot['shot_id']} ({shot['camera_motion']})")
        else:
            print(f"   ✗ Thất bại khi render clip {shot['shot_id']}")

    # 4. GHÉP TOÀN BỘ CÁC CẢNH THÀNH VIDEO HOÀN CHỈNH
    print("\n[Bước 4/4] 🎞️ Đang ghép toàn bộ các phân cảnh thành video master hoàn chỉnh...")
    final_video_path = os.path.join("output", output_name)
    success = composer.concatenate_shots(rendered_clips, final_video_path)

    if success and os.path.exists(final_video_path):
        print("\n" + "=" * 65)
        print(f"🎉 XUẤT BẢN THÀNH CÔNG VIDEO ĐIỆN ẢNH!")
        print(f"📍 File Video Master: {os.path.abspath(final_video_path)}")
        print(f"📍 File Phụ đề SRT:   {os.path.abspath(srt_path)}")
        print(f"📍 Bảng Storyboard:   {os.path.abspath(storyboard_path)}")
        print("=" * 65)
    else:
        print("[Lỗi] Không thể tạo video master cuối cùng.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline tạo video truyện audio YouTube chuẩn điện ảnh")
    parser.add_argument("--input", default="input/sample_chapter.txt", help="Đường dẫn file văn bản chương truyện")
    parser.add_argument("--output", default="final_chapter_video.mp4", help="Tên file video đầu ra (.mp4)")
    args = parser.parse_args()

    run_pipeline(args.input, args.output)
