# Phase 2: Lookdev – Da, Mắt, Tóc & Trang phục

## Mục tiêu
Biến nhân vật gốc từ trạng thái “mô hình CGI thô” thành nhân vật đạt chất lượng **quay cận cảnh cho phim 3D** (da có độ thấu quang, mắt có hồn, tóc tự nhiên, trang phục và phụ kiện đồng bộ).

> [!TIP]
> **Điều chỉnh theo phong cách đã chọn ở README:**
> - **Photorealistic (Người thật):** Làm đủ Pore Normal/Roughness map, mạch máu nhẹ ở mắt và tóc sợi **Hair Curves**.
> - **Bán thực tế / Stylized:** Giữ SSS nhẹ và bề mặt da sạch (không cần lỗ chân lông quá dày), có thể dùng tóc **Hair Curves** gom cụm lớn (clump) hoặc **Mesh Hair** để giữ nét gọn và render nhanh hơn.

---

## Đầu vào & Đầu ra
- **Đầu vào:** File `<char_name>_v01_base.blend` từ Phase 1.
- **Đầu ra:** File `<char_name>_v02_lookdev.blend` với đầy đủ shader da/mắt, tóc Hair Curves và trang phục hoàn chỉnh.

---

## Các bước thực hiện

### Bước 1: Nâng cấp Shader Da (Skin Lookdev)
> [!IMPORTANT]
> Da và mắt là 2 yếu tố quyết định nhân vật có giống người thật hay bị giả nhựa khi lên phim.

1. Dùng **Principled BSDF** (Blender 4.2+):
   - Bật **Subsurface Weight** (khoảng `0.05 – 0.15` tùy cường độ ánh sáng, dùng `Random Walk`) để ánh sáng xuyên nhẹ qua tai, cánh mũi, đầu ngón tay.
   - Kết hợp **Roughness Map** (vùng chữ T trên mặt bóng nhẹ hơn vùng má) và **Normal / Bump Map** lỗ chân lông (micro-detail) để da không bị lì như sáp.
2. Kiểm tra dưới ánh sáng HDRI tự nhiên (tuyệt đối không đánh giá da dưới ánh sáng trắng phẳng mặc định).

### Bước 2: Làm lại Vật liệu Mắt
1. Tách riêng **Cornea (giác mạc ngoài)** và **Iris/Sclera (tròng mắt trong)**:
   - Giác mạc ngoài: `Transmission = 1.0`, `Roughness = 0.0 – 0.02`, `IOR = 1.376–1.4` để bắt được đốm sáng phản chiếu (catchlight).
   - Tròng trắng (Sclera): thêm chút mạch máu mờ ở rìa và độ ẩm nhẹ ở viền mí mắt (Tearline/Meniscus).

### Bước 3: Làm Tóc, Lông mày & Lông mi
- **Không dùng tóc khối cứng (mesh hair)** nếu nhân vật có cảnh quay cận.
- Sử dụng hệ thống **Hair Curves** (Geometry Nodes Hair mới trong Blender 4.x):
  - Tạo tóc chính theo từng lớp (tóc nền, tóc mái, tóc con ở gáy/mai).
  - Dùng shader **Principled Hair BSDF** (hoặc Melanin-based) để ánh sáng xuyên qua sợi tóc tự nhiên.
- Gắn tóc vào xương đầu (`Head` bone) bằng Surface Deform hoặc Parent đúng cách để không bị trôi khi nhân vật cúi/ngẩng.

### Bước 4: Trang phục & Đạo cụ (kết hợp `Hunyuan3D-2` nếu cần)
1. **Trang phục chính (quần, áo, áo khoác):**
   - Dùng asset trang phục tương thích MPFB2 hoặc dựng/import trang phục, sau đó dùng **Data Transfer / Transfer Weights** từ thân người sang quần áo để quần áo uốn theo xương.
   - Bổ sung nếp gấp vải (Normal map / Sculpt nhẹ) và vật liệu vải (Sheen Weight trong Principled BSDF).
2. **Đạo cụ & Phụ kiện cứng (kính, đồng hồ, thắt lưng, túi, vũ khí...):**
   - Có thể dùng **`Tencent-Hunyuan/Hunyuan3D-2`** sinh phôi 3D từ ảnh concept 2D $\rightarrow$ import vào Blender $\rightarrow$ dọn lưới (`Decimate` / `Remesh` nhẹ nếu quá nặng), chỉnh kích thước chuẩn và gắn (Parent/Constraint) vào xương tương ứng (tay, hông, đầu).

---

## Tiêu chí hoàn thành (Checklist)
- [ ] Da có độ thấu quang (SSS) ở tai/mũi và chi tiết lỗ chân lông khi soi cận.
- [ ] Mắt có giác mạc phản chiếu ánh sáng tự nhiên (có catchlight).
- [ ] Tóc dùng Hair Curves và đi theo chuyển động đầu chính xác.
- [ ] Trang phục không bị xuyên thủng da (clipping) ở tư thế đứng nghỉ.
- [ ] Đã lưu `<char_name>_v02_lookdev.blend`.
