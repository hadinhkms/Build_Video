# Kế hoạch Xây dựng Nhân vật 3D Phục vụ Làm Phim 3D

Bộ tài liệu này chia quy trình xây dựng **nhân vật 3D hoàn chỉnh** (ưu tiên độ chân thật, lưới sạch để diễn hoạt và biểu cảm điện ảnh) thành các Phase độc lập, có thể làm tuần tự và kiểm chứng sau mỗi bước.

## 1. Bộ công cụ cốt lõi

| Thành phần | Công cụ / Repo | Vai trò trong Pipeline |
| :--- | :--- | :--- |
| **Nền tảng 3D chính** | Blender 4.2+ (LTS) | Dựng hình, shader, rig, diễn hoạt và render (Cycles/EEVEE Next) |
| **Tạo nhân vật gốc** | `makehumancommunity/mpfb2` | Tạo cơ thể, khuôn mặt, tỷ lệ, UV và rig chuẩn giải phẫu |
| **Tự động hóa AI $\leftrightarrow$ Blender** | `ahujasid/mcp-for-blender` | Điều khiển Blender bằng AI qua MCP: dựng đèn, camera, chạy script `bpy`, batch render |
| **Phôi đạo cụ / phụ kiện từ ảnh** | `Tencent-Hunyuan/Hunyuan3D-2` | Tạo nhanh phôi 3D đạo cụ, trang sức, mũ nón từ ảnh concept 2D *(tùy chọn theo phần cứng)* |

> [!NOTE]
> **Nguyên tắc quan trọng:** Không dùng mesh AI (Hunyuan3D-2) làm thân/mặt nhân vật chính để diễn hoạt vì lưới không đạt chuẩn topology cho biểu cảm và bẻ khớp. Nhân vật chính luôn đi từ **MPFB2 + Rigify**, còn AI 3D chỉ hỗ trợ phần đạo cụ/phụ kiện cứng hoặc phôi trang phục.

---

## 1.5. Chọn hướng phong cách nhân vật (Style Branch)

Trước khi bắt đầu Phase 1 & Phase 2, cần chốt nhân vật theo 1 trong 2 hướng sau:

| Tiêu chí | Hướng A: Người thật (Photorealistic) | Hướng B: Bán thực tế / Stylized (3D Film) |
| :--- | :--- | :--- |
| **Hình khối (Phase 1)** | Tỷ lệ giải phẫu người thật chuẩn (đầu ~1/7.5–1/8 thân) | Tỷ lệ cách điệu nhẹ (mắt to hơn, đường nét mặt gọn, sắc nét) |
| **Da & Mắt (Phase 2)** | Bắt buộc SSS + Pore Normal/Roughness map + giác mạc khúc xạ | SSS nhẹ, bề mặt da sạch/mịn hoặc vẽ tay (hand-painted/procedural), mắt ít mạch máu |
| **Tóc (Phase 2)** | **Hair Curves** (sợi tóc thật + Principled Hair BSDF) | **Hair Curves** bản to (clumped) hoặc **Mesh Hair** khối gọn dễ kiểm soát |
| **Thời gian & Phần cứng** | Tốn công lookdev + nặng GPU khi render Cycles | Nhanh hơn, dễ đồng nhất phong cách toàn phim, render nhẹ hơn |

---

## 2. Lộ trình các Phase

| Phase | Tài liệu | Mục tiêu chính | Đầu ra (Deliverable) |
| :--- | :--- | :--- | :--- |
| **Phase 0** | [PHASE_0_ENVIRONMENT_AND_MCP_SETUP.md](./PHASE_0_ENVIRONMENT_AND_MCP_SETUP.md) | Cài đặt Blender, MPFB2, `mcp-for-blender` và chuẩn hóa thư mục asset | Môi trường hoạt động, AI điều khiển được Blender qua MCP |
| **Phase 1** | [PHASE_1_CONCEPT_AND_BASE_CHARACTER_MPFB2.md](./PHASE_1_CONCEPT_AND_BASE_CHARACTER_MPFB2.md) | Chốt concept 2D (Front/Side) & dựng base body/face + Rigify | File `.blend` nhân vật gốc có xương + test pose cơ bản |
| **Phase 2** | [PHASE_2_LOOKDEV_SKIN_EYES_HAIR_AND_COSTUME.md](./PHASE_2_LOOKDEV_SKIN_EYES_HAIR_AND_COSTUME.md) | Nâng cấp shader da (SSS), mắt, tóc Hair Curves & trang phục/đạo cụ | Nhân vật có ngoại hình đạt chuẩn render phim cận cảnh |
| **Phase 3** | [PHASE_3_RIGGING_WEIGHTS_AND_FACIAL_ACTING.md](./PHASE_3_RIGGING_WEIGHTS_AND_FACIAL_ACTING.md) | Kiểm tra bẻ khớp, sửa Weight Paint, cài biểu cảm mặt & Lip-sync | Nhân vật diễn được các tư thế cực đoan & biểu cảm thoại |
| **Phase 4** | [PHASE_4_LIGHTING_TURNAROUND_AND_ASSET_PACKAGING.md](./PHASE_4_LIGHTING_TURNAROUND_AND_ASSET_PACKAGING.md) | Tự động hóa Lookdev studio, render Turntable 360° & đóng gói Asset | Video Turntable nghiệm thu + file `.blend` sẵn sàng vào phim |

---

## 3. Quy ước thư mục dự án nhân vật 3D (khuyến nghị)

```text
3D_Characters/
├── _references/          # Ảnh concept Front, Side, 3/4, moodboard ánh sáng
├── _hdri/                # File .exr / .hdr môi trường để test ánh sáng
├── assets_props/         # Đạo cụ, phụ kiện tạo từ Hunyuan3D-2 hoặc dựng tay
├── characters/
│   └── <char_name>/
│       ├── textures/     # Texture da, vải, mắt, normal/roughness maps
│       ├── <char_name>_v01_base.blend
│       ├── <char_name>_v02_lookdev.blend
│       ├── <char_name>_v03_rigged.blend
│       └── <char_name>_FINAL.blend   # Bản sạch đánh dấu Asset Library
└── renders/              # Ảnh test lookdev và video turntable 360°
```
