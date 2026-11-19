# Module 01 — Repository Reader

## Thu thập có trọng tâm

1. Nhận đầu vào từ workspace local, thư mục upload, archive đã được mở an toàn hoặc repository URL có quyền truy cập. Mặc định dùng filesystem hiện tại. Chỉ dùng GitHub hoặc kết nối ngoài khi người dùng/công cụ cho phép.
2. Ưu tiên `README`, `docs`, `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, các entry point, router, controllers, background workers, schema DB.
3. Tìm theo luồng: từ nút UI/điểm kích hoạt, truy tới handler, API endpoint, middleware, service, repository, model, event/queue, response. Đọc file nhỏ có liên quan rồi mở rộng theo import/call graph.
4. Monorepo: xác định app/service sở hữu hành vi, tạo context map giữa các package. Không mặc định một repo = một luồng.
5. Loại trừ `node_modules`, `.git`, `dist`, `build`, `.next`, `vendor`, generated assets, binary và log trừ khi chúng chính là phạm vi cần xem.

## Ghi chú phân tích

Tạo danh sách `module | responsibility | entrypoints | files | relationships` và các câu hỏi chưa chắc. Ưu tiên `rg -n "<symbol>"` và hiển thị số dòng thật (hoặc công cụ tương đương). Không bịa số dòng. Nếu code chứa secret, không sao chép vào ghi chú hoặc HTML.

## Bất đồng giữa nguồn

Code runtime quan sát được đáng tin hơn README/cũ; test có thể mô tả dự kiến chứ chưa phản ánh production; config phụ thuộc env/feature flag phải được nêu là điều kiện. Với các module chưa đọc, ghi "chưa xác minh".
