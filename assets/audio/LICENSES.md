# Audio Assets Licenses & Provenance

Tài liệu này ghi nhận nguồn gốc và bản quyền của các tài nguyên âm thanh (BGM, Foley Ambience, One-shot SFX) được tích hợp trong hệ thống Short Film.

---

## 1. Nguyên Tắc Bản Quyền

- **Cam kết bản quyền:** Hệ thống cam kết chỉ sử dụng các mẫu âm thanh thuộc phạm vi **Public Domain (CC0)**, **Royalty-Free Commercial Use**, hoặc âm thanh được **tổng hợp thuật toán (Synthetic Audio Generation)**.
- **Không vi phạm:** Tuyệt đối không nhúng các tệp âm thanh có bản quyền thương mại độc quyền hoặc chưa qua cấp phép.

---

## 2. Danh Mục Tài Sản Âm Thanh

| Phân Loại | Tên File / Thư mục | Nguồn Gốc | Giấy Phép (License) | Mô Tả |
| :--- | :--- | :--- | :--- | :--- |
| **BGM** | `assets/audio/bgm/dark_ambient_drone.mp3` | Synthetic / AI Audio Lab | CC0 1.0 Universal / Royalty-Free | Nhạc nền ambient tone tối, drone căng thẳng cho không khí trinh thám/kinh dị. |
| **Ambience** | `assets/audio/foley/rain/rain_ambient.mp3` | Synthetic Noise Filter / Freesound | CC0 1.0 Universal (Public Domain) | Tiếng mưa rào đều đặn, lọc qua bộ lọc dải tần thấp (Low-pass) cho bối cảnh trong phòng. |
| **Ambience / SFX** | `assets/audio/foley/wind/wind_howl.mp3` | Synthetic White/Pink Noise | CC0 1.0 Universal | Tiếng gió rít qua khe cửa, tạo cảm giác lạnh lẽo và cô độc. |
| **SFX** | `assets/audio/foley/thunder/thunder_rumble.mp3` | Synthetic Sub-bass Resonance | CC0 1.0 Universal | Tiếng sấm rền xa với xung tần số thấp (40-90Hz), không làm vỡ âm thoại. |
| **SFX** | `assets/audio/foley/heartbeat/heartbeat_suspense.mp3` | Synthetic Dual-Pulse Generator | CC0 1.0 Universal | Tiếng tim đập dồn dập (thump-thump), tăng áp lực cho các phân cảnh hồi hộp (HOOK, CLIMAX). |
| **SFX** | `assets/audio/foley/door/door_creak.mp3` | Synthetic Friction Synthesis | CC0 1.0 Universal | Tiếng bản lề cửa gỗ cọt kẹt, báo hiệu sự xâm nhập hoặc chuyển cảnh. |
| **SFX** | `assets/audio/foley/footsteps/footsteps_creak.mp3` | Synthetic Impact Resonance | CC0 1.0 Universal | Tiếng bước chân bước trên sàn gỗ cũ kỹ, tạo cảm giác ai đó đang tiến lại gần. |

---

## 3. Công Cụ & Mã Nguồn Tổng Hợp

Các âm thanh dạng placeholder và synthetic sound wave được sinh trực tiếp bằng thuật toán Python chuẩn hóa dải tần (Sine, Low-frequency Triangle wave, Bandpass Filtered Pink Noise) thông qua module:
- `src/audio/stock_foley_generator.py`

Khi người dùng bổ sung các file âm thanh chất lượng studio từ các nguồn như **Pixabay Music**, **Freesound.org (CC0)**, hoặc **Epidemic Sound (Licensed)**, cần cập nhật vào bảng kê trên kèm mã xác nhận bản quyền tương ứng.
