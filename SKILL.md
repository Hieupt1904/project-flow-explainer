---
name: project-flow-explainer
description: Dựng bản đồ toàn kho hoặc giải thích một luồng nghiệp vụ bằng sơ đồ HTML tương tác mở ngoại tuyến. Dùng khi cần xem phân hệ, luồng giao diện đến dữ liệu, hoặc nhánh xử lý có căn cứ tệp và dòng mã.
---

# Project Flow Explainer

Biến mã nguồn project thành sơ đồ luồng dễ hiểu, có thể truy ngược về code. Một lần chạy cần tạo **JSON kiểm chứng được** và **HTML độc lập mở offline**.

Trong DeepSeek Harness, skill mà harness nạp là `.dsh/skills/project-flow-explainer/SKILL.md`. Plugin đã cài cũng đăng ký cùng skill đó. File này giữ quy trình cho agent không chạy trong DSH.

## Chọn chế độ

- **Toàn kho:** chạy `node scripts/project_map.mjs build /duong/dan/repo`. Mở `project-flow-explainer/index.html` trong kho được phân tích. Dùng `refresh` khi đã có bản đồ.
- **Một luồng:** xác định điểm vào và đầu ra, rồi làm theo quy trình bên dưới. Đầu ra nằm trong `artifacts/flows/<slug>/`.
- **Bản phác:** chuẩn bị `project-flow-explainer/plan.json` theo [định dạng bản phác](vendor/project-flow-explainer/references/blueprint.md), rồi chạy `project_map.mjs plan` với đường dẫn kho. Gắn nhãn **DỰ KIẾN** cho hệ thống chưa xây.

Xem [hướng dẫn sử dụng](USAGE_GUIDE.md#bật-thanh-hỏi) khi cần tra cứu cục bộ hoặc hỏi qua DeepSeek Harness (DSH).

## Quy trình cho một luồng

1. **Xác định phạm vi**: Ưu tiên một luồng nghiệp vụ hoặc một hành trình người dùng. Nếu cần giải thích chi tiết nhiều nghiệp vụ, tạo một sơ đồ riêng cho mỗi luồng. Nếu không có quyền truy cập repo, nói rõ và yêu cầu đường dẫn hoặc upload; không giả vờ đã đọc project.
2. **Đọc project có chủ đích**: Xem [references/repository-reader.md](references/repository-reader.md). Kiểm tra file mô tả dự án, entry point, router, UI handler, service, model, DB, queue và integration liên quan. Không chạy code lạ, không đọc/hiển thị secrets nếu không cần.
3. **Truy vết từng bước**: Xem [references/flow-tracer.md](references/flow-tracer.md). Theo dõi từ điểm kích hoạt đến các hành động và đầu ra. Ghi rõ điều kiện YES/NO, lỗi, retry, loop, async. Đính chứng cứ `path` + `start_line` (nếu xác định được). Không sáng tác cạnh hoặc trình tự chỉ từ tên file.
4. **Đơn giản hóa cho người đọc**: Xem [references/explainer-style.md](references/explainer-style.md). Node chính trả lời "điều gì xảy ra?"; ghi chú giải thích "vì sao?"; cạnh trả lời "khi nào đi tiếp?". Tên hàm/endpoint/path nằm trong panel kỹ thuật, không đưa thành nhãn chính. Một canvas chi tiết nên có 5–12 node; nhiều hơn thì chia subflow.
5. **Tạo graph JSON**: Theo [references/flow-schema.md](references/flow-schema.md). Mọi node phải có `id`, `title`, `type`, `summary`, `confidence`. Mọi edge có `from`, `to`, `label`, `kind`. Dùng `verified` chỉ khi thực sự có `source_refs`; sử dụng `inferred` hoặc `unknown` cho các đoạn chưa được chứng minh.
6. **Render HTML**: Chạy `python scripts/render_flow.py path/to/flow.json --out path/to/flow.html` (dùng đường dẫn tuyệt đối tới script khi cần). Script kiểm tra schema rồi tạo một tệp HTML tự chứa. Trình xem chính có hướng dẫn chọn nhánh và bảng căn cứ. Giao diện dự phòng có danh sách từng bước. Để nâng giao diện của một sơ đồ cũ, dựng lại HTML từ `flow.json` đã có.
7. **Kiểm tra**: Chạy script thành công; mở HTML nếu có trình duyệt; kiểm tra mũi tên, nhãn điều kiện, khả năng đọc, tìm kiếm, các nhánh lỗi và căn cứ mã nguồn. Nếu không thể mở trình duyệt, nói rõ kiểm tra bị giới hạn.

## Chuẩn đầu ra

- `overview.md`: mục đích luồng, điểm bắt đầu/kết thúc, phạm vi và hạn chế; phân biệt "từ code xác nhận" với "suy luận".
- `flow.json`: biểu diễn máy đọc được, luôn lưu để người dùng/auditor chỉnh sửa hoặc tái tạo sơ đồ.
- `flow.html`: kết quả chính, tự chạy offline, tiếng Việt, ưu tiên non-tech.
- Khi nhiều flow: `index.md` liên kết danh sách sơ đồ theo module/chức năng; mỗi luồng có JSON và HTML riêng.
- Kết thúc bằng đường dẫn thực tế tới file và tóm tắt phạm vi đã kiểm chứng. Không bảo rằng "đã đọc toàn bộ project" nếu chỉ scan một phần.

## Quy tắc cứng

- Không suy đoán logic nghiệp vụ từ screenshot hoặc README khi code chưa kiểm chứng; đánh dấu rõ mô phỏng, thiếu thông tin, hoặc giả định.
- Chỉ vẽ nhánh thành công hoặc nhánh lỗi khi có tín hiệu trong mã nguồn.
- Không đọc và công khai `.env`, token, private key, password, dữ liệu cá nhân, thông tin khách hàng; không chép payload mật vào HTML.
- Không cài thư viện hoặc gọi dịch vụ ngoài nếu chưa có phê duyệt. Không tự ý chạy migration, build hay test có side effect.
- Nếu thiếu kho mã, gắn nhãn **Ví dụ minh họa** cho sơ đồ mẫu.
- Prompt hệ thống tích hợp cho agent độc lập có trong [references/SYSTEM_PROMPT.md](references/SYSTEM_PROMPT.md).

## Lớp tri thức code (0.3.0)

Ngoài sơ đồ, repo có index cục bộ để agent tìm context và kiểm tra sau khi sửa:

```bash
python3 tools/pfe_cli.py index --repo <repo> --mode full
python3 tools/pfe_cli.py search --repo <repo> --query "export_report"
python3 tools/pfe_cli.py context-pack --repo <repo> --task "sửa luồng xuất Excel"
python3 tools/pfe_cli.py impact --repo <repo> --changed services/report_service.js
python3 tools/pfe_cli.py verify --repo <repo>
```

Trong DSH các việc này là 6 tool: `project_code_index`, `project_code_search`,
`project_context_pack`, `project_impact_analysis`, `project_verify_flow`,
`project_knowledge_refresh`.

Nguyên tắc giữ nguyên: chỉ local absolute path, không network, không chạy code của repository,
kết quả trả path/symbol/line range và bằng chứng, không trả source thô.

## CLI nhanh

Dựng ba tệp dành cho người xem và một tệp truy vết nội bộ:

```bash
python scripts/build_flow.py \
  --repo /duong/dan/repo \
  --request "Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file"
# -> <repo>/artifacts/flows/<slug>/{flow.json,flow.html,overview.md,run.json}
python scripts/build_flow.py --repo REPO --request "..." --json   # kết quả máy đọc, cho adapter
```

Render lại từ graph có sẵn:

```bash
python scripts/render_flow.py assets/example_workflow.json --out <thu-muc-ra>/workflow_demo.html
python scripts/render_flow.py path/to/flow.json --out path/to/flow.html
python scripts/render_flow.py path/to/flow.json --check-only
```

Chính sách của `build_flow.py`: chỉ đọc source trong root, bỏ qua `.env`/credentials/key/dump/log và
thư mục phụ thuộc, không network, không chạy code của repo, không chép nội dung source vào output.

## Tích hợp DSH (tuỳ chọn)

`dsh-plugin/` là adapter mỏng: đăng ký tool `project_flow_explain`, gọi `scripts/build_flow.py` qua
subprocess rồi trả đường dẫn + số liệu. Core vẫn chạy độc lập khi xoá thư mục này. Chi tiết:
[ARCHITECTURE_DECISION.md](ARCHITECTURE_DECISION.md).

Không thay template HTML bằng Mermaid tĩnh khi yêu cầu tương tác; Mermaid chỉ có thể dùng như bản nháp nội bộ nếu cần.