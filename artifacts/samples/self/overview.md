# Luồng: phân tích repository và sinh sơ đồ HTML

Sinh tự động: 2026-11-19T21:45:42+07:00 · `scripts/build_flow.py` (schema 2).

## Yêu cầu

> luồng phân tích repository và sinh sơ đồ HTML

## Repository được phân tích

| Mục | Giá trị |
|---|---|
| Tên | `project-flow-explainer` |
| Nhánh | `không có git` |
| Commit | `không có git` |
| Thay đổi chưa commit | không |

Đường dẫn tuyệt đối không được ghi vào artifact để tránh lộ cấu trúc máy cá nhân.

## Luồng xử lý

Sơ đồ dựng từ phân tích tĩnh theo yêu cầu: luồng phân tích repository và sinh sơ đồ HTML. Mỗi bước trỏ tới file và dòng thật; bước chỉ khớp từ khoá được tách riêng thay vì nối vào luồng.

| # | Bước | Loại | Vị trí | Bằng chứng thành viên | Tin cậy |
|---|---|---|---|---|---|
| 1 | Bắt đầu từ yêu cầu | start | — | — | partial |
| 2 | Bắt đầu tại main | action | `scripts/build_flow.py`:1063 | entry | verified |
| 3 | Xử lý tại main | action | `scripts/render_flow.py`:201 | import | verified |
| 4 | Có lỗi trong bước này? | decision | `scripts/build_flow.py`:238 | import | partial |
| 5 | Trả lỗi cho người gọi | error | `scripts/build_flow.py`:238 | structure | partial |
| 6 | Kết thúc xử lý | end | — | call | inferred |

## Quan hệ giữa các bước

| Cạnh | Nhãn | Loại | Bằng chứng | Ghi chú |
|---|---|---|---|---|
| start → step-1 | `bắt đầu xử lý` | success | entry | route khai báo tại scripts/build_flow.py:1063 |
| step-1 → step-2 | `dùng module` | normal | import | `scripts/build_flow.py` import `scripts/render_flow.py` (qua sys.path) |
| step-1 → decision-scripts-build_flow-py | `vào bước xử lý` | normal | import | cùng bước `scripts/build_flow.py` |
| decision-scripts-build_flow-py → step-2 | `không lỗi` | success | structure | đường đi tiếp khi không lỗi |
| decision-scripts-build_flow-py → error-scripts-build_flow-py | `có lỗi` | error | structure | khối xử lý ngoại lệ trong file |
| step-2 → end | `hoàn tất` | success | call | bước cuối của luồng |

## File khớp từ khoá nhưng KHÔNG thuộc luồng

- `dsh-plugin/index.js` — khớp từ khoá nhưng không nối được tới điểm vào bằng import/gọi hàm

## Giới hạn và phần chưa xác minh

- Phân tích tĩnh trên source; hành vi runtime và dữ liệu thật chưa được kiểm chứng.
- Chỉ đọc source trong repository; file bí mật, dump, log và thư mục phụ thuộc bị loại.
- Thư mục test/fixture/example/sample/demo bị bỏ qua.
- Chưa có call graph đầy đủ: quan hệ bước dựa trên route, import và lời gọi theo tên.
- Thứ tự bước phản ánh quan hệ import/gọi hàm, không phải thứ tự thực thi tại runtime.
- Không tìm thấy điểm trả kết quả rõ ràng; node kết thúc là suy luận.

- Không có cảnh báo.

## Phạm vi đọc và loại trừ

Chỉ đọc file source trong repository. Các mục sau bị loại:

- suffix: 12
- test_dir: 11

Không gọi network, không chạy code của repository, không sửa file nguồn, không chép nội dung source.

## Tệp sinh ra

- `flow.json` — dữ liệu có cấu trúc, dùng lại được cho lần render sau
- `flow.html` — sơ đồ mở offline
- `overview.md` — tài liệu này
