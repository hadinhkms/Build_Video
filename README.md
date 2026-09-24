# HƯỚNG DẪN SỬ DỤNG HỆ THỐNG BIẾN CHƯƠNG TRUYỆN THÀNH VIDEO ĐIỆN ẢNH YOUTUBE

Hệ thống tự động hóa chuyển thể văn bản 1 chương truyện thành video điện ảnh hoàn chỉnh, giữ trọn **Raccord (Tính nhất quán nhân vật & bối cảnh)** và tối ưu **Giữ chân người xem YouTube (Retention Rate)**.

---

## 📁 Cấu trúc Thư mục Dự án

```
d:\_Short_film\
├── config/
│   ├── settings.json         # Cấu hình video (1080p, 24fps), âm thanh, tốc độ đọc
│   ├── characters.json       # Lưu bộ mã DNA nhân vật & ảnh tham chiếu khuôn mặt
│   └── environments.json     # Lưu bộ mỏ neo không gian & ánh sáng bối cảnh
├── assets/
│   ├── characters/           # Chứa ảnh khuôn mặt nhân vật gốc (main_char_face.jpg)
│   ├── images/               # Chứa ảnh minh họa từng cảnh (shot_00_hook.jpg, shot_01.jpg...)
│   └── audio/shots/          # Chứa file giọng đọc AI từng cảnh (.mp3)
├── input/
│   └── sample_chapter.txt    # File văn bản chương truyện đầu vào
├── output/
│   ├── clips/                # Các đoạn clip con với hiệu ứng chuyển động máy quay
│   ├── storyboard.json       # Bảng phân cảnh chi tiết chuẩn điện ảnh
│   ├── final_chapter_video.srt # File phụ đề chạy chữ chuẩn YouTube
│   └── final_chapter_video.mp4 # File VIDEO THÀNH PHẨM MASTER
├── src/
│   ├── story_parser.py       # Tự động chia cảnh (Shot 4-6s, Hook 15s, gắn DNA & mỏ neo)
│   ├── tts_service.py        # Tạo giọng đọc Edge-TTS tiếng Việt tự nhiên & đo thời lượng
│   └── video_composer.py     # Dựng video FFmpeg (hiệu ứng Ken Burns, ghép nhạc & audio)
├── _Plan_Implement/          # Thư mục chứa 5 kế hoạch chi tiết từng Phase
│   ├── README.md             # Điều phối danh mục kế hoạch
│   ├── PHASE_0_...md         # Kế hoạch chi tiết Phase 0 -> Phase 4
├── RULES_AUDIO_TO_VIDEO.md   # Bộ quy tắc chuẩn SOP
└── run_pipeline.py           # File chạy toàn bộ quy trình chỉ bằng 1 câu lệnh
```

---

## 🚀 Cách Sử Dụng Nhanh

### Bước 1: Chuẩn bị nội dung truyện
Mở file [input/sample_chapter.txt](file:///d:/_Short_film/input/sample_chapter.txt) và dán nội dung chương truyện của bạn vào đây.

### Bước 2: Thêm ảnh khuôn mặt nhân vật (Tùy chọn)
Nếu bạn có ảnh khuôn mặt người thật muốn giữ cho nhân vật chính:
* Lưu ảnh vào [assets/characters/main_char_face.jpg](file:///d:/_Short_film/assets/characters/main_char_face.jpg).

### Bước 3: Chạy tạo video tự động
Mở Terminal/PowerShell tại thư mục `d:\_Short_film` và chạy:
```powershell
python run_pipeline.py
```
Hoặc tùy biến file đầu vào và tên video xuất ra:
```powershell
python run_pipeline.py --input input/chuong_1.txt --output chuong_1_final.mp4
```

---

## 🎬 Các tính năng tự động được tích hợp:
1. **Hook Giữ chân 15s:** Tự động trích xuất câu thoại nghẹt thở nhất đưa lên đầu.
2. **Quy tắc đổi cảnh 4–6s:** Không để cảnh đứng yên nhàm chán.
3. **Hiệu ứng Máy quay Ken Burns:** Zoom-in (căng thẳng), Zoom-out (cô đơn), Pan trái/phải (chuyển động).
4. **Giọng đọc tiếng Việt tự nhiên:** Tích hợp Microsoft Edge-TTS (Nam Minh / Hoài My) không tốn phí, không cần API key.
5. **Tự động xuất phụ đề SRT:** Sẵn sàng tải lên YouTube để tăng SEO và lượt xem.
