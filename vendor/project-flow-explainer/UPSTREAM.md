# Project Flow Explainer — ghi chú thư viện bản đồ

Nguồn thư viện tích hợp: [haydenschmitty/floorplan](https://github.com/haydenschmitty/floorplan), phiên bản 0.11.0, commit `94f81b4`. Bản tiếng Việt lấy từ gói tham chiếu người dùng cung cấp. Project Flow Explainer phân phối phần tích hợp theo MIT và giữ giấy phép của phông chữ cùng ELK.

Project Flow Explainer dùng trình xem, bộ quét, bố cục và các mô-đun giao diện của bản gốc. Cầu nối sinh nhóm ban đầu, nhập luồng có căn cứ, ghi thay đổi theo lần dựng và dựng HTML nghiệp vụ từ `flow.json`. Máy chủ mặc định chỉ lắng nghe loopback và hỏi từ dữ liệu bản đồ. Chế độ `--agent` dùng hồ sơ DSH headless đã cấu hình. Bản tích hợp không dùng dịch vụ danh sách chờ của thư viện bên ngoài.
