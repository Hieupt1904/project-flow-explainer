# Project Flow Explainer

Bộ skill tích hợp 4 module: đọc repository → truy vết flow → viết dễ hiểu → dựng HTML. Các file trong `references/` đóng vai trò prompt/tài liệu module; `scripts/render_flow.py` là renderer offline dùng chung.

## Dành cho người dùng

1. Đưa thư mục project hoặc source code vào môi trường nơi agent có quyền đọc. Nếu là GitHub URL, chỉ sử dụng khi agent có khả năng truy cập repository hợp lệ.
2. Cung cấp lệnh cho agent: `Phân tích quy trình đăng ký bảo hành từ frontend đến backend trong project này. Xuất HTML dễ hiểu, kèm source file/line.`
3. Agent đọc code và sinh `flow.json`, sau đó chạy script renderer để nhận `flow.html`.
4. Mở file HTML bằng trình duyệt, kéo sơ đồ, phóng to, tìm tên bước hoặc nhấn vào card để kiểm tra chi tiết.

### Độc lập với hệ thống skill

Nếu chỉ muốn dùng **system prompt**, sao chép nội dung từ `references/SYSTEM_PROMPT.md` vào System / Instructions của agent. Cần cấp quyền đọc file project và khả năng ghi HTML/JSON. Trong prompt, điều chỉnh đường dẫn `scripts/render_flow.py` cho phù hợp vị trí đặt skill.

### Render thủ công

```bash
python scripts/render_flow.py assets/example_workflow.json --out flow.html
python scripts/render_flow.py own_flow.json --out own_flow.html
python scripts/render_flow.py own_flow.json --check-only
```

**Demo**: `assets/example_workflow.json` minh họa sơ đồ chatbot, không được coi là kết quả phân tích project thực.

## Đầu ra agent nên giao

- `flow.html`: sơ đồ HTML mở offline, không cần server/CDN.
- `flow.json`: dữ liệu có thể sửa hoặc render lại.
- `overview.md`: giải thích phạm vi, assumptions, các phần chưa xác minh.

Mọi phần `verified` cần trích file và dòng thực, `partial/inferred/unknown` được hiển thị minh bạch trên panel. Không đọc/đưa secrets vào sơ đồ. Với hệ thống nhiều chức năng, tạo mỗi workflow một HTML thay vì nhồi mọi bước vào một canvas.
