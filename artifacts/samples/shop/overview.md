# Luồng: Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file

Sinh tự động: 2026-11-19T23:43:33+07:00 · `scripts/build_flow.py` (schema 2).

## Yêu cầu

> Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file

## Repository được phân tích

| Mục | Giá trị |
|---|---|
| Tên | `shop-app` |
| Nhánh | `không có git` |
| Commit | `không có git` |
| Thay đổi chưa commit | không |
| File đã đọc | 6 |
| Byte source đã đọc | 2748 |
| Số ngân sách bị cắt | không |

Đường dẫn tuyệt đối không được ghi vào artifact để tránh lộ cấu trúc máy cá nhân.

## Luồng xử lý

Sơ đồ dựng từ phân tích tĩnh theo yêu cầu: Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file. Mỗi bước trỏ tới file và dòng thật; bước chỉ khớp từ khoá được tách riêng thay vì nối vào luồng.

| # | Bước | Loại | Vị trí | Bằng chứng thành viên | Tin cậy |
|---|---|---|---|---|---|
| 1 | Bắt đầu từ yêu cầu | start | — | — | partial |
| 2 | Nhận yêu cầu /api/reports/export | action | `server.js`:16 | entry | verified |
| 3 | Xử lý tại exportReport | action | `services/report_service.js`:5 | import | verified |
| 4 | Xử lý tại loadReportRows | action | `db/report_repo.js`:4 | import | verified |
| 5 | Module connection | action | `db/connection.js`:1 | import | verified |
| 6 | Trả kết quả | end | `server.js`:18 | import | verified |

## Quan hệ giữa các bước

| Cạnh | Nhãn | Loại | Bằng chứng | Ghi chú |
|---|---|---|---|---|
| start → step-1 | bắt đầu xử lý | success | entry | route khai báo tại server.js:16 |
| step-1 → step-2 | dùng module | success | import | server.js import services/report_service.js · dòng import 3 |
| step-2 → step-3 | dùng module | success | import | services/report_service.js import db/report_repo.js · dòng import 3 |
| step-3 → step-4 | dùng module | success | import | db/report_repo.js import db/connection.js · dòng import 2 |
| step-4 → end | hoàn tất | success | import | bước cuối của luồng |

## Mô hình bằng chứng

- `verified` = vị trí có thật (file + dòng) và có bằng chứng thành viên (route/import); xác minh tĩnh, KHÔNG phải chạy runtime
- `partial`  = vị trí có thật nhưng vai trò trong luồng chỉ suy ra từ cấu trúc
- `inferred` = suy luận từ ngữ cảnh, chưa có bằng chứng trực tiếp
- Có cạnh `call` trong sơ đồ: không
- Có bằng chứng runtime: không

## File khớp từ khoá nhưng KHÔNG thuộc luồng

- jobs/export_worker.py — khớp từ khoá nhưng không nối được tới điểm vào bằng import/gọi hàm
- routes/preview.js — khớp từ khoá nhưng không nối được tới điểm vào bằng import/gọi hàm

## Giới hạn và phần chưa xác minh

- Chưa có call graph runtime: cạnh chỉ mang bằng chứng entry/import/structure; không có cạnh nào tự nhận là call.

- Không có cảnh báo.

## Phạm vi đọc và loại trừ

Chỉ đọc file source trong repository. Các mục sau bị loại:

- sensitive_name: 1
- test_dir: 1

Không gọi network, không chạy code của repository, không sửa file nguồn, không chép nội dung source.

## Tệp sinh ra

- `flow.json` — dữ liệu có cấu trúc, dùng lại được cho lần render sau (public)
- `flow.html` — sơ đồ mở offline (public)
- `overview.md` — tài liệu này (public)
- `run.json` — internal provenance, KHÔNG phải public output: chứa số đếm, giới hạn và trạng thái git của lần chạy
