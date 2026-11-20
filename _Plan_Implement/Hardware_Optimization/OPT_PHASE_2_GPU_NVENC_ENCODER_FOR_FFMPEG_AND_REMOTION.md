# KẾ HOẠCH CHI TIẾT — OPT PHASE 2

## TĂNG TỐC MÃ HÓA GPU NVIDIA NVENC (GTX 1650 TURING) CHO CẢ REMOTION & FFMPEG

*(Mã tài liệu: PLAN_HW_OPT_PHASE_2 · rev 1 · 2026-11-19)*  
*(Phụ thuộc: OPT Phase 1)*

---

## 1. BỐI CẢNH & PHÁT HIỆN KỸ THUẬT QUAN TRỌNG

Kiểm chứng trực tiếp trên máy và mã nguồn `@remotion/renderer@4.0.407`:

1. **GTX 1650 trên máy này là bản `0x1F0A` (TU106 GDDR6 — Turing NVENC thế hệ 6):**
   - Đã kiểm thử chạy thật: `ffmpeg -c:v h264_nvenc -preset p4 -cq 18 -bf 2` → **`EXIT=0`** (hỗ trợ đầy đủ B-frames và Spatial AQ cho chất lượng nén tiệm cận `libx264` nhưng tốc độ gấp nhiều lần và **0% tải CPU**).
2. **Tại sao bật `hardwareAcceleration: "if-possible"` trong Remotion KHÔNG có tác dụng trên Windows:**
   - Trong `remotion/node_modules/@remotion/renderer/dist/get-codec-name.js` (dòng 43–84), Remotion chỉ bật phần cứng khi `process.platform === 'darwin'` (`h264_videotoolbox`), và luôn trả về `libx264` cho Windows lẫn `codec: "h264-mkv"`.
   - Thêm vào đó, `ffmpeg.exe` đóng gói sẵn trong `@remotion/compositor-win32-x64-msvc` chỉ biên dịch `libx264`, không có `h264_nvenc`.
3. **Giải pháp cầu nối sạch đã xác minh không xung đột DLL:**
   - `@remotion/compositor-win32-x64-msvc` dùng các DLL FFmpeg 6/7 (`avcodec-60/61.dll`, `avutil-58/59.dll`, `avformat-60/61.dll`, `avfilter-9/10.dll`, `swresample-4/5.dll`, `swscale-7/8.dll`).
   - FFmpeg hệ thống (`C:\Program Files\ffmpeg-master-latest-win64-gpl-shared\bin`) dùng bộ DLL FFmpeg 8 (`avcodec-62.dll`, `avutil-60.dll`, `avformat-62.dll`, `avfilter-11.dll`, `swresample-6.dll`, `swscale-9.dll`).
   - **Không có bất kỳ tệp DLL nào trùng tên!** Do đó có thể tạo thư mục `hw-bin/` trên NVMe `C:` ghép `remotion.exe` (từ `@remotion/compositor`) với `ffmpeg.exe`/`ffprobe.exe` hệ thống, truyền vào `renderMedia({ binariesDirectory, ffmpegOverride })` để Remotion pipe thẳng khung hình từ Chromium vào **`h264_nvenc`** trên GTX 1650!
4. **Nút thắt ở `--renderer ffmpeg` (`src/video_composer.py`):**
   - Hiện ghi cứng `-c:v libx264` (bỏ qua `settings.json`) và chạy vòng lặp tuần tự 1 shot/lần trong `stage_video_master.py`.
   - Khi chuyển sang `h264_nvenc` + worker pool song song, cần khống chế **Semaphore ≤ 4 phiên NVENC đồng thời** để tôn trọng giới hạn phiên của driver GeForce và 4 GB VRAM.

---

## 2. DANH MỤC TỆP TẠO MỚI & CHỈNH SỬA

```text
d:\_Short_film\
├── config/
│   └── settings.json                       # [sửa] Thêm render.encoder, render.nvenc_preset, render.nvenc_cq, render.ffmpeg_workers
├── src/
│   ├── render/
│   │   ├── encoder_probe.py                # [mới] Kiểm chứng sống h264_nvenc / B-frames / max concurrent sessions / fallback libx264
│   │   └── remotion_runner.py              # [sửa] Truyền cấu hình encoder (auto/nvenc/libx264) & nvenc_cq vào render.ts
│   ├── video_composer.py                   # [sửa] Hỗ trợ h264_nvenc + libx264 từ settings, tối ưu scale zoompan, hỗ trợ gọi song song
│   ├── pipeline/
│   │   └── stage_video_master.py           # [sửa] Song song hóa render_shot_clip bằng ThreadPoolExecutor có Semaphore NVENC + NVMe scratch
│   └── audio/
│       └── mastering.py                    # [sửa] Đọc/ghi qua NVMe scratch, giữ nguyên -c:v copy & loudnorm 2-pass -14 LUFS
├── remotion/
│   └── scripts/
│       ├── ffmpeg-bridge.ts                # [mới] Tạo NVMe hw-bin/ an toàn (kiểm tra va chạm DLL động) + hàm buildNvencOverride()
│       └── render.ts                       # [sửa] Kích hoạt binariesDirectory + ffmpegOverride khi encoder=nvenc, fallback êm về libx264
└── tests/
    ├── test_encoder_probe.py               # [mới] Unit test probe NVENC & fallback khi giả lập không có GPU
    ├── test_video_composer_parallel.py     # [mới] Test song song hóa shot, thứ tự concat, giới hạn semaphore
    └── test_opt_gate2.py                   # [mới] Gate 2: đối chiếu SSIM/PSNR NVENC vs libx264, duration ±1f, -14 LUFS
```

---

## 3. THIẾT KẾ KỸ THUẬT CHI TIẾT (TASKS)

### Task 2.1: Bộ thăm dò Encoder phần cứng thực tế (`src/render/encoder_probe.py`)
Không chỉ đọc `ffmpeg -encoders` (có thể liệt kê `h264_nvenc` ngay cả khi máy không có GPU), mà chạy phép thử mã hóa thật 1 khung hình vào `null` (< 300 ms, cache kết quả trong phiên):
- Kiểm tra `h264_nvenc` cơ bản (`-f lavfi -i color=black:s=256x256:r=24:d=0.1 -c:v h264_nvenc -f null -`).
- Kiểm tra hỗ trợ B-frames (`-bf 2`) để phân biệt Turing/Ada (TU106/RTX → bật `-bf 2`) với Volta (TU117 cũ → đặt `-bf 0`).
- Trả về `EncoderCapability`:
  - `selected_encoder`: `"h264_nvenc"` hoặc `"libx264"`
  - `supports_bframes`: `bool`
  - `ffmpeg_bin_dir`: `Optional[Path]` (thư mục chứa `ffmpeg.exe` hệ thống có NVENC)
  - `max_parallel_nvenc`: `int` (mặc định `3` trên GPU ≤ 4 GB VRAM để chừa VRAM an toàn; tối đa `4`).
- Tôn trọng cấu hình người dùng:
  - `render.encoder == "libx264"` → ép dùng CPU `libx264`.
  - `render.encoder == "nvenc"` → dùng NVENC (báo lỗi rõ nếu không khả dụng).
  - `render.encoder == "auto"` (mặc định) → tự bật `h264_nvenc` nếu probe PASS, ngược lại fallback về `libx264`.

### Task 2.2: Cầu nối Remotion NVENC an toàn DLL (`remotion/scripts/ffmpeg-bridge.ts`)
Xây dựng hàm `prepareRemotionNvencBridge({ scratchDir, systemFfmpegDir, nvencPreset, cq, supportsBframes })`:
1. **Kiểm tra va chạm DLL động:**
   - Liệt kê toàn bộ `*.dll` trong `@remotion/compositor-win32-x64-msvc` (bỏ qua `ffmpeg.exe`, `ffprobe.exe`) và trong `systemFfmpegDir`.
   - Tính tập giao (intersection) không phân biệt hoa thường.
   - **Nếu tập giao khác rỗng** (ví dụ tương lai nâng cấp Remotion dùng chung `avcodec-62.dll`) → **tự động hủy cầu nối và trả về `null`** (fallback về bundled `libx264`), tuyệt đối không gây crash DLL!
2. **Dựng `hw-bin/` trên NVMe `C:`** (chỉ làm lại khi phiên bản FFmpeg hoặc Remotion thay đổi):
   - Copy `remotion.exe` + các DLL của `@remotion/compositor` vào `<scratchDir>/hw-bin/`.
   - Copy `ffmpeg.exe`, `ffprobe.exe` + các DLL của `systemFfmpegDir` vào `<scratchDir>/hw-bin/`.
   - Kiểm chứng nhanh: chạy `<hw-bin>/remotion.exe --version` và `<hw-bin>/ffmpeg.exe -h encoder=h264_nvenc`.
3. **Viết `ffmpegOverride` chuẩn xác cho `renderMedia()`:**
   - Chỉ biến đổi khi `args` chứa cặp `-c:v libx264` (tức giai đoạn `pre-stitcher` hoặc `stitcher` khi chưa pre-encode); **giữ nguyên 100%** khi `args` dùng `-c:v copy` (giai đoạn mux video + audio PCM vào `video.prenorm.mkv`).
   - Ánh xạ tham số:
     - Xóa: `["-c:v", "libx264"]`, `["-crf", <val>]`, `["-preset", <val>]`.
     - Chèn:
       ```ts
       "-c:v", "h264_nvenc",
       "-preset", nvencPreset,    // mặc định "p5" (cân bằng chất lượng cao & tốc độ ~250+ fps trên GTX 1650)
       "-tune", "hq",
       "-rc", "vbr",
       "-cq", String(cq),         // mặc định crf + 1 (ví dụ 19 tương đương chất lượng CRF 18 của x264)
       "-b:v", "0",
       "-spatial-aq", "1",
       "-aq-strength", "8",
       ...(supportsBframes ? ["-bf", "2"] : ["-bf", "0"])
       ```
   - Giữ nguyên `-pix_fmt yuv420p` và audio codec `pcm-16` của `h264-mkv` (bảo toàn Quyết định D7).
4. **Cơ chế tự phục hồi (Auto-Retry Fallback):**
   - Trong `render.ts`, nếu `renderMedia()` với NVENC Bridge trả lỗi liên quan đến NVENC (`OpenEncodeSessionEx`, `Cannot load nvcuda`, exit code FFmpeg) → tự động log cảnh báo và chạy lại 1 lần bằng bundled `libx264` + `x264Preset: "faster"`.

### Task 2.3: Song song hóa & GPU-hóa `VideoComposer` (`--renderer ffmpeg`)
Cập nhật `src/video_composer.py` và `src/pipeline/stage_video_master.py`:
1. **Đọc cấu hình encoder thay vì ghi cứng:**
   - Lấy `encoder`, `crf`, `preset`, `nvenc_preset`, `nvenc_cq` từ `config/settings.json`.
   - Khi dùng `h264_nvenc`: `-c:v h264_nvenc -preset p5 -tune hq -rc vbr -cq 19 -b:v 0 -bf 2 -spatial-aq 1 -pix_fmt yuv420p -c:a pcm_s16le`.
   - Khi dùng CPU `libx264`: `-c:v libx264 -preset faster -crf 18 -threads 4 -pix_fmt yuv420p -c:a pcm_s16le` (giới hạn `-threads 4` mỗi worker để tránh oversubscription khi chạy nhiều worker song song trên 28 nhân!).
2. **Tối ưu filter `zoompan`:**
   - Thay `scale=2560:-1` cố định bằng độ phân giải tỉ lệ sát biên độ zoom thực tế (`max_zoom = 1.18` → `scale=2304:-2` cho zoom, `2160:-2` cho pan `1.12`) để giảm ~20–28% số pixel `zoompan` phải nội suy mỗi frame mà không giảm độ nét.
3. **Render song song các shot (`stage_video_master.py`):**
   - Dùng `ThreadPoolExecutor`:
     - Nếu `h264_nvenc`: `max_workers = min(4, cap.max_parallel_nvenc)` (mặc định `3` trên GTX 1650 4 GB VRAM) — vừa tận dụng song song CPU cho `zoompan` vừa không vượt ngưỡng phiên NVENC.
     - Nếu `libx264`: `max_workers = min(12, max(2, physical_cores // 2))` (mỗi worker dùng 4 luồng x264 → tổng 48 luồng trên 56T Dual Xeon).
   - **Bảo toàn thứ tự tuyệt đối:** Thu kết quả theo chỉ số `idx` ban đầu trước khi xuất `SRT` và gọi `concatenate_shots()`.
   - Toàn bộ `clips/*.mov` và `<out>.prenorm.mov` ghi vào **NVMe Scratch (`C:`)** (từ OPT Phase 1).

### Task 2.4: Tối ưu đường dữ liệu Mastering (`src/audio/mastering.py`)
- Bước `master` đọc trực tiếp `prenorm.mkv` / `prenorm.mov` từ NVMe `C:`, xuất `video.master.tmp.mp4` trên NVMe `C:` (giữ nguyên `-c:v copy`, 2-pass `loudnorm` `-14 LUFS`, AAC 192k 1 lần duy nhất), sau đó gọi `ScratchManager.promote_to_output()` chép bản hoàn thiện về `D:\_Short_film\output\<chapterId>\`.
- Thêm flag `-threads 0` cho bước decode/filter audio.

---

## 4. TIÊU CHUẨN NGHIỆM THU (GATE 2 ACCEPTANCE)

1. **Remotion NVENC thực chiến:** Render `sample_chapter` (240 frames) qua `render.ts` với `encoder="auto"`:
   - Log xác nhận sử dụng `h264_nvenc` (không phải `libx264`).
   - `ffprobe` trên `video.prenorm.mkv` xác nhận video stream là `h264` (`yuv420p`) và audio stream là `pcm_s16le`.
   - CPU sử dụng cho tiến trình `ffmpeg.exe` gần ~0–5%; `nvidia-smi dmon` xác nhận khối NVENC hoạt động và VRAM đỉnh $\le 3.5\text{ GB}$.
2. **Chất lượng hình ảnh tương đương (Visual Parity):**
   - So sánh cùng đoạn 240 frame giữa `h264_nvenc (p5, cq=19, bf=2)` và `libx264 (crf=18)` bằng bộ lọc `ssim` của FFmpeg: **SSIM trung bình $\ge 0.985$**, dung lượng tệp không phình quá 1.35×.
3. **FFmpeg Renderer song song:** Chạy `--renderer ffmpeg` trên `sample_chapter` hoàn tất với tốc độ nhanh hơn bản tuần tự ít nhất **3×**, thứ tự shot & thời lượng SRT khớp chính xác 100%, không gặp lỗi vượt giới hạn phiên NVENC.
4. **Kiểm tra Fallback an toàn:** Chạy test giả lập `encoder="libx264"` và giả lập va chạm DLL → pipeline tự fallback êm ái, mã thoát `0`, video đầu ra hợp lệ.
5. **Bảo toàn bất biến:** Video sau `master` đạt thời lượng khớp $\pm 1$ frame và loudness $-14\text{ LUFS} \pm 1$, True Peak $\le -1.5\text{ dBTP}$.
