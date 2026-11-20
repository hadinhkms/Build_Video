# Phase 4: Tự động hóa Lookdev Studio, Turntable & Đóng gói Asset Phim

## Mục tiêu
Dùng **`ahujasid/mcp-for-blender`** tự động hóa khâu kiểm duyệt hình ảnh cuối cùng (ánh sáng điện ảnh, render Turntable 360° & cận cảnh) và đóng gói nhân vật thành Asset chuẩn để chỉ cần **Link/Append** vào bất kỳ cảnh phim nào.

---

## Đầu vào & Đầu ra
- **Đầu vào:** File `<char_name>_v03_rigged.blend` từ Phase 3.
- **Đầu ra:**
  1. Video render Turntable 360° (full body + close-up mặt) để duyệt chất lượng.
  2. File `<char_name>_FINAL.blend` đã dọn sạch rác và đánh dấu sẵn trong **Blender Asset Browser**.

---

## Các bước thực hiện

### Bước 1: Dùng `mcp-for-blender` dựng Studio Lookdev tự động
Yêu cầu AI qua MCP thực hiện các thao tác dựng scene test chuẩn trong 1 Collection riêng (`_Lookdev_Studio`):
1. Tạo nền phông vô cực (Backdrop Cyclorama) màu trung tính (`#808080` hoặc xám đậm điện ảnh).
2. Thiết lập **3-Point Lighting** chuẩn phim:
   - **Key Light:** Area Light lớn, đặt chếch 45° tạo khối khuôn mặt.
   - **Fill Light:** Ánh sáng mềm cường độ thấp hơn ở phía đối diện.
   - **Rim / Back Light:** Đèn viền tách tóc và vai khỏi nền.
3. Gắn thêm HDRI nhẹ để kiểm tra phản chiếu mắt và da.

### Bước 2: Render Turntable 360° & Cận cảnh bằng Script (`bpy`)
Nhờ AI qua MCP viết/chạy script tự động:
1. Đặt 1 camera xoay 360° quanh nhân vật trong 120–180 frames (toàn thân).
2. Đặt 1 camera cận cảnh khuôn mặt (tiêu cự `85mm`, `F-stop = 2.8` để giống ống kính chân dung điện ảnh) render 3 góc: chính diện, 3/4, nghiêng.
3. Xuất ra thư mục `renders/` để bạn soi kỹ lỗi da, tóc, đường may áo, độ bóng mắt dưới ánh sáng thực tế.

### Bước 3: Dọn dẹp & Đóng gói Asset (`_FINAL.blend`)
1. Xóa toàn bộ Collection `_Lookdev_Studio` và ảnh tham chiếu `_references` khỏi file nhân vật gốc (hoặc tách thành 2 file riêng) để file nhân vật nhẹ nhất khi đưa vào cảnh phim.
2. Đặt tên chuẩn toàn bộ Collection, Mesh, Material, Rig (ví dụ: `CH_<Name>_Rig`, `CH_<Name>_Body`, `CH_<Name>_Cloth`).
3. Chạy `File` $\rightarrow$ `Clean Up` $\rightarrow$ `Purge Unused Data` để xóa vật liệu/mesh thừa.
4. Gom toàn bộ nhân vật (Mesh + Rig) vào 1 Collection chính `CH_<Name>`, chuột phải chọn **Mark as Asset**.
5. Lưu `<char_name>_FINAL.blend`.

### Bước 4: Kiểm tra tái sử dụng (Link Test)
- Mở một file Blender mới tinh (giả lập cảnh phim đầu tiên), kéo nhân vật từ **Asset Browser** vào (chế độ `Link` + `Make Library Override`) và kiểm tra xem có điều khiển được xương Rigify ngay lập tức không.

---

## Tiêu chí hoàn thành (Checklist)
- [ ] Đã có video Turntable 360° và ảnh cận cảnh `85mm` đạt chuẩn nhìn điện ảnh.
- [ ] File `<char_name>_FINAL.blend` sạch, không chứa đèn/camera/rác thừa.
- [ ] Đã đánh dấu **Asset** và test **Link + Library Override** sang file cảnh phim mới thành công.
- [ ] Sẵn sàng chuyển sang giai đoạn dựng cảnh và làm phim 3D.
