# KẾ HOẠCH CHI TIẾT - PHASE 3
## DIỄN XUẤT 2.5D AUDIO-REACTIVE & KHE CẮM HYBRID VIDEO NÂNG CAO
*(Mã tài liệu: PLAN_PHASE_3_AUDIO_REACTIVE_ACTING)*

---

## 1. MỤC TIÊU & PHẠM VI (SCOPE & OBJECTIVES)

### 1.1. Mục tiêu
Giải quyết trọn vẹn yêu cầu **"nhân vật biết diễn xuất"** với **chi phí 0 VNĐ** bằng cách kế thừa cơ chế Avatar thông minh từ **`auto-compare-video`**, đồng thời mở sẵn khe cắm **Hybrid Mode** để nâng cấp lên video AI điện ảnh bất kỳ lúc nào:
1. **Diễn Xuất 2.5D Audio-Reactive (Miễn Phí 100%):**
   * **Nhịp thở tự nhiên:** Tự động co giãn nhẹ nhàng (`scaleY`) theo hàm sin chu kỳ 1.5 giây.
   * **Chớp mắt ngẫu nhiên:** Tự động khép mí mắt sau mỗi 3–4 giây (kéo dài 4 frame) tạo cảm giác người thật đang sống trong khung hình.
   * **Mấp máy môi/cơ mặt theo âm lượng (Lip Vibration):** Đo biên độ âm thanh từ file MP3 câu thoại để kích hoạt khóe miệng và cằm rung nhẹ theo từng âm tiết phát ra.
2. **Khe Cắm Hybrid Mode (Linh hoạt tuyệt đối):**
   * Nếu phân cảnh chỉ dùng ảnh tĩnh $\rightarrow$ Remotion tự động áp dụng Diễn xuất 2.5D.
   * Nếu người dùng kéo thả 1 clip video 5s từ Kling AI / Hedra vào thư mục `input/rendered_clips/shot_XX.mp4` $\rightarrow$ Remotion tự động nhận diện và chuyển sang phát video clip chuyển động thực thụ mà không làm hỏng cấu trúc phim!

---

## 2. KIẾN TRÚC PHÂN HỆ & DANH MỤC TỆP

```
d:\_Short_film\
├── src/
│   ├── components/
│   │   ├── Character2D.tsx          # Component nhân vật 2.5D có nhịp thở & chớp mắt
│   │   ├── AudioReactiveMouth.tsx   # Điều khiển mấp máy môi theo biên độ âm thanh
│   │   └── HybridVideoSlot.tsx      # Tự động chuyển đổi giữa Video Clip AI và 2.5D
│   └── utils/
│       └── audio-waveform.ts        # Thuật toán trích xuất biên độ âm thanh từng frame
└── input/
    └── rendered_clips/              # Thư mục để người dùng thả clip Kling/Hedra (tùy chọn)
```

---

## 3. THIẾT KẾ KỸ THUẬT CHI TIẾT

### 3.1. Nhịp Thở & Chớp Mắt Trong Remotion (`Character2D.tsx`)
```typescript
import { useCurrentFrame } from "remotion";

export const useCharacterLife = () => {
  const frame = useCurrentFrame();

  // 1. Nhịp thở nhẹ nhàng theo trục Y
  const breathScaleY = 1.0 + 0.012 * Math.sin((frame * Math.PI) / 45);

  // 2. Chớp mắt tự nhiên: Mỗi 100 frame (~3.3s), khép mắt trong 4 frame
  const cycleFrame = frame % 100;
  const isBlinking = cycleFrame >= 96 && cycleFrame <= 99;

  return { breathScaleY, isBlinking };
};
```

### 3.2. Mấp Máy Môi Theo Âm Lượng (`AudioReactiveMouth.tsx`)
* Dựa trên phân tích biên độ âm thanh của từng frame:
* Khi nhân vật nói (âm lượng $> 0.15$), khóe miệng mở rộng nhẹ từ 1.0 $\rightarrow$ 1.08 và cằm hơi chuyển động xuống dưới. Khi dứt câu thoại (khoảng lặng), cơ mặt tự động trở về trạng thái nghỉ.
* Mang lại cảm giác nhân vật **thực sự đang phát âm** câu thoại mà không tốn 1 xu chi phí cloud!

### 3.3. Cơ Chế Khe Cắm Hybrid (`HybridVideoSlot.tsx`)
```typescript
import { OffthreadVideo, staticFile } from "remotion";
import { Character2D } from "./Character2D";

export const HybridVideoSlot: React.FC<{ shotId: string; faceImg: string }> = ({ shotId, faceImg }) => {
  const videoClipPath = `rendered_clips/${shotId}.mp4`;
  const hasClip = checkFileExists(videoClipPath);

  if (hasClip) {
    // Phát video clip điện ảnh từ Kling/Hedra
    return <OffthreadVideo src={staticFile(videoClipPath)} className="w-full h-full object-cover" />;
  }

  // Fallback: Diễn xuất 2.5D Audio-Reactive chất lượng cao
  return <Character2D faceImg={faceImg} />;
};
```

---

## 4. DANH MỤC CÔNG VIỆC THỰC HIỆN (TASK BREAKDOWN)

- [ ] **Task 3.1:** Xây dựng hook `useCharacterLife` tính toán nhịp thở và chu kỳ chớp mắt.
- [ ] **Task 3.2:** Triển khai module `AudioReactiveMouth.tsx` phản ứng theo biên độ âm thanh.
- [ ] **Task 3.3:** Xây dựng component `HybridVideoSlot.tsx` hỗ trợ nhận video clip ngoài.
- [ ] **Task 3.4:** Viết script tự động trích xuất các gói `packages/shot_XX/` (Ảnh + Audio + Prompt) để người dùng tiện kéo thả lên Kling/Hedra khi cần.
- [ ] **Task 3.5:** Chạy kiểm thử nghiệm thu Gate 3.

---

## 5. TIÊU CHÍ NGHIỆM THU GATE 3 (ACCEPTANCE CRITERIA)

| Tiêu chí | Điều kiện bắt buộc | Phương thức kiểm tra |
| :--- | :--- | :--- |
| **Nhân vật Có Sự Sống** | Nhân vật có cử động thở và chớp mắt rõ ràng, không còn là ảnh chết | Quan sát trực quan trên Remotion Studio |
| **Đồng Bộ Khẩu Hình** | Cơ miệng mấp máy khi giọng nói vang lên và dừng lại khi ngắt câu | Kiểm tra đồng bộ audio waveform |
| **Hybrid Mode Liền Mạch** | Khi thả file clip MP4 vào thư mục, hệ thống tự động phát clip thay thế 2.5D | Thử nghiệm thả file clip mẫu |

---

## 6. LỆNH XÁC MINH (VERIFICATION COMMAND)

```powershell
npx tsx scripts/test-character-animation.ts
```
