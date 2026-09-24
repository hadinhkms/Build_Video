# KẾ HOẠCH CHI TIẾT - PHASE 1
## ÂM THANH ĐIỆN ẢNH: CHUẨN HÓA PHÁT ÂM TIẾNG VIỆT, EDGE-TTS & FOLEY SOUNDSCAPE
*(Mã tài liệu: PLAN_PHASE_1_AUDIO_AND_FOLEY)*

---

## 1. MỤC TIÊU & PHẠM VI (SCOPE & OBJECTIVES)

### 1.1. Mục tiêu
Kế thừa trọn vẹn giải pháp xử lý âm thanh xuất sắc từ **`auto-video-gen`** và **`remotion-cuongit-template`**:
1. **Chuẩn Hóa Phiên Âm Tiếng Việt (Vietnamese Phonetics):** Xóa bỏ triệt để lỗi đọc ngô nghê của AI (ví dụ: đọc "18.2" thành "mười tám chấm hai", đọc "100%" thành "một trăm phần trăm", đọc "tháng 10" thành "tháng mười").
2. **Tạo Giọng Đọc 0 Đồng (`edge-tts-universal`):** Tự động sinh file giọng đọc tiếng Việt đa giọng (`vi-VN-NamMinhNeural` cho người dẫn chuyện, `vi-VN-HoaiMyNeural` cho đối thoại nữ) mà **không cần bất kỳ API key nào**.
3. **Đo Thời Lượng Khớp Từng Frame (Frame-Accurate Timing):** Đọc trực tiếp MPEG audio frame header từ buffer MP3 để tính chính xác số frame Remotion (`durationInFrames`) tới mili-giây mà không cần gọi tiến trình ngoài.
4. **Hòa Âm 3 Tầng Đồng Bộ (Foley SFX & BGM Ducking):** Tự động quét từ khóa hành động trong truyện để ghép tiếng động chân thực và tự động hạ âm lượng nhạc nền khi có giọng đọc.

---

## 2. KIẾN TRÚC PHÂN HỆ & DANH MỤC TỆP

```
d:\_Short_film\
├── scripts/
│   ├── phonetics/
│   │   └── vietnamese-normalizer.ts # Bộ quy tắc chuẩn hóa số, ngày, ký hiệu sang chữ
│   ├── audio/
│   │   ├── tts-generator.ts         # Wrapper edge-tts-universal đa giọng
│   │   ├── mp3-duration.ts          # Bộ phân tích frame header MPEG tính duration
│   │   └── foley-indexer.ts         # Quét từ khóa hành động và ánh xạ file SFX
└── public/
    └── audio/
        ├── foley/                   # Kho âm thanh tiếng động (rain, thunder, door, heart)
        ├── bgm/                     # Nhạc nền ambient
        └── shots/                   # File mp3 giọng đọc từng phân cảnh
```

---

## 3. THIẾT KẾ KỸ THUẬT CHI TIẾT

### 3.1. Bộ Quy Tắc Chuẩn Hóa Phiên Âm Tiếng Việt (`vietnamese-normalizer.ts`)
Áp dụng bộ luật từ `auto-video-gen`:
```typescript
export function normalizeVietnameseForTTS(rawText: string): string {
  let text = rawText;
  // 1. Chuẩn hóa số thập phân: "5.5" -> "năm chấm năm"
  text = text.replace(/(\d+)\.(\d+)/g, "$1 chấm $2");
  // 2. Chuẩn hóa phần trăm: "80%" -> "tám mươi phần trăm"
  text = text.replace(/(\d+)%/g, "$1 phần trăm");
  // 3. Chuẩn hóa số thứ tự/chương: "Chương 1" -> "Chương một"
  // 4. Đọc chuẩn số đếm tiếng Việt từ 0 đến 9999
  return text;
}
```

### 3.2. Đo Frame-Accurate Từ MPEG Frame Header (`mp3-duration.ts`)
Kế thừa thuật toán từ `remotion-cuongit-template/scripts/generate-tts.ts`:
* Đọc trực tiếp byte header của file MP3 (`0xFF 0xFB/0xE0`).
* Tính toán số mẫu âm thanh (Sample count) chia cho tần số lấy mẫu (24.000 Hz / 44.100 Hz).
* Quy đổi trực tiếp sang số frame Remotion:
  $$\text{durationInFrames} = \lceil \text{durationInSeconds} \times \text{fps} \rceil + 3 \text{ (buffer 0.1s chuyển cảnh)}$$

### 3.3. Từ Điển Quét Từ Khóa Foley Tự Động (`foley-indexer.ts`)
| Từ khóa trong truyện | File SFX tương ứng | Âm lượng hòa âm |
| :--- | :--- | :---: |
| *"mưa"*, *"mái hiên"*, *"giọt nước"* | `public/audio/foley/rain_ambient.mp3` | `volume: 0.35` |
| *"sấm"*, *"sét"*, *"chớp"* | `public/audio/foley/thunder_rumble.mp3` | `volume: 0.60` |
| *"tim đập"*, *"thở dốc"* | `public/audio/foley/heartbeat_suspense.mp3` | `volume: 0.45` |
| *"cửa gỗ"*, *"cọt kẹt"* | `public/audio/foley/door_creak.mp3` | `volume: 0.40` |

---

## 4. DANH MỤC CÔNG VIỆC THỰC HIỆN (TASK BREAKDOWN)

- [ ] **Task 1.1:** Cài đặt package `edge-tts-universal` qua npm.
- [ ] **Task 1.2:** Triển khai module `scripts/phonetics/vietnamese-normalizer.ts` với đầy đủ test case cho số, phần trăm, ngày tháng.
- [ ] **Task 1.3:** Triển khai module `scripts/audio/mp3-duration.ts` đo chính xác độ dài audio.
- [ ] **Task 1.4:** Xây dựng script `scripts/generate-story-audio.ts` tự động nhận file kịch bản, chuẩn hóa câu, sinh audio và xuất ra file metadata `audioData.ts`.
- [ ] **Task 1.5:** Chạy kiểm thử nghiệm thu Gate 1.

---

## 5. TIÊU CHÍ NGHIỆM THU GATE 1 (ACCEPTANCE CRITERIA)

| Tiêu chí | Điều kiện bắt buộc | Phương thức kiểm tra |
| :--- | :--- | :--- |
| **Phát âm Tiếng Việt Chuẩn** | Không còn ký tự số hoặc ký hiệu lạ trong `voiceText`; TTS đọc trôi chảy 100% | Kiểm tra output của `normalizeVietnameseForTTS` |
| **Frame Timing Tuyệt Đối** | Số frame Remotion tính toán khớp hoàn hảo với thời lượng audio (sai số $\le 1$ frame) | Đối chiếu `durationInFrames` với file MP3 thực tế |
| **Tự Động Hòa Âm SFX** | Phân cảnh có từ khóa mưa/sấm tự động kích hoạt file âm thanh nền tương ứng | `test_foley_keyword_matching` PASS |

---

## 6. LỆNH XÁC MINH (VERIFICATION COMMAND)

```powershell
npx tsx scripts/generate-story-audio.ts --input input/sample_chapter.txt
```
