# KẾ HOẠCH CHI TIẾT - PHASE 0
## THIẾT LẬP KIẾN TRÚC REMOTION V4, TYPESCRIPT & DATA CONTRACTS (ZOD SCHEMAS)
*(Mã tài liệu: PLAN_PHASE_0_REMOTION_ARCHITECTURE)*

---

## 1. MỤC TIÊU & PHẠM VI (SCOPE & OBJECTIVES)

### 1.1. Mục tiêu
Thiết lập dự án **Remotion v4** tích hợp **React 19 / TypeScript / TailwindCSS** ngay trong `d:\_Short_film`, chuẩn hóa toàn bộ hợp đồng dữ liệu (Data Schemas) bằng **Zod** (kế thừa từ `auto-video-gen` và `remotion-cuongit-template`), và xây dựng bộ điều phối kịch bản (Script Orchestrator).

### 1.2. Ngoài phạm vi
* Chưa xử lý audio và các hiệu ứng động phức tạp (thuộc Phase 1 & 2).

---

## 2. KIẾN TRÚC DỰ ÁN & DANH MỤC TỆP

```
d:\_Short_film\
├── package.json              # Khai báo Remotion, React, TailwindCSS, Zod, edge-tts
├── remotion.config.ts        # Cấu hình Remotion renderer (gl=angle, codec=h264, crf=18)
├── tsconfig.json             # Cấu hình TypeScript nghiêm ngặt (Strict mode, ES2022)
├── src/
│   ├── index.ts              # Entry point Remotion registration
│   ├── Root.tsx              # Root composition (1080x1920 9:16 hoặc 1920x1080 16:9)
│   ├── schemas/
│   │   ├── story-schema.ts   # Zod schema cho Kịch bản truyện, Phân cảnh, DNA, Mỏ neo
│   │   └── config-schema.ts  # Cấu hình giọng đọc, độ phân giải, FPS
│   └── orchestrator/
│       ├── story-parser.ts   # Phân rã văn bản truyện thành danh sách Scene có Hook 15s
│       └── state-manager.ts  # Quản lý checkpoint tiến trình dạng JSON
└── tests/
    └── test_phase0_schemas.ts # Kiểm thử Zod schema và nạp kịch bản
```

---

## 3. THIẾT KẾ KỸ THUẬT CHI TIẾT

### 3.1. Cấu Trúc Data Contracts (Zod Schema trong `src/schemas/story-schema.ts`)
Kế thừa cấu trúc từ `auto-video-gen` nhưng tối ưu riêng cho truyện điện ảnh:

```typescript
import { z } from "zod";

export const CharacterDNASchema = z.object({
  id: z.string(),
  name: z.string(),
  age: z.number().default(28),
  faceReferenceImage: z.string(),
  dnaPrompt: z.string(),
  fixedWardrobe: z.string(),
});

export const SceneSchema = z.object({
  id: z.string(),
  act: z.enum(["HOOK", "SETUP", "RISING", "CLIMAX", "CLIFFHANGER"]),
  voiceText: z.string(), // Lời đọc sau khi đã chuẩn hóa phát âm tiếng Việt
  rawText: z.string(),   // Lời gốc hiển thị trên phụ đề
  shotType: z.enum(["wide", "medium", "closeup", "over-shoulder"]).default("medium"),
  cameraMotion: z.enum(["zoom_in", "zoom_out", "pan_left", "pan_right", "static"]).default("zoom_in"),
  highlightKeyword: z.string().optional(),
  speakingCharacterId: z.string().default("main_char"),
  sfxCue: z.string().optional(),
  durationInFrames: z.number().default(150), // Mặc định 5s @ 30fps
});

export const StoryScriptSchema = z.object({
  chapterId: z.string(),
  title: z.string(),
  aspectRatio: z.enum(["16:9", "9:16"]).default("16:9"),
  fps: z.number().default(30),
  scenes: z.array(SceneSchema),
});
```

### 3.2. Cấu Hình Remotion Cho Máy Trạm Xeon (`remotion.config.ts`)
Tận dụng tối đa 28 nhân / 56 luồng của Dual Xeon E5-2680 v4:
```typescript
import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setPixelFormat("yuv420p");
Config.setCodec("h264");
Config.setCrf(18); // Chất lượng hình ảnh cực cao
// Tận dụng đa luồng CPU Xeon
Config.setConcurrency(8); // Chạy 8 tiến trình render song song
```

---

## 4. DANH MỤC CÔNG VIỆC THỰC HIỆN (TASK BREAKDOWN)

- [ ] **Task 0.1:** Tạo file `package.json` với các dependencies chuẩn: `remotion`, `@remotion/cli`, `@remotion/tailwind`, `react`, `react-dom`, `zod`, `dotenv`.
- [ ] **Task 0.2:** Viết `remotion.config.ts` và `tsconfig.json` tối ưu hóa đa luồng cho CPU Xeon.
- [ ] **Task 0.3:** Xây dựng `src/schemas/story-schema.ts` với đầy đủ validation rules.
- [ ] **Task 0.4:** Khởi tạo `src/Root.tsx` và `src/index.ts` đăng ký Composition chuẩn 1080p.
- [ ] **Task 0.5:** Chạy lệnh `npm install` và thực hiện test kiểm thử Gate 0.

---

## 5. TIÊU CHÍ NGHIỆM THU GATE 0 (ACCEPTANCE CRITERIA)

| Tiêu chí | Điều kiện bắt buộc | Phương thức kiểm tra |
| :--- | :--- | :--- |
| **Dependencies Clean** | Cài đặt thành công toàn bộ npm packages, không có lỗi xung đột phiên bản | `npm run build` hoặc `npx tsc --noEmit` |
| **Schema Validation** | Zod parse chính xác kịch bản mẫu và từ chối nếu thiếu trường bắt buộc | Unit test Zod Validation PASS 100% |
| **Remotion Preview Sẵn sàng** | Chạy được giao diện Remotion Studio nội bộ | `npx remotion preview` khởi chạy thành công |

---

## 6. LỆNH XÁC MINH (VERIFICATION COMMAND)

```powershell
npm run typecheck
```
