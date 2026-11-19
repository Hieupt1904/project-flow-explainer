# Luồng: Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file

Sinh tự động: 2026-11-19T17:22:01+07:00 · `scripts/build_flow.py` (schema 2).

## Yêu cầu

> Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file

## Repository được phân tích

| Mục | Giá trị |
|---|---|
| Tên | `shop-app` |
| Nhánh | `không có git` |
| Commit | `không có git` |
| Thay đổi chưa commit | không |

Đường dẫn tuyệt đối không được ghi vào artifact để tránh lộ cấu trúc máy cá nhân.

## Luồng xử lý

Sơ đồ dựng từ phân tích tĩnh theo yêu cầu: Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file. Mỗi bước trỏ tới file và dòng thật; bước chỉ khớp từ khoá được tách riêng thay vì nối vào luồng.

| # | Bước | Loại | Vị trí | Bằng chứng thành viên | Tin cậy |
|---|---|---|---|---|---|
| 1 | Bắt đầu từ yêu cầu | start | — | — | partial |
| 2 | Nhận yêu cầu /api/reports/export | action | `server.js`:16 | entry | verified |
| 3 | Xử lý tại exportReport | action | `services/report_service.js`:5 | import | verified |
| 4 | Có lỗi trong bước này? | decision | `server.js`:8 | import | partial |
| 5 | Trả lỗi cho người gọi | error | `server.js`:8 | structure | partial |
| 6 | Xử lý tại loadReportRows | action | `db/report_repo.js`:4 | import | verified |
| 7 | Bước trong db/connection.js | action | `db/connection.js`:1 | import | verified |
| 8 | Trả kết quả | end | `server.js`:18 | call | verified |

## Quan hệ giữa các bước

| Cạnh | Nhãn | Loại | Bằng chứng | Ghi chú |
|---|---|---|---|---|
| start → step-1 | `bắt đầu xử lý` | success | entry | route khai báo tại server.js:16 |
| step-1 → step-2 | `gọi tiếp` | normal | import | `server.js` import `services/report_service.js` |
| step-1 → decision-server-js | `vào bước xử lý` | normal | import | cùng bước `server.js` |
| decision-server-js → step-2 | `không lỗi` | success | structure | đường đi tiếp khi không lỗi |
| decision-server-js → error-server-js | `có lỗi` | error | structure | khối xử lý ngoại lệ trong file |
| step-2 → step-3 | `gọi tiếp` | normal | import | `services/report_service.js` import `db/report_repo.js` |
| step-3 → step-4 | `gọi tiếp` | normal | import | `db/report_repo.js` import `db/connection.js` |
| step-4 → end | `hoàn tất` | success | call | bước cuối của luồng |

## File khớp từ khoá nhưng KHÔNG thuộc luồng

- `jobs/export_worker.py` — khớp từ khoá nhưng không nối được tới điểm vào bằng import/gọi hàm
- `routes/preview.js` — khớp từ khoá nhưng không nối được tới điểm vào bằng import/gọi hàm

## Giới hạn và phần chưa xác minh

- Phân tích tĩnh trên source; hành vi runtime và dữ liệu thật chưa được kiểm chứng.
- Chỉ đọc source trong repository; file bí mật, dump, log và thư mục phụ thuộc bị loại.
- Thư mục test/fixture/example/sample/demo bị bỏ qua.
- Chưa có call graph đầy đủ: quan hệ bước dựa trên route, import và lời gọi theo tên.

- Không có cảnh báo.

## Phạm vi đọc và loại trừ

Chỉ đọc file source trong repository. Các mục sau bị loại:

- sensitive_name: 1

Không gọi network, không chạy code của repository, không sửa file nguồn, không chép nội dung source.

## Tệp sinh ra

- `flow.json` — dữ liệu có cấu trúc, dùng lại được cho lần render sau
- `flow.html` — sơ đồ mở offline
- `overview.md` — tài liệu này
