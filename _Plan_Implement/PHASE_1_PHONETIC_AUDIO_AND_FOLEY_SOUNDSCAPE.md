# KẾ HOẠCH CHI TIẾT - PHASE 1

## ÂM THANH ĐIỆN ẢNH: CHUẨN HÓA PHÁT ÂM, ĐA GIỌNG, CĂN MỐC TỪ & FOLEY 3 TẦNG

*(Mã tài liệu: PLAN_PHASE_1_AUDIO_AND_FOLEY · rev 2 · 2026-09-25)*

> **Ghi chú sửa đổi so với rev 1**
>
> - Toàn bộ phase này viết bằng **Python** (quyết định D1). Bỏ `edge-tts-universal`, `mp3-duration.ts` và `audioData.ts`. Thời lượng audio đo bằng ffprobe như baseline đang làm.
> - `auto-video-gen` **không có code** chuẩn hóa phát âm. Nó chỉ có một bảng quy tắc trong `SKILL.md` để AI agent tự viết `voiceText`. Vì vậy module chuẩn hóa phải viết mới, và bảng đó được dùng làm ca test.
> - **Sửa quy tắc đọc số.** Tiếng Việt dùng `.` để ngăn cách hàng nghìn và `,` cho phần thập phân. Regex rev 1 `(\d+)\.(\d+)` → "chấm" sẽ đọc "1.500 người" thành "một chấm năm trăm người". Ngoài ra rev 1 chỉ chèn chữ "chấm", còn chữ số thì vẫn giữ nguyên.
> - **Bổ sung những phần rev 1 thiếu:**
>   - căn mốc từ về văn bản gốc, để phụ đề hiển thị đúng chữ gốc;
>   - khoảng lặng kịch tính (`dramatic_pause_sec` đã có trong config nhưng chưa được dùng);
>   - tốc độ đọc theo từng hồi;
>   - cache TTS;
>   - Foley theo **mốc thời gian** của từ khóa, ambience liền mạch giữa các cảnh, BGM ducking;
>   - bản quyền SFX.
> - Edge chỉ có **2 giọng tiếng Việt** (HoaiMy nữ, NamMinh nam). Người dẫn chuyện và nhân vật nam vì vậy phải phân biệt bằng pitch và tốc độ đọc, hoặc chuyển sang Vbee (đã tích hợp, xem mục 3.3).
>
> **Bổ sung rev 2.1 (sau khi rà soát plan)**
>
> - **Thư mục Foley theo nhóm:** thêm Task 1.0 chuyển 4 file tổng hợp hiện có vào `foley/<nhóm>/` và sinh thêm placeholder cho các nhóm còn thiếu. Nhờ vậy Gate 1 chạy được mà chưa cần file thật.
> - **Thêm quy tắc chọn file BGM.** Rev 2 chưa nói chọn BGM thế nào.
> - **Chọn file SFX bằng hash ổn định (sha1).** Hàm `hash()` của Python bị ngẫu nhiên hóa theo từng tiến trình, nên mỗi lần chạy sẽ chọn ra file khác nhau.
> - Mốc SFX sau khi trừ `preroll_sec` được kẹp về ≥ 0.
> - Task 1.8 (sửa exporter và file mẫu) phải merge **trước** Task 2.4 của Phase 2A.
>
> **Bổ sung rev 2.2 (rà soát lần 2)**
>
> - **Phối hợp với cách tách hình mới** (Phase 0 mục 3.4c):
>   - Khoảng lặng kịch tính ở `...` là điểm cắt bậc 0.
>   - Phụ đề, SFX và mặc định theo hồi được chia lại theo cảnh con.
>   - Gate "Thời lượng" tính trên câu gốc.
> - Đệm cuối cảnh dài hơn truyền qua tham số `pad_sec` của `plan_shot_frames`.
> - **SFX mặc định theo hồi:** nói rõ mốc bắt đầu, số lần phát và thứ tự ưu tiên.
> - Thẻ chỉ định tay `[SFX: …]` / `[BGM: …]` / `[EMO: …]` theo cú pháp chung ở Phase 0 mục 3.4b.
> - **Sau khi agent độc lập rà soát:**
>   - Gate "Thời lượng" có tính mức tối thiểu 4 s.
>   - Test đọc bản đóng băng trong `tests/fixtures/sample_chapter/`, không đọc thư mục mà TTS ghi ra.
>   - Định nghĩa `exclude` và đưa "chớp" đứng một mình vào pattern, để ca test "chớp mắt" có ý nghĩa.
>   - Ambience mưa nhận cả "drizzle" / "drizzling", cho khớp với `rain_mode: full` của con hẻm ở Phase 2.

---

## 1. MỤC TIÊU & PHẠM VI (SCOPE & OBJECTIVES)

### 1.1. Mục tiêu

1. Chuẩn hóa `raw_text` thành `voice_text` không còn chữ số hay ký hiệu, kèm bảng ánh xạ vị trí giữa hai bản.
2. TTS đa giọng theo `speaker`, có cache theo hash và có retry.
3. Căn mốc: WordBoundary (âm tiết của `voice_text`) → từ của `raw_text` → cụm phụ đề (`captions`).
4. Khoảng lặng kịch tính và tốc độ đọc theo hồi.
5. Kế hoạch Foley gồm: ambience theo bối cảnh, SFX một lần (one-shot) theo mốc từ khóa, BGM có ducking. Toàn bộ xuất vào `render_props`.

### 1.2. Hiện trạng đã có

- `src/tts_service.py`: dùng thư viện `edge_tts` của Python. Nhận WordBoundary và ghi ra `.words.json`, mỗi phần tử là một âm tiết, đã bỏ dấu câu, giữ chữ hoa.
- `src/audio/mastering.py`: loudnorm 2 lượt.
- `src/audio/stock_foley_generator.py`: sinh âm Foley tổng hợp bằng FFmpeg, chỉ để chạy thử.
- `settings.json` đã có sẵn mức âm lượng (giọng 0 dB, SFX −8 dB, BGM −22 dB) và `dramatic_pause_sec: 0.9`.

### 1.3. Ngoài phạm vi

- Mix âm thanh trong Remotion (Phase 2B, `AudioLayer`).
- Biên độ miệng (Phase 3).
- Mastering đầu ra Remotion (Phase 4).

---

## 2. KIẾN TRÚC PHÂN HỆ & DANH MỤC TỆP

```text
d:\_Short_film\
├── src/
│   ├── text/
│   │   ├── vi_numbers.py          # [mới] đọc số tiếng Việt (0 → hàng tỷ)
│   │   ├── vi_normalizer.py       # [mới] raw_text → voice_text + spans
│   │   └── alignment.py           # [mới] WordBoundary → từ gốc → captions
│   ├── tts_service.py             # [sửa] giọng theo speaker, cache, retry, ghép khoảng lặng
│   └── audio/
│       ├── foley_planner.py       # [mới] ambience + one-shot + ducking + chọn BGM
│       └── stock_foley_generator.py  # [sửa] ghi vào foley/<nhóm>/, thêm placeholder door, footsteps
├── config/
│   ├── pronunciations.json        # [mới] từ viết tắt / tên riêng → cách đọc (người dùng tự sửa được)
│   ├── foley_rules.json           # [mới] từ khóa → nhóm SFX, chế độ phát, âm lượng dB
│   ├── characters.json            # [sửa] thêm "voice", "pitch", "rate"
│   └── settings.json              # [sửa] audio.narrator, audio.rate_by_act, audio.dialect, audio.bgm_src
├── assets/audio/
│   ├── foley/<nhóm>/*.mp3         # thư viện SFX theo nhóm: rain, wind, thunder, heartbeat, door, footsteps
│   ├── bgm/*.mp3
│   └── LICENSES.md                # nguồn + giấy phép của từng file
└── tests/
    ├── test_vi_normalizer.py
    ├── test_alignment.py
    └── test_foley_planner.py      # dùng thư viện SFX giả trong thư mục tạm, không phụ thuộc assets/
```

---

## 3. THIẾT KẾ KỸ THUẬT CHI TIẾT

### 3.1. Đọc số tiếng Việt (`vi_numbers.py`)

| Quy tắc | Ví dụ |
| :--- | :--- |
| Hàng đơn vị sau "mươi": 1 đọc là **mốt**, 5 đọc là **lăm**, 4 đọc là **tư** (bật/tắt bằng cờ) | 21 → hai mươi mốt · 25 → hai mươi lăm · 24 → hai mươi tư |
| Sau "mười": 1 vẫn đọc là **một**, 5 đọc là **lăm** | 11 → mười một · 15 → mười lăm |
| Hàng chục bằng 0 và hàng đơn vị khác 0 thì chèn **linh** (giọng Bắc) hoặc **lẻ** (giọng Nam) | 105 → một trăm linh năm |
| Nhóm không đứng đầu có hàng trăm bằng 0 thì đọc **không trăm** | 1.005 → một nghìn không trăm linh năm · 2026 → hai nghìn không trăm hai mươi sáu |
| **nghìn** (Bắc) hay **ngàn** (Nam) chọn theo `settings.audio.dialect`, mặc định `bac` cho hợp với giọng NamMinh/HoaiMy | 1.000 → một nghìn |
| Chuỗi từ 8 chữ số trở lên bắt đầu bằng 0 (số điện thoại, mã) thì đọc từng chữ số | 0912… → không chín một hai… |

### 3.2. Chuẩn hóa phiên âm (`vi_normalizer.py`)

**Đầu ra:** `NormalizedText(voice_text: str, spans: list[Span])`. Mỗi `Span = (raw_start, raw_end, voice_start, voice_end)` ghi lại một đoạn đã bị thay thế. Phần không thay đổi được ánh xạ 1-1.

**Thứ tự áp dụng quy tắc** (thứ tự quan trọng, ví dụ tiền tệ phải chạy trước viết tắt để `50k` không bị hiểu thành `k` = "không"):

| # | Mẫu | Ví dụ | Kết quả |
| :---: | :--- | :--- | :--- |
| 1 | Tiền tệ | `50k`, `50.000đ`, `$5`, `2 triệu VNĐ` | năm mươi nghìn · năm mươi nghìn đồng · năm đô la · hai triệu đồng |
| 2 | Phần trăm, khoảng phần trăm | `82,7%`, `10-15%` | tám mươi hai phẩy bảy phần trăm · mười đến mười lăm phần trăm |
| 3 | Số có dấu ngăn nghìn `\d{1,3}(\.\d{3})+` | `1.500 người` | một nghìn năm trăm người |
| 4 | Thập phân dùng dấu phẩy | `3,5 km` | ba phẩy năm ki lô mét |
| 5 | Các số có dấu chấm còn lại (phiên bản) | `iOS 18.2`, `GPT 5.5` | iOS mười tám chấm hai · GPT năm chấm năm |
| 6 | Ngày tháng | `10/5/2024`, `ngày 5/10` | mười tháng năm năm hai nghìn không trăm hai mươi tư · ngày năm tháng mười |
| 7 | "tháng N" | `tháng 4`, `tháng 10` | **tháng tư** · tháng mười |
| 8 | "thứ N" | `thứ 2`, `thứ 4`, `thứ 1` | thứ hai · **thứ tư** · **thứ nhất** |
| 9 | Giờ | `7h30`, `19:05` | bảy giờ ba mươi · mười chín giờ năm phút |
| 10 | Đơn vị đo | `km`, `kg`, `cm`, `°C` | ki lô mét · ki lô gam · xen ti mét · độ xê |
| 11 | Số La Mã sau Chương / Hồi / Phần / Quyển | `Chương IV` | Chương bốn |
| 12 | Khoảng số `a-b` | `3-4 người` | ba đến bốn người |
| 13 | Viết tắt, lấy từ `pronunciations.json` | `TP.HCM`, `ko` | thành phố Hồ Chí Minh · không |
| 14 | Ký hiệu | `&`, `+`, `→`, emoji, URL | và · cộng · (bỏ) · (bỏ) · (bỏ) |
| 15 | Các số đếm còn lại | `21`, `105`, `năm 2026` | hai mươi mốt · một trăm linh năm · năm hai nghìn không trăm hai mươi sáu |

- **Giữ nguyên** dấu câu `. , ? ! … "` trong `voice_text`, vì TTS dựa vào đó để ngắt nhịp và lên giọng.
- **Edge-TTS không nhận SSML tùy biến** (không chèn được `<break>` hay `<phoneme>`). Vì vậy mọi xử lý đều phải làm ở mức văn bản hoặc bằng cách ghép audio (mục 3.4).
- **Bộ test:** ≥ 40 ca. Gồm mọi dòng của bảng trên, mọi ví dụ trong bảng quy tắc của `auto-video-gen/SKILL.md` (đã đổi sang dấu phân cách kiểu Việt), và các ca hồi quy:
  - Sau khi chuẩn hóa, regex `[0-9%$#&@→]` không còn khớp với ký tự nào.
  - Văn bản không có số (như chương mẫu hiện tại) phải được giữ nguyên.

### 3.3. Đa giọng (`tts_service.py`)

- **Cấu hình giọng:**
  - `characters.json` thêm cho mỗi nhân vật: `"voice"`, `"pitch"`, `"rate"`.
  - `settings.audio.narrator` chứa giọng của người dẫn chuyện.
  - Ví dụ: người dẫn chuyện dùng NamMinh `+0Hz`. Nhân vật Nam dùng NamMinh `−6Hz`, `−5%`. Nhân vật Mai dùng HoaiMy.
- **Tốc độ theo hồi** (RULES §1.3: đoạn thắt nút đọc nhanh hơn 5–10 %): `settings.audio.rate_by_act = {"RISING": "+5%", "CLIMAX": "+8%"}`. Giá trị này được cộng với `rate` của người nói.
- **Nhà cung cấp TTS** (**đã làm 2026-09-25**): chọn bằng `settings.audio.provider` hoặc cờ `run_pipeline.py --tts edge|vbee`.

  | Dịch vụ | Chi phí | Mốc từng từ | Ghi chú |
  | :--- | :--- | :--- | :--- |
  | `edge` (mặc định) | 0đ | Có (WordBoundary) | Chỉ 2 giọng tiếng Việt. Endpoint không chính thức. |
  | `vbee` | Trả phí theo ký tự | **Không**, phải ước lượng | Nhiều giọng, nhiều vùng miền. Khóa để trong `.env`, giọng và tốc độ đặt ở `settings.audio.vbee`. Code: `src/vbee_client.py`. |
  | `vieneu` (chưa làm) | 0đ, chạy local | Chưa rõ | Phương án dự phòng, xem `_ref_sources/auto-compare-video/vieneu.md` |

  - **Vbee giải quyết giới hạn 2 giọng:** người dẫn chuyện và từng nhân vật có thể dùng `voice_code` khác nhau, bằng cách thêm trường `vbee_voice_code` vào `characters.json`.
  - **Ước lượng mốc từ với Vbee:** không có WordBoundary, nên `TTSService` đo khoảng có tiếng nói bằng `silencedetect`, rồi chia âm tiết theo số ký tự. Mốc đầu và cuối câu khớp audio thật (SRT hiện tại chỉ cần hai mốc này). Mốc giữa câu chỉ gần đúng, nên cụm phụ đề (mục 3.5) sẽ lệch nhẹ ở chỗ ngắt nhịp. Muốn chính xác hơn thì thêm bước forced alignment (ví dụ `faster-whisper` với word timestamps, chạy CPU) như một tùy chọn.
- **Cache:** khóa cache = `sha1(voice_text | voice | rate | pitch | provider)`, lưu trong file đi kèm `output/<chapterId>/audio/<shot_id>.meta.json`. Nếu khóa trùng và file đã tồn tại thì bỏ qua bước gọi TTS.
- **Retry:** thử lại 3 lần, chờ 1 s, 2 s, 4 s (giống `auto-video-gen`). Nếu vẫn lỗi thì cảnh bị đánh dấu `FAILED` và pipeline dừng với thông báo rõ ràng.
- **Bỏ fallback im lặng:** hiện `get_audio_duration()` trả về `5.0` khi ffprobe lỗi. Phải đổi thành raise lỗi, nếu không thời lượng sai sẽ âm thầm lan xuống tới video.

### 3.4. Khoảng lặng kịch tính

- **Dấu `...` / `…` giữa câu:** tách câu thành nhiều phần, TTS từng phần, rồi ghép lại với khoảng im lặng dài `dramatic_pause_sec` (0,9 s) bằng ffmpeg ở dạng PCM. Mốc từ của các phần sau được cộng thêm độ lệch tương ứng. Kết quả lưu ở dạng `.wav` để không phải mã hóa lossy hai lần.
  - Đây chỉ là tách ở mức TTS: câu vẫn là **một cảnh, một file audio**.
  - Nếu cảnh đó vẫn dài hơn `shot_max_duration` thì Phase 0 mục 3.4c tách hình, và chỗ `...` là điểm cắt bậc 0.
  - Ví dụ trong chương mẫu: "…trong phòng khách... không hề có hơi thở." Khoảng lặng 0,9 s nằm đúng điểm cắt giữa hai cảnh con của Hook.
- **Đệm cuối cảnh:** cảnh ngay trước title card và cảnh cuối của hồi CLIMAX dùng đệm `dramatic_pause_sec` thay cho 0,6 s. Truyền qua `plan_shot_frames(..., pad_sec=dramatic_pause_sec)`.

### 3.5. Căn mốc & cụm phụ đề (`alignment.py`)

1. **Căn âm tiết.** Tách `voice_text` thành âm tiết (bỏ dấu câu, chuẩn NFC, chữ thường). Căn với các sự kiện WordBoundary bằng `difflib.SequenceMatcher` để chịu được trường hợp TTS tách hoặc gộp âm tiết khác với dự kiến.
2. **Ánh xạ về văn bản gốc.** Dùng `spans` để đưa mỗi âm tiết về từ gốc. Một từ gốc bị thay thế thì nhận `start` của âm tiết đầu và `end` của âm tiết cuối. Ví dụ `2026` ứng với 8 âm tiết đọc ra.
3. **Làm đầy chỗ trống.** Token gốc không có âm tiết nào ứng với nó thì mượn mốc của token bên cạnh. Mốc phải không giảm dần.
4. **Tạo cụm phụ đề (`captions`)** theo RULES §4:
   - Tối đa 6 từ mỗi cụm, ưu tiên ngắt sau `, . ! ? … :`, tối đa 42 ký tự (vừa 1 dòng ở 1080p).
   - `start` = mốc của từ đầu cụm.
   - `end` = `start` của cụm kế tiếp. Với cụm cuối thì lấy mốc từ cuối + 0,3 s, không vượt quá cuối cảnh.
   - `highlight` lấy từ `story_rules.json → emotion_keywords` cộng với các từ trong thẻ `[EMO: …]` của chương. Hỗ trợ cụm nhiều từ ("kinh hoàng", "không hề").
5. **Một nguồn dữ liệu:** `captions` là nguồn duy nhất cho **cả** `SubtitleBox` (Phase 2B) **lẫn** SRT (Phase 4).
6. **Cảnh con** (Phase 0 mục 3.4c): tính captions cho cả câu, nhưng **bắt buộc ngắt cụm tại điểm cắt**. Sau đó chia `words` và `captions` về từng cảnh con, trừ mốc đi `startInFileSec`. Cụm cuối của mỗi cảnh con kết thúc tại mốc từ cuối + 0,3 s, không vượt quá cuối cảnh con.

### 3.6. Kế hoạch Foley & BGM (`foley_planner.py`)

`config/foley_rules.json`:

```json
{
  "ambience": [
    { "env_weather_pattern": "rain|drizzle|drizzling", "category": "rain", "volume_db": -20, "fade_sec": 1.5 }
  ],
  "oneshot": [
    { "pattern": "tia chớp|chớp giật|chớp|sấm|sét đánh", "exclude": "chớp mắt|nháy mắt", "category": "thunder",
      "volume_db": -10, "preroll_sec": 0.2 },
    { "pattern": "tim đập|thở dốc|nín thở", "category": "heartbeat", "volume_db": -12 },
    { "pattern": "cọt kẹt|cửa gỗ|đẩy cửa|mở cửa", "category": "door", "volume_db": -10 },
    { "pattern": "bước chân|bước vào|lùi lại", "category": "footsteps", "volume_db": -14 }
  ],
  "act_defaults": { "HOOK": "heartbeat", "CLIFFHANGER": "heartbeat" },
  "limits": { "max_oneshot_per_scene": 2, "min_gap_sec": 1.5 }
}
```

- **Thứ tự ưu tiên** (port từ `auto-video-gen/src/assets/sfx-selector.ts`):
  1. Chỉ định tay bằng thẻ `[SFX: ten_file.mp3]` hoặc `[SFX: none]` (cú pháp ở Phase 0 mục 3.4b). File tìm trong `assets/audio/foley/**/`. Có thẻ thì bỏ qua bước 2 và 3 cho câu đó.
  2. Từ khóa khớp trong `raw_text`. Mốc bắt đầu = `max(0, mốc đã căn của từ khóa − preroll_sec)`, vì schema không cho phép mốc âm.
  3. **Mặc định theo hồi** (`act_defaults`): chỉ áp khi câu không có SFX nào từ bước 1 hoặc 2. Phát một lần tại `startSec = 0` của cảnh đầu tiên thuộc hồi đó (ví dụ cảnh Hook, cảnh CLIFFHANGER đầu tiên), không lặp. SFX này vẫn tính vào `max_oneshot_per_scene`.
- **Cảnh con:** SFX được gán vào cảnh con chứa mốc bắt đầu của nó, và mốc được trừ đi `startInFileSec`.
- **Chọn file:**
  - Trong cùng một nhóm, sắp xếp danh sách file theo tên rồi chọn theo `int(sha1(shot_id).hexdigest(), 16) mod n`.
  - **Không dùng `hash()` của Python.** Hàm này bị ngẫu nhiên hóa theo từng tiến trình (`PYTHONHASHSEED`), nên mỗi lần chạy sẽ chọn file khác nhau.
  - Kết quả: chạy lại cho cùng file, còn các cảnh khác nhau thì được file khác nhau.
- **Chọn BGM** (một bản cho cả chương, phát `loop`):
  1. Chỉ định tay bằng thẻ `[BGM: ten_file.mp3]` trong file `.txt`, hoặc `[BGM: none]` để tắt nhạc (Phase 0 mục 3.4b). File tìm trong `assets/audio/bgm/`.
  2. Nếu `settings.audio.bgm_src` khác `"auto"` thì dùng đúng file đó.
  3. `"auto"` (mặc định): chọn trong `assets/audio/bgm/*.mp3` theo `sha1(chapterId) mod n`.
  4. Thư mục BGM rỗng thì `bgm = null` và in cảnh báo.
- **Ambience liền mạch.** Mưa được gắn với **bối cảnh**, không gắn với từng cảnh. Một dải ambience liên tục phủ mọi cảnh liên tiếp có cùng `environmentId`, kèm fade vào và fade ra. Cách xen kẽ chẵn/lẻ hiện tại làm tiếng mưa bật tắt liên tục, phá raccord âm thanh.
- **Cách so khớp:**
  - `pattern`, `exclude` và `env_weather_pattern` là regex.
  - Chạy trên chuỗi chuẩn NFC, chữ thường, và khớp nguyên từ (`(?<!\w)…(?!\w)`).
  - `env_weather_pattern` so với trường `weather` của bối cảnh (tiếng Anh). Vì khớp nguyên từ, pattern phải liệt kê đủ dạng từ: `drizzl` sẽ **không** khớp "drizzling". Đã chạy thử: hai bối cảnh hiện có đều khớp ("heavy midnight **rain**", "**drizzling** fog"), nên cùng có ambience mưa, đúng với `rain_mode` ở Phase 2.
  - Đã chạy thử trên chương mẫu: câu 1 khớp "tia chớp" và được giữ lại; câu 4 khớp "chớp" nhưng bị `exclude` loại.
- **`exclude`:** một lần khớp `pattern` bị bỏ qua nếu đoạn văn bản của nó **chồng lên** một lần khớp `exclude` trong cùng câu.
- **Bẫy từ khóa có trong chương mẫu:** "Anh không hề **chớp** mắt".
  - `pattern` có "chớp" đứng một mình (vì "trời chớp" vẫn là tia chớp), nên câu này khớp `pattern`.
  - Nhưng đoạn đó chồng lên lần khớp `exclude` "chớp mắt", nên bị bỏ qua và không sinh tiếng sấm.
  - Ca test bắt buộc: câu 1 ("từng tia chớp xé toang") có sấm; câu 4 ("không hề chớp mắt") không có sấm.
- **Âm lượng:** đổi từ dB sang tuyến tính, `10^(dB/20)`, so với giọng đọc ở 0 dB. Khoảng theo RULES §3: SFX −6…−12 dB, ambience −18…−22 dB, BGM −18…−24 dB.
- **BGM ducking:**
  - Khoảng có giọng = hợp các đoạn [từ đầu, từ cuối] của mỗi cảnh, quy ra giây tuyệt đối bằng offset cộng dồn từ `durationInFrames / fps`. Đoạn im bên trong dài hơn 0,6 s thì tách thành khoảng riêng.
  - Trong khoảng có giọng dùng `duckedVolume` (−30 dB). Ngoài khoảng có giọng trở về `volume` (−22 dB), đúng tinh thần "đẩy nhẹ lên ở đoạn chuyển cảnh" của RULES.
  - Attack 0,15 s và release 0,5 s được xử lý ở Remotion (Phase 2B).
- **Cliffhanger** (RULES §1.3.4 "âm nhạc tắt phụt, để lại tiếng tim đập"): đặt `bgm.cutAtSec` = thời điểm bắt đầu hồi CLIFFHANGER. BGM tắt trong 0,3 s, riêng heartbeat vẫn giữ.
- **Kiểm tra file:** mọi `src` phải tồn tại. Thiếu file thì báo tên nhóm và bỏ qua SFX đó, không làm hỏng cả pipeline.

### 3.7. Nguồn SFX/BGM & bản quyền

- Các file hiện có trong `assets/audio/foley/` và `bgm/` là âm tổng hợp để chạy thử. Thay dần bằng file thật theo nhóm.
- **Chuyển sang cấu trúc theo nhóm (Task 1.0).** Hiện 4 file Foley đang nằm phẳng trong `foley/`, còn `foley_planner` thì tìm theo `foley/<nhóm>/`:

  | File hiện tại | Chuyển tới |
  | :--- | :--- |
  | `foley/rain_ambient.mp3` | `foley/rain/rain_ambient.mp3` |
  | `foley/wind_ambient.mp3` | `foley/wind/wind_ambient.mp3` |
  | `foley/thunder_rumble.mp3` | `foley/thunder/thunder_rumble.mp3` |
  | `foley/heartbeat_suspense.mp3` | `foley/heartbeat/heartbeat_suspense.mp3` |
  | *(chưa có)* | `foley/door/door_placeholder.mp3`, `foley/footsteps/footsteps_placeholder.mp3`: do `stock_foley_generator.py` sinh bằng ffmpeg |

  Sửa `stock_foley_generator.py` để ghi thẳng vào các thư mục nhóm. Nhờ vậy mọi nhóm trong `foley_rules.json` đều có ít nhất 1 file trước khi người dùng thêm file thật.
- Chỉ dùng nguồn có giấy phép rõ ràng: CC0 trên Freesound, YouTube Audio Library, Pixabay… Mỗi file ghi một dòng vào `assets/audio/LICENSES.md` gồm: tên file, nguồn, giấy phép, link.
- **Không dùng** `download-sfx.ts` của `auto-video-gen` (tải từ myinstants.com, rủi ro Content ID khi đăng YouTube).

---

## 4. DANH MỤC CÔNG VIỆC THỰC HIỆN (TASK BREAKDOWN)

- [ ] **Task 1.0:** Chuyển 4 file Foley tổng hợp vào `foley/<nhóm>/`, sửa `stock_foley_generator.py` và sinh placeholder `door`, `footsteps` (mục 3.7).
- [ ] **Task 1.1:** Viết `vi_numbers.py` và test.
- [ ] **Task 1.2:** Viết `vi_normalizer.py`, `pronunciations.json` và bộ test ≥ 40 ca.
- [ ] **Task 1.3:** Sửa TTS: giọng theo speaker, pitch, tốc độ theo hồi, cache, retry, raise lỗi thay cho fallback 5,0 s.
- [ ] **Task 1.4:** Làm khoảng lặng kịch tính: tách câu tại `...`, ghép với khoảng im lặng, dời mốc từ. Viết test.
- [ ] **Task 1.5:** Viết `alignment.py` và phần tạo captions. Test gồm cả các file `.words.json` thật đã đóng băng trong `tests/fixtures/sample_chapter/`. Không đọc `output/…/audio/`, vì tốc độ theo hồi và khoảng lặng của Phase 1 sẽ làm thay đổi các file đó.
- [ ] **Task 1.6:** Viết `foley_planner.py` và `foley_rules.json`. Test trên chương mẫu: sấm ở "tia chớp", **không** có sấm ở "chớp mắt", mưa phủ liên tục, chọn file ổn định giữa 2 tiến trình khác nhau, mốc SFX ≥ 0.
- [ ] **Task 1.7:** Chọn BGM, tính ducking và điểm cắt nhạc ở CLIFFHANGER.
- [ ] **Task 1.8:** Cập nhật exporter để điền `voiceText`, `words`, `captions`, `sfx`, `ambience`, `bgm` vào `render_props`. Cập nhật file mẫu và 2 test hợp đồng. **Merge task này trước Task 2.4** (Phase 2A cũng sửa schema, exporter và file mẫu).
- [ ] **Task 1.9:** Thay SFX/BGM tạm bằng file có giấy phép, viết `LICENSES.md`. Người dùng chọn file; phần code chỉ cần đúng cấu trúc thư mục.
- [ ] **Task 1.10:** *(Tùy chọn)* Mix Foley vào renderer ffmpeg bằng bản port của `mixSfxOntoVoice`.
- [ ] **Task 1.11:** Chạy kiểm thử Gate 1.

---

## 5. TIÊU CHÍ NGHIỆM THU GATE 1 (ACCEPTANCE CRITERIA)

| Tiêu chí | Điều kiện bắt buộc | Phương thức kiểm tra |
| :--- | :--- | :--- |
| **Phát âm (tự động)** | Bộ ≥ 40 ca PASS. Không còn `[0-9%$#&@→]` trong mọi `voice_text`. | `tests/test_vi_normalizer.py` |
| **Phát âm (nghe thử)** | 10 câu mẫu có số, ngày, tiền tệ được đọc đúng. | Checklist nghe tay (file mẫu nằm trong `tests/fixtures/`) |
| **Đa giọng** | Cảnh thoại dùng giọng của nhân vật. Người dẫn chuyện và nhân vật nam có pitch khác nhau. | Unit test trên storyboard + nghe thử |
| **Căn mốc** | Mỗi từ gốc có `start ≤ end`, mốc không giảm. "năm 2026" được gộp thành đúng 1 từ gốc. Không cụm nào quá 6 từ hoặc 42 ký tự. | `tests/test_alignment.py` |
| **Thời lượng** | Với mỗi câu gốc: Σ `durationInFrames` của các cảnh con / fps trừ `max(audio + đệm, shot_min_duration)` lệch < 1 frame, audio đo bằng ffprobe. Không **cảnh `story`** nào > 6,5 s. Mọi cảnh con ≥ 2,5 s. | Unit test |
| **Foley** | Chương mẫu: sấm ở mốc "tia chớp" (±0,1 s sau khi trừ preroll). **Không** có sấm ở "chớp mắt". Mưa phủ liên tục các cảnh cùng bối cảnh. Mọi `src` đều tồn tại. | `tests/test_foley_planner.py` |
| **Ducking** | BGM ở mức ducked trong mọi khoảng có giọng và tắt từ CLIFFHANGER trở đi. | Unit test trên props |
| **Cache** | Chạy lại lần 2 không phát sinh request TTS nào. | Unit test với mock |

---

## 6. LỆNH XÁC MINH (VERIFICATION COMMAND)

```powershell
python -m unittest discover -s tests
python run_pipeline.py --renderer remotion --stage audio --input input/sample_chapter.txt   # renderer ffmpeg chỉ nhận --stage all
```

---

## 7. RỦI RO & LƯU Ý

- **Edge-TTS bị chặn hoặc đổi API:** đã có cache và phương án dự phòng VieNeu. Test không được gọi mạng thật (dùng mock).
- **WordBoundary tiếng Việt** có thể tách âm tiết khác với dự kiến (tên riêng, từ mượn). Căn mốc dùng SequenceMatcher và luôn có test trên file `.words.json` thật.
- **Âm lượng Foley tổng hợp** khác xa file thật. Chỉ tinh chỉnh mức dB sau khi đã có file thật (Task 1.9).
