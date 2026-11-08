# KẾ HOẠCH CHI TIẾT - PHASE 5

## BỘ XUẤT DỰ ÁN CAPCUT DESKTOP & CẦU NỐI ĐA TRACK (CAPCUT DRAFT EXPORTER)

*(Mã tài liệu: PLAN_PHASE_5_CAPCUT_EXPORTER · rev 1 · 2026-11-09)*  
*(Tham khảo trực tiếp từ kho mã nguồn: `_ref_sources/capcut-cli/` — https://github.com/renezander030/capcut-cli.git)*

---

## 1. MỤC TIÊU & BỐI CẢNH (CONTEXT & OBJECTIVES)

### 1.1. Bối cảnh & Vấn đề giải quyết
Hiện tại, CineStory dựng hình qua 2 bộ renderer:
1. **Remotion v4**: Dựng 2.5D Parallax, Canvas shaders, Audio Envelope mouth-rig. Nhược điểm: ngốn tài nguyên CPU/GPU (Chromium headless), thời gian render video dài (10-30 phút) khá lâu, và không cho phép can thiệp chỉnh sửa thủ công (Human-in-the-loop) trực quan sau khi pipeline hoàn tất.
2. **FFmpeg Composer**: Bộ dựng dự phòng cổ điển (Ken Burns). Nhược điểm: thiếu tính linh hoạt và khó tinh chỉnh layer.

**Giải pháp đột phá học hỏi từ `renezander030/capcut-cli`:**
- Thay vì chỉ xuất ra video phẳng `.mp4`, pipeline CineStory sẽ xuất trực tiếp **một thư mục Dự án CapCut Desktop hoàn chỉnh** (`draft_content.json` và `draft_info.json`).
- Người dùng chỉ cần mở phần mềm CapCut Desktop (hoặc JianYing 剪映) là toàn bộ kịch bản đã nằm sẵn trên các track:
  - **Track 1 (Visual/Plates):** Ảnh bối cảnh và cutout nhân vật căn đúng in-out point từng shot.
  - **Track 2 (TTS Voice):** Giọng đọc từng câu thoại khớp mili-giây.
  - **Track 3 (Foley SFX):** Tiếng động sấm sét, mưa rơi, tiếng mở cửa, bước chân...
  - **Track 4 (BGM):** Nhạc nền đã tính toán ducking âm lượng.
  - **Track 5 (Subtitles):** Phụ đề chữ động khớp từng từ (karaoke/subtitles).
- **Lợi ích to lớn:**
  - **Render siêu tốc:** Tận dụng bộ mã hóa phần cứng GPU (Nvidia NVENC, Intel QuickSync, Apple Silicon) của CapCut Desktop, xuất video 1080p/4K trong tích tắc.
  - **Tự do sáng tạo:** Creator có thể dễ dàng gắn thêm hiệu ứng chuyển cảnh, sticker, filter màu cinematic, auto-reframe, lồng nhạc trending sẵn có của CapCut.

### 1.2. Mục tiêu kỹ thuật Phase 5
1. **Engine Native CapCut Draft Exporter (Python):** Viết module thuần Python `src/export/capcut_exporter.py` sinh `draft_content.json` và `draft_info.json` theo đúng schema của CapCut v5/v6 mà không cần cài thêm dependency nặng.
2. **Chuẩn hóa Timebase Microseconds:** Quy đổi toàn bộ mốc thời gian từ khung hình Remotion (24fps) và giây âm thanh sang đơn vị chuẩn của CapCut: **1 giây = 1,000,000 µs (microseconds)**.
3. **Multi-Track Sequencer:** Sắp xếp các tài nguyên vào đúng track, tính toán in-point, out-point, source_timerange, target_timerange và speed curve.
4. **Auto Draft Discovery & Deployment:** Tự động phát hiện thư mục lưu draft CapCut trên Windows (`%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft\`) để người dùng mở CapCut là thấy ngay dự án mới xuất hiện ở trang chủ.
5. **CLI & Skill Integration:** Hỗ trợ cờ `--renderer capcut`, `--stage capcut`, hoặc xuất song song `--export-capcut` trong lệnh chạy pipeline.

---

## 2. THIẾT KẾ KỸ THUẬT & KIẾN TRÚC TỆP

### 2.1. Cấu trúc thư mục bổ sung

```text
d:\_Short_film\
├── src/
│   ├── export/
│   │   ├── capcut_exporter.py          # [mới] Bộ sinh draft CapCut (draft_content.json & draft_info.json)
│   │   ├── capcut_models.py            # [mới] Pydantic models mô phỏng cấu trúc Draft CapCut
│   │   └── capcut_locator.py           # [mới] Tự động tìm thư mục Projects của CapCut Desktop trên Windows
├── tests/
│   ├── test_capcut_exporter.py         # [mới] Kiểm tra logic sinh json, microsecond math, track structure
│   └── test_gate5_acceptance.py        # [mới] Test Gate 5: Mở được draft hợp lệ từ kịch bản mẫu
└── _ref_sources/capcut-cli/            # [tham khảo] Kho mã nguồn mẫu để đối soát cấu trúc JSON
```

### 2.2. Đặc tả dữ liệu CapCut Draft (`draft_content.json`)
*(Rút ra từ `_ref_sources/capcut-cli/src/draft.ts` và `materials-register.ts`)*

1. **Timebase:**
   $$\text{duration\_us} = \text{round}(\text{duration\_sec} \times 1\,000\,000)$$
   $$\text{fps} = 24 \quad (\text{hoặc theo } \text{config/settings.json})$$
2. **Materials Container:**
   - `videos`: Danh sách ảnh bối cảnh (`photo_mode: true`), cutout nhân vật, clip video minh họa.
   - `audios`: File âm thanh giọng đọc TTS, nhạc nền BGM, âm thanh hiệu ứng Foley.
   - `texts`: Các đoạn văn bản phụ đề (nội dung, kích thước font, màu chữ, vị trí tọa độ).
   - `speeds`: Thông số tốc độ phát (`speed: 1.0`).
   - `canvases`: Tỉ lệ khung hình (16:9 hoặc 9:16).
3. **Tracks Layering:**
   - `tracks[0]` (Type: `video`): Main Plate / Background ảnh.
   - `tracks[1]` (Type: `video`): Overlay Character Cutout (nếu có 2 lớp).
   - `tracks[2]` (Type: `audio`): Voice TTS chính.
   - `tracks[3]` (Type: `audio`): Foley SFX (mưa, sấm, cửa...).
   - `tracks[4]` (Type: `audio`): Background Music (BGM).
   - `tracks[5]` (Type: `text`): Subtitle chữ đồng bộ theo mốc từ.

---

## 3. DANH SÁCH CÔNG VIỆC CHI TIẾT (TASKS)

### Task 5.1: Xây dựng Data Models cho CapCut Draft (`src/export/capcut_models.py`)
- Định nghĩa các lớp Pydantic: `CapCutTimerange`, `CapCutSegment`, `CapCutTrack`, `CapCutMaterialVideo`, `CapCutMaterialAudio`, `CapCutMaterialText`, `CapCutDraftContent`, `CapCutDraftInfo`.
- Đảm bảo cơ chế serialize JSON chính xác, không dùng `None` ở các trường CapCut yêu cầu chuỗi rỗng `""` hoặc list rỗng `[]`.

### Task 5.2: Bộ định vị CapCut Draft trên máy cục bộ (`src/export/capcut_locator.py`)
- Kiểm tra đường dẫn mặc định trên Windows:
  `$env:LOCALAPPDATA\CapCut\User Data\Projects\com.lveditor.draft\`
  (và bản JianYing: `$env:LOCALAPPDATA\JianyingPro\User Data\Projects\com.lveditor.draft\`).
- Hỗ trợ lưu trữ local dự phòng tại: `output/<chapterId>/capcut_draft/` nếu máy chưa cài đặt CapCut Desktop.

### Task 5.3: Hiện thực hóa CapCut Exporter (`src/export/capcut_exporter.py`)
- Đọc dữ liệu từ `RenderProps` và `Storyboard` của CineStory.
- Map từng `ShotProps`:
  - Lấy file audio TTS từ `output/<chapterId>/audio/<shot_id>.mp3`.
  - Lấy file plate ảnh từ `remotion/public/chapters/<chapterId>/...`.
  - Tính toán `target_timerange`: `start` tích lũy liên tục theo microsecond.
  - Chuyển `captions` thành `texts` và tạo text track bám theo mốc phát âm.
  - Tích hợp Foley plan & BGM plan vào audio tracks kèm thông số `volume` phù hợp với ducking.
- Ghi file `draft_content.json` và `draft_info.json`.

### Task 5.4: Tích hợp vào Pipeline chính (`run_pipeline.py`)
- Bổ sung tùy chọn `--renderer capcut` (bên cạnh `remotion` và `ffmpeg`).
- Thêm cờ `--export-capcut`: Cho phép sau khi chạy xong stage `props` hoặc `render`, tự động xuất thêm CapCut draft vào máy.
- Bổ sung vào Antigravity Skill `/create-story-video`.

---

## 4. TIÊU CHUẨN NGHIỆM THU (GATE 5 ACCEPTANCE)

Tạo file kiểm thử tự động `tests/test_gate5_acceptance.py`:
1. **Schema Check:** File `draft_content.json` sinh ra phải có đủ các trường bắt buộc (`tracks`, `materials`, `duration`, `fps`).
2. **Timeline Integrity:** Tổng thời lượng các segments trên track Video chính và track Voice chính phải khớp nhau, sai số không quá $1\,000\,\mu\text{s}$ ($0.001\text{ s}$).
3. **Asset Validation:** Tất cả đường dẫn file trong `materials.videos` và `materials.audios` phải trỏ tới các file thực tế đang tồn tại trên ổ đĩa.
4. **Desktop Compatibility:** Draft mở trực tiếp trên CapCut Desktop hiển thị đầy đủ timeline, không báo lỗi "Project Corrupted".
