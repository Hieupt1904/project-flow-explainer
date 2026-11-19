# Module 03 — Viết cho người đọc không rành code

## Khung diễn giải

Mỗi node trả lời theo thứ tự: **Tên dễ hiểu → chuyện gì xảy ra → tại sao/cần điều kiện gì → kết quả tiếp theo**. Trong card chính chỉ hiện title + summary; chi tiết khác mở theo click.

Ví dụ:

| Mã nguồn gốc | Node dành cho người đọc |
| --- | --- |
| `onSubmit -> POST /api/warranty` | **Gửi thông tin kích hoạt** · Hệ thống nhận số điện thoại và thông tin sản phẩm để đăng ký bảo hành. |
| `if (!isValidSerial)` | **Kiểm tra mã sản phẩm** · Nếu mã không hợp lệ, yêu cầu nhập lại. |
| `queue.add("activate", payload)` | **Đưa yêu cầu vào hàng chờ** · Hệ thống tiếp nhận yêu cầu và xử lý ở bước nền, chưa phải kích hoạt thành công. |

Tránh "Call handleRegister rồi invoke warrantyService" ở phần nhìn chính. Tránh thuật ngữ kỹ thuật nếu không giải thích. Viết một chủ thể/hành động chính trên mỗi card; tối đa 140 ký tự cho phần summary.

## Màu theo chức năng

- `start`: xanh lá nhạt; điểm khởi động
- `message`: tím nhạt; nội dung gửi/hiển thị
- `action`: xanh dương nhạt; xử lý hoặc thao tác
- `decision`: vàng nhạt; rẽ nhánh
- `data`: lam-xanh nhạt; cập nhật/đọc dữ liệu
- `end`: xanh lục; hoàn thành
- `error`: đỏ nhạt; từ chối/lỗi/không đạt
- `external`: xám-vàng; hệ thống ngoài

Màu chỉ bổ sung, luôn có nhãn loại node cho người mù màu.
