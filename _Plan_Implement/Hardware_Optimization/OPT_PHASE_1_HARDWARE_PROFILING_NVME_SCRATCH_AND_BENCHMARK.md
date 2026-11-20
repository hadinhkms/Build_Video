# KẾ HOẠCH CHI TIẾT — OPT PHASE 1

## NHẬN DIỆN PHẦN CỨNG, CHUYỂN SCRATCH/CACHE LÊN NVMe `C:` & PHÁ TRẦN CONCURRENCY REMOTION

*(Mã tài liệu: PLAN_HW_OPT_PHASE_1 · rev 1 · 2026-11-19)*  
*(Phụ thuộc: Không — nền tảng cho OPT Phase 2, 3, 4)*

---

## 1. BỐI CẢNH & VẤN ĐỀ CẦN GIẢI QUYẾT

Qua đo kiểm trực tiếp trên máy hiện tại (**Dual Xeon E5-2680 v4 28C/56T · 64 GB RAM · GTX 1650 4 GB · `C:` NVMe 530 GB trống · `D:` USB HDD WD My Book**), có 3 nút thắt hạ tầng đang kìm hãm toàn bộ pipeline:

1. **Nút thắt ổ cứng ngoài USB `D:`:** Toàn bộ repo nằm trên `D:` (USB HDD). Khi render, pipeline đang ghi `output/<chapterId>/video.prenorm.mkv` (audio PCM 16-bit + H.264), `clips/*.mov`, chạy 2 lượt `loudnorm`, và đọc asset tĩnh cho hàng chục tab Chromium từ ổ USB có độ trễ seek cao.
2. **Trần `concurrency = 8` ẩn của Remotion:** Khi `config/settings.json` để `"concurrency": null`, hàm `resolveConcurrency()` trong `remotion/node_modules/@remotion/renderer/dist/get-concurrency.js` (dòng 8) tự cắt ở `Math.min(8, maxCpus / 2)` → chỉ dùng **8 trên 56 luồng logic** (~14% CPU).
3. **Biên dịch Webpack lặp lại & lệch đường benchmark:**
   - `remotion/scripts/render.ts` gọi `bundle()` từ đầu mỗi lần chạy, tốn 5–12 giây cho cả những lần chỉ đổi `render_props.json`.
   - Khi chạy `--frames` hoặc `--bench`, `src/pipeline/stage_video_master.py` (dòng 32–50) rẽ nhánh sang CLI `npx remotion render` thay vì đi qua `scripts/render.ts` → số đo benchmark không phản ánh đúng cấu hình Node API thật.

---

## 2. DANH MỤC TỆP TẠO MỚI & CHỈNH SỬA

```text
d:\_Short_film\
├── config/
│   └── settings.json                       # [sửa] Mở rộng mục render.* (scratch_dir, concurrency, gl, x264_preset, bundle_cache)
├── src/
│   ├── core/
│   │   ├── hardware_profile.py             # [mới] Tự động quét CPU/NUMA/RAM/GPU/Disk/FFmpeg encoders
│   │   └── scratch_manager.py              # [mới] Quản lý thư mục scratch & cache trên ổ NVMe nhanh nhất (C:)
│   ├── pipeline/
│   │   ├── context.py                      # [sửa] Gắn hardware_profile & scratch_manager vào PipelineContext
│   │   └── stage_video_master.py           # [sửa] Ghi prenorm trên NVMe scratch; gom --frames/--bench vào RemotionRunner
│   └── render/
│       └── remotion_runner.py              # [sửa] Truyền cấu hình render đầy đủ (concurrency, gl, x264_preset, frame_range, scratch_dir)
├── remotion/
│   └── scripts/
│       ├── bundle-cache.ts                 # [mới] Cache Webpack bundle theo SHA-256 mã nguồn + đồng bộ public/ lên NVMe
│       └── render.ts                       # [sửa] Dùng bundle-cache, hỗ trợ frameRange, gl, x264Preset, imageFormat, jpegQuality
├── scripts/
│   └── benchmark_hardware.py               # [mới] Tự động sweep concurrency × gl × preset, đo fps/RAM/VRAM và ghi settings.json
└── tests/
    ├── test_hardware_profile.py            # [mới] Unit test nhận diện phần cứng & fallback
    ├── test_scratch_manager.py             # [mới] Unit test chọn ổ NVMe, atomic move & dọn file tạm
    └── test_opt_gate1.py                   # [mới] Gate 1 acceptance test
```

---

## 3. THIẾT KẾ KỸ THUẬT CHI TIẾT (TASKS)

### Task 1.1: Bộ nhận diện cấu hình máy (`src/core/hardware_profile.py`)
Xây dựng dataclass `HardwareProfile` kèm hàm `detect_hardware_profile()` (có cache trong tiến trình và timeout ngắn $\le 3\text{s}$):
- **CPU & NUMA:** Đọc số nhân vật lý, số luồng logic (`os.cpu_count()`), số socket/NUMA node (trên Windows qua `wmic`/PowerShell hoặc Win32 API `GetLogicalProcessorInformationEx` bằng `ctypes` để chạy < 10 ms mà không cần spawn PowerShell nặng).
- **RAM:** Đọc tổng RAM và RAM trống (qua `ctypes.windll.kernel32.GlobalMemoryStatusEx`).
- **GPU & VRAM:** Gọi `nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits` (nếu có). Lưu `gpu_name`, `vram_mb`, `has_nvidia`.
- **Ổ đĩa:** Phân biệt ổ workspace (`D:`) và ổ hệ thống (`C:`) là `NVMe/SSD` hay `USB/HDD` (Windows PowerShell/CIM hoặc `DeviceIoControl` `StorageDeviceSeekPenaltyProperty` + `BusType`).
- **Khuyến nghị khởi điểm (Heuristic Default):**
  - Nếu máy $\ge 24$ nhân & $\ge 32\text{ GB}$ RAM: gợi ý dải benchmark `concurrency` = `[8, 12, 16, 20, 24, 28, 32]`.
  - Giới hạn an toàn VRAM 4 GB khi dùng `gl="angle"`: cảnh báo nếu `concurrency > 24` với `angle` để tránh tràn VRAM.

### Task 1.2: Quản lý thư mục Scratch & Cache trên NVMe (`src/core/scratch_manager.py`)
Thiết kế lớp `ScratchManager`:
- Cấu hình trong `config/settings.json → render`:
  ```json
  "render": {
    "renderer": "remotion",
    "encoder": "auto",
    "concurrency": 16,
    "gl": "angle",
    "x264_preset": "faster",
    "crf": 18,
    "image_format": "jpeg",
    "jpeg_quality": 85,
    "scratch_dir": "auto",
    "bundle_cache": true
  }
  ```
- **Quy tắc phân giải `scratch_dir`:**
  - Nếu `"auto"`: kiểm tra nếu thư mục dự án nằm trên ổ `USB` hoặc `HDD` VÀ `%LOCALAPPDATA%` nằm trên ổ `NVMe/SSD` còn trống $\ge 15\text{ GB}$ → chọn `%LOCALAPPDATA%\CineStory\scratch\`. Ngược lại dùng `cache/scratch/` trong repo.
  - Nếu người dùng ghi rõ đường dẫn (ví dụ `"C:\\CineStoryScratch"`) → dùng đúng đường dẫn đó.
- **Bố cục thư mục trên NVMe:**
  ```text
  %LOCALAPPDATA%\CineStory\scratch\
  ├── bundle-cache\
  │   └── <sha256_src_16hex>\     # Webpack bundle đã biên dịch + public/ được sync
  ├── hw-bin\                     # (Dùng ở OPT Phase 2) Cầu nối NVENC
  └── work\
      └── <chapter_id>\
          ├── video.prenorm.mkv   # Video H.264 + PCM trung gian (Remotion)
          ├── clips\              # Clip .mov trung gian (FFmpeg)
          └── video.master.tmp.mp4 # Thành phẩm trước khi chép sang D:\_Short_film\output\
  ```
- **Di chuyển an toàn xuyên ổ đĩa (`C:` → `D:`):** Vì `os.replace()` không chạy xuyên phân vùng (`C:` sang `D:`), viết hàm `promote_to_output(src_nvme: Path, dst_output: Path)` sao chép sang `dst_output.with_suffix(".tmp")` rồi `os.replace()` nguyên tử tại đích, sau đó xóa thư mục `work/<chapter_id>/` khi thành công.

### Task 1.3: Cache Webpack Bundle & Đồng bộ `public/` lên NVMe (`remotion/scripts/bundle-cache.ts`)
Thay thế lời gọi `bundle()` trực tiếp trong `render.ts` bằng hàm `getOrCreateBundle({ remotionDir, cacheRoot, chapterId, forceRebuild })`:
1. **Tính khóa cache (`sourceHash`):** SHA-256 nội dung tất cả tệp trong `remotion/src/**`, `remotion/package.json`, `remotion/package-lock.json`, `remotion/tsconfig.json`, `remotion/remotion.config.ts`.
2. **Cache Hit:** Nếu `<cacheRoot>/bundle-cache/<sourceHash>/index.html` và `.bundle-complete` đã tồn tại → **bỏ qua hoàn toàn `bundle()`** (tiết kiệm 5–12 giây).
3. **Cache Miss:** Gọi `bundle({ entryPoint, webpackOverride: enableTailwind, outDir: targetDir, enableCaching: true, publicDir: null })` rồi ghi tệp đánh dấu `.bundle-complete` (dọn các thư mục hash cũ, chỉ giữ 2 bản gần nhất).
4. **Đồng bộ `public/` gia tăng lên NVMe:**
   - Đồng bộ `remotion/public/textures/` và `remotion/public/chapters/<chapterId>/` sang `<targetDir>/public/` (chỉ copy khi file chưa có hoặc khác `size`/`mtime`).
   - Toàn bộ 16–28 tab Chromium sẽ tải ảnh nền, cutout, audio từ **NVMe `C:`** thay vì **USB HDD `D:`**.
   - **An toàn dữ liệu:** Không bao giờ phục vụ asset cũ của chương — luôn đối chiếu `size + mtime` trước mỗi lần render.

### Task 1.4: Thống nhất `render.ts` & `RemotionRunner` hỗ trợ đầy đủ tham số hiệu năng
Cập nhật `remotion/scripts/render.ts` nhận cấu hình qua file JSON hoặc CLI flags chuẩn (ví dụ `--props`, `--out`, `--concurrency`, `--crf`, `--gl`, `--x264-preset`, `--image-format`, `--jpeg-quality`, `--frames`, `--scratch-dir`, `--chapter-id`):
- Hỗ trợ `frameRange: [start, end]` trực tiếp trong `renderMedia()` (xóa bỏ nhánh fallback `npx remotion render` CLI cũ trong `stage_video_master.py`).
- Truyền rõ `imageFormat`, `jpegQuality`, `x264Preset`, `chromiumOptions: { gl }`.
- In thống kê tách bạch 3 mốc thời gian lên `stdout`:
  - `TIMING bundle_ms=...`
  - `TIMING select_ms=...`
  - `TIMING render_ms=...`
  để `RemotionRunner` ghi đầy đủ vào `render_report.json` và `bench_*.json`.

### Task 1.5: Công cụ Benchmark Sweep tự động (`scripts/benchmark_hardware.py`)
Viết script CLI:
```powershell
python scripts/benchmark_hardware.py --input input/sample_chapter.txt --frames 0-239 --apply
```
- **Ma trận quét mặc định trên Dual Xeon 56T + GTX 1650 4 GB:**
  1. `gl="angle"` với `concurrency` $\in [8, 12, 16, 20, 24]$ và `x264_preset="faster"`.
  2. `gl="swangle"` với `concurrency` $\in [16, 24, 28, 32]$ (đo kiểm thực nghiệm xem ở concurrency cao, bỏ tranh chấp 4 GB VRAM GPU có nhanh hơn `angle` hay không!).
  3. So sánh `x264_preset` $\in [\text{"medium"}, \text{"faster"}, \text{"veryfast"}]$ ở `concurrency` thắng cuộc.
- Trong mỗi lần đo, luồng nền ghi nhận **Peak RAM (GB)**, **Peak VRAM (MB)** (qua `nvidia-smi`), **CPU utilization (%)**, **`bundle_ms`**, **`render_ms`**, **`fps_render`**.
- **Quy tắc chọn cấu hình tối ưu:** Chọn tổ hợp đạt `fps_render` cao nhất thỏa điều kiện an toàn: `peak_vram_mb <= 3400` (< 85% của 4096 MB) và `peak_ram_gb <= 48` (< 75% của 64 GB), không timeout, mã thoát `0`.
- Lưu bảng kết quả chi tiết ra `output/<chapterId>/bench_hw_matrix.json`. Nếu có cờ `--apply`, tự động cập nhật `config/settings.json → render`.

---

## 4. TIÊU CHUẨN NGHIỆM THU (GATE 1 ACCEPTANCE)

1. **Hardware Prober chính xác:** `python -m src.core.hardware_profile` in đúng `28 cores / 56 threads`, `64 GB RAM`, `GTX 1650 (4096 MB)`, phát hiện `C:` là NVMe và `D:` là USB HDD.
2. **NVMe Scratch hoạt động:** Khi chạy `--stage video`, file `video.prenorm.mkv` nằm trên `C:\Users\...\AppData\Local\CineStory\scratch\work\...`, không ghi bản prenorm lên USB `D:`. Sau `--stage master`, file cuối `video.mp4` nằm đúng tại `output/<chapterId>/` và file tạm trên `C:` được dọn sạch.
3. **Bundle Cache Hit:** Chạy render lần 2 không sửa mã nguồn `remotion/src/` có `bundle_ms < 500 ms` (so với 5.000–12.000 ms ở lần 1). Khi sửa 1 file `.tsx` trong `remotion/src/`, hash đổi và tự rebuild sạch.
4. **Phá trần `concurrency = 8`:** Benchmark sweep trên `sample_chapter` (240 frames) hoàn tất không lỗi, chứng minh tốc độ `fps_render` vượt rõ rệt baseline `15.29 fps` (`bench_p2.json`) và lưu kết quả vào `bench_hw_matrix.json`.
5. **Regression Zero:** Toàn bộ unit test cũ (`python -m unittest discover -s tests`) và test mới (`test_hardware_profile.py`, `test_scratch_manager.py`, `test_opt_gate1.py`) PASS 100%.
