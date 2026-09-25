import argparse
import json
import math
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
from src.audio.mastering import encode_without_mastering, master_loudness

# Khoảng đệm sau lời thoại để chuyển cảnh mượt
SHOT_TAIL_PAD_SEC = 0.6
# Giữ phụ đề thêm một chút sau từ cuối cùng để người xem kịp đọc hết
SUBTITLE_HOLD_SEC = 0.3

def format_srt_time(seconds: float) -> str:
    """Đổi số giây sang định dạng chuẩn SRT (HH:MM:SS,mmm), làm tròn tới mili giây."""
    total_ms = int(round(max(seconds, 0.0) * 1000))
    hrs, rem = divmod(total_ms, 3_600_000)
    mins, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

def plan_shot_duration(audio_duration: float, fps: int, min_duration: float) -> float:
    """Thời lượng shot = giọng đọc + đệm, tối thiểu min_duration, làm tròn lên số frame nguyên."""
    raw = max(audio_duration + SHOT_TAIL_PAD_SEC, min_duration)
    frames = math.ceil(raw * fps - 1e-6)
    return round(frames / fps, 4)

def build_srt_entries(clips: list) -> list:
    """
    clips: [{"text", "duration" (thời lượng THỰC của clip đã render), "words" ([{start, end}] tính trong clip)}].
    Mốc thời gian cộng dồn từ thời lượng thực nên SRT luôn khớp video đã ghép.
    Có mốc từng từ thì phụ đề hiện từ lúc bắt đầu nói tới hết câu (+ SUBTITLE_HOLD_SEC), không thì phủ cả clip.
    """
    entries = []
    clip_start = 0.0
    for idx, clip in enumerate(clips, start=1):
        words = clip.get("words") or []
        if words:
            start = clip_start + max(words[0]["start"], 0.0)
            end = clip_start + min(words[-1]["end"] + SUBTITLE_HOLD_SEC, clip["duration"])
        else:
            start, end = clip_start, clip_start + clip["duration"]
        entries.append(f"{idx}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{clip['text']}\n")
        clip_start += clip["duration"]
    return entries

def run_pipeline(chapter_file="input/sample_chapter.txt", output_name="final_chapter_video.mp4"):
    print("=" * 65)
    print("🎬 KHỞI ĐỘNG HỆ THỐNG BIẾN CHƯƠNG TRUYỆN THÀNH VIDEO ĐIỆN ẢNH")
    print("=" * 65)

    if not os.path.exists(chapter_file):
        print(f"[Lỗi] Không tìm thấy file đầu vào: {chapter_file}")
        return

    with open(chapter_file, "r", encoding="utf-8") as f:
        chapter_content = f.read().strip()

    with open("config/settings.json", "r", encoding="utf-8") as f:
        settings = json.load(f)
    fps = settings["video"]["fps"]
    shot_min = settings["visuals"]["shot_min_duration"]
    shot_max = settings["visuals"]["shot_max_duration"]

    # 1. BÓC TÁCH KỊCH BẢN PHÂN CẢNH (STORYBOARD)
    print("\n[Bước 1/5] 📜 Đang bóc tách kịch bản phân cảnh (Storyboard) & Khóa Raccord...")
    parser = StoryParser()
    storyboard = parser.parse_chapter_to_storyboard(chapter_content)

    storyboard_path = "output/storyboard.json"
    os.makedirs("output", exist_ok=True)
    with open(storyboard_path, "w", encoding="utf-8") as f:
        json.dump(storyboard, f, ensure_ascii=False, indent=2)
    print(f" -> Đã tạo {len(storyboard)} phân cảnh chuẩn raccord lưu tại: {storyboard_path}")

    # 2. TẠO GIỌNG ĐỌC AI & TÍNH THỜI LƯỢNG CHUẨN TỪNG SHOT
    print("\n[Bước 2/5] 🎙️ Đang tạo giọng đọc Edge-TTS tiếng Việt & đo thời lượng...")
    tts = TTSService()
    audio_dir = "assets/audio/shots"
    os.makedirs(audio_dir, exist_ok=True)

    for idx, shot in enumerate(storyboard):
        # Dấu "/" để storyboard.json (được commit) mở được trên mọi hệ điều hành
        audio_file = f"{audio_dir}/{shot['shot_id']}.mp3"
        duration = tts.generate_audio(shot["voiceover"], audio_file)

        shot_duration = plan_shot_duration(duration, fps, shot_min)
        shot["audio_file"] = audio_file
        shot["words_file"] = TTSService.words_path_for(audio_file)
        shot["duration"] = shot_duration
        print(f"   Shot {idx+1}/{len(storyboard)} [{shot['narrative_act']}]: '{shot['voiceover'][:30]}...' -> {shot_duration:.1f}s")
        if shot_duration > shot_max:
            print(f"   [Cảnh báo] Shot {shot['shot_id']} dài {shot_duration:.2f}s, vượt tối đa {shot_max}s — nên tách thành 2 shot")

    # Cập nhật lại storyboard với thông số thời lượng thật
    with open(storyboard_path, "w", encoding="utf-8") as f:
        json.dump(storyboard, f, ensure_ascii=False, indent=2)

    # 3. RENDER TỪNG CLIP VỚI HIỆU ỨNG MÁY QUAY KEN BURNS
    print("\n[Bước 3/5] 🎥 Đang render chuyển động máy quay (Ken Burns Motion) cho từng shot...")
    composer = VideoComposer()
    clip_dir = "output/clips"
    os.makedirs(clip_dir, exist_ok=True)

    rendered_clips = []
    default_image = "assets/characters/main_char_face.jpg"

    for idx, shot in enumerate(storyboard):
        # Ưu tiên ảnh theo từng scene nếu có, nếu chưa có thì dùng ảnh anchor
        specific_scene_img = f"assets/images/{shot['shot_id']}.jpg"
        source_img = specific_scene_img if os.path.exists(specific_scene_img) else default_image

        # .mov vì clip trung gian giữ audio PCM (xem VideoComposer.render_shot_clip)
        clip_out = os.path.join(clip_dir, f"{shot['shot_id']}.mov")
        success = composer.render_shot_clip(
            image_path=source_img,
            audio_path=shot["audio_file"],
            output_clip_path=clip_out,
            motion_type=shot.get("camera_motion", "zoom_in"),
            duration=shot["duration"]
        )
        if success:
            clip_duration = VideoComposer.probe_duration(clip_out) or shot["duration"]
            rendered_clips.append({
                "clip": clip_out,
                "text": shot["voiceover"],
                "duration": clip_duration,
                "words": TTSService.load_words(shot["audio_file"]),
            })
            print(f"   ✓ Đã render clip {shot['shot_id']} ({shot['camera_motion']}) -> {clip_duration:.3f}s")
        else:
            print(f"   ✗ Thất bại khi render clip {shot['shot_id']}")

    # Xuất phụ đề SRT theo thời lượng THỰC của các clip đã render (chỉ clip thành công)
    srt_path = os.path.join("output", output_name.replace(".mp4", ".srt"))
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(build_srt_entries(rendered_clips)))
    print(f" -> Đã xuất file phụ đề YouTube tự động: {srt_path}")

    # 4. GHÉP TOÀN BỘ CÁC CẢNH THÀNH VIDEO HOÀN CHỈNH
    print("\n[Bước 4/5] 🎞️ Đang ghép toàn bộ các phân cảnh thành video master hoàn chỉnh...")
    final_video_path = os.path.join("output", output_name)
    prenorm_path = os.path.join("output", Path(output_name).stem + ".prenorm.mov")
    success = composer.concatenate_shots([c["clip"] for c in rendered_clips], prenorm_path)

    # 5. CHUẨN HÓA ĐỘ LỚN ÂM THANH CHO YOUTUBE (1 LẦN, TRÊN BẢN MIX CUỐI)
    if success:
        print("\n[Bước 5/5] 🔊 Đang chuẩn hóa độ lớn âm thanh (loudnorm 2 lượt)...")
        audio_cfg = settings.get("audio", {})
        loudness = audio_cfg.get("loudness", {})
        measured = master_loudness(
            prenorm_path, final_video_path,
            target_i=loudness.get("integrated_lufs", -14.0),
            target_tp=loudness.get("true_peak_db", -1.0),
            target_lra=loudness.get("lra", 11.0),
            sample_rate=audio_cfg.get("sample_rate", 44100),
        )
        if measured is None:
            print("   [Cảnh báo] Chuẩn hóa thất bại, xuất bản với âm thanh chưa chuẩn hóa")
            success = encode_without_mastering(prenorm_path, final_video_path, audio_cfg.get("sample_rate", 44100))
        else:
            print(f"   Kết quả: I={measured.get('output_i')} LUFS, TP={measured.get('output_tp')} dBTP "
                  f"({measured.get('normalization_type')})")
        if success:
            os.remove(prenorm_path)

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
