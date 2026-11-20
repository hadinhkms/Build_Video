# KẾ HOẠCH CHI TIẾT — OPT PHASE 3

## TỐI ƯU KHUNG HÌNH REMOTION (CSS/CANVAS/VRAM 4 GB), ASSET PROXY & BATCH STILLS/THUMBNAIL

*(Mã tài liệu: PLAN_HW_OPT_PHASE_3 · rev 1 · 2026-11-19)*  
*(Phụ thuộc: OPT Phase 1 — có thể triển khai song song với OPT Phase 2)*

---

## 1. BỐI CẢNH & CÁC ĐIỂM NÓNG ĐÃ XÁC MINH TRONG `remotion/src/`

Sau khi bật `concurrency` cao (16–24 tab Chromium ở OPT Phase 1) và đẩy encode H.264 sang NVENC (OPT Phase 2), **nút thắt chính còn lại sẽ là thời gian Chromium vẽ mỗi khung hình và dung lượng 4 GB VRAM của GTX 1650**. Kiểm tra từng component trong `remotion/src/` đã phát hiện 6 điểm nóng cụ thể:

1. **Tốn VRAM gấp 11× ở cảnh cận (`BackgroundPlate.tsx:53-61`):**
   - Ở cảnh `extreme_closeup` (`cropRect.w = 0.30`), `innerWidthPercent = 333.3%`. Thuộc tính `filter: grade?.cssFilter` đang đặt trên `div` con kích thước **6400×3600 px** → Chromium phải cấp phát bề mặt raster offscreen **~92 MB/tab** để chạy CSS filter mỗi frame. Với 20 tab = **1.84 GB VRAM** chỉ riêng lớp nền, dễ gây tràn 4 GB VRAM GTX 1650 và tụt fps đột ngột!
2. **`backdrop-brightness-50` ở `EndScreen.tsx:49`:**
   - Vi phạm trực tiếp quy tắc phần cứng trong `_Plan_Implement/README.md:212` ("tránh `backdrop-filter`"). Gây ép Chromium readback framebuffer suốt 240 frame (10 giây) của EndScreen.
3. **`blur-[2px]` trên nền 1080p ở `TitleCard.tsx:34` & `drop-shadow` ở `SubtitleBox.tsx:64`:**
   - Gaussian blur toàn màn hình chạy lại từng frame; `drop-shadow` là CSS filter pass thay vì `text-shadow` gốc của trình duyệt.
4. **Canvas mưa tính 720 hash + 180 lệnh `stroke()` mỗi frame (`AtmosphericEffects.tsx:21-71`):**
   - Trong `useEffect`, mỗi frame gọi `random(...)` 4 lần × 180 giọt = **720 lần băm chuỗi** và gọi **180 cặp `ctx.beginPath() / ctx.stroke()`** riêng lẻ.
5. **`FilmGrain.tsx:29` animate `backgroundPosition`:**
   - Đổi `backgroundPosition` ép Chromium repaint toàn màn hình 1920×1080 mỗi frame, thay vì dịch chuyển GPU compositor (`transform: translate3d(...)`).
6. **Lãng phí cực lớn ở `stage stills` & `thumbnail`:**
   - `src/visuals/stills_generator.py:37-63` gọi `npx remotion still` trong vòng lặp `for scene` → 20 cảnh = **20 lần khởi động Node + 20 lần Webpack bundle + 20 lần bật/tắt Chromium**!
   - `src/packaging/youtube.py:161-173` lại mở thêm 1 tiến trình `npx remotion still` độc lập chỉ để chụp đúng frame 30 làm thumbnail.

---

## 2. DANH MỤC TỆP TẠO MỚI & CHỈNH SỬA

```text
d:\_Short_film\
├── remotion/
│   ├── src/
│   │   ├── components/
│   │   │   ├── BackgroundPlate.tsx         # [sửa] Chuyển cssFilter lên wrapper 1920x1080 đã clip (giảm 11× VRAM)
│   │   │   ├── AtmosphericEffects.tsx      # [sửa] useMemo 180 giọt mưa + gộp 1 lần beginPath/stroke duy nhất
│   │   │   ├── FilmGrain.tsx               # [sửa] Chuyển sang translate3d compositor-only trên layer quá khổ +256px
│   │   │   └── SubtitleBox.tsx             # [sửa] Thay drop-shadow bằng text-shadow + useMemo cho highlight nodes
│   │   └── scenes/
│   │       ├── EndScreen.tsx               # [sửa] Xóa backdrop-brightness-50 → thay bằng bg-black/45
│   │       └── TitleCard.tsx               # [sửa] Loại bỏ blur-[2px] chạy từng frame, giữ sắc độ điện ảnh sạch
│   └── scripts/
│       ├── render.ts                       # [sửa] Cấu hình offthreadVideoThreads, mediaCacheSizeInBytes cho 64 GB RAM
│       └── render_stills.ts                # [mới] Render hàng loạt stills + thumbnail trong 1 phiên Node API + 1 openBrowser()
├── src/
│   ├── visuals/
│   │   ├── asset_optimizer.py              # [mới] Chuẩn hóa độ phân giải proxy cho ảnh plate/cutout (tránh Chromium giải mã ảnh 4K–8K)
│   │   └── stills_generator.py             # [sửa] Gọi scripts/render_stills.ts thay cho vòng lặp N × npx remotion still
│   ├── export/
│   │   └── visual_builder.py               # [sửa] Tích hợp asset_optimizer khi stage ảnh vào remotion/public/
│   └── packaging/
│       └── youtube.py                      # [sửa] Gọi scripts/render_stills.ts (tái dùng bundle-cache) để chụp frame 30
└── tests/
    ├── test_asset_optimizer.py             # [mới] Test resize bảo toàn tỉ lệ, alpha PNG, cache theo hash
    └── test_opt_gate3.py                   # [mới] Gate 3: kiểm tra cấm backdrop-filter, SSIM >= 0.99, tốc độ batch stills
```

---

## 3. THIẾT KẾ KỸ THUẬT CHI TIẾT (TASKS)

### Task 3.1: Tối ưu CSS Filter & Loại bỏ Backdrop Readback
1. **`EndScreen.tsx`:** Thay `bg-white/5 backdrop-brightness-50` thành `bg-black/45` — giữ độ tương phản tương đương nhưng xóa 100% lệnh `backdrop-filter`.
2. **`TitleCard.tsx`:** Thay `filter brightness-[0.25] saturate-50 blur-[2px]` bằng lớp phủ tối tĩnh (`opacity-30 grayscale-[40%]` trên nền đen + lớp vignette gradient) — không kích hoạt Gaussian blur filter 1080p ở mọi frame.
3. **`SubtitleBox.tsx`:**
   - Thay `drop-shadow-[0_2px_8px_rgba(245,158,11,0.6)]` bằng `[text-shadow:0_2px_8px_rgba(245,158,11,0.6)]`.
   - Bọc `renderHighlightedText(cap.text, cap.highlight)` trong `useMemo` theo `[cap.text, cap.highlight]` để không tách/sort/merge lại mảng ký tự suốt 40–80 frame hiển thị cùng 1 cụm phụ đề.

### Task 3.2: Giảm 11× VRAM ở `BackgroundPlate.tsx`
- Di chuyển `filter: grade?.cssFilter ?? undefined` từ `div` con kích thước `innerWidthPercent × innerHeightPercent` (lên tới `333% × 333%`) lên **`div` bọc ngoài cùng có kích thước cố định `100% × 100%` (`1920×1080`, `overflow-hidden`)**.
- Vì cả `<Img>` và `{grade?.overlayGradient}` đều nằm bên trong wrapper này, kết quả màu sắc **trùng khớp hoàn toàn** trong khi diện tích raster filter bị cắt cứng tối đa ở `1920×1080` (~8 MB thay vì ~92 MB trên mỗi tab Chromium!).
- Thêm `contain: "strict"` trên lớp nền để cô lập layout/paint subtree cho Chromium.

### Task 3.3: Tối ưu `AtmosphericEffects.tsx` & `FilmGrain.tsx`
1. **`AtmosphericEffects.tsx`:**
   - Dùng `useMemo` tính sẵn mảng 180 cấu trúc giọt mưa (`speed`, `length`, `initY`, `xOffset`) một lần duy nhất cho mỗi scene (giữ nguyên seed `rain-drop-${i}` của Remotion → **tất định 100%, hình ảnh y hệt bản cũ**).
   - Trong `useEffect`: gọi `ctx.beginPath()` **1 lần**, lặp 180 lệnh `ctx.moveTo(...)` + `ctx.lineTo(...)`, rồi gọi `ctx.stroke()` **1 lần duy nhất** (giảm 180× số lệnh draw Canvas 2D mỗi frame).
   - Khi `rain === "window"` có `rainRegion`, chỉ `clearRect(clipX, clipY, clipW, clipH)` vùng cửa sổ thay vì xóa toàn màn hình 1920×1080.
2. **`FilmGrain.tsx`:**
   - Mở rộng `div` grain ra kích thước `calc(100% + 256px) × calc(100% + 256px)` với `backgroundRepeat: "repeat"` cố định, rồi dịch chuyển mỗi frame bằng `transform: translate3d(-${shiftX}px, -${shiftY}px, 0)` + `willChange: "transform"`.
   - Giữ nguyên công thức `random('grain-x-' + frame)` → hạt grain khớp chính xác từng pixel nhưng chạy hoàn toàn trên GPU compositor layer, không trigger repaint!

### Task 3.4: Chuẩn hóa kích thước ảnh đầu vào (`src/visuals/asset_optimizer.py`)
Khi người dùng đặt ảnh AI độ phân giải rất cao (4K/6K/8K) vào `assets/environments/` hoặc `assets/characters/`:
- Tạo hàm `prepare_render_asset(src_path: Path, dst_path: Path, kind: Literal["plate", "cutout", "full_image"])`:
  - **`plate`:** Nếu chiều rộng > `2560 px` → thu về đúng `2560 px` (giữ nguyên tỉ lệ, bộ lọc `Image.Resampling.LANCZOS`, chất lượng JPEG `92` hoặc WebP `92`). Mức `2560 px` vẫn thừa nét cho `medium`/`closeup` 1080p nhưng giảm 4×–9× dung lượng texture decode trong Chromium.
  - **`full_image`:** Nếu chiều rộng > `2304 px` → thu về `2304 px` (đủ cho zoom 1.18× ở 1080p).
  - **`cutout` (có kênh alpha PNG):** Nếu chiều cao > `1920 px` → thu về `1920 px` giữ nguyên alpha RGBA (`PNG`, `compress_level=1` để giải mã cực nhanh).
  - Nếu ảnh gốc đã nhỏ hơn hoặc bằng ngưỡng → bỏ qua resize, copy/hardlink trực tiếp.
  - Có kiểm tra cache theo `(src_size, src_mtime, target_max_dim)` để không xử lý lại.
- Tích hợp vào `src/export/visual_builder.py` khi xuất tài sản sang `remotion/public/chapters/<chapterId>/`.

### Task 3.5: Gộp Batch Stills & Thumbnail vào 1 phiên Node API (`remotion/scripts/render_stills.ts`)
Viết script `remotion/scripts/render_stills.ts` dùng `@remotion/renderer`:
- Tái sử dụng `getOrCreateBundle()` từ OPT Phase 1 (NVMe cache → **0 giây re-bundle**).
- Mở **1 phiên trình duyệt duy nhất** bằng `openBrowser("chrome", { chromiumOptions: { gl } })` và giữ sống `puppeteerInstance` xuyên suốt danh sách frame cần chụp.
- Nhận danh sách `{ frame, outputPath }` (hỗ trợ cả chế độ `all-scenes` cho `StillsGenerator` lẫn chế độ `--frame 30 --out ...` cho `YouTubePackager`).
- Chụp song song theo batch nhỏ (ví dụ `concurrency = 6` promises cùng lúc trên cùng `puppeteerInstance`), sau đó đóng browser 1 lần duy nhất.
- Cập nhật `src/visuals/stills_generator.py` và `src/packaging/youtube.py` gọi `render_stills.ts` thay vì vòng lặp `npx remotion still`.

### Task 3.6: Tinh chỉnh bộ nhớ đệm Remotion cho máy 64 GB RAM (`remotion/scripts/render.ts`)
Bổ sung các tham số đã xác minh trong `renderMedia()` (`remotion@4.0.407`):
- `mediaCacheSizeInBytes`: đặt `2 * 1024 * 1024 * 1024` (2 GB, tự co theo `ram_gb`) để giữ ảnh/audio đã giải mã trong bộ nhớ đệm.
- `offthreadVideoCacheSizeInBytes`: đặt `1 * 1024 * 1024 * 1024` (1 GB) khi có cảnh Hybrid Video (`Kling`/`Hedra`).
- `offthreadVideoThreads`: cấu hình `4` (tận dụng nhân Xeon khi decode clip MP4 hybrid).
- `imageFormat`: `"jpeg"`, `jpegQuality`: `85` (đọc từ `settings.json`).

---

## 4. TIÊU CHUẨN NGHIỆM THU (GATE 3 ACCEPTANCE)

1. **Quét tĩnh cấm CSS nặng:** Test tự động quét toàn bộ `remotion/src/**/*.tsx` xác nhận **0 lần xuất hiện** `backdrop-blur`, `backdrop-brightness`, `backdrop-filter`, và `blur-[` chạy động trong scene render.
2. **Bảo toàn hình ảnh (SSIM Parity):** So sánh khung hình still của cảnh `layered`, `extreme_closeup`, cảnh có mưa, và cảnh có `FilmGrain` trước vs sau tối ưu: **SSIM $\ge 0.99$**.
3. **Tính tất định (Determinism):** Render 2 lần liên tiếp cùng `render_props.json` trên cùng cảnh mưa + grain → hash ảnh PNG đầu ra trùng khớp 100% (hoặc SSIM = `1.0`).
4. **Đo kiểm VRAM & Tốc độ:**
   - Benchmark 240 frames sau OPT Phase 3 cho `fps_render` tăng thêm rõ rệt so với cuối OPT Phase 2, đồng thời VRAM đỉnh ở `concurrency=20` giảm đáng kể trên cảnh `extreme_closeup`.
   - `stage stills` trên `sample_chapter` hoàn tất nhanh gấp **$\ge 8\times$** so với cách gọi `npx remotion still` từng cảnh cũ.
5. **Kiểm thử tự động:** `cd remotion; npm run typecheck; npm test` và `python -m unittest discover -s tests` PASS 100%.
