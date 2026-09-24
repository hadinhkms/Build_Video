# KẾ HOẠCH CHI TIẾT - PHASE 2
## BỘ SCENE COMPONENT REMOTION ĐIỆN ẢNH & BẢO TOÀN RACCORD 2.5D
*(Mã tài liệu: PLAN_PHASE_2_REMOTION_SCENE_COMPONENTS)*

---

## 1. MỤC TIÊU & PHẠM VI (SCOPE & OBJECTIVES)

### 1.1. Mục tiêu
Xây dựng thư viện React Component chuẩn cho Remotion v4, hiện thực hóa phong cách điện ảnh cao cấp:
1. **Kiến Trúc Scene 3 Lớp (3-Layer Architecture):**
   * **Lớp 1 (Background Plate):** Bối cảnh không gian khóa Raccord (cửa sổ vòm, sofa, kệ sách).
   * **Lớp 2 (Character 2.5D Layer):** Khung hình nhân vật với chuyển động máy quay Parallax độc lập.
   * **Lớp 3 (Atmospheric Foreground):** Hiệu ứng mưa rơi Canvas, ánh đèn lập lòe (flickering rim light), hạt phim 35mm (Film Grain) và dải đen điện ảnh (Cinematic Letterbox).
2. **Bộ Chuyển Động Máy Quay Bằng Vật Lý (Spring Camera Moves):** Thay thế zoom FFmpeg thô cứng bằng các hàm `spring()` và `interpolate()` của Remotion để máy quay lia (Pan) và phóng to (Push-in) mượt mà như dùng ray trượt dolly thật.
3. **Phụ Đề Động Pill-Box `SubtitleBox` (Kế thừa từ `remotion-cuongit-template`):** Ngắt cụm 5–7 từ/lần, hiệu ứng nảy chữ Spring Pop-in, tự động highlight từ khóa vàng neon (`text-amber-300`).

---

## 2. KIẾN TRÚC COMPONENT & DANH MỤC TỆP

```
d:\_Short_film\
├── src/
│   ├── components/
│   │   ├── SubtitleBox.tsx          # Thanh phụ đề động ngắt cụm 5-7 từ có Spring
│   │   ├── AtmosphericEffects.tsx   # Canvas mưa rơi, hạt film grain & ánh sáng lập lòe
│   │   ├── BackgroundPlate.tsx      # Tấm nền bối cảnh khóa raccord mỏ neo không gian
│   │   └── CinematicLetterbox.tsx   # Dải đen điện ảnh tỉ lệ 2.39:1 hoặc 16:9
│   ├── scenes/
│   │   ├── CinematicStoryScene.tsx  # Master Scene container điều khiển Parallax & Camera
│   │   └── StoryComposition.tsx     # Ghép toàn bộ các phân cảnh thành 1 timeline liên tục
│   └── styles/
│       └── cinematic.css            # Font chữ Be Vietnam Pro (@font-face) & Token màu
```

---

## 3. THIẾT KẾ KỸ THUẬT CHI TIẾT

### 3.1. Chuyển Động Máy Quay Bằng Remotion Spring (`CinematicStoryScene.tsx`)
```typescript
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

export const useCinematicCamera = (motionType: string, durationInFrames: number) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Tạo độ trôi mượt mà bằng Spring physics
  const progress = interpolate(frame, [0, durationInFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  if (motionType === "zoom_in") {
    const scale = interpolate(progress, [0, 1], [1.0, 1.15]);
    return { transform: `scale(${scale})` };
  } else if (motionType === "pan_left") {
    const translateX = interpolate(progress, [0, 1], [0, -40]);
    return { transform: `scale(1.10) translateX(${translateX}px)` };
  }
  return { transform: `scale(1.0)` };
};
```

### 3.2. Hiệu Ứng Mưa Rơi Bằng Canvas (`AtmosphericEffects.tsx`)
* Chạy trực tiếp trên thẻ `<canvas>` bằng toán tử thời gian Remotion (`useCurrentFrame()`).
* 60 hạt mưa lăn nghiêng nhẹ theo chiều gió, tạo cảm giác đêm mưa lạnh lẽo chân thực mà **không tốn tài nguyên GPU**.

### 3.3. Phụ Đề Động Chuẩn `SubtitleBox.tsx`
* Kế thừa trọn vẹn từ `remotion-cuongit-template`:
  * Tự động chia `wordsPerChunk = 6`.
  * Viền neon bo tròn sang trọng `rounded-full border border-sky-400/30 bg-slate-950/80 backdrop-blur-md`.
  * Từ khóa cảm xúc hiển thị màu vàng hổ phách nổi bật `text-amber-300 drop-shadow-[0_0_12px_rgba(252,211,77,0.7)]`.

---

## 4. DANH MỤC CÔNG VIỆC THỰC HIỆN (TASK BREAKDOWN)

- [ ] **Task 2.1:** Cài đặt font `Be Vietnam Pro` qua `@font-face` trong `cinematic.css` để phụ đề tiếng Việt hiển thị hoàn hảo.
- [ ] **Task 2.2:** Xây dựng component `src/components/SubtitleBox.tsx` kế thừa từ template Cường IT.
- [ ] **Task 2.3:** Xây dựng component `src/components/AtmosphericEffects.tsx` (mưa rơi, hạt film grain).
- [ ] **Task 2.4:** Xây dựng `src/scenes/CinematicStoryScene.tsx` kết nối 3 lớp và áp dụng chuyển động Spring Camera.
- [ ] **Task 2.5:** Đăng ký Composition vào `src/Root.tsx` và kiểm tra trên Remotion Preview Studio.

---

## 5. TIÊU CHÍ NGHIỆM THU GATE 2 (ACCEPTANCE CRITERIA)

| Tiêu chí | Điều kiện bắt buộc | Phương thức kiểm tra |
| :--- | :--- | :--- |
| **Không Lỗi Font Tiếng Việt** | 100% ký tự có dấu (ă, â, ê, ô, ơ, ư) hiển thị đẹp mắt, không bị lỗi font fallback | Kiểm tra trực quan trên Remotion Studio |
| **Camera Mượt Mà 30/24 FPS** | Không bị giật khung hình (frame stutter), chuyển động scale/translate có độ giảm tốc tự nhiên | Kiểm tra Remotion playback |
| **Khóa Raccord Bối Cảnh** | Tấm nền không gian giữ nguyên cửa sổ và đồ đạc giữa các cảnh liên tiếp | Đối chiếu các scene trong StoryComposition |

---

## 6. LỆNH XÁC MINH (VERIFICATION COMMAND)

```powershell
npx remotion preview
```
*(Mở giao diện Web Studio tại `http://localhost:3000` để xem trước chuyển động thời gian thực).*
