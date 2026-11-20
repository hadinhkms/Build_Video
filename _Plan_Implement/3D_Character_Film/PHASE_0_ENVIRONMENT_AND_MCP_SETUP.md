# Phase 0: Thiết lập Môi trường & Kết nối Blender MCP

## Mục tiêu
Chuẩn bị đầy đủ phần mềm, add-on và đường truyền AI $\leftrightarrow$ Blender (`mcp-for-blender`) để từ Phase 1 trở đi có thể vừa làm thủ công vừa nhờ AI tự động hóa thao tác trong Blender.

---

## Đầu vào & Đầu ra
- **Đầu vào:** Máy tính có GPU rời (khuyến nghị RTX series để render Cycles nhanh; nếu chạy `Hunyuan3D-2` local cần ~16 GB VRAM, hoặc dùng API/cloud).
- **Đầu ra:**
  1. Blender 4.2+ cài sẵn **MPFB2** và **Rigify** (add-on có sẵn của Blender).
  2. Kết nối **MCP** hoạt động: AI đọc được thông tin scene và tạo/chỉnh được vật thể trong Blender.
  3. Cấu trúc thư mục `3D_Characters/` sẵn sàng.

---

## Các bước thực hiện

### Bước 1: Cài Blender & bật Add-on nền tảng
1. Cài **Blender 4.2 LTS** (hoặc bản 4.3+ mới hơn nếu MPFB2 đã hỗ trợ).
2. Mở Blender $\rightarrow$ `Edit` $\rightarrow$ `Preferences` $\rightarrow$ `Add-ons`:
   - Tìm và bật **Rigging: Rigify** (có sẵn trong Blender).
3. Kiểm tra GPU Render:
   - `Edit` $\rightarrow$ `Preferences` $\rightarrow$ `System` $\rightarrow$ `Cycles Render Devices` $\rightarrow$ chọn **OptiX** (NVIDIA) hoặc **HIP/Metal** tương ứng.

### Bước 2: Cài đặt `makehumancommunity/mpfb2`
1. Tải bản release mới nhất của **MPFB2** (từ GitHub `makehumancommunity/mpfb2` hoặc Blender Extensions platform).
2. Cài đặt vào Blender (`Edit` $\rightarrow$ `Preferences` $\rightarrow$ `Get Extensions` hoặc `Install from Disk` chọn file `.zip`), sau đó bật add-on.
3. Tải thêm các **Asset Packs** đi kèm của MakeHuman/MPFB2 (ít nhất gồm: `skins`, `eyes`, `eyebrows`, `eyelashes`, `teeth`, `clothes` cơ bản) và giải nén/import vào thư mục dữ liệu của MPFB2.
4. Kiểm tra: Nhấn phím `N` ở Viewport $\rightarrow$ thấy tab **MPFB**.

### Bước 3: Cài đặt & Cấu hình `ahujasid/mcp-for-blender`
1. **Cài `uv` (nếu chưa có trên Windows):**
   Mở PowerShell và chạy:
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
2. **Cài Blender Add-on:**
   - Tải file `addon.py` từ repo `ahujasid/mcp-for-blender`.
   - Trong Blender: `Edit` $\rightarrow$ `Preferences` $\rightarrow$ `Add-ons` $\rightarrow$ `Install...` $\rightarrow$ chọn `addon.py` và tích bật **Interface: Blender MCP**.
3. **Cấu hình MCP Server cho AI Client:**
   Thêm block sau vào file cấu hình MCP của client AI bạn đang dùng:
   ```json
   {
     "mcpServers": {
       "blender": {
         "command": "uvx",
         "args": ["blender-mcp"]
       }
     }
   }
   ```
4. **Kết nối & Test:**
   - Trong Blender Viewport, nhấn `N` $\rightarrow$ tab **BlenderMCP** $\rightarrow$ bấm **Connect to MCP server** (mặc định mở socket tại `localhost:9876`).
   - **Bài test kết nối:** Ra lệnh cho AI *"Kiểm tra scene hiện tại trong Blender và tạo 1 đèn Area Light + 1 camera hướng vào gốc tọa độ"*. Nếu thấy xuất hiện trong Blender là đạt.

### Bước 4: (Tùy chọn) Chuẩn bị `Tencent-Hunyuan/Hunyuan3D-2`
- Nếu máy có $\ge$ 16 GB VRAM: cài đặt theo hướng dẫn repo để chạy API server local (phục vụ Phase 2 tạo đạo cụ/phụ kiện).
- Nếu máy dưới 16 GB VRAM: không cần cài nặng máy, có thể dùng bản API/cloud hoặc dựng phụ kiện đơn giản trực tiếp trong Blender.

---

## Tiêu chí hoàn thành (Checklist)
- [ ] Blender Cycles nhận GPU thành công.
- [ ] Tab **MPFB** xuất hiện và tạo thử được 1 nhân vật người mặc định.
- [ ] **Rigify** đã được bật.
- [ ] **BlenderMCP** kết nối thành công và AI thực thi được lệnh `bpy` vào scene.
- [ ] Đã tạo cấu trúc thư mục dự án nhân vật 3D.
