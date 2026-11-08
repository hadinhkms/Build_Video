# KẾ HOẠCH CHI TIẾT - PHASE 3

## DIỄN XUẤT 2.5D TỪ ẢNH BIẾN THỂ & KHE CẮM HYBRID VIDEO

*(Mã tài liệu: PLAN_PHASE_3_AUDIO_REACTIVE_ACTING · rev 2 · 2026-09-25)*

> **Ghi chú sửa đổi so với rev 1**
>
> - **Không kế thừa được avatar của `auto-compare-video`.** Avatar đó là robot vẽ bằng SVG/CSS: mắt và miệng là hình khối, nhấp nháy theo khung thời gian cố định. Cơ chế này không áp dụng được cho ảnh chân dung.
> - **Một ảnh tĩnh không thể "khép mí" hay "mở khóe miệng"** chỉ bằng scale hay transform. Cần có **ảnh biến thể khớp pixel với ảnh gốc** (mắt nhắm, miệng hé), do người dùng tạo bằng cùng công cụ. Nếu không có ảnh biến thể thì **không giả lập**, vì kết quả sẽ trông kỳ dị (uncanny). Khi đó chỉ giữ nhịp thở và camera.
> - **Miệng chỉ cử động khi `isDialogue` đúng và `speaker` là nhân vật đang có trên hình.** Rev 1 mặc định `speakingCharacterId = "main_char"`, nên nhân vật Nam sẽ "nói" cả lời người dẫn chuyện "tôi". Chương mẫu toàn là lời dẫn, nên đúng ra không cảnh nào được cử động miệng.
> - **Nhịp thở:** công thức rev 1 `sin(frame·π/45)` có chu kỳ 3 s ở 30 fps, không phải 1,5 s như ghi. Mà 1,5 s là thở gấp (40 nhịp/phút). Đổi sang tính theo giây: 4 s khi bình thường, 2,5 s ở hồi CLIMAX.
> - **Chớp mắt:** chu kỳ cố định 100 frame trông máy móc. Đổi sang khoảng cách ngẫu nhiên tất định 2,5–5 s, mỗi lần chớp ~120 ms. Tính theo giây nên đúng ở cả 24 lẫn 30 fps.
> - **Hybrid slot:**
>   - `checkFileExists` không tồn tại trong trình duyệt nơi Remotion chạy.
>   - `input/rendered_clips/` nằm ngoài `public/` nên `staticFile` không đọc được.
>   - Cách sửa: Python phát hiện clip lúc tạo props và copy vào `remotion/public/`.
> - **Biên độ âm thanh:** tính trước bằng Python (RMS theo từng frame) và đưa vào props, thay cho `audio-waveform.ts`. Cách này nhẹ, tất định và test được. Phương án thay thế là `useAudioData` + `visualizeAudio` của `@remotion/media-utils`.
> - **Thêm** phần xử lý khi thời lượng clip Kling/Hedra (5 hoặc 10 s) lệch với thời lượng cảnh.
> - Task 3.4 cũ (xuất gói `packages/`) đã chuyển lên Phase 2. Phase 3 chỉ thêm gói dành cho clip hybrid.
> - Lệnh xác minh `npx tsx scripts/test-character-animation.ts` chưa từng được định nghĩa, nay thay bằng test cụ thể.
>
> **Bổ sung rev 2.1 (sau khi rà soát plan)**
>
> - **Python tính cách khớp thời lượng clip.** Rev 2 cho `lib/clip-fit.ts` đọc `settings.visuals.clip_fit`, nhưng Remotion không đọc được settings (D5). Nay Python tính `visual.clipFit` và Remotion chỉ áp dụng.
> - Thêm schema đầy đủ cho `faceRig`, `mouthEnvelope`, `clipDurationSec`, `clipFit` theo quy ước key/`null` của Phase 0.
> - **Clip "idle loop" nhận diện bằng tên file** `<shot_id>.loop.mp4`. Rev 2 nhắc tới loại clip này nhưng không nói cách nhận biết.
> - Thêm `opencv-python-headless` và `scikit-image` vào `requirements.txt`.
>
> **Bổ sung rev 2.2 (rà soát lần 2, đã kiểm chứng trên gói Remotion 4.0.407)**
>
> - **`<OffthreadVideo>` không có prop `loop`**, nên clip idle loop phải bọc bằng `<Loop>`. `<Freeze>` có prop `active` nhận hàm. Hai điều này đã được kiểm chứng.
> - **Cảnh con** (Phase 0 mục 3.4c): envelope miệng và `voice.wav` trong gói hybrid được cắt theo `startInFileSec` + `durationSec` của từng cảnh con.
> - Envelope được đệm thêm số 0 khi audio ngắn hơn cảnh.
> - **Sau khi agent độc lập rà soát:**
>   - Envelope tính trên **cả câu** rồi mới cắt cho từng cảnh con. Nếu tính riêng thì bộ làm mượt attack/release sẽ reset tại điểm cắt.
>   - Tọa độ face rig quy về ảnh cutout qua `crop_box`.
>   - Thêm file mẫu sai cho các ràng buộc chéo.
>   - Đổi `CinematicLayers` thành `CinematicStoryScene` cho khớp Phase 2.
>   - Gate hiệu năng so `bench_p3.json` với `bench_p2.json` của Phase 2.
>   - Thư mục nhân vật đặt theo khóa object.

---

## 1. MỤC TIÊU & PHẠM VI (SCOPE & OBJECTIVES)

### 1.1. Mục tiêu

1. **Nhân vật "có sự sống":** thở, chớp mắt, đầu chuyển động rất nhẹ. Mọi chuyển động tất định và tính theo giây.
2. **Miệng theo biên độ giọng nói** ở cảnh thoại, khi có ảnh biến thể miệng.
3. **Hybrid:** thả clip vào `input/rendered_clips/<shot_id>.mp4` thì cảnh đó phát clip thay cho diễn xuất 2.5D, cấu trúc phim giữ nguyên.

### 1.2. Ngoài phạm vi

- Lip-sync theo âm vị (viseme). Tiếng Việt chưa có công cụ viseme miễn phí đủ tốt; biên độ là đủ cho mức "mấp máy".
- Tự sinh ảnh biến thể bằng AI local.

---

## 2. KIẾN TRÚC PHÂN HỆ & DANH MỤC TỆP

```text
d:\_Short_film\
├── src/
│   ├── visual/face_rig.py              # [mới] so ảnh gốc với biến thể → vùng mắt/miệng + patch có mask mờ biên
│   ├── audio/envelope.py               # [mới] RMS theo frame (0–1) cho cảnh thoại
│   └── export/
│       ├── clip_fit.py                 # [mới] hàm thuần: chọn cắt / chậm lại / freeze / loop
│       └── remotion_props.py           # [sửa] thêm faceRig, mouthEnvelope, clipSrc, clipDurationSec, clipFit
├── assets/characters/<char_key>/       # khóa object trong characters.json, vd nhan_vat_chinh
│   ├── base.png → base_cutout.png      # từ Phase 2
│   ├── eyes_closed.png                 # (tùy chọn) cùng kích thước, cùng tư thế với base
│   └── mouth_open.png                  # (tùy chọn)
├── input/rendered_clips/               # (tùy chọn) clip Kling/Hedra
│   ├── <shot_id>.mp4                   #   clip thường
│   └── <shot_id>.loop.mp4              #   clip "idle loop": được phép lặp lại
├── packages/<chapter>/shots/<shot_id>/ # gói để gửi lên Kling/Hedra
│   ├── image.png  voice.wav  motion_prompt.txt  README.txt
└── remotion/src/
    ├── lib/life.ts                     # hàm thuần: breathScale, blinkAmount, headDrift
    ├── components/CharacterLayer.tsx   # [sửa từ Phase 2] ghép ảnh gốc + patch mắt/miệng
    └── components/HybridVideoSlot.tsx
```

---

## 3. THIẾT KẾ KỸ THUẬT CHI TIẾT

### 3.1. Ảnh biến thể & face rig (`face_rig.py`)

**Cách tạo ảnh biến thể.** Gói prompt của Phase 2 hướng dẫn người dùng dùng tính năng chỉnh sửa ảnh của công cụ ngay trên ảnh `base`, với yêu cầu kiểu "giữ nguyên mọi thứ, chỉ nhắm mắt" hoặc "chỉ hé miệng như đang nói".

**`face_rig.py` xử lý như sau:**

1. Kiểm tra ảnh biến thể có cùng kích thước với ảnh gốc. Nếu lệch vài pixel thì căn chỉnh bằng phase correlation hoặc ECC của OpenCV.
2. Lấy ảnh khác biệt `|base − variant|`. Vùng thay đổi lớn nhất ở nửa trên khuôn mặt là mắt, ở nửa dưới là miệng. Nếu có MediaPipe face landmarks thì dùng để khoanh vùng chính xác hơn (tùy chọn).
3. Cắt patch kèm mask làm mờ biên 6–10 px. Xuất ra `eyes_closed_patch.png`, `mouth_open_patch.png` và `face_rig.json` dạng `{eyes: {x,y,w,h}, mouth: {x,y,w,h}}`.
   - Tọa độ tính theo tỉ lệ 0..1 của **ảnh cutout**, để khớp với `RectSchema` trong props.
   - Ảnh khác biệt được đo trên ảnh `base` gốc (chưa crop), nên phải quy đổi qua `crop_box` trong `base_cutout.json` (Phase 2): `x_cutout = (x_gốc − crop_box.x) / crop_box.w`, tương tự với `y`, `w`, `h`.
   - Patch được cắt từ ảnh biến thể theo đúng `crop_box` đó, để khớp pixel với `base_cutout.png`.
4. **Từ chối** ảnh biến thể (in cảnh báo và bỏ qua) nếu phần ngoài khuôn mặt cũng bị thay đổi nhiều, tức là công cụ đã vẽ lại cả ảnh. Ngưỡng: SSIM ngoài vùng mặt < 0,95.

Remotion chỉ **đè patch lên ảnh gốc**, không đổi cả ảnh. Nhờ vậy toàn thân nhân vật không bị nhấp nháy mỗi lần chớp mắt.

### 3.2. Nhịp thở, chớp mắt, chuyển động đầu (`lib/life.ts`)

```typescript
import { random } from "remotion";

// Thở: tính chu kỳ theo giây, biên độ nhỏ, chỉ scaleY phần thân (transform-origin: bottom center)
export function breathScale(t: number, act: string): number {
  const period = act === "CLIMAX" ? 2.5 : 4.0;
  return 1 + 0.008 * Math.sin((2 * Math.PI * t) / period);
}

// Chớp mắt: khoảng cách ngẫu nhiên tất định 2,5–5 s; mỗi lần ~120 ms
// Trả về 0..1 = độ phủ của patch mắt nhắm (đóng rồi mở theo hình tam giác)
export function blinkAmount(t: number, seed: string): number {
  let at = 0.8 + random(`${seed}-0`) * 2.0; // lần chớp đầu tiên
  for (let i = 1; at <= t; i++) {
    const d = t - at;
    if (d < 0.12) return 1 - Math.abs(d - 0.06) / 0.06;
    at += 2.5 + random(`${seed}-${i}`) * 2.5;
  }
  return 0;
}
```

- `t` là thời gian **tính từ đầu cảnh** (`frame / fps`). `seed` = `${characterId}-${sceneId}`.
- **Chuyển động đầu:** xoay ±0,4° và dịch ±3 px theo `noise2D` của `@remotion/noise`. Đây là "dấu hiệu sống" rẻ nhất, vẫn dùng được khi không có ảnh biến thể.
- **Giới hạn:** thở tối đa 0,8 % theo trục Y. Nếu scale toàn bộ cutout, kể cả phần đầu, mặt sẽ bị méo.

### 3.3. Miệng theo biên độ (`envelope.py` + `CharacterLayer`)

- **Điều kiện kích hoạt:** chỉ khi `isDialogue && speaker === onScreenCharacterId`. Các cảnh khác có `mouthEnvelope = null`. Theo quy ước của Phase 0, key vẫn có mặt.
- **`envelope.py`:**
  1. Giải mã audio của cảnh thoại (ffmpeg → PCM mono 16 kHz).
  2. Tính RMS theo cửa sổ `1/fps`.
  3. Chuẩn hóa theo phân vị 95 của chính cảnh đó.
  4. Làm mượt với attack 30 ms và release 80 ms.
  5. Áp ngưỡng 0,15: dưới ngưỡng thì bằng 0.

  Kết quả là mảng giá trị 0..1 dài đúng `durationInFrames`, làm tròn 2 chữ số. Ở 24 fps, một cảnh 6 s chỉ có 144 số.
  - **Cảnh con:** chạy cả 5 bước trên **toàn bộ file audio của câu**, được một envelope liền mạch cho cả câu. Sau đó mới cắt ra từng cảnh con theo `[startInFileSec · fps, (startInFileSec + durationSec) · fps)`.
    - Chuẩn hóa phân vị 95 và bộ làm mượt attack/release đều chạy trên cả câu.
    - Nếu tính riêng từng đoạn thì bộ làm mượt sẽ reset tại điểm cắt và độ mở miệng bị nhảy.
  - Phần cuối cảnh không có audio (đệm) được điền số 0 cho đủ `durationInFrames`.
- **Remotion:** opacity của `mouth_open_patch` = `mouthEnvelope[frame]`. Hàm dưới dịch xuống 0–2 px theo cùng giá trị.
- **Không có ảnh biến thể miệng:** không vẽ miệng. Có thể cho đầu gật rất nhẹ (±0,3°) theo envelope, làm tín hiệu "đang nói" yếu hơn.

### 3.4. Khe cắm Hybrid

- **Python (exporter):** nếu có file `input/rendered_clips/<shot_id>.mp4` hoặc `<shot_id>.loop.mp4` thì:
  - đo thời lượng bằng ffprobe;
  - copy vào `remotion/public/chapters/<id>/clips/`;
  - đặt `visual.mode = "clip"`, `clipSrc`, `clipDurationSec`;
  - tính `clipFit` bằng `plan_clip_fit()` trong `src/export/clip_fit.py`, theo quyết định D5: Python tính mọi thứ liên quan tới thời gian.
  - Có cả hai file cho cùng một cảnh thì ưu tiên clip thường và in cảnh báo.
- **Chính sách khớp thời lượng.** Ngưỡng lấy từ `settings.visuals.clip_fit.min_ratio`, mặc định 0,8:

  | Trường hợp | `clipFit` |
  | :--- | :--- |
  | Clip dài hơn hoặc bằng cảnh | `playbackRate = 1`, `freezeAtFrame = null`, `loop = false`. Remotion cắt ở cuối cảnh. |
  | Clip ngắn hơn nhưng ≥ `min_ratio` × cảnh | `playbackRate = clip / cảnh`, tức chậm lại tối đa 20 %. `freezeAtFrame = null`. |
  | Clip ngắn hơn `min_ratio` × cảnh, file thường | `playbackRate = 1`, `freezeAtFrame = floor(clipDurationSec · fps) − 1`: phát hết clip rồi `<Freeze>` ở khung cuối. |
  | Clip ngắn hơn `min_ratio` × cảnh, file `.loop.mp4` | `playbackRate = 1`, `loop = true`. |

- **Cách `ClipWithFit` dựng các trường hợp trên** (đã kiểm chứng API trên 4.0.407):
  - **Chậm lại:** `<OffthreadVideo src muted playbackRate={fit.playbackRate} />`.
  - **Freeze:** bọc bằng `<Freeze frame={fit.freezeAtFrame} active={(f) => f >= fit.freezeAtFrame}>`. Trước khung đó clip chạy bình thường, từ khung đó trở đi giữ nguyên hình.
  - **Loop:** `<OffthreadVideo>` **không có prop `loop`**. Phải bọc bằng `<Loop durationInFrames={Math.floor(clipDurationSec * fps)}>`.

- **Mở rộng schema** (theo quy ước của Phase 0 mục 3.1):

  ```typescript
  // VisualSchema thêm:
  clipDurationSec: Sec.nullable(),
  clipFit: z.object({
    playbackRate: z.number().positive().max(1),  // ≥ min_ratio; Python đảm bảo
    freezeAtFrame: z.number().int().nonnegative().nullable(),
    loop: z.boolean(),
  }).strict().nullable(),                       // khác null khi và chỉ khi mode = "clip"
  faceRig: z.object({
    eyesPatchSrc: z.string().nullable(),        // null = không có ảnh biến thể mắt hợp lệ
    mouthPatchSrc: z.string().nullable(),
    eyes: RectSchema.nullable(),                // tỉ lệ 0..1 theo ảnh cutout
    mouth: RectSchema.nullable(),
  }).strict().nullable(),                       // null khi cảnh không có nhân vật
  // SceneSchema thêm:
  mouthEnvelope: z.array(z.number().min(0).max(1)).nullable(),
  // độ dài = durationInFrames; null khi không phải cảnh thoại của nhân vật đang trên hình (mục 3.3)
  ```

  Ràng buộc chéo (kiểm ở cả hai phía; Zod `.superRefine` đặt trên `SceneSchema` và `VisualSchema`, Pydantic `model_validator`):

  - Độ dài `mouthEnvelope` bằng `durationInFrames`.
  - `clipFit != null` khi và chỉ khi `mode = "clip"`.

  Thêm hai file mẫu sai: `fixtures/invalid/envelope_length_mismatch.json` và `clip_fit_without_clip.json`.

  Lưu ý: `.superRefine` trên `SceneSchema` làm nó thành `ZodEffects`. Điều này không sao, vì `RenderPropsSchema` ở cấp gốc vẫn là `z.object`, đúng yêu cầu của prop `schema`.

- **Âm thanh của clip:** clip luôn `muted`, tiếng lấy từ giọng TTS. Clip Hedra (có lip-sync) phải được tạo từ **đúng** file `voice.wav` trong gói của cảnh đó, và bắt đầu tại frame 0 của cảnh, thì miệng mới khớp.
- **Hòa vào phim:** clip vẫn đi qua cùng lớp grade, grain và letterbox như các cảnh khác.

```tsx
export const HybridVideoSlot: React.FC<{ scene: Scene }> = ({ scene }) => {
  const { fps } = useVideoConfig();
  if (scene.visual.mode === "clip" && scene.visual.clipSrc && scene.visual.clipFit) {
    // clipFit do Python tính sẵn (D5); Remotion chỉ áp dụng
    return (
      <ClipWithFit src={staticFile(scene.visual.clipSrc)} fit={scene.visual.clipFit} /> // OffthreadVideo muted + <Freeze> / <Loop>
    );
  }
  return <CinematicStoryScene scene={scene} />; // plate + CharacterLayer (Phase 2, thêm diễn xuất ở Phase 3)
};
```

- **Gói hybrid** (`packages/<chapter>/shots/<shot_id>/`):
  - `image.png`: khung hình đã dựng, lấy bằng `npx remotion still` ở frame đầu cảnh.
  - `voice.wav`: giọng đọc của đúng cảnh đó. Với cảnh con thì cắt đoạn `[startInFileSec, startInFileSec + durationSec)` ra từ file audio của câu, để clip Hedra khớp miệng với phần giọng mà cảnh đó phát.
  - `motion_prompt.txt`: sinh từ `action` và `cameraMotion`.
  - `README.txt`: tỉ lệ khung và thời lượng cần có.

---

## 4. DANH MỤC CÔNG VIỆC THỰC HIỆN (TASK BREAKDOWN)

- [ ] **Task 3.1:** Viết `lib/life.ts` và test: khoảng cách giữa 2 lần chớp trong 2,5–5 s; mỗi lần chớp 80–200 ms; biên độ thở ≤ 0,8 %; cùng seed thì cùng kết quả.
- [ ] **Task 3.2:** Viết `face_rig.py`, thêm `opencv-python-headless` và `scikit-image` vào `requirements.txt`. Test bằng ảnh tổng hợp: chỉ vùng mắt thay đổi → rig đúng; biến thể bị vẽ lại toàn ảnh → bị từ chối.
- [ ] **Task 3.3:** Cập nhật `CharacterLayer`: thở, patch chớp mắt, chuyển động đầu.
- [ ] **Task 3.4:** Viết `envelope.py` và test: sóng có đoạn im lặng thì envelope bằng 0 ở đoạn đó; độ dài luôn bằng `durationInFrames` (có đệm số 0); hai cảnh con của cùng một câu ghép lại bằng envelope của cả câu. Thêm patch miệng.
- [ ] **Task 3.5:** Cài quy tắc "ai được cử động miệng", có test trên props của chương mẫu: 0 cảnh có envelope.
- [ ] **Task 3.6:** Hybrid: mở rộng schema ở cả hai phía cùng file mẫu, viết `clip_fit.py` (test đủ 4 trường hợp trong bảng), cập nhật exporter, viết `HybridVideoSlot`.
- [ ] **Task 3.7:** Xuất gói hybrid cho từng cảnh.
- [ ] **Task 3.8:** Chạy kiểm thử Gate 3.

---

## 5. TIÊU CHÍ NGHIỆM THU GATE 3 (ACCEPTANCE CRITERIA)

| Tiêu chí | Điều kiện bắt buộc | Phương thức kiểm tra |
| :--- | :--- | :--- |
| **Nhân vật có sự sống** | Test của `life.ts` PASS. Ảnh still ở khung chớp mắt cho thấy patch mắt nhắm (khi có ảnh biến thể). Nhân vật thở rõ nhưng không méo mặt. | vitest + `npx remotion still` + duyệt mắt |
| **Không giả lập** | Nhân vật không có ảnh biến thể: không vẽ patch nào, không lỗi. Vẫn có thở và chuyển động đầu. | Unit test props + still |
| **Khẩu hình** | Cảnh thoại: envelope > 0 khi có tiếng và = 0 trong mọi đoạn im lặng ≥ 200 ms. Cảnh lời dẫn: không có envelope. | Unit test |
| **Hybrid** | Thả clip mẫu 5 s vào một cảnh dài 6 s: cảnh đó phát clip, chậm lại ≤ 20 % hoặc freeze. Tổng thời lượng video không đổi. Clip không có tiếng. | Test E2E nhỏ + ffprobe |
| **Hiệu năng** | Chạy `--stage video --frames 0-239 --bench p3` với cùng concurrency như Gate 2. `fps_render` trong `bench_p3.json` giảm không quá 20 % so với `bench_p2.json`. | So sánh `bench_p3.json` với `bench_p2.json` (Phase 2 Task 2.13) |

---

## 6. LỆNH XÁC MINH (VERIFICATION COMMAND)

```powershell
python -m unittest discover -s tests
cd remotion; npm test
npx remotion still src/index.ts StoryComposition ../output/sample_chapter/stills/blink.png --frame=<frame có chớp mắt> --props=../output/sample_chapter/render_props.json
```

---

## 7. RỦI RO & LƯU Ý

- **Công cụ chỉnh ảnh vẽ lại cả khuôn mặt** thay vì chỉ sửa mắt hoặc miệng. `face_rig` sẽ từ chối và ta quay về chế độ không có biến thể. Người dùng có thể thử lại hoặc bỏ qua.
- **Patch miệng trên ảnh chân dung thật** vẫn có thể trông giả nếu biên độ quá lớn. Giữ opacity tối đa khoảng 0,8 và duyệt bằng mắt ở Gate.
- **Clip Kling/Hedra khác phong cách** với plate và cutout. Lớp grade chung chỉ giảm được một phần khác biệt; nên tạo clip từ chính `image.png` trong gói hybrid.
