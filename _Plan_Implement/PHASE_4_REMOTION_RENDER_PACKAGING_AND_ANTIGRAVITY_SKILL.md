# KẾ HOẠCH CHI TIẾT - PHASE 4
## RENDER MULTI-THREAD XEON, ĐÓNG GÓI YOUTUBE & TÍCH HỢP ANTIGRAVITY SKILL
*(Mã tài liệu: PLAN_PHASE_4_REMOTION_RENDER_AND_SKILL)*

---

## 1. MỤC TIÊU & PHẠM VI (SCOPE & OBJECTIVES)

### 1.1. Mục tiêu
Kế thừa giải pháp đóng gói và triển khai tự động hóa đỉnh cao từ **`auto-video-gen`** và **`remotion-cuongit-template`**:
1. **Render Siêu Tốc Bằng CPU Xeon 56 Luồng:** Tận dụng tối đa 2 chip Xeon E5-2680 v4 và 64GB RAM để xuất video Full HD 1080p bằng Remotion CLI trong thời gian $< 90$ giây.
2. **Xuất Bản Phụ Đề Chuẩn YouTube (.srt):** Tự động sinh file SRT đồng bộ từng frame để upload trực tiếp lên YouTube Video Manager.
3. **Bộ Đóng Gói Giữ Chân Người Xem (YouTube Retention Package):** Tự động đề xuất 3 tiêu đề giật gân (Clickbait Hook), thẻ mô tả có gắn mốc thời gian (Timestamps), và prompt vẽ ảnh Thumbnail tỷ lệ CTR cao.
4. **Tích Hợp Native Antigravity Skill (`.agents/skills/create-story-video`):** Cho phép bạn chỉ cần gõ 1 câu lệnh trong chat Antigravity IDE:
   > `/create-story-video input/sample_chapter.txt`
   là AI tự động chạy từ kịch bản truyện $\rightarrow$ Video hoàn chỉnh mà không cần chạm tay vào bàn phím!

---

## 2. KIẾN TRÚC PHÂN HỆ & DANH MỤC TỆP

```
d:\_Short_film\
├── .agents/
│   └── skills/
│       └── create-story-video/
│           └── SKILL.md              # Antigravity Skill điều phối toàn bộ pipeline
├── scripts/
│   ├── render/
│   │   ├── remotion-renderer.ts      # Bộ gọi Remotion CLI với cấu hình đa luồng
│   │   └── srt-exporter.ts           # Trình xuất phụ đề chuẩn .srt từ metadata audio
│   └── packaging/
│       └── youtube-packager.ts       # Sinh tiêu đề, mô tả và prompt thumbnail
├── output/
│   ├── final_story.mp4               # File VIDEO THÀNH PHẨM MASTER 1080p
│   ├── final_story.srt               # File PHỤ ĐỀ YOUTUBE ĐỒNG BỘ
│   └── youtube_metadata.json         # Tiêu đề, mô tả, timestamps và prompt thumbnail
└── package.json                      # Bổ sung các lệnh script: npm run render, npm run build
```

---

## 3. THIẾT KẾ KỸ THUẬT CHI TIẾT

### 3.1. Cấu Hình Render Đa Luồng Remotion CLI (`remotion-renderer.ts`)
```typescript
import { renderMedia, selectComposition } from "@remotion/renderer";

export async function renderMasterVideo(entryPoint: string, outputPath: string) {
  const composition = await selectComposition({
    serveUrl: entryPoint,
    id: "StoryComposition",
  });

  await renderMedia({
    composition,
    serveUrl: entryPoint,
    codec: "h264",
    crf: 18,
    pixelFormat: "yuv420p",
    outputLocation: outputPath,
    concurrency: 8, // Chạy 8 tiến trình render song song trên 56 luồng Xeon
    gl: "angle",    // Tương thích tối đa với card đồ họa Windows
    verbose: false,
  });
}
```

### 3.2. Đặc Tả Native Skill Cho Google Antigravity (`.agents/skills/create-story-video/SKILL.md`)
Kế thừa chuẩn skill từ `remotion-cuongit-template` và `auto-video-gen`:
* **Trigger:** Khi người dùng yêu cầu tạo video từ truyện, gõ `/create-story-video`, hoặc đưa đường dẫn file `.txt`.
* **Quy trình 5 bước tự động của Skill:**
  1. *Đọc file truyện:* Trích xuất nội dung và tiêu đề.
  2. *Bóc tách phân cảnh:* Gọi script sinh kịch bản JSON có Hook 15s.
  3. *Sinh giọng đọc:* Chạy `generate-story-audio.ts` (Edge-TTS 0$).
  4. *Render video Remotion:* Gọi CLI render xuất ra file `.mp4`.
  5. *Báo cáo kết quả:* Trình bày video demo, file phụ đề SRT và gợi ý Thumbnail cho người dùng.

---

## 4. DANH MỤC CÔNG VIỆC THỰC HIỆN (TASK BREAKDOWN)

- [ ] **Task 4.1:** Xây dựng script `scripts/render/remotion-renderer.ts` tích hợp Remotion Renderer API.
- [ ] **Task 4.2:** Xây dựng script `scripts/render/srt-exporter.ts` tạo phụ đề YouTube.
- [ ] **Task 4.3:** Xây dựng script `scripts/packaging/youtube-packager.ts` đóng gói SEO metadata.
- [ ] **Task 4.4:** Tạo thư mục `.agents/skills/create-story-video/SKILL.md` để kích hoạt tính năng Agentic Workflow trong Antigravity IDE.
- [ ] **Task 4.5:** Thực hiện chạy kiểm thử nghiệm thu toàn diện End-to-End Gate 4.

---

## 5. TIÊU CHÍ NGHIỆM THU GATE 4 (FINAL ACCEPTANCE CRITERIA)

| Tiêu chí | Điều kiện bắt buộc | Phương thức kiểm tra |
| :--- | :--- | :--- |
| **Tốc Độ Render CPU Xeon** | Video 60 giây xuất xưởng trong thời gian $\le 90$ giây | Đo thời gian chạy lệnh render |
| **Chất Lượng Video Master** | Độ phân giải 1080p, 30fps mượt mà, âm thanh trong trẻo, chữ sắc nét | Kiểm tra qua VLC / Media Player |
| **Đồng Bộ Phụ Đề SRT** | Phụ đề khớp chính xác từng giây với giọng nói khi upload lên YouTube | Kiểm tra file `output/final_story.srt` |
| **Kích Hoạt Qua Antigravity Skill** | Gọi lệnh `/create-story-video` thực thi thành công từ đầu đến cuối | Kiểm tra workflow trong Antigravity chat |

---

## 6. LỆNH XÁC MINH (VERIFICATION COMMAND)

```powershell
npm run render
```
*(Hoặc dùng trực tiếp câu lệnh slash command trong chat: `/create-story-video input/sample_chapter.txt`)*
