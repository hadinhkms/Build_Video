# KẾ HOẠCH CHI TIẾT - PHASE 4

## RENDER ĐA TIẾN TRÌNH, MASTERING, SRT, GÓI YOUTUBE & SKILL `/create-story-video`

*(Mã tài liệu: PLAN_PHASE_4_REMOTION_RENDER_AND_SKILL · rev 2 · 2026-09-25)*

> **Ghi chú sửa đổi so với rev 1**
>
> - **Code render rev 1 sai.** Nó truyền thẳng entry point `.ts` vào `serveUrl`. Đúng ra phải `bundle()` trước (`@remotion/bundler`), rồi mới gọi `selectComposition` / `renderMedia` kèm `inputProps`. Ngoài ra `remotion.config.ts` không áp dụng cho Node API, nên phải tự truyền Tailwind (`webpackOverride`), codec, crf…
> - **Không ghi cứng `concurrency: 8`.** Giá trị này phải chọn bằng `npx remotion benchmark` trên chính máy Xeon.
> - **Thêm bước mastering** mà rev 1 bỏ quên. Render ra audio PCM, sau đó chạy loudnorm 2 lượt bằng `src/audio/mastering.py` đã có, và mã hóa AAC đúng **1 lần** (quyết định D7).
> - **SRT:** không viết `srt-exporter.ts` mới. Dùng `captions` trong props (cùng dữ liệu với phụ đề trên hình), xuất qua hàm Python `format_srt_time` đã có test.
> - **Gói YouTube:** rev 1 không nói tiêu đề "0đ" do ai viết. Nay giao cho agent trong IDE (Antigravity/Claude Code) viết theo mẫu và schema, Python kiểm tra lại. Timestamps sinh tự động từ ranh giới các hồi, theo đúng luật chapters của YouTube.
> - **Skill:** thêm bước dừng chờ người dùng tạo ảnh (quyết định D2), và thêm bản sao cho `.claude/skills/`.
> - **Mục tiêu "≤ 90 s cho video 60 s"** giữ làm mục tiêu kéo dài. Gate dựa trên số đo benchmark thật.
> - **Thêm** `run_pipeline.py --stage` có resume bằng `StateManager`, và test E2E tự động.
>
> **Bổ sung rev 2.1 (sau khi rà soát plan)**
>
> - **`render.ts` bọc trong `async function main()`**, không dùng top-level await. Top-level await chỉ chạy được khi `package.json` có `"type": "module"`, và rev 2 không nói tới điều này.
> - Liệt kê gói npm cần thêm ở phase này: `@remotion/bundler`, `@remotion/renderer`, `tsx`.
> - **Thống nhất tên stage** với bảng chuẩn trong README. `render` là stage gộp gồm assets → props → video → master → package (rev 2.2 thêm `assets`, xem ghi chú bên dưới). Stage render video đơn lẻ tên là `video`.
> - **Task 4.10:** hiện `input/` mới có 1 chương. Gate 4 dùng chương mẫu cộng ít nhất 1 chương thật do người dùng cung cấp.
>
> **Bổ sung rev 2.2 (rà soát lần 2, đã kiểm chứng trên gói Remotion 4.0.407)**
>
> - **Đã kiểm chứng:** codec `h264-mkv` có trong 4.0.407, audio mặc định là `pcm-16`. `npx remotion benchmark` nhận `--props`.
> - **Thumbnail 1280×720:** render still ở độ phân giải gốc, sau đó thu nhỏ bằng ffmpeg. Không dùng `--scale=0.667`, vì 1920 × 0,667 không ra số nguyên.
> - **Timestamps YouTube:** video quá ngắn, không chia được ≥ 3 đoạn mỗi đoạn ≥ 10 s, thì bỏ hẳn timestamps và in cảnh báo, không làm hỏng Gate.
> - **Sau khi agent độc lập rà soát:**
>   - **Stage gộp `render` phải chạy lại `assets` trước `props`.** Nếu không, ảnh người dùng thêm sau `prepare` sẽ không được tách nền và không được dùng.
>   - `concurrency: null` không được đổi thành `NaN`.
>   - Agent ghi từ khóa cảm xúc bằng thẻ `[EMO: …]`.
>   - Mọi đường dẫn đặt theo `output/<chapterId>/`.

---

## 1. MỤC TIÊU & PHẠM VI (SCOPE & OBJECTIVES)

### 1.1. Mục tiêu

1. Render bằng Node API. `concurrency` lấy theo benchmark. Âm thanh xuất ở dạng PCM.
2. Mastering loudness và mux thành MP4 cuối.
3. Xuất SRT từ `captions`.
4. Xuất `youtube_metadata.json` và ảnh nền cho thumbnail.
5. Skill `/create-story-video` chạy 2 lượt: chuẩn bị → chờ ảnh → render.
6. Có test E2E và số đo hiệu năng. Quyết định giữ hay bỏ renderer ffmpeg.

### 1.2. Ngoài phạm vi

- Tự động upload lên YouTube (cần OAuth và YouTube Data API). Có thể làm ở một phase sau.
- Tự sinh ảnh thumbnail hoàn chỉnh. Pipeline chỉ cung cấp ảnh nền + prompt + chữ gợi ý.

---

## 2. KIẾN TRÚC PHÂN HỆ & DANH MỤC TỆP

```text
d:\_Short_film\
├── remotion/scripts/render.ts          # [mới] bundle + selectComposition + renderMedia
├── src/
│   ├── render/remotion_runner.py       # [mới] gọi render.ts, đọc tiến độ, timeout, báo lỗi rõ
│   ├── audio/mastering.py              # [giữ] loudnorm 2 lượt, copy video, AAC 1 lần
│   ├── export/srt.py                   # [tách ra từ run_pipeline.py] captions → SRT
│   └── packaging/youtube.py            # [mới] kiểm tra youtube_draft.json, sinh timestamps
├── config/
│   ├── settings.json                   # [sửa] render.concurrency, render.crf, youtube.*
│   └── youtube_template.json           # [mới] mẫu mô tả, hashtag, CTA, link chương trước/sau
├── .agents/skills/create-story-video/SKILL.md   # [mới] Antigravity
├── .claude/skills/create-story-video/SKILL.md   # [mới] bản sao cho Claude Code
├── tests/test_e2e_render.py            # [mới] tự bỏ qua nếu máy không có node/ffmpeg
└── output/<chapterId>/
    ├── video.mp4                       # bản master
    ├── video.srt
    ├── youtube_metadata.json
    ├── thumbnail_base.png
    └── render_report.json              # thời gian, fps render, concurrency, loudness đo được
```

---

## 3. THIẾT KẾ KỸ THUẬT CHI TIẾT

### 3.1. Render bằng Node API (`remotion/scripts/render.ts`)

```typescript
import fs from "node:fs";
import path from "node:path";
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import { enableTailwind } from "@remotion/tailwind-v4";

// Không dùng top-level await: package.json không đặt "type": "module"
async function main() {
  const [propsPath, outPath, concurrencyArg, crf] = process.argv.slice(2);
  const inputProps = JSON.parse(fs.readFileSync(propsPath, "utf8"));
  // settings.render.concurrency = null → runner truyền "auto" → null = để Remotion tự chọn (renderMedia nhận null)
  const concurrency = concurrencyArg === undefined || concurrencyArg === "auto" ? null : Number(concurrencyArg);

  // bundle() KHÔNG đọc remotion.config.ts → phải tự truyền Tailwind, nếu không toàn bộ class CSS sẽ mất
  const serveUrl = await bundle({
    entryPoint: path.resolve("src/index.ts"),
    webpackOverride: enableTailwind,
  });
  const composition = await selectComposition({ serveUrl, id: "StoryComposition", inputProps });

  await renderMedia({
    composition,
    serveUrl,
    inputProps,
    codec: "h264-mkv",               // video H.264 + audio PCM → mastering mã hóa AAC đúng 1 lần
    crf: Number(crf),
    pixelFormat: "yuv420p",
    concurrency, // từ settings.render.concurrency (kết quả benchmark) hoặc null
    chromiumOptions: { gl: "angle" },
    outputLocation: outPath,
    onProgress: ({ progress }) => console.log(`PROGRESS ${progress.toFixed(3)}`),
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1); // remotion_runner.py dựa vào exit code để báo lỗi
});
```

- **Gói npm cần thêm ở phase này:** `@remotion/bundler` và `@remotion/renderer`, cùng phiên bản chính xác với `remotion`. Thêm `tsx` vào devDependencies.

- **Codec (đã kiểm chứng trên 4.0.407):** `h264-mkv` có sẵn, và `audioCodec` mặc định của nó là `pcm-16`, nên không cần truyền thêm. Nếu sau này nâng Remotion mà codec này bị bỏ thì làm 2 lần render: video với `codec: "h264"` + `muted: true`, audio với `codec: "wav"`, rồi mux lại ở bước mastering.
- **`remotion_runner.py`:**
  - Trên Windows gọi `npx.cmd tsx scripts/render.ts <props> <out> <concurrency|auto> <crf>` với `cwd="remotion"`. Truyền `auto` khi `settings.render.concurrency` là `null`.
  - Đọc các dòng `PROGRESS` để in tiến độ.
  - Có timeout. Khi lỗi thì in 30 dòng cuối của stderr.
- Thêm lệnh `"render": "tsx scripts/render.ts"` vào `remotion/package.json`.

### 3.2. Benchmark concurrency

- Chạy `npx remotion benchmark src/index.ts StoryComposition --props=../output/sample_chapter/render_props.json --concurrencies=4,8,12,16,20,24` và chọn mức concurrency nhanh nhất. Ghi kết quả vào `settings.render.concurrency` và ghi chú lại ngày đo.
- Mỗi lần render đều ghi `render_report.json`: thời gian tổng, fps render, concurrency, số frame, RAM đỉnh (nếu đo được).
- Nếu chưa đạt mục tiêu 90 s cho video 60 s thì xem báo cáo để tìm nút thắt. Các nghi phạm thường gặp: hiệu ứng CSS nặng, canvas mưa, `OffthreadVideo`, ảnh quá lớn (nên resize plate về tối đa 2× khung hình).

### 3.3. Mastering & mux

- **Đầu vào:** `video.prenorm.mkv` (H.264 + PCM).
- **Xử lý:** gọi `master_loudness()` hiện có: đo lượt 1, áp lượt 2 `linear=true`, `asetpts`, `-c:v copy`, `-c:a aac -b:a 192k -ar 44100`, `+faststart`. Kết quả là `video.mp4`. Khi mastering thất bại thì dùng `encode_without_mastering()` hiện có và ghi cảnh báo vào report.
- **Kiểm tra sau mastering:** I = −14 ±1 LUFS, TP ≤ −1,5 dBTP.
- **Dọn dẹp:** chỉ xóa file `.prenorm.mkv` khi mọi bước đã thành công.

### 3.4. SRT (`src/export/srt.py`)

- Mỗi phần tử trong `captions` thành một mục SRT. Thời gian tuyệt đối = offset của cảnh (Σ `durationInFrames` của các cảnh trước / fps) + `caption.start`.
- Dùng lại `format_srt_time` (làm tròn ms) và giữ nguyên các test hiện có khi tách hàm ra khỏi `run_pipeline.py`.
- `title_card` và `end_screen` không có mục SRT nào.
- Nếu sau này dùng chuyển cảnh chồng lấn thì phải dùng **cùng hàm tính offset** với Remotion (bất biến #2).
- Phụ đề đã in trên hình nhưng vẫn upload SRT (người xem tự bật CC, có lợi cho tìm kiếm). Cờ bật/tắt: `settings.youtube.upload_srt`.

### 3.5. Gói YouTube (`src/packaging/youtube.py`)

- **Agent viết bản nháp.** Trong bước của skill, agent viết `youtube_draft.json` theo `config/youtube_template.json`, gồm:
  - 3 tiêu đề, mỗi tiêu đề ≤ 70 ký tự, gây tò mò nhưng **đúng nội dung**. Tiêu đề sai sự thật có thể vi phạm chính sách của YouTube về nội dung gây hiểu lầm.
  - Mô tả và 10–15 tag.
  - Prompt thumbnail, cùng dòng chữ trên thumbnail tối đa 5 từ (RULES §5).
- **Python kiểm tra và bổ sung:** `youtube.py` kiểm tra bản nháp theo schema, rồi tự sinh **timestamps** từ ranh giới các hồi:
  - Dòng đầu tiên phải là `00:00`.
  - Có ít nhất 3 mốc.
  - Mỗi đoạn dài ≥ 10 s. Đây là điều kiện để YouTube tạo chapters; hồi nào ngắn hơn 10 s thì gộp với hồi kế bên.
  - Nếu sau khi gộp vẫn không đạt ≥ 3 đoạn ≥ 10 s (thường gặp khi video < 30 s) thì **bỏ hẳn timestamps** khỏi mô tả và in cảnh báo. Để timestamps sai luật thì YouTube bỏ qua, còn có thể làm người xem hiểu lầm.
- **Không có agent** (chạy CLI thuần): sinh bản nháp tất định từ template. Tiêu đề = tên chương + câu hook rút gọn.
- **Ảnh nền thumbnail:**
  - Dùng `npx remotion still` lấy khung giữa của cảnh HOOK (hoặc cảnh con đầu của Hook) ở độ phân giải gốc 1920×1080.
  - Thu nhỏ bằng `ffmpeg -vf scale=1280:720:flags=lanczos` ra `thumbnail_base.png`.
  - Không dùng `--scale` của Remotion: 1280/1920 = 2/3 là số thập phân vô hạn, nên kích thước ra sẽ bị làm tròn lệch khỏi 1280×720.
  - Người dùng thêm chữ lên ảnh này, hoặc dùng prompt để tạo ảnh riêng.

### 3.6. Các stage & resume (`run_pipeline.py`)

Danh sách đầy đủ nằm trong README, mục "Các stage của pipeline". Phase này làm các stage đơn `master`, `package` và các stage gộp:

| Stage gộp | Công việc |
| :--- | :--- |
| `prepare` | `script` → `audio` → `assets` (gói prompt + checklist ảnh) → `props`, rồi **dừng lại** |
| `render` | **`assets`** (tách nền ảnh mới, chọn lại `visual.mode`, hạ cấp `over_shoulder`) → `props` → `video` → `master` → `package` (SRT, metadata, thumbnail) |
| `all` | `prepare` + `render` liền một mạch, dùng ảnh dự phòng cho chỗ còn thiếu |

Stage `video` từ Phase 0 được đổi sang gọi `remotion_runner.py` (Node API, đầu ra `video.prenorm.mkv`) thay cho lệnh CLI.

`StateManager` lưu trạng thái từng cảnh (`AUDIO_READY`, `VISUAL_READY`, `COMPOSITED`…). Chạy lại thì chỉ làm phần còn thiếu.

### 3.7. Skill `/create-story-video` (`.agents/skills/create-story-video/SKILL.md`)

Frontmatter gồm `name` và `description`, trong `description` liệt kê các câu kích hoạt ("tạo video từ truyện", "/create-story-video", "làm video chương…"), giống cách hai repo tham khảo đang làm.

**Quy trình của skill:**

1. **Đọc file `.txt`** và xác định tiêu đề chương.
2. **(Agent) Chú thích chương** theo cú pháp thẻ ở Phase 0 mục 3.4b: `[HOOK]`, `[Tên]:`, `[ENV: …]`, `[ON: …]`, `[EMO: …]` cho từ khóa cảm xúc, và `[SFX: …]` / `[BGM: …]` nếu cần. Ghi ra `input/<chapter>.annotated.txt`, **không sửa file gốc**.
3. **Chuẩn bị:** chạy `python run_pipeline.py --renderer remotion --stage prepare --input <file annotated>`. `chapterId` tự bỏ hậu tố `.annotated`, nên thư mục đầu ra vẫn là `output/<chapter>/`.
4. **Báo checklist ảnh còn thiếu** kèm đường dẫn tới gói prompt, rồi **dừng lại hỏi người dùng**: "Đã tạo ảnh xong" hay "Render luôn với ảnh dự phòng".
5. **Render:** chạy `--stage render`.
6. **(Agent) Viết `youtube_draft.json`**, rồi chạy `python -m src.packaging.youtube` để kiểm tra.
7. **Báo cáo kết quả:** đường dẫn video, SRT, metadata, thumbnail; loudness đo được; thời gian render; các cảnh báo.

**Bảng lỗi thường gặp** (đưa vào SKILL.md):

| Lỗi | Cách xử lý |
| :--- | :--- |
| Edge-TTS lỗi mạng | Chạy lại, đã có cache |
| Thiếu `node_modules` | `cd remotion; npm install` |
| Thiếu ffmpeg / ffprobe | Cài ffmpeg và thêm vào PATH |
| Thiếu ảnh | Xem checklist, hoặc render với ảnh dự phòng |
| Render lỗi hết bộ nhớ | Giảm `settings.render.concurrency` |

**Bản sao cho Claude Code:** `.claude/skills/create-story-video/SKILL.md` có nội dung giống hệt. Chỉ sửa một nguồn là `.agents/`, rồi dùng script copy sang.

---

## 4. DANH MỤC CÔNG VIỆC THỰC HIỆN (TASK BREAKDOWN)

- [ ] **Task 4.1:** Thêm `@remotion/bundler`, `@remotion/renderer` và `tsx` vào `package.json`. Viết `render.ts` và `remotion_runner.py`: tiến độ, timeout, báo lỗi rõ ràng, exit code khác 0 khi lỗi. Kiểm tra file `.prenorm.mkv` bằng ffprobe: luồng audio là `pcm_s16le`.
- [ ] **Task 4.2:** Chạy benchmark concurrency, ghi vào settings, sinh `render_report.json`.
- [ ] **Task 4.3:** Nối mastering và mux cho đầu ra Remotion, dùng lại `mastering.py`. Có test.
- [ ] **Task 4.4:** Viết `srt.py` từ `captions`, tách khỏi `run_pipeline.py`, giữ nguyên test cũ và thêm test mới.
- [ ] **Task 4.5:** Viết `youtube.py`, template và phần sinh timestamps. Test luật chapters.
- [ ] **Task 4.6:** Xuất ảnh nền thumbnail.
- [ ] **Task 4.7:** Thêm stage `master`, `package` và các stage gộp `prepare` / `render` / `all` theo bảng chuẩn trong README. Resume bằng `StateManager`. Có test.
- [ ] **Task 4.8:** Viết `SKILL.md` cho Antigravity và bản sao cho Claude Code.
- [ ] **Task 4.9:** Viết `tests/test_e2e_render.py`.
- [ ] **Task 4.10:** Chạy chương mẫu và **ít nhất 1 chương thật** do người dùng cung cấp (ví dụ `input/chapter_02.txt`; hiện `input/` mới có chương mẫu). Chương thật nên có lời thoại và số liệu để kiểm tra phần nhận diện lời thoại và chuẩn hóa phát âm. Quyết định giữ hay bỏ renderer ffmpeg, ghi quyết định vào README.
- [ ] **Task 4.11:** Chạy kiểm thử Gate 4.

---

## 5. TIÊU CHÍ NGHIỆM THU GATE 4 (FINAL ACCEPTANCE CRITERIA)

| Tiêu chí | Điều kiện bắt buộc | Phương thức kiểm tra |
| :--- | :--- | :--- |
| **Thời lượng** | Độ dài video lệch Σ frame / fps không quá 1 frame. Luồng video và luồng audio dài bằng nhau ±1 frame. | E2E + ffprobe |
| **Định dạng** | Độ phân giải và fps đúng config. `yuv420p`, H.264 + AAC 44,1 kHz. | ffprobe |
| **Loudness** | −14 ±1 LUFS, TP ≤ −1,5 dBTP. | Đo lại bằng ffmpeg loudnorm |
| **SRT** | Mốc tăng dần, không chồng lấn, không vượt thời lượng video, khớp với phụ đề trên hình ±1 frame. | Unit test + E2E |
| **Metadata** | Qua schema. Timestamps hợp lệ (bắt đầu `00:00`, ≥ 3 mốc, mỗi đoạn ≥ 10 s), hoặc không có timestamps kèm cảnh báo khi video quá ngắn. | Unit test, gồm ca video 25 s |
| **Hiệu năng** | Có `render_report.json` với concurrency tối ưu. Mục tiêu video 60 s render ≤ 90 s. Chưa đạt thì không chặn Gate, nhưng phải có số đo và phân tích nút thắt. | Report |
| **Skill** | `/create-story-video input/sample_chapter.txt` chạy thành công cả 2 lượt (prepare → render) trong Antigravity. | Chạy tay |
| **Không hồi quy** | Toàn bộ test Python và TS PASS. `--renderer ffmpeg` vẫn chạy nếu còn giữ. | `unittest` + `npm test` |

---

## 6. LỆNH XÁC MINH (VERIFICATION COMMAND)

```powershell
python run_pipeline.py --renderer remotion --stage prepare --input input/sample_chapter.txt
python run_pipeline.py --renderer remotion --stage render  --input input/sample_chapter.txt
python -m unittest discover -s tests
cd remotion; npm test; npx remotion benchmark src/index.ts StoryComposition --props=../output/sample_chapter/render_props.json
```

*(Hoặc gõ trong chat IDE: `/create-story-video input/sample_chapter.txt`)*

---

## 7. RỦI RO & LƯU Ý

- **RAM khi concurrency cao:** mỗi tiến trình Chromium tốn vài trăm MB tới hơn 1 GB tùy độ nặng của cảnh. Theo dõi RAM trong lúc benchmark.
- **Đường dẫn dài hoặc có dấu tiếng Việt trên Windows:** giữ tên file ASCII (`shot_01`, `chapter_01`) và đặt dự án ở thư mục ngắn.
- **Tiêu đề do agent viết** có thể quá giật gân. Schema giới hạn độ dài, và người dùng luôn duyệt trước khi đăng.
