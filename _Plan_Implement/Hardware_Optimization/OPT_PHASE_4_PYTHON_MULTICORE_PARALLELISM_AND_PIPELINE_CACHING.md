# KẾ HOẠCH CHI TIẾT — OPT PHASE 4

## SONG SONG HÓA ĐA NHÂN PYTHON (28C/56T NUMA), CACHE ENVELOPE & TỔNG NGHIỆM THU E2E

*(Mã tài liệu: PLAN_HW_OPT_PHASE_4 · rev 1 · 2026-11-19)*  
*(Phụ thuộc: OPT Phase 2, OPT Phase 3)*

---

## 1. BỐI CẢNH & CÁC NÚT THẮT PYTHON CÒN LẠI

Sau khi render hình ảnh (Remotion & FFmpeg) đã đạt tốc độ tối đa nhờ NVMe + NVENC + 16–24 worker + tối ưu React/Canvas, các stage tiền xử lý Python sẽ trở thành phần chiếm tỉ trọng lớn nhất trong tổng thời gian từ file `.txt` tới `video.mp4` — đặc biệt trên chương dài 40–80 câu:

1. **Stage `audio` chạy Edge-TTS tuần tự & chạy lại `stage script` thừa:**
   - `src/pipeline/stage_script_audio.py:34`: `run_stage_audio()` luôn gọi lại `run_stage_script(ctx)`, khiến `--stage all` phân tích kịch bản 2 lần liên tiếp.
   - `src/pipeline/stage_script_audio.py:53-96`: Vòng lặp `for shot` gọi `asyncio.run(...)` một câu một lần → 50 câu mất 50 vòng chờ mạng WebSocket tuần tự!
2. **Stage `props` giải mã FFmpeg lặp lại nhiều lần và thiếu cache cho `AudioEnvelopeCalculator`:**
   - `src/export/scene_builder.py:183`: Mỗi cảnh con sau khi tách hình (`split_long_shot`) đều gọi `compute_shot_envelope()` trên cùng 1 file `.mp3` → giải mã toàn bộ file `.mp3` bằng `ffmpeg` **2–3 lần trùng lặp** và **chạy tuần tự**, không có cache đĩa!
3. **`rembg` chạy ONNX cross-NUMA trên Dual Xeon:**
   - `src/visuals/cutout.py:40`: `rembg.new_session(model_name)` dùng mặc định của `onnxruntime`, tự kéo luồng dàn trải cả 2 socket Xeon (56 luồng) gây nghẽn băng thông bộ nhớ liên socket (QPI/UPI). Ngoài ra duyệt thư mục `characters/` hoàn toàn tuần tự.
4. **Khuếch đại ghi trên USB HDD `D:` & `ffprobe`/`ffmpeg` tuần tự:**
   - `src/export/crop_utils.py:8-19`: `copy_file_if_different()` luôn dùng `shutil.copy2` nhân bản tệp âm thanh/ảnh/clip ngay trên cùng ổ USB `D:` thay vì tạo hardlink NTFS (`os.link`) tức thì.
   - `src/visuals/asset_packager.py:186-198`: Cắt `voice.wav` cho gói Hybrid bằng `ffmpeg` tuần tự từng cảnh.

---

## 2. DANH MỤC TỆP TẠO MỚI & CHỈNH SỬA

```text
d:\_Short_film\
├── config/
│   └── settings.json                       # [sửa] Thêm audio.tts_concurrency, visuals.rembg_threads, visuals.rembg_device
├── src/
│   ├── audio/
│   │   ├── edge_client.py                  # [sửa] Thêm hàm async batch_generate_edge() có Semaphore & exponential backoff
│   │   └── envelope.py                     # [sửa] Thêm cache đĩa .envelope.json theo SHA1 + batch_compute_envelopes() đa luồng
│   ├── pipeline/
│   │   └── stage_script_audio.py           # [sửa] Chạy Edge-TTS song song có giới hạn + bỏ re-parse script thừa khi đã có state
│   ├── export/
│   │   ├── crop_utils.py                   # [sửa] Hardlink-first (os.link) khi cùng phân vùng NTFS, fallback copy2; cache ffprobe
│   │   └── scene_builder.py                # [sửa] Tiền tính & deduplicate envelope song song theo từng audio_file duy nhất
│   └── visuals/
│       ├── cutout.py                       # [sửa] Ghim ONNX intra_op_num_threads theo 1 socket NUMA (14T) + tùy chọn GPU + song song đa nhân vật
│       └── asset_packager.py               # [sửa] Song song hóa cắt voice.wav bằng ThreadPoolExecutor
├── scripts/
│   └── benchmark_e2e_report.py             # [mới] Đo toàn bộ pipeline theo từng stage (script/audio/assets/props/video/master/package)
└── tests/
    ├── test_async_tts_batch.py             # [mới] Test song song hóa Edge-TTS, giữ nguyên thứ tự & cache SHA1
    ├── test_envelope_cache.py              # [mới] Test deduplicate split shot, cache .envelope.json & độ chính xác bit-exact
    ├── test_cutout_numa.py                 # [mới] Test cấu hình ONNX SessionOptions & fallback provider
    └── test_opt_gate4_e2e.py               # [mới] Gate 4: E2E full pipeline + đối chiếu 5 bất biến kỹ thuật
```

---

## 3. THIẾT KẾ KỸ THUẬT CHI TIẾT (TASKS)

### Task 4.1: Song song hóa Edge-TTS có kiểm soát (`src/audio/edge_client.py`, `src/pipeline/stage_script_audio.py`)
1. **Chống thừa công ở `run_stage_audio`:**
   - Chỉ gọi `run_stage_script(ctx)` nếu `ctx.storyboard_path` chưa tồn tại hoặc được chạy độc lập `--stage audio` khi file input mới hơn `storyboard.json`. Tránh parse lại 2 lần trong `--stage all` / `--stage prepare`.
2. **Async Batch Edge-TTS (`asyncio.Semaphore`):**
   - Trong `edge_client.py`, giữ nguyên `generate_edge_with_retry()` (tương thích ngược 100% với unit test cũ), bổ sung `generate_edge_batch_async(tasks, max_concurrency=5)`.
   - Mặc định `audio.tts_concurrency = 5` (đủ nhanh gấp 4×–5× nhưng lịch sự với endpoint Microsoft Edge, tránh HTTP 429/rate-limit).
   - **Cơ chế an toàn:**
     - Các câu đã trúng cache SHA1 hoàn tất tức thì không chiếm slot semaphore.
     - Các câu có `...` (`dramatic_pause`) chạy từng đoạn con song song rồi ghép FFmpeg trong `asyncio.to_thread()`.
     - Vẫn giữ nguyên thứ tự `sb.shots` và logic tách hình (`split_long_shot`) + cỡ cảnh không trùng sau khi tất cả tác vụ TTS hoàn tất.
   - Với `--tts vbee`: giữ giới hạn `concurrency = 2` (tôn trọng rate-limit API Vbee).

### Task 4.2: Cache & Song song hóa `AudioEnvelopeCalculator` (`src/audio/envelope.py`, `src/export/scene_builder.py`)
1. **Khử giải mã trùng lặp (Deduplication):**
   - Trong `scene_builder.py`, gom danh sách các đường dẫn `audio_file` **duy nhất** cần tính khẩu hình miệng (những cảnh có `is_dialogue == True` và `speaker == on_screen_character_id`).
   - Thay vì gọi FFmpeg 3 lần cho 3 cảnh con tách ra từ cùng 1 câu thoại dài, chỉ tính `full_envelope` **đúng 1 lần** cho file gốc rồi `slice_envelope()` cho từng cảnh con (O(1) cắt mảng Python).
2. **Cache bền vững trên đĩa:**
   - Lưu `<audio_stem>.envelope.json` cạnh file audio, kèm metadata `{ "source_sha1": ..., "fps": 24, "target_sr": 16000, "envelope": [...] }`.
   - Lần chạy `stage props` tiếp theo (ví dụ sau khi người dùng bổ sung ảnh) đạt **cache hit 100%** (< 5 ms).
3. **Song song hóa khi cache miss:**
   - Dùng `ThreadPoolExecutor(max_workers=min(8, physical_cores))` giải mã FFmpeg + tính RMS NumPy song song cho các file audio chưa có cache.

### Task 4.3: Tinh chỉnh NUMA cho `rembg` / ONNX Runtime (`src/visuals/cutout.py`)
1. **Cấu hình `onnxruntime.SessionOptions` chuẩn Dual Xeon (2 socket × 14 nhân):**
   - Đọc `cores_per_socket` từ `HardwareProfile` (trên máy này = `14`).
   - Thiết lập:
     ```python
     sess_opts = ort.SessionOptions()
     sess_opts.intra_op_num_threads = min(14, max(4, cores_per_socket))
     sess_opts.inter_op_num_threads = 1
     sess_opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
     sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
     ```
   - Truyền `sess_opts` vào `rembg.new_session(self.model_name, sess_opts=sess_opts, providers=providers)`.
2. **Tự động phát hiện GPU Provider (tùy chọn nâng cao, không phá vỡ `rembg[cpu]`):**
   - Cấu hình `visuals.rembg_device`: `"auto" | "cpu" | "cuda" | "dml"`.
   - Khi `"auto"`: kiểm tra `ort.get_available_providers()`. Nếu máy có cài `onnxruntime-gpu` (`CUDAExecutionProvider`) hoặc `onnxruntime-directml` (`DmlExecutionProvider`) và VRAM trống ≥ 1.5 GB → ưu tiên GPU; hiện tại máy cài `rembg[cpu]` (`CPUExecutionProvider`) → tự dùng CPU 14 luồng gọn trong 1 socket NUMA (nhanh & ổn định hơn mặc định 56 luồng cross-NUMA).
3. **Song song đa nhân vật:**
   - Khi có $\ge 2$ nhân vật mới chưa có cache `base_cutout.png`:
     - Chế độ CPU trên máy 2 socket: chạy `ThreadPoolExecutor(max_workers=2)` (mỗi socket xử lý 1 nhân vật).
     - Chế độ GPU 4 GB VRAM: giữ `max_workers=1` để tránh tràn VRAM.

### Task 4.4: Hardlink-First trên NTFS `D:` & Song song hóa `ffprobe` / `asset_packager`
1. **`copy_file_if_different(src, dst)` (`src/export/crop_utils.py`):**
   - Khi `src` và `dst` nằm trên cùng ổ đĩa NTFS (`src.stat().st_dev == dst.parent.stat().st_dev`) và file đích là chỉ đọc (tài sản trong `remotion/public/chapters/`):
     - Thử `os.link(src, dst)` trước (0 byte ghi xuống đĩa USB HDD `D:`, thực thi < 1 ms!).
     - Nếu đích đã tồn tại cùng inode (`st_ino`) → bỏ qua ngay.
     - Nếu `OSError` (khác ổ đĩa hoặc không hỗ trợ link) → fallback sạch về `shutil.copy2`.
   - Lưu ý: Khi `asset_optimizer` (OPT Phase 3) cần resize ảnh thì ghi file mới riêng vào đích, không sửa ảnh gốc qua hardlink!
2. **Song song hóa `ffprobe` & cắt `voice.wav` (`src/visuals/asset_packager.py`):**
   - Dùng `ThreadPoolExecutor(max_workers=8)` cắt `voice.wav` cho các shot hybrid và thêm cache LRU theo `(path, mtime, size)` cho `get_media_duration()`.

### Task 4.5: Bộ Benchmark & Báo cáo E2E toàn diện (`scripts/benchmark_e2e_report.py`)
Viết script chạy đo toàn bộ 7 stage (`script`, `audio`, `assets`, `props`, `video`, `master`, `package`) trên `input/sample_chapter.txt` và `input/chapter_02.txt`:
- Ghi báo cáo JSON + bảng Markdown so sánh **Trước vs Sau** từng stage (`output/<chapterId>/e2e_perf_report.json`):
  - Thời gian từng stage (giây)
  - `fps_render`, `encoder`, `concurrency`, `gl`, `scratch_drive`
  - Peak RAM (GB), Peak VRAM (MB)
  - Kết quả kiểm tra 5 bất biến kỹ thuật (frame delta, LUFS, True Peak, SRT sync, determinism).

---

## 4. TIÊU CHUẨN NGHIỆM THU (GATE 4 ACCEPTANCE — TỔNG KẾT 4 PHASE)

1. **Tốc độ các stage Python:**
   - Stage `audio` (cold cache) nhanh hơn tuần tự $\ge 3\times$, kết quả `storyboard.json` và `.words.json` giữ đúng thứ tự và nội dung 100%.
   - Stage `props` (warm cache) hoàn tất trong **< 1 giây** trên `sample_chapter`; không chạy `ffmpeg` trùng lặp cho cảnh con tách hình.
   - `rembg` khởi tạo thành công với `intra_op_num_threads <= 14`, không gây cross-NUMA thrashing.
2. **Bảo toàn 100% bộ test hiện hữu + test mới:**
   - `python -m unittest discover -s tests` → **100% PASS** (bao gồm toàn bộ 150+ test gốc + test OPT Phase 1–4).
   - `cd remotion; npm run typecheck; npm test` → **100% PASS**.
3. **Nghiệm thu E2E thực tế trên 2 chương (`sample_chapter.txt` & `chapter_02.txt`):**
   - Xuất đủ `video.mp4`, `video.srt`, `youtube_metadata.json`, `thumbnail_base.png`, `render_report.json`, `e2e_perf_report.json`.
   - Tổng thời lượng khớp `render_props.json` trong sai số $\pm 1$ frame.
   - Loudness bản cuối: $-14.0 \pm 1.0\text{ LUFS}$, True Peak $\le -1.5\text{ dBTP}$, luồng audio là AAC 44.1 kHz (mã hóa đúng 1 lần).
   - Không còn rác file tạm tồn đọng trong thư mục NVMe scratch `work/<chapterId>/`.
4. **Cập nhật tài liệu & Skill:**
   - Cập nhật `README.md` và `.agents/skills/create-story-video/SKILL.md` ghi chú các tùy chọn mới (`render.encoder`, `render.scratch_dir`, `benchmark_hardware.py`).
