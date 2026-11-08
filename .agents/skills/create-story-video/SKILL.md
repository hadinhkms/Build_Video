---
name: create-story-video
description: Tự động biến văn bản chương truyện (.txt) thành video điện ảnh 2.5D YouTube hoàn chỉnh (âm thanh chuẩn hoá, foley, raccord, phụ đề, mastering -14 LUFS, gói YouTube). Kích hoạt khi người dùng gõ /create-story-video, "tạo video từ truyện", "làm video chương...", "dựng phim từ truyện".
---

# HƯỚNG DẪN KỸ NĂNG: TẠO VIDEO ĐIỆN ẢNH TỪ TRUYỆN (/create-story-video)

Kỹ năng này điều phối toàn bộ quy trình CineStory biến văn bản chương truyện thô thành video điện ảnh 2.5D chất lượng cao sẵn sàng đăng tải lên YouTube.

---

## 1. QUY TRÌNH THỰC THI (WORKFLOW 2 LƯỢT)

### Lượt 1: Chuẩn bị & Phân tích (Stage `prepare`)
1. **Đọc văn bản gốc** tại `input/<tên_chương>.txt`.
2. **Gắn nhãn chỉ dẫn kịch bản (Annotation)**:
   - Thêm thẻ hồi kịch bản: `[HOOK]`, `[SETUP]`, `[RISING]`, `[CLIMAX]`, `[CLIFFHANGER]`.
   - Gắn nhãn nhân vật nói và nhân vật trên hình: `[Tên nhân vật]: ...` hoặc `[ON: tên_nhân_vật]`.
   - Gắn bối cảnh: `[ENV: id_bối_cảnh]`.
   - Gắn từ khóa cảm xúc: `[EMO: từ_khóa_1, từ_khóa_2]`.
   - Lưu ra tệp: `input/<tên_chương>.annotated.txt` (không sửa tệp gốc).
3. **Chạy stage prepare**:
   ```powershell
   python run_pipeline.py --renderer remotion --stage prepare --input input/<tên_chương>.annotated.txt
   ```
4. **Kiểm tra và dừng lại hỏi người dùng**:
   - Mở và hiển thị bảng kiểm tài sản (Checklist) ảnh bối cảnh và nhân vật còn thiếu.
   - Chỉ dẫn người dùng đến thư mục gói prompt miễn phí 0đ tại `packages/<chapter_id>/`.
   - Hỏi người dùng:
     > *"Bạn muốn dừng lại để tạo ảnh chân dung và bối cảnh (0đ) theo gói prompt, hay muốn tôi tiếp tục render ngay với ảnh dự phòng?"*

---

### Lượt 2: Sản xuất & Hoàn thiện (Stage `render`)
5. **Chạy stage render**:
   Khi người dùng đã tạo ảnh xong (hoặc chọn render với ảnh dự phòng):
   ```powershell
   python run_pipeline.py --renderer remotion --stage render --input input/<tên_chương>.annotated.txt
   ```
   Pipeline sẽ:
   - Tự động tách nền các ảnh nhân vật mới bằng `rembg` thành `base_cutout.png`.
   - Dựng phân cảnh 2.5D Parallax trong Remotion.
   - Render video trung gian chất lượng cao (H.264 + PCM 16-bit).
   - Đo và cân bằng âm lượng (Mastering 2-pass EBU R128: -14 LUFS, True Peak <= -1.5 dBTP).
   - Xuất phụ đề rời `video.srt`.
   - Xuất siêu dữ liệu YouTube `youtube_metadata.json` (kèm timestamps theo hồi kịch bản).
   - Xuất ảnh nền thumbnail chuẩn 1280x720 `thumbnail_base.png`.

6. **Báo cáo kết quả**:
   - Đường dẫn video hoàn thiện: `output/<chapter_id>/final_chapter_video.mp4`.
   - Thông số âm lượng thực tế (Integrated LUFS, True Peak, LRA).
   - Danh sách mốc thời gian (Chapters) và thẻ Tags gợi ý.

---

## 2. BẢNG XỬ LÝ LỖI THƯỜNG GẶP (TROUBLESHOOTING)

| Lỗi gặp phải | Nguyên nhân | Cách khắc phục |
| :--- | :--- | :--- |
| **Edge-TTS lỗi kết nối** | Mạng chập chờn hoặc timeout WebSocket | Chạy lại lệnh; các audio đã sinh thành công đều có cache sha1 nên không bị mất. |
| **Thiếu thư viện Node** | Thư mục `remotion/node_modules` chưa được cài đặt | Chạy `cd remotion; npm install` trong terminal. |
| **Thiếu ffmpeg / ffprobe** | Máy chưa cài đặt hoặc chưa thêm vào PATH | Tải ffmpeg và thêm vào biến môi trường hệ thống PATH. |
| **Chưa có ảnh bối cảnh/nhân vật** | Người dùng chưa kịp tạo ảnh | Pipeline tự động fallback sang ảnh nền mặc định mà không làm gãy luồng render. |
| **Render hết RAM** | Concurrency quá cao trên máy yếu | Sửa `"concurrency"` trong `config/settings.json` thành 4 hoặc 8. |

---

## 3. LỆNH XÁC MINH NHANH

```powershell
python -m unittest discover -s tests
cd remotion; npm test
```
