# Phase 1: Chốt Concept 2D & Dựng Nhân vật Gốc (MPFB2 + Rigify)

## Mục tiêu
Chốt thiết kế nhân vật rõ ràng trên 2D trước khi vào 3D, sau đó dựng xong khung cơ thể, khuôn mặt chuẩn giải phẫu và bộ xương diễn hoạt hoàn chỉnh trong Blender.

---

## Đầu vào & Đầu ra
- **Đầu vào:** Ý tưởng nhân vật (tuổi, giới tính, vóc dáng, phong cách, tính cách).
- **Đầu ra:** File `<char_name>_v01_base.blend` chứa:
  - Mesh cơ thể + khuôn mặt có tỷ lệ đúng concept.
  - Bộ xương **Rigify** đã generate và bind sạch vào mesh.
  - Hình ảnh tham chiếu (Reference Images) đặt sẵn trong scene.

---

## Các bước thực hiện

### Bước 1: Chốt Concept 2D (Reference Sheet)
1. Tạo/chuẩn bị bộ ảnh tham chiếu gồm ít nhất:
   - **Chính diện (Front view)** – đứng thẳng, tay hơi dang (A-pose).
   - **Mặt nghiêng (Side view)** – để canh sống mũi, cằm, hộp sọ, độ cong lưng.
   - **Cận mặt (Close-up Portrait)** – chốt thần thái, mắt, môi, cấu trúc xương gò má.
2. Lưu toàn bộ vào thư mục `_references/`.

### Bước 2: Đưa ảnh tham chiếu vào Blender (có thể dùng MCP)
- Nhờ AI qua MCP hoặc tự đặt 2 Empty Image ở góc nhìn Orthographic Front (`Numpad 1`) và Right (`Numpad 3`), canh đúng chiều cao thực tế của nhân vật (ví dụ `1.72m`).

### Bước 3: Dựng nhân vật gốc bằng MPFB2
1. Trong tab **MPFB** $\rightarrow$ `New Human` $\rightarrow$ `From scratch`:
   - Chỉnh **Phenotype**: Giới tính, tuổi, cân nặng, cơ bắp, chiều cao, tỷ lệ đầu/thân.
   - Chỉnh **Face / Head**: Tinh chỉnh từng nhóm thông số (trán, hốc mắt, sống mũi, gò má, hàm, môi) đối chiếu trực tiếp với ảnh Front và Side ở chế độ X-Ray (`Alt + Z`).
2. **Lưu ý:** Đừng cố làm quá chi tiết nếp nhăn li ti ở bước này; tập trung vào **tỷ lệ khối lớn (primary & secondary forms)** chuẩn giải phẫu.
3. Gắn thêm mắt, răng, lưỡi, lông mày mẫu từ thư viện MPFB2 để khuôn mặt có đầy đủ thành phần khi mở miệng nói.

### Bước 4: Gắn hệ xương Rigify chuẩn Phim
1. Trong MPFB2 $\rightarrow$ mục **Rigging**: chọn hệ xương hỗ trợ **Rigify** (Metarig).
2. Kiểm tra vị trí các khớp xương (đầu gối, khuỷu tay, cổ tay, xương ngón tay, xương mặt) xem có khớp đúng tâm giải phẫu của nhân vật vừa chỉnh tỷ lệ không.
3. Nhấn **Generate Rig** để tạo bộ điều khiển Rigify hoàn chỉnh (IK/FK tay chân, điều khiển cột sống, đầu, mắt).

### Bước 5: Lưu mốc & Kiểm tra sơ bộ
- Lưu file `<char_name>_v01_base.blend`.
- Chuyển sang `Pose Mode` thử gập tay, gập chân, xoay đầu, mở miệng để chắc chắn nhân vật đã đi theo xương.

---

## Tiêu chí hoàn thành (Checklist)
- [ ] Có đủ ảnh tham chiếu Front + Side khớp tỷ lệ thực tế (`1 unit = 1m`).
- [ ] Khối khuôn mặt và dáng người khớp với concept 2D ở cả 2 góc nhìn.
- [ ] Nhân vật có đủ mắt, răng, lưỡi đi kèm.
- [ ] Rigify hoạt động trơn tru (chuyển được IK/FK, không bị lỗi scale/rotation chưa Apply).
