# Sơ đồ luồng của project-flow-explainer

Ba sơ đồ, cùng một repository, cùng commit `6b6524b`. Mở file HTML trực tiếp bằng trình duyệt:
không CDN, không request ngoài, không cần server.

| # | Sơ đồ | Trả lời câu hỏi | Nguồn bằng chứng | Quy mô |
|---|---|---|---|---|
| 1 | [project-architecture/flow.html](project-architecture/flow.html) | Project này gồm những lớp nào và chúng nối với nhau ra sao? | dựng tay từ call site thật | 10 node, 11 cạnh |
| 2 | [dsh-tool-call-pipeline/flow.html](dsh-tool-call-pipeline/flow.html) | Một lần gọi `project_flow_explain` đi qua những bước nào tới `flow.html`? | dựng tay từ call site thật | 13 node, 14 cạnh |
| 3 | [self-explain-pipeline/flow.html](self-explain-pipeline/flow.html) | Chính tool nói gì khi được chạy trên repository của nó? | tool tự sinh bằng heuristic import | 13 node, 14 cạnh |

Mỗi thư mục có ba file công khai: `flow.json` (dữ liệu, render lại được), `flow.html` (sơ đồ),
`overview.md` (bằng chứng từng bước + giới hạn). Riêng sơ đồ 3 có thêm `run.json` — provenance
nội bộ, không phải output công khai.

## Đọc theo thứ tự nào

1. Bắt đầu ở sơ đồ 1 để biết bốn lớp: skill, adapter DSH, core sự thật tĩnh, hai lớp tính năng.
2. Sang sơ đồ 2 nếu cần đúng đường đi của một lần gọi tool, kèm hai nhánh lỗi.
3. Xem sơ đồ 3 như đối chứng: cùng repository nhưng do thuật toán tự dựng, nên nhãn node thô hơn
   và vài bước chỉ là "Xử lý tại <symbol>" — đúng giới hạn đã ghi trong tài liệu của tool.

## Mức tin cậy

| Nhãn | Nghĩa trong ba sơ đồ này |
|---|---|
| `verified` | vị trí file:dòng có thật và quan hệ đọc được từ import/call site; **không** phải đã chạy runtime |
| `partial` | vị trí có thật nhưng vai trò trong luồng chỉ suy ra từ cấu trúc |
| `inferred` | suy luận từ ngữ cảnh, chưa có bằng chứng trực tiếp |

## Kiểm tra đã chạy

| Việc | Kết quả |
|---|---|
| `scripts/render_flow.py` validate cả ba graph | 10/13/13 node, không chu trình lạ, entry đi tới được mọi node |
| `tools/pfe_cli.py verify` | 5/6 check pass: graph_evidence, ui_self_contained, privacy, artifact_scope, flow_artifacts. `test_mapping` blocked vì chưa có index |
| `scripts/check_repo_policy.py` | pass — 105 file, không absolute path, không nested artifact, không secret |
| `verify` khi có index (chạy một lần rồi xoá) | `test_mapping` pass: 26 test, 174 quan hệ `tested_by`, 0 fact stale |
| Mở `dsh-tool-call-pipeline/flow.html` trong Chrome | 13 `.node-card`, 14 `.edge-set`, panel chi tiết hiện nguồn `pfe/flow.py`:157-200 |
| `gate ui` và `gate runtime` | blocked — chưa có bằng chứng render tự động và chưa chạy test gắn với từng sơ đồ |

Ảnh chụp màn hình của lần kiểm tra UI: `../ui-verification/flow-dsh-tool-call-pipeline-technical.png`.
