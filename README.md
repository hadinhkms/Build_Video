# CINESTORY - HỆ THỐNG BIẾN CHƯƠNG TRUYỆN THÀNH VIDEO ĐIỆN ẢNH YOUTUBE

Hệ thống tự động hóa chuyển thể văn bản một chương truyện thành video điện ảnh 2.5D hoàn chỉnh, giữ trọn **Raccord (Tính nhất quán nhân vật & bối cảnh)** và tối ưu **Giữ chân người xem YouTube (Audience Retention Rate)**.

---

## 🏗️ Kiến Trúc Hệ Thống (Multi-Renderer Engine)

Hệ thống hỗ trợ các bộ dựng và xuất hình (Renderers / Exporters):
1. **Remotion v4 (Chính - Khuyến nghị cho 2.5D Cinema):**
   - Dựng hình 2.5D Parallax đa lớp (Plate bối cảnh, Character Cutout, Foreground/Vignette).
   - Diễn xuất tự nhiên: nhịp thở ngực, chớp mắt ngẫu nhiên, trôi nhẹ góc đầu.
   - Nhép miệng phản hồi âm thanh (Audio-reactive envelope) cho nhân vật nói.
   - Hiệu ứng môi trường Canvas: mưa rơi kèm chớp giật điện ảnh.
   - Đo và cân bằng âm lượng tự động: EBU R128 (-14 LUFS, True Peak ≤ -1.5 dBTP).
2. **CapCut / JianYing Draft Exporter (Phase 5 - Biên tập siêu tốc & Tinh chỉnh thủ công):**
   - Xuất trực tiếp thư mục dự án CapCut Desktop (`draft_content.json`, `draft_info.json`).
   - Đầy đủ đa track: Plates bối cảnh, Voice TTS, Foley SFX, BGM ducking, Subtitle karaoke.
   - Mở ngay trong CapCut Desktop để gắn hiệu ứng trending, filter màu và render phần cứng GPU siêu tốc.
3. **FFmpeg Composer (Dự phòng Baseline v0):**
   - Bộ dựng hình dự phòng cổ điển sử dụng FFmpeg filter graph (Ken Burns zoom/pan).
   - Đảm bảo hệ thống vẫn luôn hoạt động ngay cả khi môi trường không có Node.js/Remotion.

---

## 📁 Cấu trúc Thư mục Dự án

```text
d:\_Short_film\
├── config/
│   ├── settings.json                   # Cấu hình video (1080p, 24fps), render concurrency, loudnorm
│   ├── characters.json                 # Lưu bộ mã DNA nhân vật & ảnh tham chiếu khuôn mặt
│   ├── environments.json               # Lưu bộ mỏ neo không gian & ánh sáng bối cảnh
│   ├── pronunciations.json             # Từ điển chuẩn hóa phát âm tiếng Việt (tên riêng, số, từ mượn)
│   ├── story_rules.json                # Luật kịch bản: 5 hồi, cỡ cảnh không trùng, nhịp cắt
│   └── youtube_template.json           # Mẫu tiêu đề, mô tả, hashtag, timestamps YouTube
├── remotion/                           # Phân hệ Web & Remotion v4 Engine
│   ├── src/                            # Compositions, Layers, Hooks & Shaders
│   ├── scripts/render.ts               # Render script sử dụng Node API (@remotion/bundler + @remotion/renderer)
│   └── package.json                    # Cấu hình Remotion, React 19, Tailwind v4
├── assets/
│   ├── characters/                     # Chứa ảnh khuôn mặt nhân vật gốc
│   ├── images/                         # Chứa ảnh bối cảnh minh họa
│   └── audio/                          # Kho nhạc nền BGM và tiếng động Foley
├── input/
│   ├── sample_chapter.txt              # Văn bản chương truyện mẫu
│   └── chapter_02.txt                  # Văn bản chương truyện thực nghiệm
├── packages/<chapter_id>/              # Gói prompt tạo ảnh 0đ và checklist tài sản
├── output/<chapter_id>/                # Kết quả đầu ra hoàn chỉnh
│   ├── video.mp4                       # File VIDEO MASTER thành phẩm (-14 LUFS, AAC 44.1kHz)
│   ├── video.srt                       # Phụ đề chuẩn YouTube (khớp timing từng câu thoại)
│   ├── youtube_metadata.json           # Tiêu đề SEO, mô tả có chapters, 10-15 tags
│   ├── thumbnail_base.png              # Ảnh nền thumbnail chuẩn 1280x720 (Lanczos)
│   ├── render_props.json               # Hợp đồng dữ liệu giữa Python và Remotion
│   └── render_report.json              # Báo cáo hiệu năng và thông số âm lượng
├── src/                                # Lõi xử lý Python
│   ├── core/                           # StateManager & Pydantic Data Models (RenderProps)
│   ├── story/                          # StoryParser (5 hồi, phân vai, tách lời thoại)
│   ├── audio/                          # TTS, Foley soundscape, ducking, loudnorm mastering
│   ├── visuals/                        # Raccord checker, plate selection, cutout rembg
│   ├── acting/                         # Face rig SSIM, audio envelope calculator
│   ├── export/                         # SRT exporter, clip fit planner
│   ├── packaging/                      # YouTube packager & thumbnail generator
│   └── render/                         # RemotionRunner (Node API subprocess orchestrator)
├── .agents/skills/create-story-video/  # Kỹ năng tự động hóa Antigravity Skill
└── run_pipeline.py                     # Entry point điều phối toàn bộ Pipeline
```

---

## 🚀 Hướng Dẫn Sử Dụng (2 Quy Trình)

### Cách 1: Sử dụng Antigravity Skill (Khuyến nghị trong IDE)

Gõ trực tiếp vào thanh chat IDE:
```text
/create-story-video input/sample_chapter.txt
```
Quy trình sẽ tự động thực hiện 2 lượt:
1. **Lượt 1 (Chuẩn bị):** Gắn nhãn kịch bản, tạo giọng đọc, xuất gói prompt tại `packages/<chapter_id>/`, dừng lại gửi checklist ảnh cho bạn.
2. **Lượt 2 (Sản xuất):** Tách nền tự động, dựng phân cảnh 2.5D, render và xuất bản video master kèm gói YouTube.

---

### Cách 2: Sử dụng Dòng Lệnh (CLI)

#### 1. Chạy từng giai đoạn (2-Pass Workflow)

**Bước 1: Chuẩn bị kịch bản & audio**
```powershell
python run_pipeline.py --renderer remotion --stage prepare --input input/sample_chapter.txt
```

**Bước 2: Render & Hoàn thiện video**
```powershell
python run_pipeline.py --renderer remotion --stage render --input input/sample_chapter.txt
```

#### 2. Các stage độc lập có thể gọi riêng
- `--stage script`: Bóc tách văn bản thành bảng phân cảnh `storyboard.json`.
- `--stage audio`: Tạo giọng đọc TTS tiếng Việt và tách cảnh dài.
- `--stage assets`: Chuẩn bị tài sản ảnh, tách nền cutout và kiểm tra raccord.
- `--stage props`: Xuất hợp đồng `render_props.json` cho Remotion.
- `--stage video`: Render video trung gian chất lượng cao.
- `--stage master`: Cân bằng âm lượng chuẩn YouTube (-14 LUFS) và mux final MP4.
- `--stage package`: Xuất file SRT, `youtube_metadata.json` và `thumbnail_base.png`.
- `--stage all`: Chạy liên tục từ đầu đến cuối (dùng ảnh dự phòng nếu thiếu ảnh).

---

## 🧪 Kiểm Thử Hệ Thống (Verification & Quality Gates)

Để đảm bảo hệ thống không bị lỗi ("không lủng") ở bất kỳ tầng nào:

```powershell
# Chạy toàn bộ 150+ unit tests & Gate tests của Python
python -m unittest discover -s tests

# Chạy toàn bộ test component & hook của Remotion
cd remotion; npm test
```

---

## 📚 Kho Tham Khảo & Nguồn Giải Pháp (Reference Sources)

Các dự án mã nguồn mở được dùng để đối chiếu cấu trúc, học hỏi kiến trúc timeline, render và an toàn dữ liệu (lưu trong thư mục `_ref_sources/`):
- **[capcut-cli (René Zander)](https://github.com/renezander030/capcut-cli.git)**: Tham khảo reverse-engineer format `draft_content.json` của CapCut/JianYing, xử lý timeline microsecond ($1\text{s} = 1\,000\,000\,\mu\text{s}$), cơ chế ghi file an toàn nguyên tử (`atomic-write.ts`), linter timeline (`lint.ts`), và OpenTimelineIO interchange (`interchange.ts`).
- **`remotion-cuongit-template`**: Khung cấu hình Remotion 4 + Tailwind v4 + Zod schema contract.
- **`auto-video-gen`**: Quy tắc phân vai giọng đọc, cấu trúc Antigravity skills, tuyển chọn SFX.
- **`auto-compare-video`**: Ý tưởng chuyển động breathing glow và VieNeu local TTS.

