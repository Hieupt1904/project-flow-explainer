# Lịch sử phiên bản

## 0.9.1

Bản vá cho lệnh và công cụ tra cứu. Cài bằng thẻ `latest` hoặc [gói GitHub](https://github.com/Hieupt1904/project-flow-explainer/releases/tag/v0.9.1).

- Sửa lệnh `/project-flow-explainer`: đọc thư mục phiên qua `ctx.get("workingDirectory")`. Trước đây lệnh đọc `ctx.workingDirectory` trong scope chỉ khai báo `commands`, nên Cordis ném lỗi và lệnh rơi về `process.cwd()` của tiến trình web, rồi từ chối chính repository đang mở.
- Khi phải dùng `process.cwd()`, thông báo lỗi ghi rõ nguồn đường dẫn thay vì chỉ báo `repository_outside_allowed_roots`.
- Sửa `project_code_search`: bỏ trường `flow_filter` khi không có bộ lọc thay vì trả `null`. Hợp đồng khai báo trường này kiểu object nên runtime từ chối mọi lần tìm không lọc.
- Thêm kiểm thử hồi quy cho scope lệnh Cordis và cho hợp đồng đầu ra của công cụ tra cứu.

## 0.9.0

Bản ổn định của `0.9.0-rc.2`. Cài bằng thẻ npm `latest` hoặc [tải gói từ GitHub](https://github.com/Hieupt1904/project-flow-explainer/releases/tag/v0.9.0). Bản này giữ bản đồ toàn kho, bảng căn cứ và bộ chọn mô hình DSH của bản thử nghiệm.

[![](https://img.shields.io/badge/powered_by-dsh-4D6BFE?style=flat-square&logo=deepseek&logoColor=white)](https://github.com/deepseek-ai/deepseek-harness)

## 0.9.0-rc.2

**BẢN THỬ NGHIỆM** — Phiên bản này không thay thẻ ổn định `latest` trên npm.

- Dựng bản đồ toàn kho với phân hệ, tệp, đường dẫn web, luồng và căn cứ. Bản đồ và bản chia sẻ mở được ngoại tuyến.
- Dùng trình xem Project Flow Explainer cho `flow.html`. Giao diện Python dự phòng vẫn dùng được khi máy dựng thiếu Node.js.
- Thêm `--map`, `--refresh-map` và `--blueprint` cho lệnh `/project-flow-explainer`. Bản phác lấy đầu vào từ `plan.json` và không tạo mã ứng dụng.
- Thanh **Hỏi** mặc định tra cứu dữ liệu bản đồ tại máy. Khi bật `--agent`, chọn mô hình và nhà cung cấp từ danh sách cấu hình DSH.
- Hiển thị lỗi `MISSING_CREDENTIAL` rõ hơn và cho phép quay về tra cứu tại máy. DSH tự lấy thông tin xác thực đã lưu.
- Dùng thư mục đầu ra `project-flow-explainer/`. Khi thư mục mới chưa tồn tại, lệnh dựng nhận diện và chuyển bản đồ cũ đủ điều kiện, giữ các tệp người dùng đã chỉnh.

**Nâng cấp:** Cài đúng phiên bản theo [README plugin](dsh-plugin/README.md). Dựng lại bản đồ hoặc HTML để nhận giao diện mới; các tệp HTML đã xuất trước đó giữ nguyên.

**Xác minh:** Việc chọn và chuyển đúng tuyến mô hình được kiểm thử với tiến trình DSH giả lập. Kiểm tra đọc danh sách thật từ hồ sơ `web` không đồng nghĩa với kiểm tra phản hồi của mọi nhà cung cấp.

[![](https://img.shields.io/badge/powered_by-dsh-4D6BFE?style=flat-square&logo=deepseek&logoColor=white)](https://github.com/deepseek-ai/deepseek-harness)
