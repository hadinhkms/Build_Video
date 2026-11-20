# Phase 3: Kiểm tra Rigging, Sửa Weight & Diễn hoạt Khuôn mặt

## Mục tiêu
Đảm bảo nhân vật không bị gãy lưới, lòi da xuyên áo hay biến dạng kỳ dị khi diễn hoạt các tư thế mạnh, đồng thời sẵn sàng bộ điều khiển biểu cảm và nhép miệng (Lip-sync) cho phim 3D.

---

## Đầu vào & Đầu ra
- **Đầu vào:** File `<char_name>_v02_lookdev.blend` từ Phase 2.
- **Đầu ra:** File `<char_name>_v03_rigged.blend` đã vượt qua bài test bẻ khớp cực đoan và có clip test biểu cảm mặt.

---

## Các bước thực hiện

### Bước 1: Tạo bài test "Bẻ khớp cực đoan" (Calisthenics / Range of Motion Test)
- Dùng `mcp-for-blender` (hoặc tạo keyframes thủ công) dựng một chuỗi animation ngắn ~120 frames test toàn bộ khớp:
  - Tay giơ cao quá đầu, gập khuỷu tay tối đa, nắm/xòe bàn tay.
  - Ngồi xổm (squat), vặn hông, cúi gập người, xoay cổ trái/phải.
- Chạy qua từng frame để soi lỗi.

### Bước 2: Sửa lỗi Weight Painting & Clipping
1. **Lỗi biến dạng khớp (vai, hông, đầu gối):**
   - Bật `Preserve Volume` trong Armature Modifier.
   - Chỉnh lại **Weight Paint** ở vùng nách, vai, háng để chuyển tiếp mượt mà.
2. **Lỗi da xuyên qua quần áo (Mesh Interpenetration):**
   - Dùng **Mask Modifier** ẩn phần mesh da nằm bên dưới lớp quần áo dày (tiết kiệm tính toán và triệt tiêu hoàn toàn lỗi lòi da khi nhân vật chạy/ngồi).
   - Tinh chỉnh weight của quần áo khớp với da ở các vùng hở (cổ áo, cổ tay).

### Bước 3: Thiết lập & Kiểm tra Biểu cảm Khuôn mặt (Facial Acting)
1. Kiểm tra các nhóm điều khiển mặt của Rigify (mí mắt chớp, lông mày nhíu/nhướng, khóe miệng cười/buồn, hàm mở).
2. Bổ sung **Corrective Shape Keys** (nếu cần) cho các tư thế hay lỗi như: nhắm mắt hoàn toàn không bị hở mí, cười lớn không bị gãy má.
3. Tạo bộ **Pose Library (Asset Browser)** cho các biểu cảm/khẩu hình cơ bản:
   - Cảm xúc: `Neutral`, `Happy`, `Sad`, `Angry`, `Surprised`, `Thinking`.
   - Khẩu hình cơ bản (Visemes) để phục vụ thoại/lip-sync nhanh sau này (`A`, `E`, `I`, `O`, `U`, `M/B/P`).

### Bước 4: Test diễn xuất 5 giây
- Thử diễn một đoạn 3–5 giây: nhân vật quay đầu nhìn camera, chớp mắt, thở nhẹ và nói một câu ngắn hoặc đổi từ trạng thái bình thường sang mỉm cười/cau mày.

---

## Tiêu chí hoàn thành (Checklist)
- [ ] Không còn lỗi lòi da xuyên áo ở mọi tư thế ngồi, cúi, giơ tay.
- [ ] Khớp vai, hông, cổ tay gập mượt, không bị bẹp khối.
- [ ] Đã có Pose Library các biểu cảm cơ bản và khẩu hình miệng.
- [ ] Test thành công đoạn diễn xuất 3–5 giây không lỗi.
- [ ] Đã lưu `<char_name>_v03_rigged.blend`.
