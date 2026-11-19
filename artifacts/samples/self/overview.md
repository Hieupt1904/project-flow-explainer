# Luồng: Giải thích từ lúc người dùng chạy build_flow trên một repository đến khi nhận flow.json

Sinh tự động: 2026-11-19T22:53:50+07:00 · `scripts/build_flow.py` (schema 2).

## Yêu cầu

> Giải thích từ lúc người dùng chạy build_flow trên một repository đến khi nhận flow.json

## Repository được phân tích

| Mục | Giá trị |
|---|---|
| Tên | `project-flow-explainer` |
| Nhánh | `không có git` |
| Commit | `không có git` |
| Thay đổi chưa commit | không |
| File đã đọc | 25 |
| Byte source đã đọc | 284000 |
| Số ngân sách bị cắt | không |

Đường dẫn tuyệt đối không được ghi vào artifact để tránh lộ cấu trúc máy cá nhân.

## Luồng xử lý

Sơ đồ dựng từ phân tích tĩnh theo yêu cầu: Giải thích từ lúc người dùng chạy build_flow trên một repository đến khi nhận flow.json. Mỗi bước trỏ tới file và dòng thật; bước chỉ khớp từ khoá được tách riêng thay vì nối vào luồng.

| # | Bước | Loại | Vị trí | Bằng chứng thành viên | Tin cậy |
|---|---|---|---|---|---|
| 1 | Bắt đầu từ yêu cầu | start | — | — | partial |
| 2 | Bắt đầu tại main | action | `tools/pfe_cli.py`:180 | entry | verified |
| 3 | Module __init__ | action | `pfe/__init__.py`:1 | import | verified |
| 4 | Xử lý tại as_dict | action | `pfe/index.py`:82 | import | verified |
| 5 | Xử lý tại as_dict | action | `pfe/policy.py`:34 | import | verified |
| 6 | Xử lý tại run | action | `scripts/build_flow.py`:92 | import | verified |
| 7 | Xử lý tại strip_diacritics | action | `pfe/text.py`:11 | import | verified |
| 8 | Xử lý tại main | action | `scripts/render_flow.py`:201 | import | verified |
| 9 | Có lỗi trong bước này? | decision | `scripts/build_flow.py`:153 | structure | partial |
| 10 | Trả lỗi cho người gọi | error | `scripts/build_flow.py`:153 | structure | partial |
| 11 | Kết thúc xử lý | end | — | import | inferred |
| 12 | Có lỗi trong bước này? | decision | `scripts/render_flow.py`:207 | structure | partial |
| 13 | Trả lỗi cho người gọi | error | `scripts/render_flow.py`:207 | structure | partial |

## Quan hệ giữa các bước

| Cạnh | Nhãn | Loại | Bằng chứng | Ghi chú |
|---|---|---|---|---|
| start → step-1 | bắt đầu xử lý | success | entry | route khai báo tại tools/pfe_cli.py:180 |
| step-1 → step-2 | dùng module | success | import | tools/pfe_cli.py import pfe/__init__.py · dòng import 70 |
| step-2 → step-3 | dùng module | success | import | tools/pfe_cli.py import pfe/index.py · dòng import 70 |
| step-3 → step-4 | dùng module | success | import | tools/pfe_cli.py import pfe/policy.py · dòng import 33 |
| step-4 → step-5 | dùng module | success | import | tools/pfe_cli.py import scripts/build_flow.py (qua sys.path) · dòng import 63 |
| step-5 → decision-scripts-build_flow-py | vào bước xử lý | normal | structure | cùng bước `scripts/build_flow.py`, khối try tại dòng 153 |
| decision-scripts-build_flow-py → error-scripts-build_flow-py | có lỗi | error | structure | khối xử lý ngoại lệ trong file |
| decision-scripts-build_flow-py → step-6 | dùng module | success | import | scripts/build_flow.py import pfe/text.py · dòng import 44 · qua nhánh không lỗi |
| step-6 → step-7 | dùng module | success | import | scripts/build_flow.py import scripts/render_flow.py (qua sys.path) · dòng import 40 |
| step-7 → decision-scripts-render_flow-py | vào bước xử lý | normal | structure | cùng bước `scripts/render_flow.py`, khối try tại dòng 207 |
| decision-scripts-render_flow-py → error-scripts-render_flow-py | có lỗi | error | structure | khối xử lý ngoại lệ trong file |
| decision-scripts-render_flow-py → end | hoàn tất | success | import | bước cuối của luồng · qua nhánh không lỗi |

## Mô hình bằng chứng

- `verified` = vị trí có thật (file + dòng) và có bằng chứng thành viên (route/import); xác minh tĩnh, KHÔNG phải chạy runtime
- `partial`  = vị trí có thật nhưng vai trò trong luồng chỉ suy ra từ cấu trúc
- `inferred` = suy luận từ ngữ cảnh, chưa có bằng chứng trực tiếp
- Có cạnh `call` trong sơ đồ: không
- Có bằng chứng runtime: không

## File khớp từ khoá nhưng KHÔNG thuộc luồng

- dsh-plugin/index.js — khớp từ khoá nhưng không nối được tới điểm vào bằng import/gọi hàm
- dsh-plugin/lib/tools.js — khớp từ khoá nhưng không nối được tới điểm vào bằng import/gọi hàm
- pfe/facts.py — khớp từ khoá nhưng không nối được tới điểm vào bằng import/gọi hàm
- pfe/flow.py — khớp từ khoá nhưng không nối được tới điểm vào bằng import/gọi hàm
- pfe/ontology.py — khớp từ khoá nhưng không nối được tới điểm vào bằng import/gọi hàm

## Giới hạn và phần chưa xác minh

- Không tìm thấy điểm trả kết quả rõ ràng; node kết thúc là suy luận.
- Chưa có call graph runtime: cạnh chỉ mang bằng chứng entry/import/structure; không có cạnh nào tự nhận là call.

- Không có cảnh báo.

## Phạm vi đọc và loại trừ

Chỉ đọc file source trong repository. Các mục sau bị loại:

- secret_lines: 1
- suffix: 23
- test_dir: 21

Không gọi network, không chạy code của repository, không sửa file nguồn, không chép nội dung source.

## Tệp sinh ra

- `flow.json` — dữ liệu có cấu trúc, dùng lại được cho lần render sau (public)
- `flow.html` — sơ đồ mở offline (public)
- `overview.md` — tài liệu này (public)
- `run.json` — internal provenance, KHÔNG phải public output: chứa số đếm, giới hạn và trạng thái git của lần chạy
