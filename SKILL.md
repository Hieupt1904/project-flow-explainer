---
name: project-flow-explainer
description: Đọc project/repository mã nguồn và giải thích quy trình hoạt động bằng sơ đồ HTML tương tác, giống canvas workflow với node, nhánh, điều kiện và đường nối. Dùng khi người dùng muốn phân tích luồng frontend-backend-API-DB, user journey, business process, chatbot automation, hoặc kiến trúc tính năng; cần sơ đồ người không biết code cũng hiểu, có căn cứ file/dòng nguồn, tạo HTML mở offline.
---

# Project Flow Explainer

Biến mã nguồn project thành sơ đồ luồng dễ hiểu, có thể truy ngược về code. Một lần chạy cần tạo **JSON kiểm chứng được** và **HTML độc lập mở offline**.

## Quy trình bắt buộc

1. **Xác định phạm vi**: Ưu tiên một luồng nghiệp vụ hoặc một hành trình người dùng. Nếu yêu cầu "toàn bộ project", tạo sơ đồ tổng quan module, sau đó tách từng luồng thành nhiều file HTML; không nhồi mọi thứ vào một canvas. Nếu không có quyền truy cập repo, nói rõ và yêu cầu đường dẫn hoặc upload; không giả vờ đã đọc project.
2. **Đọc project có chủ đích**: Xem [references/repository-reader.md](references/repository-reader.md). Kiểm tra file mô tả dự án, entry point, router, UI handler, service, model, DB, queue và integration liên quan. Không chạy code lạ, không đọc/hiển thị secrets nếu không cần.
3. **Truy vết từng bước**: Xem [references/flow-tracer.md](references/flow-tracer.md). Theo dõi từ điểm kích hoạt đến các hành động và đầu ra. Ghi rõ điều kiện YES/NO, lỗi, retry, loop, async. Đính chứng cứ `path` + `start_line` (nếu xác định được). Không sáng tác cạnh hoặc trình tự chỉ từ tên file.
4. **Đơn giản hóa cho người đọc**: Xem [references/explainer-style.md](references/explainer-style.md). Node chính trả lời "điều gì xảy ra?"; ghi chú giải thích "vì sao?"; cạnh trả lời "khi nào đi tiếp?". Tên hàm/endpoint/path nằm trong panel kỹ thuật, không đưa thành nhãn chính. Một canvas chi tiết nên có 5–12 node; nhiều hơn thì chia subflow.
5. **Tạo graph JSON**: Theo [references/flow-schema.md](references/flow-schema.md). Mọi node phải có `id`, `title`, `type`, `summary`, `confidence`. Mọi edge có `from`, `to`, `label`, `kind`. Dùng `verified` chỉ khi thực sự có `source_refs`; sử dụng `inferred` hoặc `unknown` cho các đoạn chưa được chứng minh.
6. **Render HTML**: Chạy `python scripts/render_flow.py path/to/flow.json --out path/to/flow.html` (dùng đường dẫn tuyệt đối tới script khi cần). Script kiểm tra schema trước rồi sinh một file HTML chứa toàn bộ CSS/JS, không phụ thuộc CDN. HTML có canvas dạng card + connector cong, pan/zoom, tìm kiếm, chọn node để xem chi tiết và nguồn, làm sáng tuyến từ điểm bắt đầu.
7. **Kiểm tra**: Chạy script thành công; mở HTML nếu có trình duyệt; kiểm tra mũi tên, nhãn điều kiện, khả năng đọc, tìm kiếm, các nhánh lỗi và căn cứ mã nguồn. Nếu không thể mở trình duyệt, nói rõ kiểm tra bị giới hạn.

## Chuẩn đầu ra

- `overview.md`: mục đích luồng, điểm bắt đầu/kết thúc, phạm vi và hạn chế; phân biệt "từ code xác nhận" với "suy luận".
- `flow.json`: biểu diễn máy đọc được, luôn lưu để người dùng/auditor chỉnh sửa hoặc tái tạo sơ đồ.
- `flow.html`: kết quả chính, tự chạy offline, tiếng Việt, ưu tiên non-tech.
- Khi nhiều flow: `index.md` liên kết danh sách sơ đồ theo module/chức năng; mỗi luồng có JSON và HTML riêng.
- Kết thúc bằng đường dẫn thực tế tới file và tóm tắt phạm vi đã kiểm chứng. Không bảo rằng "đã đọc toàn bộ project" nếu chỉ scan một phần.

## Quy tắc cứng

- Không suy đoán logic nghiệp vụ từ screenshot hoặc README khi code chưa kiểm chứng; đánh dấu rõ mô phỏng, thiếu thông tin, hoặc giả định.
- Không tạo node "Thành công" nếu không có tín hiệu success thực tế; thể hiện success/error branch nếu kiểm chứng.
- Không đọc và công khai `.env`, token, private key, password, dữ liệu cá nhân, thông tin khách hàng; không chép payload mật vào HTML.
- Không cài thư viện hoặc gọi dịch vụ ngoài nếu không được phép. Không tự ý chạy migration, build hay test có side effect.
- Không có repo thực tế: được tạo một **demo minh họa**, ghi rõ không phải kết quả phân tích project.
- Prompt hệ thống tích hợp cho agent độc lập có trong [references/SYSTEM_PROMPT.md](references/SYSTEM_PROMPT.md).

## CLI nhanh

```bash
python scripts/render_flow.py assets/example_workflow.json --out /tmp/workflow_demo.html
python scripts/render_flow.py path/to/flow.json --out path/to/flow.html
python scripts/render_flow.py path/to/flow.json --check-only
```

Không thay template HTML bằng Mermaid tĩnh khi yêu cầu tương tác; Mermaid chỉ có thể dùng như bản nháp nội bộ nếu cần.
