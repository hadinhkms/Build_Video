# KẾ HOẠCH CHI TIẾT - PHASE 0

## KIẾN TRÚC HYBRID, HỢP ĐỒNG DỮ LIỆU `render_props` & WALKING SKELETON REMOTION

*(Mã tài liệu: PLAN_PHASE_0_REMOTION_ARCHITECTURE · rev 2 · 2026-09-25)*

> **Ghi chú sửa đổi so với rev 1**
>
> - Dự án Remotion chuyển vào thư mục `remotion/`. Rev 1 đặt `src/index.ts` và `src/Root.tsx`, trùng với thư mục `src/` của Python.
> - Bỏ `story-parser.ts` và `state-manager.ts`: Python đã có hai phần này và sẽ giữ lại (quyết định D1). Thay vào đó là sửa Script Orchestrator Python cho đúng `RULES_AUDIO_TO_VIDEO.md`.
> - Schema:
>   - Bỏ `durationInFrames` mặc định 150, vì giá trị mặc định này làm lệch hình với tiếng.
>   - Thêm các trường audio, words, captions, visual, sfx.
>   - Thêm `rapid_zoom_in` vào enum. Parser Python đang sinh giá trị này nhưng enum rev 1 không có, nên Zod sẽ từ chối.
> - Đổi `@remotion/tailwind` thành `@remotion/tailwind-v4`. Phiên bản zod ghim theo đúng bản Remotion yêu cầu. fps lấy từ config (24), không ghi cứng 30.
> - Đổi `npx remotion preview` thành `npx remotion studio`.
> - Lưu ý: `remotion.config.ts` **không** được áp dụng khi render bằng Node API (Phase 4). Khi đó mọi tham số render phải truyền trực tiếp.
>
> **Bổ sung rev 2.1 (sau khi rà soát plan)**
>
> - **Số frame lưu dạng số nguyên.** Rev 2 bắt exporter assert `|duration·fps − round(duration·fps)| < 1e-6`. Phép assert này sẽ báo lỗi ở 4/7 cảnh của chương mẫu, vì `plan_shot_duration` làm tròn tới 4 chữ số thập phân (ví dụ 6,4583 × 24 = 154,9992). Nay Python tính và lưu thẳng số frame nguyên (mục 3.3).
> - **Quy ước `null` thống nhất giữa Zod và Pydantic.** Bỏ `.optional()` và `.default()`: mọi key luôn có mặt, giá trị vắng ghi là `null`. Mọi object dùng `.strict()` để khớp với `extra="forbid"` (mục 3.1).
> - Định nghĩa đủ các trường cho cảnh `title_card` và `end_screen`, và cách skeleton hiển thị hai loại cảnh này.
> - Bổ sung danh sách cỡ cảnh cho HOOK và CLIFFHANGER. Nói rõ `over_shoulder` chỉ là đề xuất, có thể bị hạ cấp ở Phase 2.
> - Thêm `requirements.txt` và danh sách gói npm theo từng phase. Chốt tên các `--stage` (bảng chuẩn nằm trong README).
>
> **Bổ sung rev 2.2 (rà soát lần 2, đã kiểm chứng API trên gói Remotion 4.0.407)**
>
> - **Cú pháp chú thích trong `.txt`** gom về một bảng (mục 3.4b). Thêm các quy tắc gán `environmentId`, `onScreenCharacterId` và khóa nhân vật mà rev 2.1 chưa định nghĩa.
> - **`plan_shot_frames` nhận thêm tham số `pad_sec`**, vì Phase 1 dùng đệm `dramatic_pause_sec` cho một số cảnh.
> - **Cảnh dài được tách hình, không tách câu** (mục 3.4c). Rev 2.1 tách câu rồi chạy TTS lại, nhưng với câu 0 của chương mẫu cách đó chỉ tạo ra mảnh 3 âm tiết, hoặc làm TTS ngắt giọng sai chỗ. Nay một câu vẫn là một file TTS, còn hình chia thành các cảnh con phát nối tiếp cùng file audio (`audio.startInFileSec`).
> - Nói rõ cách tính tỉ lệ hồi khi có HOOK, cách phá hòa điểm Hook, thứ tự ưu tiên camera và cấu trúc `story_rules.json`. Cả hai đã được chạy thử trên chương mẫu.
> - **Hai chỗ trong plan không khớp với gói 4.0.407:**
>   - `<Audio>` đã bị deprecated và đổi tên thành `<Html5Audio>`.
>   - `tailwindcss` phải ghim đúng bản mà `@remotion/tailwind-v4` phụ thuộc (4.1.1), không lấy 4.0.0 của template.
> - `.gitignore` chỉ bỏ qua `remotion/public/chapters/`, để texture grain của Phase 2 vẫn commit được.
> - Khối `render` trong settings có giá trị mặc định. Pipeline truyền `--crf` và `--concurrency` tường minh khi gọi CLI.
> - **Sau khi một agent độc lập rà soát:**
>   - Mọi file sinh ra đặt trong `output/<chapterId>/`, và audio TTS chuyển ra khỏi `assets/audio/shots/` (README, mục "Bố cục file theo chương").
>   - Test đọc bản đóng băng trong `tests/fixtures/sample_chapter/`.
>   - `chapterId` bỏ hậu tố `.annotated`.
>   - Định nghĩa cách đặt id cảnh.
>   - Thêm thẻ `[EMO: …]`.
>   - `ContractModel` dùng `strict=True`.
>   - Sửa 3 tiêu chí Gate 0 không kiểm được hoặc mâu thuẫn với thiết kế:
>     - giới hạn 6,5 s chỉ áp cho cảnh `story`;
>     - khoảng lặng tại điểm cắt so với file gốc;
>     - file props của exporter được kiểm bằng Zod qua biến môi trường.

---

## 1. MỤC TIÊU & PHẠM VI (SCOPE & OBJECTIVES)

### 1.1. Mục tiêu

1. Khởi tạo dự án **Remotion v4 + React 19 + TypeScript + Tailwind v4** trong thư mục `remotion/`.
2. Định nghĩa hợp đồng dữ liệu **`render_props.json`** ở cả hai phía (Pydantic ↔ Zod), kèm test chéo hai ngôn ngữ trên cùng một file mẫu.
3. Viết **exporter Python**: nhận storyboard + audio + ảnh, xuất `output/<chapterId>/render_props.json` và copy tài sản vào `remotion/public/chapters/<chapterId>/`.
4. Sửa **Script Orchestrator** Python theo đúng `RULES_AUDIO_TO_VIDEO.md`: hook cold-open, 4 hồi theo tỉ lệ, có CLIFFHANGER, tách câu dài, nhận diện lời thoại.
5. Dựng **walking skeleton**: composition `StoryComposition` render được video từ props thật (ảnh full khung + zoom đơn giản + giọng đọc). Nhờ vậy các phase sau chỉ cần thay component, không phải đụng lại luồng dữ liệu.

### 1.2. Hiện trạng đã có (không làm lại)

- `src/core/models.py`: Pydantic `Shot`, `Storyboard`, `CharacterDNA`, `EnvironmentAnchor`.
- `src/core/state_manager.py`: có nhưng `run_pipeline.py` **chưa dùng**.
- `plan_shot_duration()` và `build_srt_entries()` trong `run_pipeline.py`, đã có test.

### 1.3. Ngoài phạm vi

- Chuẩn hóa phát âm và Foley (Phase 1).
- Component điện ảnh (Phase 2).
- Diễn xuất nhân vật (Phase 3).
- Mastering cho đầu ra Remotion (Phase 4).

---

## 2. KIẾN TRÚC DỰ ÁN & DANH MỤC TỆP

```text
d:\_Short_film\
├── run_pipeline.py                     # [sửa] thêm --renderer {ffmpeg,remotion}, --stage, --title, --env; thêm plan_shot_frames()
├── requirements.txt                    # [mới] dependency Python, ghim phiên bản (mục 3.7)
├── config/
│   ├── settings.json                   # [sửa] thêm khối "render" (mục 3.5); visuals.title_card_sec, end_screen_sec, split_min_duration
│   └── story_rules.json                # [mới] từ khóa độ căng, từ khóa cảm xúc, động từ di chuyển
├── src/                                # Python, giữ nguyên vị trí
│   ├── core/models.py                  # [sửa] thêm RenderProps / RenderScene (camelCase alias); mở rộng Shot (mục 3.5)
│   ├── story_parser.py                 # [sửa] theo RULES (mục 3.4)
│   └── export/
│       └── remotion_props.py           # [mới] storyboard → render_props.json + copy tài sản
├── tests/
│   ├── fixtures/sample_chapter/        # [mới] chép từ assets/audio/shots/ (mp3 + .words.json), không bao giờ bị pipeline ghi đè
│   ├── test_render_props_contract.py   # [mới]
│   ├── test_visual_split.py            # [mới] mục 3.4c
│   └── test_story_rules.py             # [mới]
└── remotion/                           # [mới] dự án Node độc lập
    ├── package.json
    ├── remotion.config.ts
    ├── tsconfig.json                   # strict, ES2022, resolveJsonModule
    ├── vitest.config.ts
    ├── public/
    │   └── chapters/                   # sinh tự động mỗi lần chạy, thêm vào .gitignore
    ├── src/
    │   ├── index.ts                    # registerRoot(RemotionRoot)
    │   ├── index.css                   # @import "tailwindcss"; Phase 2 thêm token màu vào đây
    │   ├── Root.tsx                    # import "./index.css" + <Composition> + calculateMetadata
    │   ├── schemas/render-props.ts     # Zod, khớp 1-1 với Pydantic
    │   ├── fixtures/
    │   │   ├── render_props.sample.json    # file mẫu dùng chung cho test Python & TS
    │   │   └── invalid/*.json              # mỗi file sai đúng 1 lỗi: phải bị từ chối ở cả 2 phía
    │   └── scenes/StoryComposition.tsx # skeleton: <Series> + <Img> + <Html5Audio>
    └── tests/
        ├── render-props.test.ts        # file mẫu đúng + bộ invalid/
        └── props-file.test.ts          # kiểm file props thật do exporter sinh ra (mục 5)
```

Thêm vào `.gitignore`: `remotion/node_modules/`, `remotion/public/chapters/`, `remotion/out/`, `packages/`.

- **Không bỏ qua cả `remotion/public/`**, vì Phase 2 commit texture `remotion/public/textures/grain_512.png`.
- `.gitignore` hiện có dòng `output/*.mp4` và `output/clips/`. Nên thêm `output/*/` để bỏ qua cả thư mục kết quả theo từng chương (`output/<chapterId>/`).

---

## 3. THIẾT KẾ KỸ THUẬT CHI TIẾT

### 3.1. Hợp đồng `render_props.json` (`remotion/src/schemas/render-props.ts`)

Các nguyên tắc chung:

- Key dạng camelCase ở cả hai phía. Pydantic dùng `alias_generator=to_camel` và `extra="forbid"`.
- Mọi đường dẫn `src` đều **tương đối với `remotion/public/`** và dùng dấu `/`.
- Mọi mốc thời gian trong một cảnh tính bằng **giây, kể từ đầu cảnh**. Riêng `ambience` và `bgm` tính theo **giây tuyệt đối** trên toàn timeline.
- Mọi giá trị thời gian đều do Python tính (quyết định D5). Remotion không tự đo lại.
- **Quy ước key và `null`** (để Zod và Pydantic kiểm tra giống hệt nhau):
  - **Mọi key luôn có mặt.** Giá trị vắng ghi là `null`, và phía Zod khai báo trường đó bằng `.nullable()`.
  - **Không dùng `.optional()` và `.default()`** trong schema. Lý do: `.optional()` của Zod từ chối `null`. Nếu Python bỏ key bằng `exclude_none=True` thì các trường `.nullable()` lại báo "Required". Còn `.default()` làm Zod chấp nhận thiếu key trong khi Pydantic thì không.
  - **Mọi `z.object` đều gọi `.strict()`.** Mặc định Zod âm thầm bỏ key lạ, còn Pydantic `extra="forbid"` thì từ chối. `.strict()` làm hai bên hành xử giống nhau.
  - **Phía Pydantic:** trường nullable khai báo `Optional[X]` **không có giá trị mặc định**. Trong Pydantic v2, như vậy nghĩa là key bắt buộc nhưng được phép `null`. Ghi file bằng `model_dump(mode="json", by_alias=True)`, **không** dùng `exclude_none` hay `exclude_defaults`.

```typescript
import { z } from "zod";

const Sec = z.number().nonnegative();

export const WordSchema = z.object({
  text: z.string(),   // từ theo VĂN BẢN GỐC (đã căn ở Phase 1)
  start: Sec,
  end: Sec,
}).strict();

export const CaptionSchema = z.object({
  text: z.string(),                // cụm 3–6 từ, văn bản gốc
  start: Sec,
  end: Sec,
  highlight: z.array(z.string()),  // cụm từ khóa cần tô màu (có thể nhiều từ); không có thì []
}).strict();

export const SfxSchema = z.object({
  src: z.string(),
  startSec: Sec,                    // tính từ đầu cảnh, Python kẹp về ≥ 0
  volume: z.number().min(0).max(1), // tuyến tính, đã đổi từ dB ở Python
  durationSec: Sec.nullable(),      // null = phát hết file
  fadeInSec: Sec,                   // không fade thì ghi 0
  fadeOutSec: Sec,
}).strict();

export const VisualSchema = z.object({
  mode: z.enum(["layered", "full_image", "clip"]),
  imageSrc: z.string().nullable(),      // full_image: ảnh full khung
  backgroundSrc: z.string().nullable(), // layered: plate theo environment (Phase 2)
  characterSrc: z.string().nullable(),  // layered: nhân vật tách nền PNG alpha (Phase 2)
  clipSrc: z.string().nullable(),       // clip Kling/Hedra (Phase 3)
}).strict();

export const SceneSchema = z.object({
  id: z.string(),
  kind: z.enum(["story", "title_card", "end_screen"]),
  act: z.enum(["HOOK", "SETUP", "RISING", "CLIMAX", "CLIFFHANGER"]),
  rawText: z.string(),                       // hiển thị (phụ đề)
  voiceText: z.string(),                     // đưa vào TTS (Phase 1 chuẩn hóa)
  speaker: z.string(),                       // "narrator" hoặc key trong characters.json
  isDialogue: z.boolean(),
  onScreenCharacterId: z.string().nullable(),
  environmentId: z.string(),
  shotType: z.enum(["wide", "medium", "closeup", "extreme_closeup", "over_shoulder"]),
  cameraMotion: z.enum(["zoom_in", "rapid_zoom_in", "zoom_out", "pan_left", "pan_right", "static"]),
  durationInFrames: z.number().int().positive(), // BẮT BUỘC, không có giá trị mặc định
  audio: z.object({ src: z.string(), startInFileSec: Sec, durationSec: Sec }).strict().nullable(), // mục 3.4c
  words: z.array(WordSchema),
  captions: z.array(CaptionSchema),
  sfx: z.array(SfxSchema),
  visual: VisualSchema,
}).strict();

export const AmbienceSchema = z.object({
  src: z.string(),
  startSec: Sec,   // tuyệt đối
  endSec: Sec,
  volume: z.number().min(0).max(1),
  fadeSec: Sec,
}).strict();

export const BgmSchema = z.object({
  src: z.string(),
  volume: z.number().min(0).max(1),        // mức nền khi không có giọng
  duckedVolume: z.number().min(0).max(1),  // mức khi có giọng
  duckIntervals: z.array(z.tuple([Sec, Sec])), // giây tuyệt đối
  cutAtSec: Sec.nullable(),                // tắt nhạc ở CLIFFHANGER (Phase 1)
}).strict();

export const RenderPropsSchema = z.object({
  schemaVersion: z.literal(1),
  chapterId: z.string(),
  title: z.string(),
  fps: z.number().int().positive(),
  width: z.number().int().positive(),
  height: z.number().int().positive(),
  scenes: z.array(SceneSchema).min(1),
  ambience: z.array(AmbienceSchema),
  bgm: BgmSchema.nullable(),
}).strict();

export type RenderProps = z.infer<typeof RenderPropsSchema>;
export type Scene = z.infer<typeof SceneSchema>;
```

**Phía Pydantic** (`src/core/models.py`), ví dụ cho `Visual`:

```python
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, NonNegativeFloat
from pydantic.alias_generators import to_camel

Sec = NonNegativeFloat  # khớp z.number().nonnegative()

class ContractModel(BaseModel):
    # strict=True: không ép kiểu "1.5" → 1.5 hay "true" → True, giống Zod (đã kiểm trên Pydantic 2.11.7).
    # Strict vẫn nhận số nguyên JSON cho trường float.
    # Strict KHÔNG nhận list Python cho trường tuple (đọc JSON thì vẫn được): exporter phải dựng
    # duckIntervals bằng tuple, ví dụ [(0.0, 1.5)], không phải [[0.0, 1.5]].
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", strict=True)

class Word(ContractModel):
    text: str
    start: Sec
    end: Sec

class Visual(ContractModel):
    mode: Literal["layered", "full_image", "clip"]
    image_src: Optional[str]       # không có default → key bắt buộc, cho phép null (khớp .nullable())
    background_src: Optional[str]
    character_src: Optional[str]
    clip_src: Optional[str]
```

`populate_by_name=True` cho phép code Python tạo model bằng tên snake_case. Nhưng nó cũng làm Pydantic chấp nhận key `image_src` trong JSON, trong khi Zod `.strict()` từ chối key đó. Vì vậy, khi **đọc file JSON**, mọi chỗ (test hợp đồng, exporter đọc lại props) đều gọi `RenderProps.model_validate_json(text, by_name=False)` để chỉ nhận key camelCase. Cờ `by_name` có từ Pydantic 2.11, máy dev đang dùng 2.11.7.

**Quy tắc tiến hóa schema.** Khi phase sau thêm trường mới, trong cùng một PR phải làm đủ 3 việc: cập nhật Zod, cập nhật Pydantic, và cập nhật `render_props.sample.json`. Trường mới cũng tuân theo quy ước key/`null` ở trên. Test hợp đồng ở hai phía sẽ bắt mọi chỗ lệch. Khi đổi schema theo cách không tương thích ngược thì tăng `schemaVersion`.

Ở Phase 0, `words`, `captions`, `sfx` và `ambience` có thể là mảng rỗng, `bgm` là `null`. Trường `captions` tạm lấy mỗi câu làm một cụm, dùng mốc `.words.json` hiện có.

**Các file mẫu sai (`fixtures/invalid/`).** Mỗi file chỉ sai **đúng một chỗ**. Nếu gộp nhiều lỗi vào một file thì chỉ cần bắt được một lỗi là test đã PASS, và các lỗi còn lại bị che mất. Test hợp đồng duyệt qua mọi file và yêu cầu **cả hai phía** đều từ chối:

| File | Lỗi |
| :--- | :--- |
| `missing_duration.json` | Thiếu `durationInFrames` |
| `unknown_camera_motion.json` | `cameraMotion: "dolly_zoom"` |
| `extra_key.json` | Cảnh có key lạ `foo` |
| `snake_case_key.json` | Dùng `image_src` thay cho `imageSrc` |
| `missing_nullable_key.json` | Thiếu hẳn key `visual.clipSrc` (thay vì ghi `null`) |
| `negative_time.json` | `words[0].start = -0.1` |
| `fractional_frames.json` | `durationInFrames: 154.9992` |
| `string_number.json` | `words[0].start: "0.1"` (chuỗi thay vì số). Pydantic chỉ từ chối được nhờ `strict=True`. |

### 3.1b. Cảnh `title_card` và `end_screen`

Hai loại cảnh này vẫn phải có đủ mọi trường của `SceneSchema`. Python điền như sau:

| Trường | `title_card` | `end_screen` |
| :--- | :--- | :--- |
| `id` | `title_card` | `end_screen` |
| `act` | `HOOK`: thuộc khối mở đầu, để hồi SETUP bắt đầu từ cảnh `story` đầu tiên | `CLIFFHANGER` |
| `rawText` | Tên chương | `""` |
| `voiceText` | `""` | `""` |
| `speaker` / `isDialogue` / `onScreenCharacterId` | `"narrator"` / `false` / `null` | như bên trái |
| `environmentId` | Bối cảnh của cảnh `story` kế tiếp | Bối cảnh của cảnh `story` cuối |
| `shotType` / `cameraMotion` | `"wide"` / `"static"` | như bên trái |
| `durationInFrames` | `round(settings.visuals.title_card_sec · fps)`, mặc định 2,5 s | `round(settings.visuals.end_screen_sec · fps)`, mặc định 10 s, giới hạn 5–20 s. Đặt `0` thì không chèn cảnh này. |
| `audio` | `null` | `null` |
| `words` / `captions` / `sfx` | `[]` | `[]` |
| `visual` | Chép từ cảnh `story` kế tiếp | Chép từ cảnh `story` cuối |

- **Bất biến #1 trong README** (tối thiểu 4 s, tính từ giọng đọc + đệm) chỉ áp dụng cho cảnh `story`. Hai loại cảnh này dùng thời lượng lấy từ config.
- **Không có mục SRT nào** cho hai loại cảnh này, vì `captions` rỗng.

### 3.2. Root & `calculateMetadata` (`remotion/src/Root.tsx`)

```tsx
import "./index.css"; // Tailwind v4, giống template
import { Composition } from "remotion";
import { StoryComposition } from "./scenes/StoryComposition";
import { RenderPropsSchema, type RenderProps } from "./schemas/render-props";
import sample from "./fixtures/render_props.sample.json";

export const RemotionRoot: React.FC = () => (
  <Composition
    id="StoryComposition"
    component={StoryComposition}
    schema={RenderPropsSchema}
    defaultProps={sample as RenderProps}
    // Giá trị giữ chỗ; calculateMetadata sẽ ghi đè bằng số liệu từ props thật
    durationInFrames={1}
    fps={24}
    width={1920}
    height={1080}
    calculateMetadata={({ props }) => ({
      durationInFrames: props.scenes.reduce((sum, s) => sum + s.durationInFrames, 0),
      fps: props.fps,
      width: props.width,
      height: props.height,
    })}
  />
);
```

Để xem chương thật trong Studio: `npx remotion studio --props=../output/<chapterId>/render_props.json`.

### 3.3. Exporter Python (`src/export/remotion_props.py`)

- **Đầu vào:** storyboard (danh sách `Shot`) và `settings.json`.
- **Copy tài sản** vào `remotion/public/chapters/<chapterId>/{audio,images}/`. Chỉ copy khi kích thước hoặc mtime khác, và xóa file thừa của lần chạy trước trong cùng chapter.
- **Số frame là số nguyên, tính một lần ở Python:**
  - Thêm hàm `plan_shot_frames(audio_duration, fps, min_duration, pad_sec=SHOT_TAIL_PAD_SEC) -> int` vào `run_pipeline.py`. Hàm trả về `ceil(max(audio + pad_sec, min_duration) · fps − 1e-6)`. Phase 1 truyền `pad_sec = dramatic_pause_sec` cho một số cảnh (Phase 1 mục 3.4).
  - `plan_shot_duration` giữ nguyên chữ ký cho renderer ffmpeg, nhưng tính lại bằng `plan_shot_frames(...) / fps`. Test hiện có vẫn PASS.
  - Storyboard lưu `duration_frames` (int). `duration = duration_frames / fps` chỉ để hiển thị.
  - Exporter ghi thẳng `durationInFrames = shot.duration_frames` và **không** nhân ngược từ giây.
  - Lý do: `plan_shot_duration` hiện làm tròn 4 chữ số thập phân, nên `round(duration · fps)` vẫn đúng, nhưng mọi phép assert "nằm trên lưới frame" chặt hơn 1e-3 đều báo lỗi. Ví dụ 6,4583 × 24 = 154,9992.
  - Test: tổng `durationInFrames` bằng tổng `duration_frames` của storyboard. Mọi giá trị là số nguyên dương.
- **`visual.mode`:** ở Phase 0 luôn là `full_image`. Ưu tiên ảnh `assets/images/<shot_id>.jpg`, không có thì dùng `assets/characters/main_char_face.jpg` (đúng hành vi baseline). Phase 2A sẽ nâng cấp lên `layered`.
- **`title_card` / `end_screen`:** điền theo bảng ở mục 3.1b.
- **`shotType`:** map từ enum. Parser hiện đang dùng chuỗi mô tả kiểu "tight close-up shot" vừa làm tên cỡ cảnh vừa làm prompt. Parser mới phải tách thành 2 trường: `shot_type` (enum) và `shot_prompt` (câu mô tả).
- **Kiểm tra trước khi ghi:** validate bằng Pydantic rồi mới ghi `output/<chapterId>/render_props.json`.

### 3.4. Script Orchestrator Python (sửa `src/story_parser.py`) theo RULES

| Quy tắc (`RULES_AUDIO_TO_VIDEO.md`) | Code hiện tại | Sửa thành |
| :--- | :--- | :--- |
| **§1.1** Hook lấy khoảnh khắc gay cấn ở giữa hoặc cuối chương, sau đó mới hiện tiêu đề chương | Luôn lấy câu đầu tiên. Không có title card. | Chấm điểm "độ căng" cho mọi câu dựa trên: từ khóa trong `config/story_rules.json`, dấu `...`, `?`, `!`. Câu điểm cao nhất làm Hook; hai câu bằng điểm thì lấy câu đứng sau (gần cao trào hơn). Nếu câu đó là câu 0 thì dùng tại chỗ. Nếu không thì lặp lại câu đó làm cold-open. Sau Hook chèn cảnh `title_card` (các trường theo mục 3.1b). Cho phép đánh dấu tay bằng thẻ `[HOOK]` (mục 3.4b). |
| **§1.3** 4 hồi theo tỉ lệ 20/40/30/10, có CLIFFHANGER | Gán hồi theo chỉ số câu (≤ 2, ≤ 5, còn lại). CLIFFHANGER không bao giờ được gán. | Gán theo tỉ lệ số âm tiết cộng dồn (xấp xỉ thời lượng trước khi chạy TTS): SETUP 0–20 %, RISING 20–60 %, CLIMAX 60–90 %, CLIFFHANGER 90–100 %. Tỉ lệ tính trên các cảnh `story` **sau** HOOK. Nếu Hook là câu 0 dùng tại chỗ thì câu đó chỉ mang hồi HOOK và không tính vào tỉ lệ. Hồi của một cảnh lấy theo vị trí **điểm giữa** của cảnh trên thang âm tiết cộng dồn. Cảnh `story` cuối luôn là CLIFFHANGER. |
| **§1.2** Mỗi cảnh 4–6 s | Chỉ in cảnh báo khi > 6,5 s. Chương mẫu có `shot_03` dài 7,4 s. | **Tách hình, không tách giọng đọc** (xem mục 3.4c). Mỗi câu vẫn là một file TTS. Cảnh nào dài hơn `shot_max_duration` thì được chia thành các cảnh con, cắt tại khoảng nghỉ giữa các từ, và các cảnh con phát nối tiếp cùng một file audio. Số đo trên chương mẫu (3,57 âm tiết/s): câu 0, 3, 4 dài 6,6 s / 7,34 s / 6,53 s nên đều phải chia. |
| **§2.2** Không để 2 cảnh liên tiếp cùng cỡ cảnh; hồi quyết định cỡ cảnh | Xoay vòng cố định 4 loại, không quan tâm hồi. | Mỗi hồi có một danh sách ưu tiên: **HOOK:** closeup / extreme_closeup · **SETUP:** wide / medium · **RISING:** medium / over_shoulder · **CLIMAX:** closeup / extreme_closeup · **CLIFFHANGER:** extreme_closeup / closeup / medium. Chọn phần tử đầu tiên trong danh sách **khác** cỡ cảnh của cảnh `story` liền trước. Một `title_card` nằm giữa hai cảnh thì hai cảnh đó không tính là liền nhau. Các cảnh sinh ra do tách câu dài cũng phải tuân thủ luật này. **`over_shoulder` chỉ là đề xuất:** Phase 2 (`asset_check`) hạ nó xuống cỡ khác khi không có ảnh riêng, rồi chạy lại luật không trùng (xem Phase 2 mục 3.1). |
| **§2.3** Camera theo cảm xúc | Xoay vòng cố định. | Xét theo thứ tự, gặp điều kiện đầu tiên thì dừng: (1) Hook → `rapid_zoom_in`. (2) Cảnh cuối của mỗi hồi → `zoom_out`. (3) Câu có động từ di chuyển → `pan_left` / `pan_right` luân phiên. (4) Câu có từ khóa căng thẳng → `zoom_in`. (5) Còn lại → `zoom_in`. `static` chỉ dùng cho `title_card` / `end_screen`, vì RULES §2.3 cấm cảnh `story` đứng yên hoàn toàn. |
| Lời thoại | Không nhận diện. | Nhận diện các dạng `“…”`, `"…"`, dòng mở đầu bằng `—` hoặc `-`, và thẻ `[Tên]:`. Lời thoại được tách thành cảnh riêng với `isDialogue=true`. `speaker` là key nhân vật, lấy từ thẻ hoặc từ tên đứng trước `:` / "nói". Mặc định là `narrator`. |
| SFX cue | Gán `rain_foley.mp3` xen kẽ cảnh chẵn/lẻ. File này **không tồn tại** (file thật tên `rain_ambient.mp3`) và cũng không cảnh nào dùng tới. | Xóa. Phase 1 sẽ lập kế hoạch Foley theo từ khóa và mốc thời gian. |
| Tiêu đề chương | Không có. | Thứ tự ưu tiên: tham số `--title`, rồi dòng đầu dạng `Chương N: …` (dòng này bị bỏ khỏi phần kể), cuối cùng là tên file (đã bỏ `.txt` và hậu tố `.annotated`). Chương mẫu không có dòng tiêu đề nên sẽ lấy theo tên file. `chapterId` = tên file bỏ đuôi `.txt` và hậu tố `.annotated`, bỏ dấu, chỉ giữ `[a-z0-9_]`. Ví dụ `sample_chapter.annotated.txt` → `sample_chapter`. |
| Cảnh kết | Không có. | Chèn cảnh `end_screen` (mục 3.1b) vào cuối storyboard nếu `settings.visuals.end_screen_sec > 0`. |

**Cấu trúc `config/story_rules.json`:**

```json
{
  "tension_keywords": ["không hề có hơi thở", "bí mật", "kinh hoàng", "máu", "chết", "run rẩy"],
  "tension_weights": { "keyword": 2, "ellipsis": 2, "question": 1, "exclamation": 1 },
  "emotion_keywords": ["kinh hoàng", "bất ngờ", "bí mật", "không hề", "kỳ lạ"],
  "movement_verbs": ["bước", "chạy", "lùi lại", "quay lại", "ngẩng đầu", "lao tới"],
  "phrase_starters": ["vào", "trong", "để", "và", "nhưng", "rồi", "khi", "mà", "thì", "với", "trên", "dưới", "từ", "nơi"]
}
```

- **Điểm độ căng** của một câu = Σ trọng số: mỗi từ khóa căng thẳng khớp, có `...` / `…`, có `?`, có `!`.
- **`emotion_keywords`** dùng để tô màu phụ đề (Phase 1 mục 3.5).
- **Ca test với chương mẫu:**
  - Câu 0 được 4 điểm, vì có `...` và cụm "không hề có hơi thở".
  - Câu 5 được 2 điểm, vì có "run rẩy".
  - Các câu còn lại được 0 điểm.
  - Vậy Hook là câu 0, dùng tại chỗ.
  - Lưu ý khi sửa danh sách từ khóa: thêm một từ có trong câu 5 (ví dụ "lạnh ngắt") sẽ làm câu 5 hòa điểm với câu 0. Khi đó quy tắc hòa điểm chọn câu đứng sau, tức câu 5, nên ca test này phải cập nhật theo.
- Mọi so khớp chạy trên chuỗi chuẩn NFC, chữ thường, và khớp nguyên từ. Nhờ vậy "bước" không khớp nhầm vào "bướng".

### 3.4b. Cú pháp chú thích, bối cảnh và nhân vật trên hình

**Các thẻ chú thích trong file `.txt`** (người dùng hoặc agent ở Phase 4 viết vào `*.annotated.txt`):

| Thẻ | Vị trí | Ý nghĩa | Dùng từ |
| :--- | :--- | :--- | :---: |
| `[HOOK]` | Đầu câu | Chọn câu này làm Hook, không chấm điểm độ căng nữa | P0 |
| `[Tên]: …` | Đầu dòng | Lời thoại của nhân vật có `name` = Tên | P0 |
| `[ENV: env_key]` | Dòng riêng | Đổi bối cảnh, áp dụng từ dòng kế tiếp trở đi | P0 |
| `[ON: Tên]` / `[ON: none]` | Đầu câu | Ép nhân vật xuất hiện trên hình ở câu này / không có ai | P0 |
| `[SFX: ten_file.mp3]` / `[SFX: none]` | Đầu câu | Chỉ định SFX one-shot cho cảnh / tắt SFX | P1 |
| `[BGM: ten_file.mp3]` / `[BGM: none]` | Dòng riêng, trước câu kể đầu tiên | Chọn BGM cho cả chương / tắt nhạc | P1 |
| `[EMO: từ 1, cụm từ 2, …]` | Dòng riêng, trước câu kể đầu tiên | Thêm từ khóa cảm xúc riêng cho chương này (tô màu phụ đề), cộng thêm vào `story_rules.json → emotion_keywords`. Agent ở Phase 4 ghi đề xuất của mình bằng thẻ này. | P1 |

- Tên thẻ không phân biệt hoa thường.
- **Parser gỡ mọi thẻ khỏi `raw_text` và `voice_text`**, kể cả thẻ `SFX` / `BGM` / `EMO` mà Phase 0 chưa dùng. Nhờ vậy TTS không bao giờ đọc thẻ lên. Gặp thẻ lạ thì in cảnh báo và gỡ bỏ.
- `[Tên]:` khác với các thẻ còn lại vì dấu `:` nằm **ngoài** ngoặc. `Tên` được so với trường `name` trong `characters.json`, không phân biệt hoa thường. Không khớp thì in cảnh báo và gán `speaker = "narrator"`.

**Khóa nhân vật và bối cảnh.** `speaker`, `onScreenCharacterId`, `environmentId` và **tên thư mục tài sản** (`assets/characters/<khóa>/`, `assets/environments/<khóa>/` ở Phase 2) đều dùng **khóa object** trong file JSON, ví dụ `nhan_vat_chinh`, `phong_khach_dem_mua`. Không dùng trường `id` (`char_01`, `env_01`). Trường `name` ("Nam") chỉ dùng để tra từ thẻ hoặc từ tên xuất hiện trong câu.

**Id cảnh.** Người dùng đặt tên file ảnh và clip theo id cảnh (`assets/images/<shot_id>.jpg`, `input/rendered_clips/<shot_id>.mp4`), nên cách đặt id phải cố định:

| Cảnh | Id |
| :--- | :--- |
| Đơn vị kể thứ i: mỗi câu kể **và** mỗi lời thoại được tách thành cảnh riêng đều là một đơn vị, đếm từ 0 theo thứ tự trong văn bản, sau khi đã gỡ thẻ | `shot_{i:02d}`, ví dụ `shot_03`. Câu 0 **luôn** là `shot_00`, kể cả khi nó được dùng làm Hook tại chỗ. |
| Hook cold-open (bản lặp lại của một câu i > 0, đặt lên đầu phim) | `shot_hook`. Câu gốc vẫn giữ `shot_{i:02d}`. |
| Cảnh con (mục 3.4c) | Id cha + `a`, `b`, `c`…, ví dụ `shot_03a` |
| Title card / end screen | `title_card` / `end_screen` |

- **Id của một câu không phụ thuộc việc câu nào được chọn làm Hook.** Rev 2.1 đặt tên `shot_00_hook` cho cả hai trường hợp, nên chỉ cần đổi từ khóa là ảnh `assets/images/shot_00_hook.jpg` đã âm thầm gắn sang câu khác.
- **Bảng trên không giữ tên `shot_00_hook` của baseline.** File `shot_00_hook.*` trong `tests/fixtures/sample_chapter/` là câu 0, tức `shot_00`; test ánh xạ tên này một lần.
- **`shot_hook.jpg`** luôn là ảnh của cảnh cold-open. Nếu đổi từ khóa làm Hook chuyển sang câu khác, pipeline in cảnh báo để người dùng kiểm tra lại ảnh này.

- **Ảnh riêng cho cảnh con:** tìm `assets/images/<id cảnh con>.jpg` trước, không có thì dùng ảnh của cảnh cha (`<id cha>.jpg`).
- **Clip hybrid (Phase 3)** chỉ khớp đúng id của cảnh con, không lấy của cảnh cha, vì thời lượng clip gắn với từng cảnh con.

**`environmentId`:**

- Mặc định lấy từ tham số `--env`. Không có thì lấy bối cảnh đầu tiên trong `environments.json` (hiện là `phong_khach_dem_mua`, giống baseline).
- Thẻ `[ENV: …]` đổi bối cảnh từ dòng kế tiếp.
- Khóa bối cảnh không tồn tại thì **dừng với lỗi rõ ràng**, vì gán sai bối cảnh sẽ phá raccord.

**`onScreenCharacterId`**, xét theo thứ tự ưu tiên:

1. Thẻ `[ON: …]`.
2. Cảnh thoại: lấy `speaker`, nếu `speaker` khác `"narrator"`.
3. Câu có nhắc tên nhân vật (khớp nguyên từ với `name`): lấy nhân vật được nhắc đầu tiên.
4. Kế thừa từ cảnh `story` liền trước, nếu hai cảnh cùng `environmentId`.
5. Còn lại là `null`: cảnh chỉ có plate, không có nhân vật.

Áp vào chương mẫu: câu 0 và câu 1 → `null` (cảnh mưa, không có ai). Câu 2 "Nam ngồi…" → `nhan_vat_chinh`. Câu 3 đến câu 6 kế thừa `nhan_vat_chinh`.

### 3.4c. Tách hình cho cảnh dài (stage `audio`)

**Vì sao không tách câu rồi chạy TTS lại.**

- Tách theo dấu câu có thể ra mảnh rất ngắn. Ví dụ câu 0 của chương mẫu có dấu phẩy duy nhất ở âm tiết thứ 3/22.
- Tách giữa mệnh đề thì TTS ngắt nhịp và xuống giọng sai chỗ.
- RULES §1.2 chỉ yêu cầu **hình** thay đổi sau mỗi 4–6 s. Giọng đọc không cần cắt.

**Cách làm.** Việc tách chạy sau khi đã có TTS, dựa trên mốc từ thật:

1. `total = plan_shot_frames(audio, fps, shot_min, pad)` cho cả câu, như bất biến #1.
2. Nếu `total / fps ≤ shot_max_duration` thì giữ nguyên, không tách.
3. Ngược lại, chia thành `N = ceil(total / (shot_max_duration · fps))` cảnh con. Điểm cắt nằm tại ranh giới giữa hai từ; vị trí thời gian là điểm giữa `end` của từ trước và `start` của từ sau, làm tròn về lưới frame.
   - **Ứng viên hợp lệ:** mọi cảnh con dài từ `settings.visuals.split_min_duration` (mặc định 2,5 s) tới `shot_max_duration`.
   - **Chọn theo bậc**, bậc nhỏ hơn thắng. Trong cùng một bậc thì lấy điểm gần mốc `k · total / N` nhất:
     - **Bậc 0:** ngay sau dấu câu `, ; : . … ...`. Phase 1 chèn khoảng lặng kịch tính đúng vào chỗ `...`, nên đây là chỗ cắt đẹp nhất.
     - **Bậc 1:** ngay trước một từ mở đầu cụm, lấy từ danh sách `story_rules.json → phrase_starters` (ví dụ "vào", "trong", "để", "và", "nhưng", "rồi", "khi", "trên", "dưới", "nơi").
     - **Bậc 2:** mọi ranh giới còn lại, **trừ** chỗ nằm giữa hai âm tiết giống nhau (từ láy như "chằm chằm").
   - **Không dùng độ dài khoảng lặng làm tiêu chí.** Mốc WordBoundary của Edge liền nhau (khoảng lặng 0 ms) ở mọi chỗ trừ dấu phẩy, nên tiêu chí này không phân biệt được các ứng viên.
   - **Kết quả mong đợi trên chương mẫu** (đã chạy thử với `.words.json` thật, 24 fps, trước khi Phase 1 chèn khoảng lặng):

     | Câu | Bậc | Cắt | Hai cảnh con |
     | :---: | :---: | :--- | :--- |
     | 0 | 0 | "…trong phòng khách... // không hề có hơi thở." | 3,94 s / 2,69 s |
     | 3 | 0 | "…trầm mặc của anh, // để lộ vết sẹo…" | 3,73 s / 3,65 s |
     | 4 | 1 | "…nhìn chằm chằm // vào chiếc cốc…" | 3,44 s / 3,10 s |

   - **Biết dấu câu nằm ở âm tiết nào.** Ở Phase 0, token của văn bản gốc (một từ kèm dấu câu đứng sau) ánh xạ 1-1 với âm tiết WordBoundary: chương mẫu khớp đủ ở cả 7 câu. Nếu số lượng lệch nhau thì bỏ bậc 0, chỉ xét bậc 1 và 2, và in cảnh báo. Từ Phase 1 trở đi, dùng ánh xạ của `alignment.py`.
4. **Cảnh con** giữ id gốc thêm hậu tố `a`, `b`, `c`… (ví dụ `shot_03a`, `shot_03b`), để id và cache của các cảnh khác không đổi.
   - Các cảnh con dùng **chung file audio**. Cảnh con thứ k có `audio.startInFileSec` = tổng frame của các cảnh con trước nó chia cho fps.
   - `words`, `captions`, `sfx` được chia theo điểm cắt, và mốc thời gian được trừ đi phần lệch để tính lại từ đầu cảnh con. Một cụm phụ đề không được vắt qua điểm cắt.
   - Tổng `durationInFrames` của các cảnh con bằng đúng `total`.
5. **Áp lại luật cỡ cảnh (§2.2) và camera (§2.3)** cho từng cảnh con. Cảnh con sau phải khác cỡ cảnh con trước, nên phần cắt ăn khớp như một cú cắt máy. Với Hook, chỉ cảnh con đầu dùng `rapid_zoom_in`.
6. **`--renderer ffmpeg`** gộp các cảnh con có chung file audio lại thành một clip như baseline. Renderer này không tách hình.

**Schema:** trường `audio` của `SceneSchema` đổi thành:

```typescript
audio: z.object({
  src: z.string(),
  startInFileSec: Sec,   // 0 với cảnh thường; > 0 với cảnh con thứ 2 trở đi (luôn nằm trên lưới frame)
  durationSec: Sec,      // độ dài đoạn audio phát trong cảnh này
}).strict().nullable(),
```

Remotion phát bằng `<Html5Audio src={…} trimBefore={Math.round(startInFileSec * fps)} />` đặt trong Sequence của cảnh. Vì điểm cắt nằm trên lưới frame nên các đoạn audio nối liền nhau, không hụt và không lặp.

### 3.5. `run_pipeline.py`

- Tham số dòng lệnh mới: `--renderer ffmpeg|remotion`, `--stage` (bên dưới), `--title` và `--env` (mục 3.4 và 3.4b).
- `--renderer` mặc định giữ `ffmpeg` cho tới khi qua Gate 4.
  - **`--renderer ffmpeg`** giữ nguyên luồng baseline: chỉ render các cảnh `kind == "story"` và bỏ qua `title_card` / `end_screen`. Renderer này chỉ hỗ trợ `--stage all`.
- Thêm `--stage`. **Danh sách stage chuẩn nằm ở README, mục "Các stage của pipeline".** Phase 0 làm các stage `script`, `audio`, `props`, `video` và `all`. Ở Phase 0, `all` = script → audio → props → video.
- **Chuyển storyboard từ dict sang model** để dùng được `StateManager`:
  - `Shot` trong `src/core/models.py` thêm các trường: `kind`, `shot_type` (enum), `shot_prompt`, `voice_text`, `speaker`, `is_dialogue`, `on_screen_character_id`, `duration_frames`, `audio_start_in_file_sec` (mục 3.4c), `parent_id` (id câu gốc của cảnh con; `null` nếu không tách).
  - `run_pipeline.py` đọc và ghi storyboard qua `Storyboard` / `StateManager` thay cho dict thô. Chạy lại một stage thì bỏ qua những cảnh đã ở trạng thái cần thiết (ví dụ `AUDIO_READY` và file audio vẫn còn).
- **Khối `render` trong `settings.json`:**

  ```json
  "render": { "renderer": "ffmpeg", "concurrency": null, "crf": 18 }
  ```

  - `concurrency: null` nghĩa là để Remotion dùng mặc định của nó. Phase 4 ghi giá trị benchmark vào đây.
  - `renderer` là giá trị mặc định khi không truyền `--renderer`.
- Cách render ở Phase 0 (stage `video`; Phase 4 sẽ thay bằng Node API + mastering). `remotion.config.ts` chỉ phục vụ Studio và lúc chạy CLI bằng tay. **Pipeline luôn truyền `--crf` tường minh**, và truyền `--concurrency` khi giá trị trong settings khác `null`:

  ```powershell
  # cwd = remotion/ ; trên Windows gọi npx.cmd khi chạy từ subprocess
  npx remotion render src/index.ts StoryComposition ../output/<chapterId>/video.remotion.mp4 --props=../output/<chapterId>/render_props.json --crf=18
  ```

- **Âm thanh trong component:** dùng `<Html5Audio>` của `remotion`. Ở bản 4.0.407, `<Audio>` đã bị deprecated và đổi tên thành `Html5Audio`; hai component có cùng props (`volume` dạng hàm, `loop`, `trimBefore`…).
- **Skeleton hiển thị cảnh không phải `story` như sau** (Phase 2 sẽ thay bằng component thật):
  - `title_card`: nền đen, tên chương (`rawText`) chữ trắng ở giữa khung, không có hiệu ứng.
  - `end_screen`: ảnh `visual.imageSrc` làm tối 70 %.

### 3.6. `remotion/package.json` & `remotion.config.ts`

- `remotion` và **mọi gói `@remotion/*` phải cùng một phiên bản chính xác**, không dùng `^`. Remotion yêu cầu điều này.
- **Ghim `4.0.407`**, giống template. Mọi API mà plan dùng đã được kiểm chứng trên bộ gói của bản này (xem bảng bên dưới). Ngày 2026-09-26 đã có bản 4.0.529. Muốn nâng lên thì phải kiểm lại bảng đó và peer dependency zod của `@remotion/zod-types`.
- **Zod**: cài đúng bản mà `@remotion/zod-types` khai báo trong peerDependencies. Với 4.0.407 là `zod@3.22.3` (đã kiểm). Không lấy zod 4 từ `auto-video-gen`.
- **Tailwind**: `tailwindcss` phải cùng phiên bản với bản mà `@remotion/tailwind-v4` phụ thuộc. Với 4.0.407 là **4.1.1** (đã kiểm), **không** lấy `4.0.0` của template. Nếu hai bản lệch nhau, dòng `@import "tailwindcss"` và plugin PostCSS sẽ chạy hai phiên bản Tailwind khác nhau.
- `@remotion/bundler`, `@remotion/renderer` và `@remotion/media-utils` đã được `@remotion/cli` kéo theo, cùng phiên bản. Phase 4 khai báo tường minh hai gói đầu vì `render.ts` import trực tiếp.
- **Danh sách gói theo phase.** Phase nào cần gói nào thì thêm gói đó trong chính PR của phase ấy:

  | Phase | `dependencies` | `devDependencies` |
  | :---: | :--- | :--- |
  | 0 | `remotion`, `@remotion/cli`, `@remotion/zod-types`, `@remotion/tailwind-v4`, `tailwindcss@4.1.1`, `react`, `react-dom` (19.2), `zod@3.22.3` | `typescript`, `@types/react`, `@types/node`, `vitest`, `eslint`, `@remotion/eslint-config-flat` |
  | 2 | `@remotion/google-fonts`, `@remotion/noise` | — |
  | 3 | `@remotion/media-utils` (chỉ khi dùng phương án đo biên độ trong trình duyệt thay cho Python) | — |
  | 4 | `@remotion/bundler`, `@remotion/renderer` | `tsx` |

- **Môi trường đã kiểm tra trên máy dev (2026-09-25):** Node 20.18, npm 10.8, Python 3.12.7, ffmpeg bản build 2025-09.
- **API đã kiểm chứng trên gói 4.0.407** (đọc file `.d.ts` / `.js` trong tarball npm, ngày 2026-09-26):

  | API plan dùng | Kết quả |
  | :--- | :--- |
  | Prop `schema` của `<Composition>` | Kiểu `AnyZodObject`, nên cấp gốc phải là `z.object` |
  | Codec `h264-mkv` | Có. Audio mặc định là `pcm-16`, cả khi nén lẫn khi lossless |
  | `<Audio>` | Deprecated, đổi tên thành `<Html5Audio>` |
  | `<OffthreadVideo>` | Có `playbackRate`, `muted`. **Không có `loop`**, phải bọc bằng `<Loop>` |
  | `<Freeze frame active>` | Có. `active` nhận boolean hoặc hàm `(f) => boolean` |
  | `chromiumOptions.gl` | Nhận `"angle"`, `"swangle"`, `"egl"`, `"swiftshader"`, `"vulkan"`, `"angle-egl"` |
  | `bundle({ entryPoint, webpackOverride })` | Có. `enableTailwind(config) => config` truyền thẳng vào `webpackOverride` được |
  | `noise2D(seed, x, y)` (`@remotion/noise`) | Đúng chữ ký |
  | `loadFont("normal", { weights, subsets })` (`@remotion/google-fonts/BeVietnamPro`) | Đúng chữ ký. Có subset `vietnamese` |
  | `npx remotion benchmark --props=…` | Có. Đọc `--props`, `--concurrencies`, `--runs` |

- Các lệnh: `studio`, `typecheck` (`tsc --noEmit`), `test` (`vitest run`), `lint`. Phase 4 thêm lệnh `render`.

```typescript
// remotion/remotion.config.ts — chỉ áp dụng cho CLI và Studio, KHÔNG áp dụng cho Node API
import { Config } from "@remotion/cli/config";
import { enableTailwind } from "@remotion/tailwind-v4";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setPixelFormat("yuv420p");
Config.setCodec("h264");
Config.setCrf(18);
Config.overrideWebpackConfig(enableTailwind);
// Không đặt concurrency ở đây: giá trị lấy từ benchmark (Phase 4) và truyền qua CLI hoặc Node API
```

### 3.7. `requirements.txt` (Python)

Repo hiện **chưa có** file khai báo dependency. Các gói dưới đây đang được import và đã có sẵn trên máy dev. Ghim đúng phiên bản đang cài:

```text
# Baseline (đang dùng)
pydantic==2.11.7
edge-tts==7.2.8
requests==2.32.3        # src/vbee_client.py
python-dotenv==1.2.2    # đọc .env cho Vbee
```

- **Phase nào cần gói mới thì thêm vào file này trong chính PR đó**, ghim theo phiên bản cài được lúc đó:
  - Phase 2: `rembg[cpu]` (kéo theo `onnxruntime`, `Pillow`, `numpy`).
  - Phase 3: `opencv-python-headless`, `scikit-image` (để tính SSIM).
- **Gói tùy chọn** (`faster-whisper` cho forced alignment khi dùng Vbee, Phase 1) để riêng trong `requirements-optional.txt`.
- **Phần mềm hệ thống** không cài qua pip nhưng bắt buộc có: `ffmpeg` và `ffprobe` trong PATH, Node ≥ 20. Ghi các yêu cầu này vào `README.md` ở gốc repo.

---

## 4. DANH MỤC CÔNG VIỆC THỰC HIỆN (TASK BREAKDOWN)

- [ ] **Task 0.0:** Tạo `requirements.txt` (mục 3.7). Ghi yêu cầu hệ thống (ffmpeg, Node ≥ 20) vào `README.md` ở gốc repo.
- [ ] **Task 0.1:** Khởi tạo `remotion/`: `package.json` ghim phiên bản với các gói của Phase 0 (mục 3.6), `tsconfig.json` strict, `remotion.config.ts`, `vitest.config.ts`. Chạy `npm install`. Cập nhật `.gitignore`.
- [ ] **Task 0.2:** Viết `render-props.ts` (Zod) và model Pydantic tương ứng theo quy ước key/`null` ở mục 3.1. Tạo file mẫu đúng và bộ `fixtures/invalid/`.
- [ ] **Task 0.3:** Viết test hợp đồng ở cả hai phía: `remotion/tests/render-props.test.ts` và `tests/test_render_props_contract.py`. Mỗi phía phải từ chối **từng** file trong `invalid/`. Viết thêm `remotion/tests/props-file.test.ts`: đọc file theo biến môi trường `RENDER_PROPS` và validate bằng Zod; **bỏ qua** khi biến không được đặt, để `npm test` vẫn chạy được trên máy chưa có đầu ra pipeline.
- [ ] **Task 0.4:** Chép `assets/audio/shots/*` sang `tests/fixtures/sample_chapter/`, rồi chuyển đầu ra TTS sang `output/<chapterId>/audio/` (README, mục "Bố cục file theo chương"). Thêm `plan_shot_frames()`. Mở rộng `Shot` và chuyển storyboard sang model (mục 3.5). Viết phần tách hình (mục 3.4c) và exporter `src/export/remotion_props.py`. Test (chỉ đọc dữ liệu trong `tests/fixtures/`):
  - `durationInFrames` là số nguyên và khớp `duration_frames`;
  - tách hình: dùng bản đóng băng trong `tests/fixtures/sample_chapter/`, kết quả phải khớp bảng ở mục 3.4c (cùng điểm cắt, sai số ±1 frame); tổng frame bằng cảnh gốc; `startInFileSec` của cảnh con sau bằng số frame cảnh con trước chia fps; không cụm phụ đề nào vắt qua điểm cắt; không cắt giữa từ láy;
  - đường dẫn tương đối, copy idempotent;
  - `title_card` / `end_screen` qua được schema.
- [ ] **Task 0.5:** Sửa `story_parser.py` theo mục 3.4 và 3.4b, tạo `config/story_rules.json`, thêm `visuals.title_card_sec` / `end_screen_sec` / `split_min_duration` và khối `render` vào settings. Mỗi quy tắc có ít nhất 1 test: hook (điểm 4/2/0 như mục 3.4), title card, tỉ lệ hồi, CLIFFHANGER, không trùng cỡ cảnh liên tiếp (gồm cả HOOK và CLIFFHANGER), thứ tự ưu tiên camera, lời thoại, 7 loại thẻ bị gỡ khỏi văn bản, id cảnh theo bảng ở mục 3.4b (gồm cả lời thoại và cold-open), `[ENV]` với khóa sai phải báo lỗi, `onScreenCharacterId` trên chương mẫu khớp ví dụ ở mục 3.4b, tiêu đề và `chapterId`, end screen.
- [ ] **Task 0.6:** Viết `index.css`, `Root.tsx` + `calculateMetadata` và skeleton `StoryComposition`: `<Series>`, `<Img>` full khung, zoom tuyến tính, `<Html5Audio>` giọng đọc, và phần hiển thị tạm cho `title_card` / `end_screen` (mục 3.5).
- [ ] **Task 0.7:** Làm cho `run_pipeline.py --renderer remotion` chạy trọn chương mẫu với các stage `script` / `audio` / `props` / `video` / `all`, đồng thời `--renderer ffmpeg` vẫn chạy như cũ (bỏ qua cảnh không phải `story`).
- [ ] **Task 0.8:** Chạy kiểm thử Gate 0.

---

## 5. TIÊU CHÍ NGHIỆM THU GATE 0 (ACCEPTANCE CRITERIA)

| Tiêu chí | Điều kiện bắt buộc | Phương thức kiểm tra |
| :--- | :--- | :--- |
| **Dependencies sạch** | `npm install` không lỗi. Mọi gói `@remotion/*` cùng một phiên bản. | `npm ls remotion`, `npm run typecheck` |
| **Hợp đồng dữ liệu** | File mẫu đúng: PASS ở cả Zod lẫn Pydantic. **Từng** file trong `fixtures/invalid/` đều FAIL ở cả hai phía. File do exporter sinh ra cho chương mẫu qua được Zod. | `npm test`, `python -m unittest`, `RENDER_PROPS=../output/sample_chapter/render_props.json npm test` |
| **Script Orchestrator** | Với chương mẫu: có HOOK, có `title_card`, đủ 4 hồi kể cả CLIFFHANGER, cảnh `story` cuối là CLIFFHANGER, có `end_screen`, không có 2 cảnh `story` liền nhau cùng cỡ. Sau stage `audio`: không **cảnh `story`** nào > 6,5 s (`end_screen` mặc định dài 10 s nên không xét), mọi cảnh con ≥ 2,5 s. | `tests/test_story_rules.py`, `tests/test_visual_split.py` |
| **Walking skeleton** | `run_pipeline.py --renderer remotion` xuất ra MP4. Thời lượng = Σ `durationInFrames` / fps, sai số ±1 frame. Với cảnh thường và cảnh con đầu tiên, giọng đọc bắt đầu đúng `words[0].start` sau đầu cảnh, sai số ±1 frame. **Tại mỗi điểm cắt giữa hai cảnh con**, khoảng lặng đo được trong video bằng khoảng lặng tại cùng vị trí trong file audio gốc, sai số ±1 frame. Không được so với 0, vì điểm cắt bậc 0 nằm ở dấu câu, nơi file gốc vốn có khoảng lặng thật (ví dụ 175 ms ở câu 3). | Test tự động bằng ffprobe + `silencedetect` trên cả video lẫn file audio gốc |
| **Không hồi quy** | 32 test hiện có vẫn PASS. `--renderer ffmpeg` vẫn xuất video. | `python -m unittest discover -s tests` |
| **Studio** | `npx remotion studio` mở được với props mẫu và với props thật. | Chạy tay 1 lần |

---

## 6. LỆNH XÁC MINH (VERIFICATION COMMAND)

```powershell
cd remotion; npm run typecheck; npm test; cd ..
python -m unittest discover -s tests
python run_pipeline.py --renderer remotion --input input/sample_chapter.txt
cd remotion; $env:RENDER_PROPS = "../output/sample_chapter/render_props.json"; npm test; Remove-Item Env:RENDER_PROPS; cd ..
```

---

## 7. RỦI RO & LƯU Ý

- **Lệch schema giữa Python và TS** khi các phase sau thêm trường. Xử lý bằng quy tắc tiến hóa schema ở mục 3.1 và 2 test hợp đồng.
- **`npx` trên Windows:** khi gọi từ `subprocess` phải dùng `npx.cmd` (hoặc `shell=True`).
- **Lần render đầu tiên** Remotion tải Chrome Headless Shell về, nên cần có mạng.
- **Đường dẫn Windows trong props:** luôn dùng `/`, tương đối với `remotion/public/`. Không ghi đường dẫn tuyệt đối. Template tham khảo có ghi `filePath: "D:\\cuongit\\..."` vào manifest, đừng làm theo.
