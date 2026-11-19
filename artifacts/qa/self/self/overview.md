# Luồng: phân tích repository và sinh sơ đồ HTML

Sinh tự động: 2026-11-19T16:43:13+07:00 · công cụ: `scripts/build_flow.py` (schema 1).

## Yêu cầu

> luồng phân tích repository và sinh sơ đồ HTML

## Repository được phân tích

| Mục | Giá trị |
|---|---|
| Đường dẫn | `/home/hieupt/Documents/Agent-skills-main/project-flow-explainer` |
| Nhánh | `main` |
| Commit | `7ab202a86c09` |
| Thay đổi chưa commit | có — 7 file |
| File đã đọc | 5 |

## Luồng xử lý

Sơ đồ dựng từ phân tích tĩnh repository project-flow-explainer, theo yêu cầu: luồng phân tích repository và sinh sơ đồ HTML. Mọi bước đều trỏ tới file và dòng thật; phần chưa chứng minh được đánh dấu tin cậy thấp.

| # | Bước | Loại | Tin cậy | Bằng chứng |
|---|---|---|---|---|
| 1 | Bắt đầu từ yêu cầu | start | partial | — |
| 2 | Bắt đầu tại run | action | verified | `scripts/build_flow.py`:220 |
| 3 | Xử lý tại apply | action | verified | `dsh-plugin/index.js`:79 |
| 4 | Có lỗi trong bước này? | decision | verified | `dsh-plugin/index.js`:66 |
| 5 | Trả lỗi cho người gọi | error | partial | `dsh-plugin/index.js`:66 |
| 6 | Xử lý tại main | action | verified | `scripts/render_flow.py`:201 |
| 7 | Kết thúc xử lý | end | inferred | — |

## Quan hệ giữa các bước

- start → step-1 · `bắt đầu xử lý` · success
- step-1 → decision-error · `vào bước xử lý` · normal
- decision-error → error-branch · `có lỗi` · error
- decision-error → step-2 · `không lỗi` · success
- step-2 → step-3 · `tiếp tục` · normal
- step-3 → end · `hoàn tất` · success

## Thành phần chính

- `entry=request` — Bắt đầu từ yêu cầu
- `scripts/build_flow.py` — Bắt đầu tại run
- `dsh-plugin/index.js` — Xử lý tại apply
- `dsh-plugin/index.js` — Có lỗi trong bước này?
- `dsh-plugin/index.js` — Trả lỗi cho người gọi
- `scripts/render_flow.py` — Xử lý tại main

## Giới hạn và phần chưa xác minh

- Phân tích tĩnh trên source; hành vi runtime, dữ liệu thật và cấu hình môi trường chưa được kiểm chứng.
- Không chép nội dung source vào kết quả; chỉ ghi tên file, số dòng và tên hàm/khối.
- Chỉ đọc file source trong repository; file cấu hình bí mật, dump, log và thư mục phụ thuộc bị loại trừ.
- Thư mục test/fixture/example/sample/demo bị bỏ qua để không phân tích nhầm ứng dụng mẫu.
- Không tìm thấy điểm trả kết quả rõ ràng; node kết thúc là suy luận.
- Không thấy khai báo route/handler cho yêu cầu này; điểm vào là hàm đầu tiên khớp chủ đề.

- Không có cảnh báo.

## Phạm vi đọc và loại trừ

Chỉ đọc file source trong root ở trên. Các mục sau bị loại khỏi phân tích:

- suffix: 14
- test_dir: 11

Tool không gọi network, không chạy code của repository, không sửa file nguồn. Nội dung source không được chép vào báo cáo này; chỉ tên file, số dòng và tên hàm/khối.

## Tệp sinh ra

- `flow.json` — dữ liệu có cấu trúc, dùng lại được cho lần render sau
- `flow.html` — sơ đồ mở offline
- `overview.md` — tài liệu này
