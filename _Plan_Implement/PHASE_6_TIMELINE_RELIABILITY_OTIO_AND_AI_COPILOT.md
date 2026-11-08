# KẾ HOẠCH CHI TIẾT - PHASE 6

## CHUẨN HÓA ĐỘ TIN CẬY TIMELINE, ĐỔI CHUẨN MỞ OTIO & AI AGENT CO-PILOT

*(Mã tài liệu: PLAN_PHASE_6_TIMELINE_AND_OTIO · rev 1 · 2026-11-09)*  
*(Học hỏi giải pháp độ tin cậy và chuẩn mở từ `_ref_sources/capcut-cli/`)*

---

## 1. MỤC TIÊU & BỐI CẢNH (CONTEXT & OBJECTIVES)

### 1.1. Bối cảnh
Khi phát triển hệ thống sản xuất video tự động từ truyện dài, các lỗi phổ biến làm gãy pipeline thường là:
- File trạng thái (`storyboard.json` hoặc draft) bị hỏng (corrupted) khi tiến trình bị gián đoạn đột ngột (mất điện, kill process, hết RAM).
- Lệch timeline âm thanh và hình ảnh (desync drift) do làm tròn số lẻ giữa frame rate và sample rate.
- Thiếu các công cụ chẩn đoán môi trường (Doctor) dẫn tới việc render thất bại giữa chừng mà không rõ nguyên nhân (thiếu font, thiếu FFmpeg codecs, lỗi đường dẫn).
- Đóng kín trong một định dạng duy nhất, thiếu khả năng chuyển giao timeline sang các phần mềm dựng phim chuẩn điện ảnh như DaVinci Resolve hoặc Adobe Premiere Pro.

### 1.2. Giải pháp kế thừa từ `capcut-cli`
1. **Atomic File Write + Backup `.bak`** (từ `atomic-write.ts`): Mọi thao tác ghi đè trạng thái và render props đều ghi vào file tạm `.tmp` trước, tạo bản backup `.bak`, sau đó mới rename atomic để chống hỏng file 100%.
2. **Timeline Linter & Gap Detector** (từ `lint.ts`): Module quét timeline kiểm tra tính toàn vẹn: phát hiện chồng lấn track ngoài ý muốn, khoảng lặng chết (silent gap), âm lượng vượt ngưỡng (clipping), văn bản phụ đề tràn viền.
3. **OpenTimelineIO (OTIO) Interchange** (từ `interchange.ts`): Xuất định dạng chuẩn mở OTIO để người dùng có thể mở dự án trên DaVinci Resolve, Adobe Premiere Pro, Final Cut Pro.
4. **Hệ thống chẩn đoán môi trường (`doctor.py`)** (từ `doctor.ts`): Cung cấp lệnh `python run_pipeline.py doctor` kiểm tra toàn bộ toolchain (FFmpeg, Node.js, Remotion, CapCut draft path, GPU acceleration, TTS endpoints).
5. **AI Agent Co-pilot Interface**: Định dạng đặc tả các thao tác chỉnh sửa video thành schema rõ ràng (`command-specs.ts`) để AI Agent trong IDE có thể thực thi các lệnh tinh chỉnh theo yêu cầu của người dùng.

---

## 2. THIẾT KẾ KỸ THUẬT & KIẾN TRÚC TỆP

```text
d:\_Short_film\
├── src/
│   ├── core/
│   │   └── atomic_io.py                # [mới] Bộ ghi file an toàn nguyên tử (atomic write + auto .bak)
│   ├── export/
│   │   ├── timeline_linter.py          # [mới] Bộ kiểm tra timeline, phát hiện lệch nhịp và lỗi cảnh
│   │   └── otio_exporter.py            # [mới] Xuất timeline sang chuẩn mở OpenTimelineIO (.otio)
│   └── diagnostics/
│       └── doctor.py                   # [mới] Bộ chẩn đoán môi trường hệ thống (FFmpeg, Node, GPU, TTS...)
├── tests/
│   ├── test_atomic_io.py               # [mới] Kiểm tra cơ chế ghi atomic và phục hồi file backup
│   ├── test_timeline_linter.py         # [mới] Kiểm tra khả năng phát hiện lỗi timeline
│   ├── test_otio_exporter.py           # [mới] Kiểm tra cấu trúc file .otio xuất ra
│   └── test_gate6_acceptance.py        # [mới] Test Gate 6 tích hợp
└── _ref_sources/capcut-cli/            # [tham khảo] atomic-write.ts, lint.ts, interchange.ts, doctor.ts
```

---

## 3. DANH SÁCH CÔNG VIỆC CHI TIẾT (TASKS)

### Task 6.1: Cơ chế ghi file Atomic & Backup (`src/core/atomic_io.py`)
- Hiện thực hóa hàm `atomic_write_json(file_path, data, create_backup=True)`:
  - Ghi dữ liệu vào file tạm cùng thư mục: `<file>.tmp.<uuid>`.
  - Nếu file đích đã tồn tại, copy thành `<file>.bak`.
  - Thực hiện `os.replace` nguyên tử từ file tạm sang file đích.
- Tích hợp vào `StateManager.save()` và exporter.

### Task 6.2: Bộ kiểm thử & rà soát Timeline (`src/export/timeline_linter.py`)
- Quét qua danh sách các shot và audio:
  - **Check Gap:** Cảnh báo nếu khoảng cách giữa 2 shot âm thanh thoại > 1.5 giây mà không có Foley/BGM chuyển cảnh.
  - **Check Overlap:** Đảm bảo không có 2 clip thoại nào bị đè lên nhau trên cùng một track.
  - **Check Bounds:** Mốc thời gian của từ cuối trong subtitle không được vượt quá thời lượng của shot.
  - **Check Assets:** Kiểm tra kích thước ảnh bối cảnh phải đạt tối thiểu 1080p, tỉ lệ không bị méo.

### Task 6.3: Bộ xuất OpenTimelineIO (`src/export/otio_exporter.py`)
- Tạo file `.otio` (JSON-based schema của Pixar/ASWF):
  - Định nghĩa `Timeline`, `Track` (Video & Audio), `Clip`, `LinearTimeWarp` (Speed).
  - Map toàn bộ Media References từ `output/<chapterId>/...`.
  - Cho phép người dùng chạy: `python run_pipeline.py --export-otio`.

### Task 6.4: Công cụ chẩn đoán hệ thống (`src/diagnostics/doctor.py`)
- Lệnh chạy: `python run_pipeline.py doctor`.
- Báo cáo chi tiết:
  - FFmpeg & ffprobe: Version, hỗ trợ hardware acceleration (`h264_nvenc`, `hevc_nvenc`, `qsv`).
  - Node.js & npm: Version Node ($\ge 18$), trạng thái cài đặt Remotion và `capcut-cli`.
  - CapCut Desktop: Trạng thái cài đặt trên máy, thư mục draft tồn tại hay chưa.
  - Python Environment: Phiên bản các thư viện lõi (Pydantic, edge-tts, rembg, pillow).
  - Voice Services: Kiểm tra kết nối mạng tới Edge-TTS và trạng thái API Vbee (nếu có).

### Task 6.5: Nâng cấp Skill AI Agent Co-pilot (`.agents/skills/create-story-video/`)
- Bổ sung khả năng hội thoại điều chỉnh:
  - "Tăng âm lượng nhạc nền ở Hồi 2 thêm 3dB".
  - "Đổi ảnh bối cảnh cảnh 4 thành ảnh rừng ban đêm".
  - "Rút ngắn cảnh dạo đầu còn 3 giây".
- Agent sẽ gọi `timeline_linter` và tự động cập nhật timeline mà không cần chạy lại toàn bộ từ đầu.

---

## 4. TIÊU CHUẨN NGHIỆM THU (GATE 6 ACCEPTANCE)

1. **Atomic Resilience Test:** Giả lập ngắt tiến trình đột ngột trong khi ghi, hệ thống phải tự động phục hồi từ `.bak` mà không mất dữ liệu.
2. **Linter Accuracy:** Linter bắt được chính xác 100% các ca vi phạm biên thời gian, thiếu tài sản, đè track được cố tình đưa vào trong bộ test fixture.
3. **OTIO Import Verification:** File `.otio` sinh ra từ kịch bản mẫu hợp lệ theo đặc tả OpenTimelineIO.
4. **Doctor Complete Diagnostic:** Lệnh `python run_pipeline.py doctor` trả về mã thoát `0` và in báo cáo màu trực quan về toàn bộ hệ thống.
