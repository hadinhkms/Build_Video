# KẾ HOẠCH CHI TIẾT - PHASE 2

## TÀI SẢN HÌNH ẢNH (THỦ CÔNG 0Đ) & BỘ SCENE COMPONENT REMOTION 3 LỚP GIỮ RACCORD

*(Mã tài liệu: PLAN_PHASE_2_REMOTION_SCENE_COMPONENTS · rev 2 · 2026-09-25)*

> **Ghi chú sửa đổi so với rev 1**
>
> - **Thêm Phần A: tài sản hình ảnh.** Rev 1 cần plate và nhân vật tách nền nhưng không nói ảnh lấy từ đâu. Hiện dự án chỉ có `assets/characters/main_char_face.jpg`. File `female_char_face.jpg` có khai báo trong config nhưng không tồn tại. Task 3.4 cũ (xuất gói `packages/`) được chuyển lên đây vì Phase 2 đã cần ảnh.
> - **Sửa `SubtitleBox`.** Bản trong template chia thời gian **đều** cho các cụm, nên phụ đề không khớp với giọng đọc. Bản mới:
>   - đọc `captions` từ Phase 1 để có mốc thật;
>   - highlight được cụm nhiều từ (bản cũ chỉ khớp một từ đơn, nên "kinh hoàng" không bao giờ được tô);
>   - bỏ `backdrop-blur` (rất chậm khi render) và bỏ emoji 🎙️;
>   - đặt ở 1/3 dưới màn hình, cụm 3–6 từ theo RULES §4, thay cho 5–7 từ.
> - **Sửa code camera.** Code rev 1 ghi là "spring" nhưng thực tế dùng `interpolate` tuyến tính, và thiếu `zoom_out`, `pan_right`, `rapid_zoom_in`.
> - **Mưa và grain phải tất định**, dùng `random(seed)` của Remotion, không dùng `Math.random()`. Remotion render các frame không theo thứ tự trên nhiều tiến trình, nên dùng `Math.random()` sẽ làm hình nhấp nháy.
> - **Mưa trong nhà:** bối cảnh "phòng khách đêm mưa" chỉ được có mưa ở vùng cửa sổ, không phủ cả khung hình.
> - **Font:** dùng `@remotion/google-fonts/BeVietnamPro`, thư viện này tự chờ font tải xong. Bỏ cách khai báo `@font-face` thủ công.
> - **Thêm component:** `TitleCard` (RULES §1.1), `EndScreen` (RULES §5), `AudioLayer` (mix 3 tầng + ducking).
> - Đổi `npx remotion preview` thành `npx remotion studio`. Gate có kiểm tra tự động bằng `npx remotion still`.
>
> **Bổ sung rev 2.1 (sau khi rà soát plan)**
>
> - **Thiết lập hình ảnh đi qua props.** Rev 2 cho component đọc thẳng `settings.visuals.*` và `environments.json → grade`, nhưng theo D5 thì Remotion chỉ đọc props. Nay thêm `style` (cấp gốc), `effects` và `grade` (cấp cảnh), `characterAnchor` và `cropRect` (trong `visual`), kèm schema đầy đủ (mục 3.1b).
> - Định nghĩa cấu trúc các khóa mới trong `environments.json`.
> - **Quy tắc hạ cấp `over_shoulder`:** khi hạ cấp phải chạy lại luật "không trùng cỡ cảnh liền nhau". Gate 2 kiểm tra luật này trên props cuối.
> - Task 2.4 chỉ bắt đầu sau khi Task 1.8 của Phase 1 đã merge.
>
> **Bổ sung rev 2.2 (rà soát lần 2)**
>
> - **Cách đặt ảnh nhân vật bán thân lên plate.** Rev 2.1 để điểm neo chân ở `y = 0,95`, nhưng ảnh nhân vật được tạo theo kiểu *half-body*, nên mép cắt ngang người sẽ lơ lửng trên đáy khung. Nay:
>   - định nghĩa `base_cutout.json`;
>   - `y` là mép dưới của ảnh cutout, đặt ≥ 1,0 để mép cắt nằm ngoài khung;
>   - vùng crop lấy tâm ở mặt (closeup) hoặc ngực (medium).
> - **Âm thanh dùng `<Html5Audio>`**, vì `<Audio>` đã deprecated ở 4.0.407. Giọng đọc của cảnh con phát bằng `trimBefore`.
> - CSS Tailwind dùng chung file `src/index.css` mà Phase 0 đã tạo.
> - Texture grain được commit, vì Phase 0 chỉ `.gitignore` thư mục `public/chapters/`.
> - **Sau khi agent độc lập rà soát:**
>   - Thư mục tài sản đặt theo **khóa object** (`nhan_vat_chinh`), không theo trường `id`.
>   - `base_cutout.json` có thêm `crop_box`, để Phase 3 quy tọa độ về ảnh cutout.
>   - Cảnh con dùng ảnh riêng, không có thì dùng ảnh của cảnh cha.
>   - Gate Raccord chỉ xét cảnh `layered`.
>   - Test tất định render một dải frame.
>   - Phase này tạo `render_report.json` tối giản và cơ chế đo hiệu năng trên một dải frame (`bench_<nhãn>.json`), để Gate 3 có mốc so sánh không bị ghi đè.
>   - Lệnh xác minh có thêm `--stage props`.

---

## 1. MỤC TIÊU & PHẠM VI (SCOPE & OBJECTIVES)

### 1.1. Mục tiêu

- **Phần A: tài sản hình ảnh (Python, chạy song song với Phase 1).**
  - Mỗi bối cảnh có 1 plate, dùng lại cho mọi cảnh trong bối cảnh đó. Như vậy raccord được giữ ở mức pixel.
  - Mỗi nhân vật có 1 ảnh đã tách nền.
  - Quy trình thủ công 0đ, có kiểm tra tài sản và có ảnh dự phòng.
- **Phần B: component Remotion.** Gồm `BackgroundPlate`, `CharacterLayer` (tĩnh ở Phase 2, thêm diễn xuất ở Phase 3), `AtmosphericEffects`, `FilmGrain`, `CinematicLetterbox`, `SubtitleBox`, `TitleCard`, `EndScreen`, `AudioLayer`, cùng camera có parallax.

### 1.2. Ngoài phạm vi

- Thở, chớp mắt, miệng, clip hybrid (Phase 3).
- Chuyển cảnh chồng lấn. Phiên bản 1 dùng cắt thẳng. Nếu sau này thêm chuyển cảnh thì phải tuân thủ bất biến #2 trong README.

---

## 2. KIẾN TRÚC COMPONENT & DANH MỤC TỆP

```text
d:\_Short_film\
├── src/visual/                         # Python (Phần A)
│   ├── asset_packager.py               # [mới] xuất gói prompt → packages/<chapter>/
│   ├── cutout.py                       # [mới] rembg tách nền → *_cutout.png (có cache)
│   └── asset_check.py                  # [mới] kiểm tra tài sản, in checklist, chọn fallback
├── config/environments.json            # [sửa] thêm rain_mode, rain_region, flicker, character_slots, default_character_slot, grade
├── config/settings.json                # [sửa] visuals.letterbox_ratio, visuals.film_grain
├── packages/<chapter>/                 # sinh tự động, thêm vào .gitignore
│   ├── README.md                       # hướng dẫn tạo ảnh từng bước
│   ├── environments/<env_key>/plate_prompt.txt
│   └── characters/<char_key>/base_prompt.txt
├── assets/                             # người dùng thả ảnh vào đây; <…_key> = khóa object trong JSON, vd phong_khach_dem_mua, nhan_vat_chinh
│   ├── environments/<env_key>/plate.(png|jpg)
│   ├── characters/<char_key>/base.(png|jpg)     → sinh ra base_cutout.png + base_cutout.json
│   └── images/<shot_id>.jpg                     # (tùy chọn) ảnh full khung thay cho 1 cảnh, baseline đã hỗ trợ
└── remotion/
    ├── public/textures/grain_512.png   # texture noise, commit vào repo (.gitignore chỉ bỏ qua public/chapters/)
    └── src/
        ├── components/
        │   ├── BackgroundPlate.tsx
        │   ├── CharacterLayer.tsx
        │   ├── AtmosphericEffects.tsx  # mưa (window/full/off) + đèn lập lòe
        │   ├── FilmGrain.tsx
        │   ├── CinematicLetterbox.tsx
        │   ├── SubtitleBox.tsx
        │   └── AudioLayer.tsx          # giọng + SFX + ambience + BGM có ducking
        ├── scenes/
        │   ├── CinematicStoryScene.tsx # ghép 3 lớp + camera
        │   ├── TitleCard.tsx
        │   ├── EndScreen.tsx
        │   └── StoryComposition.tsx    # <Series> theo scene.kind
        ├── lib/
        │   ├── camera.ts               # hàm thuần, có test
        │   └── ducking.ts              # hàm thuần, có test
        ├── fonts.ts
        └── index.css                   # [sửa từ Phase 0] thêm token màu vào sau @import "tailwindcss"
```

---

## 3. THIẾT KẾ KỸ THUẬT CHI TIẾT

### 3.1. Phần A: quy trình ảnh thủ công (quyết định D2)

1. **`python run_pipeline.py --stage assets`** gọi `asset_packager.py` để xuất gói prompt:
   - **Plate:** ghép từ `spatial_anchors`, `lighting`, `camera_profile` trong `environments.json`, thêm "empty room, no people". Tỉ lệ 16:9, **tối thiểu 2560×1440** để có đủ biên cho zoom 1,18 và pan.
   - **Nhân vật:** ghép từ `dna_prompt` và `fixed_wardrobe`, thêm "half-body, front-facing, neutral expression, eyes open, mouth closed, plain light-grey background, soft even light", kèm `forbidden_traits`. Khuyến nghị dùng `face_reference_image` làm ảnh tham chiếu khuôn mặt.
   - **`README.md`:** gợi ý công cụ (Gemini/ImageFX, Bing Image Creator…), đường dẫn và tên file cần lưu, kích thước tối thiểu.
2. **Người dùng tạo ảnh** và lưu đúng đường dẫn quy ước.
3. **`cutout.py`:**
   - Chạy `rembg` (model `isnet-general-use`, CPU) để ra `base_cutout.png` có kênh alpha.
   - Crop sát viền, làm mềm biên 1–2 px.
   - Ghi `base_cutout.json` để đặt nhân vật lên plate. Mọi tọa độ tính theo tỉ lệ 0..1 của ảnh cutout:

     ```json
     { "aspect": 0.72, "crop_box": { "x": 412, "y": 96, "w": 1180, "h": 1638 },
       "face": { "x": 0.50, "y": 0.16 }, "chest": { "x": 0.50, "y": 0.42 }, "cut_bottom": true }
     ```

     - `aspect` = rộng / cao.
     - `crop_box` = vùng đã cắt ra từ ảnh `base` gốc, tính bằng **pixel của ảnh gốc**. Phase 3 dùng nó để quy tọa độ mắt và miệng (đo trên ảnh gốc) về ảnh cutout.
     - `face` và `chest` mặc định ở (0,5; 0,16) và (0,5; 0,42) cho ảnh bán thân nhìn thẳng. Phase 3 (`face_rig`) hoặc MediaPipe có thể tinh chỉnh `face`.
     - `cut_bottom = true` khi các hàng pixel dưới cùng còn đục, tức nhân vật bị cắt ngang người.
   - Bỏ qua nếu ảnh gốc đã có alpha. Cache theo hash của ảnh.
4. **`asset_check.py`** chọn `visual.mode` cho từng cảnh theo thứ tự ưu tiên sau:
   1. Có `assets/images/<shot_id>.jpg` → `full_image`. Với cảnh con, tìm theo id cảnh con trước, rồi tới id cảnh cha (Phase 0 mục 3.4b).
   2. Có plate + cutout, và cảnh có nhân vật trên hình → `layered`.
   3. Chỉ có plate (cảnh không có nhân vật, hoặc thiếu cutout) → `layered` không có nhân vật.
   4. Không có gì → ảnh mặc định `main_char_face.jpg` ở chế độ `full_image` (hành vi baseline).

   In ra checklist những ảnh còn thiếu. **Không bao giờ** dừng pipeline chỉ vì thiếu ảnh.

**Raccord & giới hạn kỹ thuật:**

- **Plate dùng chung:** mọi cảnh cùng `environmentId` dùng cùng một file plate, nên cửa sổ và đồ vật không thể xê dịch giữa các cảnh.
- **Cỡ cảnh = vùng crop trên plate:** wide 100 %, medium ~70 %, closeup ~45 %, extreme_closeup ~30 %. Vùng crop đặt quanh vị trí nhân vật, lấy từ `environments.json → character_slots` (left/center/right).
- **Đặt nhân vật lên plate theo slot `{x, y, height}`**, tính theo tỉ lệ plate:
  - `x`: tâm ngang của ảnh cutout.
  - `y`: **mép dưới** của ảnh cutout.
  - `height`: chiều cao ảnh cutout so với chiều cao plate.
  - Với ảnh bán thân (`cut_bottom = true`) phải có `y ≥ 1,0`, để mép cắt nằm dưới đáy plate và không bao giờ lộ ra, kể cả khi camera `zoom_out` về scale 1,0. `asset_check` báo lỗi nếu vi phạm.
  - **Giới hạn đã biết:** chỉ có một ảnh bán thân nên cảnh `wide` trông giống medium-wide. Muốn có wide thật thì dùng ảnh riêng `assets/images/<shot_id>.jpg`, hoặc để cảnh đó không có nhân vật (`[ON: none]`).
- **Closeup bị mềm ảnh:** crop 45 % của plate 2560 px chỉ còn ~1150 px, phóng lên 1920 px sẽ bị mềm. Vì vậy closeup và extreme_closeup cần ảnh riêng hoặc plate ≥ 3840 px. `asset_check` cảnh báo khi tỉ lệ phóng > 1,5×.
- **over_shoulder:** không dựng đúng được từ 1 plate + 1 cutout. Phải dùng ảnh riêng `assets/images/<shot_id>.jpg`. Nếu không có ảnh riêng thì hạ cấp:
  - Chọn phần tử đầu tiên trong `[medium, closeup, wide]` **khác** cỡ cảnh của cả cảnh `story` liền trước lẫn liền sau. Cỡ cảnh của cảnh liền trước là giá trị sau khi đã hạ cấp.
  - Ví dụ: `medium → over_shoulder → medium` hạ thành `medium → closeup → medium`.
  - In cảnh báo kèm tên cảnh. Nếu chỉ hạ thẳng xuống `medium` như rev 2 thì sẽ ra 2 cảnh medium liền nhau, phạm luật RULES §2.2 mà Gate 0 kiểm tra.
- **Lệch ánh sáng:** cutout và plate được tạo riêng nên màu và hướng sáng sẽ lệch nhau. Cách xử lý: dùng lớp grade chung theo `environments.json → grade`, gồm CSS filter, lớp gradient màu ánh đèn/cửa sổ, và bóng đổ tiếp xúc dưới chân nhân vật. Lớp grade áp cho cả hai lớp ảnh.

### 3.1b. Mở rộng schema & cấu hình (Task 2.4)

Mọi thiết lập mà component cần đều phải đi qua props (quyết định D5). Component **không** đọc `settings.json` hay `environments.json`. Các trường mới tuân theo quy ước ở Phase 0 mục 3.1: `.strict()`, mọi key luôn có mặt, giá trị vắng ghi là `null`.

```typescript
const Frac = z.number().min(0).max(1);

// Hình chữ nhật theo tỉ lệ 0..1. Hệ quy chiếu do trường dùng nó quy định:
// cropRect, rainRegion → theo plate; faceRig.eyes / faceRig.mouth (Phase 3) → theo ảnh cutout
export const RectSchema = z.object({ x: Frac, y: Frac, w: Frac, h: Frac }).strict();

export const GradeSchema = z.object({
  cssFilter: z.string(),                  // áp cho cả plate lẫn nhân vật, vd "saturate(0.85) contrast(1.08)"
  overlayGradient: z.string().nullable(), // lớp màu ánh đèn / cửa sổ (CSS gradient)
  overlayBlend: z.enum(["soft-light", "overlay", "multiply", "screen"]),
  contactShadowOpacity: Frac,             // bóng đổ dưới chân nhân vật
}).strict();

export const EffectsSchema = z.object({
  rain: z.enum(["window", "full", "off"]),
  rainRegion: RectSchema.nullable(),      // khác null khi và chỉ khi rain = "window"
  flicker: z.boolean(),
}).strict();

export const StyleSchema = z.object({
  subtitles: z.boolean(),                          // ← settings.visuals.enable_subtitles
  letterboxRatio: z.number().positive().nullable(), // ← settings.visuals.letterbox_ratio; null với 9:16
  grain: z.boolean(),                              // ← settings.visuals.film_grain
}).strict();

// VisualSchema thêm:
//   characterAnchor: z.object({ x: Frac, y: z.number().min(0).max(1.2), height: Frac }).strict().nullable(),
//     tâm ngang (x), mép dưới (y, được phép > 1 để giấu mép cắt) và chiều cao ảnh cutout, theo tỉ lệ plate;
//     null khi cảnh không có nhân vật
//   cropRect: RectSchema.nullable(),  // vùng plate được hiển thị theo cỡ cảnh; null = cả plate
// SceneSchema thêm:
//   effects: EffectsSchema,
//   grade: GradeSchema.nullable(),     // null khi bối cảnh không khai báo grade
// RenderPropsSchema thêm:
//   style: StyleSchema,
```

- **Ràng buộc chéo** `rain = "window"` ⇔ `rainRegion != null`: kiểm ở cả hai phía, Zod dùng `.superRefine` **đặt trên `EffectsSchema`**, Pydantic dùng `model_validator`. Không đặt refine ở `RenderPropsSchema`, vì prop `schema` của `<Composition>` cần một `z.object` ở cấp gốc. Thêm file `fixtures/invalid/window_rain_without_region.json` vào bộ file mẫu sai.
- **`environments.json`**: mỗi bối cảnh thêm các khóa sau (ví dụ cho `phong_khach_dem_mua`):

  ```json
  "rain_mode": "window",
  "rain_region": { "x": 0.02, "y": 0.08, "w": 0.30, "h": 0.60 },
  "flicker": true,
  "default_character_slot": "center",
  "character_slots": {
    "left":   { "x": 0.28, "y": 1.02, "height": 0.62 },
    "center": { "x": 0.50, "y": 1.02, "height": 0.62 },
    "right":  { "x": 0.72, "y": 1.02, "height": 0.62 }
  },
  "grade": {
    "css_filter": "saturate(0.85) contrast(1.08) brightness(0.95)",
    "overlay_gradient": "radial-gradient(circle at 85% 40%, rgba(255,190,110,0.35), transparent 55%)",
    "overlay_blend": "soft-light",
    "contact_shadow_opacity": 0.45
  }
  ```

  `con_hem_co_dien` là cảnh ngoài trời nên dùng `"rain_mode": "full"`, `"rain_region": null`.
- **Exporter điền props như sau:**
  - **Vị trí nhân vật:** mọi cảnh dùng `default_character_slot` của bối cảnh. Đổi slot theo từng cảnh chưa cần ở v1.
  - **`cropRect`:**
    - Bề rộng theo cỡ cảnh: wide 1,0 · medium 0,7 · closeup 0,45 · extreme_closeup 0,30. Chiều cao giữ đúng tỉ lệ khung hình.
    - Tâm vùng crop: **mặt** (`face` trong `base_cutout.json`) với closeup / extreme_closeup, **ngực** (`chest`) với medium. Tọa độ này quy từ ảnh cutout sang plate thông qua slot.
    - Vùng crop được kẹp trong biên plate.
    - Cảnh không có nhân vật: lấy tâm plate.
  - **`style`:** lấy từ `settings.visuals`. Riêng `letterboxRatio` bị đặt `null` khi tỉ lệ khung khác 16:9.
- **`settings.json`:** đổi ý tưởng `letterbox: "2.39"` của rev 2 thành `visuals.letterbox_ratio: 2.39` (số, hoặc `null` để tắt). Thêm `visuals.film_grain: true`.

### 3.2. Camera & parallax (`lib/camera.ts`)

```typescript
import { Easing, interpolate } from "remotion";

export type CameraMotion = "zoom_in" | "rapid_zoom_in" | "zoom_out" | "pan_left" | "pan_right" | "static";

// [scale đầu, scale cuối, x đầu, x cuối]; x tính theo tỉ lệ bề rộng khung
const MOVES: Record<CameraMotion, [number, number, number, number]> = {
  zoom_in:       [1.0, 1.12, 0, 0],
  rapid_zoom_in: [1.0, 1.25, 0, 0],
  zoom_out:      [1.12, 1.0, 0, 0],
  pan_left:      [1.1, 1.1, 0.03, -0.03], // biên an toàn ở scale 1.1 là 5 % mỗi bên
  pan_right:     [1.1, 1.1, -0.03, 0.03],
  static:        [1.04, 1.04, 0, 0],
};

// depth: plate = 1, nhân vật = 1.35 (tạo parallax 2.5D), lớp hiệu ứng tiền cảnh = 0 (đứng yên)
export function cameraTransform(motion: CameraMotion, frame: number, duration: number, depth = 1) {
  const easing = motion === "rapid_zoom_in" ? Easing.out(Easing.cubic) : Easing.inOut(Easing.sin);
  const t = interpolate(frame, [0, Math.max(1, duration - 1)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing,
  });
  const [s0, s1, x0, x1] = MOVES[motion];
  return {
    scale: 1 + (interpolate(t, [0, 1], [s0, s1]) - 1) * depth,
    xPercent: interpolate(t, [0, 1], [x0, x1]) * depth * 100,
  };
}
```

Easing `inOut(sin)` cho cảm giác dolly: tăng tốc và giảm tốc êm ở hai đầu. Nếu muốn có độ nảy thì dùng `spring({ fps, frame, durationInFrames })`. `spring` hợp với chữ và UI hơn là với camera.

### 3.3. Hiệu ứng khí quyển

- **Mưa (`AtmosphericEffects.tsx`):**
  - Vẽ lại `<canvas>` mỗi frame. Vị trí mỗi hạt là hàm của `(random(\`rain-${i}\`), frame)`. Khoảng 150–250 vệt mảnh, nghiêng theo gió.
  - Chế độ lấy từ `scene.effects.rain`. Python điền giá trị này từ `environments.json → rain_mode`:
    - `window`: chỉ mưa trong vùng `scene.effects.rainRegion` (cảnh trong nhà).
    - `full`: cảnh ngoài trời.
    - `off`: không mưa.
- **Đèn lập lòe** (chỉ khi `scene.effects.flicker = true`):
  - Độ sáng lớp ánh đèn = `1 + 0.04 · noise2D(seed, t)`, dùng `@remotion/noise`.
  - Biên độ ≤ 5 % và không nháy quá 3 lần/giây, để an toàn cho người nhạy cảm với ánh sáng.
- **Film grain (`FilmGrain.tsx`):** bật theo `props.style.grain`.
  - Lặp texture `grain_512.png` và dịch vị trí theo `random(frame)` mỗi frame.
  - Opacity 0,06–0,1, `mix-blend-mode: overlay`.
  - Không tính noise cho từng pixel ở 1920×1080, vì quá chậm.
- **Letterbox:**
  - Đọc `props.style.letterboxRatio`, ví dụ 2,39. Khi đó 1920 / 2,39 ≈ 803 px, nên mỗi thanh đen trên và dưới dày **138 px**. Độ dày tính bằng `(height − width / ratio) / 2`.
  - Giá trị `null` thì không vẽ thanh đen. Python đặt `null` khi khung khác 16:9, ví dụ 9:16.
  - Phụ đề nằm trong vùng hình, ngay trên thanh đen dưới.

### 3.4. `SubtitleBox.tsx` (port từ template, đổi cách tính thời gian)

```tsx
const frame = useCurrentFrame();
const { fps } = useVideoConfig();
const t = frame / fps;
const cap = captions.find((c) => t >= c.start && t < c.end); // captions do Phase 1 tính sẵn
if (!cap) return null;
const local = frame - Math.round(cap.start * fps);
const scale = spring({ frame: local, fps, config: { damping: 14, stiffness: 140, mass: 0.6 } });
```

- **Highlight:** so khớp **theo cụm** trên chuỗi đã chuẩn NFC và chữ thường, dùng danh sách `cap.highlight`. Không so từng từ đơn như template.
- **Style:**
  - Nền `bg-black/70` (không dùng `backdrop-blur`), chữ trắng, viền hoặc bóng mỏng.
  - Highlight bằng `text-amber-300`.
  - Font Be Vietnam Pro đậm 600–700, cỡ chữ ≈ 4,2 % chiều cao khung.
  - Chỉ 1 dòng, tối đa 42 ký tự (Phase 1 đã đảm bảo). Đặt ở 1/3 dưới màn hình.
- **Bật/tắt:** theo `props.style.subtitles`. Python điền giá trị này từ cờ `settings.visuals.enable_subtitles` đã có sẵn.

### 3.5. Font (`fonts.ts`)

```typescript
import { loadFont } from "@remotion/google-fonts/BeVietnamPro";
// Kiểm tra lại chữ ký hàm ở phiên bản đã cài; bắt buộc có subset "vietnamese"
export const { fontFamily } = loadFont("normal", { weights: ["600", "700"], subsets: ["vietnamese", "latin"] });
```

### 3.6. `AudioLayer.tsx` (mix 3 tầng từ props Phase 1)

Mọi thẻ âm thanh dùng `<Html5Audio>` của `remotion`. Ở bản 4.0.407, `<Audio>` đã deprecated.

- **Giọng đọc:** một `<Html5Audio trimBefore={Math.round(audio.startInFileSec * fps)}>` bên trong `Sequence` của từng cảnh. Với cảnh con thứ 2 trở đi, `trimBefore > 0` (Phase 0 mục 3.4c).
- **SFX một lần:** `<Sequence from={sceneStart + round(startSec·fps)}><Html5Audio volume={v} /></Sequence>`.
- **Ambience:** `<Sequence from … durationInFrames …>` bọc `<Html5Audio loop volume={fade}>`.
- **BGM:** `<Html5Audio loop volume={(f) => bgmVolume(f / fps, bgm)} />` ở gốc timeline.
  - Hàm thuần `lib/ducking.ts`: attack 0,15 s, release 0,5 s, tắt dần 0,3 s tại `cutAtSec`.
  - Lưu ý: `f` trong callback `volume` là frame **tính từ đầu Sequence chứa Audio**, không phải frame tuyệt đối của video.

### 3.7. `TitleCard`, `EndScreen`, `StoryComposition`

- **`TitleCard`** (`kind: "title_card"`): hiện ngay sau Hook, dài `settings.visuals.title_card_sec` (mặc định 2,5 s). Tên chương (`rawText`) xuất hiện bằng fade + spring. Nền là `visual` của cảnh `story` kế tiếp (Python đã chép sang, xem Phase 0 mục 3.1b), làm mờ và tối đi. Làm mờ bằng ảnh đã thu nhỏ rồi phóng to lại, không dùng `filter: blur` bán kính lớn.
- **`EndScreen`** (`kind: "end_screen"`):
  - Chừa khung trống an toàn cho các phần tử màn hình kết thúc của YouTube (video "Chương tiếp theo", nút đăng ký).
  - Thời lượng là `durationInFrames` do Python tính từ `settings.visuals.end_screen_sec` (5–20 s, mặc định 10 s). Cảnh này có mặt trong props chỉ khi giá trị đó > 0.
- **`StoryComposition`:**
  - `<Series>` gồm các cảnh, render theo `scene.kind`.
  - `AudioLayer` đặt ở gốc cho ambience và BGM, vì hai lớp này dùng thời gian tuyệt đối.
  - Phiên bản 1 dùng cắt thẳng.

---

## 4. DANH MỤC CÔNG VIỆC THỰC HIỆN (TASK BREAKDOWN)

**Phần A (Python):**

- [ ] **Task 2.1:** Viết `asset_packager.py` và template `README.md`. Test: prompt có đủ anchors; prompt plate có "no people".
- [ ] **Task 2.2:** Viết `cutout.py` (rembg, cache, bỏ qua ảnh đã có alpha, ghi `base_cutout.json`), thêm `rembg[cpu]` vào `requirements.txt`. Test bằng ảnh tổng hợp nhỏ: ảnh bị cắt đáy phải cho `cut_bottom = true`. Test tự bỏ qua nếu máy chưa cài `rembg`.
- [ ] **Task 2.3:** Viết `asset_check.py`: chuỗi fallback, cảnh báo phóng > 1,5×, báo lỗi slot có `y < 1` với ảnh `cut_bottom`, checklist, hạ cấp `over_shoulder` theo mục 3.1. Test gồm ca `medium → over_shoulder → medium` phải hạ thành `closeup`.
- [ ] **Task 2.4:** *(Chỉ bắt đầu sau khi Task 1.8 đã merge.)* Bổ sung `environments.json` và `settings.json` theo mục 3.1b. Thêm `style`, `effects`, `grade`, `characterAnchor`, `cropRect` vào Zod, Pydantic và file mẫu. Thêm file mẫu sai `window_rain_without_region.json`. Exporter điền các trường mới.

**Phần B (Remotion):**

- [ ] **Task 2.5:** Thêm `@remotion/google-fonts` và `@remotion/noise` vào `package.json`, cùng phiên bản với `remotion`. Làm font, thêm token màu vào `src/index.css`.
- [ ] **Task 2.6:** `lib/camera.ts` và test.
- [ ] **Task 2.7:** `BackgroundPlate` và `CharacterLayer` (tĩnh), kèm parallax, grade và bóng đổ.
- [ ] **Task 2.8:** `AtmosphericEffects` (mưa window/full/off, đèn lập lòe), `FilmGrain`, `CinematicLetterbox`.
- [ ] **Task 2.9:** `SubtitleBox` chạy theo `captions`.
- [ ] **Task 2.10:** `AudioLayer`, `lib/ducking.ts` và test.
- [ ] **Task 2.11:** `TitleCard`, `EndScreen`, `StoryComposition`.
- [ ] **Task 2.12:** Viết helper Python render ảnh still ở giữa mỗi cảnh ra `output/<chapterId>/stills/` (contact sheet để duyệt).
- [ ] **Task 2.13:** Đo hiệu năng.
  - Mỗi lần chạy stage `video` cho cả chương, ghi `output/<chapterId>/render_report.json` tối giản: `{ "frames", "seconds", "fps_render", "concurrency", "date" }`. Phase 4 bổ sung thêm các trường.
  - Thêm tham số `--frames A-B` và `--bench <nhãn>` cho stage `video`:
    - `--frames` truyền dải frame cho Remotion (`--frames=A-B`) và ghi video ra `video.bench.mp4`;
    - `--bench` ghi báo cáo cùng định dạng vào `bench_<nhãn>.json` thay cho `render_report.json`, nên lần đo sau không ghi đè mốc của lần trước.
- [ ] **Task 2.14:** Chạy kiểm thử Gate 2.

---

## 5. TIÊU CHÍ NGHIỆM THU GATE 2 (ACCEPTANCE CRITERIA)

| Tiêu chí | Điều kiện bắt buộc | Phương thức kiểm tra |
| :--- | :--- | :--- |
| **Font tiếng Việt** | Ảnh still của cảnh kiểm thử có chuỗi "Ắ Ặ Ỗ Ữ Ự ưỡ ẫ đ Đ" hiển thị đúng font Be Vietnam Pro, không bị font dự phòng. | `npx remotion still` + so với ảnh chuẩn đã duyệt |
| **Render tất định** | Render một dải 48 frame (có mưa, grain, đèn lập lòe) ra chuỗi PNG hai lần: `--concurrency=1` và `--concurrency=N`. Hash từng frame phải giống hệt nhau. Render một frame đơn lẻ không kiểm được điều này. Phải truyền `--image-format=png`, vì `remotion.config.ts` đặt JPEG và nén JPEG có thể che mất khác biệt nhỏ. | `npx remotion render … --sequence --image-format=png --frames=0-47` + script so hash |
| **Camera** | Đúng giá trị đầu và cuối, đơn điệu, không lộ mép ảnh ở mọi `cameraMotion`. | vitest `camera.test.ts` |
| **Raccord** | Mọi cảnh **`layered`** cùng `environmentId` có cùng `backgroundSrc`. Cảnh `full_image` có `backgroundSrc = null` nên không xét. | Unit test trên props |
| **Cỡ cảnh sau hạ cấp** | Trong props cuối (sau `asset_check`), không có 2 cảnh `story` liền nhau cùng `shotType`. | Unit test trên props |
| **Thiết lập qua props** | Đổi `style.subtitles`, `style.letterboxRatio` hoặc `effects.rain` trong props thì ảnh still thay đổi tương ứng. Code trong `remotion/src` không đọc file config nào. | Still + grep |
| **Phụ đề** | Mỗi cụm hiện đúng khoảng `[start, end)` ±1 frame. Không cụm nào > 6 từ. Highlight được cụm nhiều từ. | vitest |
| **Ảnh dự phòng** | Xóa plate thì pipeline vẫn render ở chế độ `full_image` và in checklist. | Unit test |
| **Hiệu năng** | Chạy `--stage video --frames 0-239 --bench p2` (đoạn mẫu 10 s), ghi `bench_p2.json`. Đây là mốc để Gate 3 so sánh. Code không chứa `backdrop-filter` hay `backdrop-blur`. | `bench_p2.json` + grep |
| **Duyệt mắt** | Contact sheet trong `output/<chapterId>/stills/` được duyệt: không lộ mép, nhân vật đứng đúng chỗ, màu hòa hợp. | Review tay |

---

## 6. LỆNH XÁC MINH (VERIFICATION COMMAND)

```powershell
python run_pipeline.py --renderer remotion --stage assets --input input/sample_chapter.txt
python run_pipeline.py --renderer remotion --stage props  --input input/sample_chapter.txt   # xuất lại props sau khi assets đổi visual.mode
cd remotion; npm test
npx remotion studio --props=../output/sample_chapter/render_props.json
npx remotion still src/index.ts StoryComposition ../output/sample_chapter/stills/f120.png --frame=120 --props=../output/sample_chapter/render_props.json
```

---

## 7. RỦI RO & LƯU Ý

- **`rembg` tách không sạch** ở tóc rối hoặc áo ướt mưa. Cho phép người dùng tự đưa ảnh PNG đã có alpha. Làm mềm biên.
- **Plate và nhân vật lệch phong cách** vì tạo ở hai lần khác nhau. Dùng lớp grade chung. Prompt của hai loại ảnh phải có chung `lighting` và `camera_profile`.
- **Công cụ web đổi giới hạn miễn phí** hoặc đổi điều khoản. Gói prompt không phụ thuộc vào công cụ cụ thể nào.
