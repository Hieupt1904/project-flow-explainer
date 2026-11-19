# Project Flow Explainer

Bộ công cụ đọc repository và giải thích quy trình hoạt động bằng sơ đồ HTML mở offline.
Bản 0.4.1 thêm **lớp tri thức code** (index, tìm kiếm exact, vector tùy chọn, truy hồi hybrid,
phân tích tác động, kiểm tra sau khi sửa) và **Simple view** cho người không chuyên.
Bản 0.4.1 cũng sửa 4 lỗi thật: CLI `flow` không import được core, incremental index làm mất file,
`context_pack` trả route giả, và `dispose` không huỷ run của tool tri thức.

Hai lớp, một core:

| Lớp | Trạng thái | Thành phần |
|---|---|---|
| Giải thích flow | **ĐÃ TRIỂN KHAI** | `scripts/build_flow.py`, `pfe/flow.py`, `scripts/render_flow.py`, `assets/workflow_template.html` |
| Tri thức code | **ĐÃ TRIỂN KHAI** (vector là tùy chọn) | `pfe/facts.py`, `pfe/ontology.py`, `pfe/knowledge.py`, `pfe/index.py`, `pfe/retrieval.py`, `pfe/impact.py`, `pfe/verify.py` |
| DSH adapter | **ĐÃ TRIỂN KHAI**; registry-runtime **ĐÃ XÁC MINH** trong profile `pfe-test` (36 tool, 14 check) | `dsh-plugin/` |
| Model tự chọn tool trong DSH | **CHƯA CHẠY** (không có API key) | — |
| Panel UI trong Harness | **BLOCKED_UI_API_UNVERIFIED** | chưa có code UI (không nằm trong scope) |
| DSH native Config schema | **BLOCKED_DSH_CONFIG_NATIVE** | profile không resolve `@deepseek-ai/schemastery` |
| Tool visibility cho 4 workflow chính | **BLOCKED_TOOL_VISIBILITY** | chưa có cơ chế visibility đã xác minh |

Bắt đầu từ [USAGE_GUIDE.md](USAGE_GUIDE.md) để dùng đúng công cụ và đọc kết quả đúng cách.

Bắt đầu từ [REVIEW_PACKET.md](REVIEW_PACKET.md) nếu bạn review. Số liệu máy đọc:
[artifacts/review/evidence-manifest.json](artifacts/review/evidence-manifest.json).

## Chạy nhanh

### 1. Giải thích một luồng

```bash
python3 scripts/build_flow.py --repo /duong/dan/repo \
  --request "Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file"
```

Kết quả trong `/duong/dan/repo/artifacts/flows/<slug>/`:

| File | Loại | Nội dung |
|---|---|---|
| `flow.json` | public | graph có bằng chứng, render lại được |
| `flow.html` | public | sơ đồ tương tác, mở offline; mặc định **Simple view** (3–7 stage), chuyển sang Kỹ thuật khi cần |
| `overview.md` | public | giải thích, bằng chứng từng bước, giới hạn |
| `run.json` | **internal provenance** | số đếm, giới hạn, trạng thái git; không phải public output |

Tool DSH trả **đường dẫn tương đối** (`artifacts/flows/<slug>/flow.html`) vì chưa có
presentation boundary nào được xác minh: absolute path không rời khỏi máy chủ.

### 2. Xây index tri thức

```bash
python3 tools/pfe_cli.py index --repo /duong/dan/repo --mode full --include-vectors
```

Index nằm ở `<repo>/.pfe/index/knowledge.sqlite` (đã có trong `.gitignore`).
Lần chạy sau dùng `--mode incremental`: file không đổi không bị parse lại.

### 3. Tìm context, phân tích tác động, kiểm tra

```bash
python3 tools/pfe_cli.py search --repo /duong/dan/repo --query "export_report"
python3 tools/pfe_cli.py context-pack --repo /duong/dan/repo --task "sửa luồng xuất Excel"
python3 tools/pfe_cli.py impact --repo /duong/dan/repo --changed services/report_service.js
python3 tools/pfe_cli.py verify --repo /duong/dan/repo
python3 tools/pfe_cli.py refresh --repo /duong/dan/repo
```

Mỗi lệnh in đúng một object JSON. Lỗi có mã ổn định, không rơi traceback.

## Tích hợp DeepSeek Harness

Plugin đăng ký 7 tool và gọi lại core qua subprocess (không shell, không network):

| Tool | Việc nó làm |
|---|---|
| `project_flow_explain` | dựng flow.json + flow.html + overview.md |
| `project_code_index` | xây index tri thức full hoặc incremental |
| `project_code_search` | truy hồi hybrid, trả path/symbol/line/relation/confidence |
| `project_context_pack` | gom context trước khi sửa: entry point theo loại (http_route, cli_command, gui_event, button_click, callback, worker, main, public_api), file nên đọc, dependency có path/line |
| `project_impact_analysis` | file thay đổi → flow/route/symbol/test/risk |
| `project_verify_flow` | kiểm tra graph/artifact/HTML tĩnh/privacy/test mapping; tách `static_verdict` và `overall_verdict` |
| `project_knowledge_refresh` | refresh tăng dần sau khi sửa code |

Cài vào profile riêng (không dùng profile `web`):

```bash
node dsh-plugin/scripts/pack.mjs
dsh plugin --profile pfe-test add "$PWD/dist/dsh-project-flow-explainer-0.4.1.tgz"
```

Bundle đã tự insert row `project-flow-explainer`. Cấu hình bằng **override row**
theo id, không insert lại cùng id:

```yaml
- id: project-flow-explainer
  config:
    allowedRoots:
      - /duong/dan/workspace
    pythonPath: python3
    timeoutMs: 180000
    maxOutputBytes: 1048576
```

Thiếu `allowedRoots` thì mọi lời gọi trả `allowed_roots_unconfigured` (deny-by-default).
Chi tiết: [dsh-plugin/README.md](dsh-plugin/README.md).

## Mô hình bằng chứng

Mỗi tool nói rõ `when_to_use`, `when_not_to_use`, `prerequisite`, `output`, `next_action`,
`limitations` trong description để model chọn đúng mà không cần đọc source.

| Nhãn | Nghĩa chính xác |
|---|---|
| `observed` | đọc được tại `path:line` (khai báo, call site, SQL, throw) |
| `structural` | suy ra từ cấu trúc (import, test nhắc tới tên) |
| `inferred` | heuristic, không có bằng chứng trực tiếp |
| `runtime_verified` | chỉ khi có bằng chứng chạy; lớp tĩnh **không** sinh nhãn này |
| `verified` (flow) | vị trí thật + bằng chứng thành viên (route/import); **không** phải đã chạy code |
| `location_confidence` | độ tin của *vị trí* (observed/unknown) |
| `relevance_confidence` | độ tin của *việc thuộc task* (observed/structural/inferred) |

Ba luật không thương lượng:

1. Không có cạnh `evidence=call` nếu không có call-site (path + line).
2. Nhánh quyết định không được có cạnh success đi tắt.
3. File chỉ khớp từ khoá nằm ở `meta.related`, không thành node của luồng.

## Chính sách đọc, ghi, mạng, riêng tư

| Chủ đề | Luật |
|---|---|
| Đọc | chỉ `allowedRoots`, so sánh sau `realpath`; symlink trỏ ra ngoài bị loại |
| Ghi | chỉ `<repo>/artifacts/flows/<slug>/`; ghi qua staging rồi rename |
| Mạng | core và adapter không mở socket; embedding local-only |
| Bí mật | loại theo tên file, theo nội dung (secret-shaped line) và theo symlink; file chứa secret không vào index |
| Kết quả tool | trả path/symbol/line range; không trả source thô; snippet chỉ khi bật rõ |
| Git | chỉ đọc (`rev-parse`, `status`, `log`), tắt hook và fsmonitor |

## Kiểm thử

```bash
python3 -m unittest discover -s tests -v                # core + knowledge + regression (143 test)
node --test dsh-plugin/tests/plugin.test.mjs            # adapter (16 test)
node --test dsh-plugin/tests/knowledge.test.mjs         # tool tri thức (9 test)
node --test dsh-plugin/tests/lifecycle.test.mjs         # mount/dispose/remount (7 test)
node --test dsh-plugin/tests/pack.test.mjs              # đóng gói + cài độc lập (2 test)
python3 scripts/check_repo_policy.py                    # policy artifact/provenance
python3 scripts/regen_evidence.py                        # sinh lại evidence-manifest.json
python3 scripts/bench_index.py --files 2000 --json       # benchmark index
```

## Bố cục repository

```text
pfe/                     core Python: policy, facts, flow, ontology, knowledge, index,
                         vectors, retrieval, impact, verify, emit
scripts/build_flow.py    CLI flow (giữ tương thích)
scripts/render_flow.py   validate + render HTML
tools/pfe_cli.py         CLI máy đọc cho 6 tool tri thức
dsh-plugin/              adapter DSH (zero dependency)
assets/                  template HTML offline
references/              schema + prompt module + code-knowledge-schema.json
tests/                   143 unittest + fixture web/desktop
artifacts/               bằng chứng: samples, review, ui-verification
```

## Giới hạn đã biết

| Giới hạn | Trạng thái |
|---|---|
| Call graph đầy đủ (type-aware) | **CHƯA CÓ**; `calls` trong index chỉ là call site đọc theo lexical |
| Vector ngữ nghĩa thật | **CHƯA CÓ**; backend mặc định là hashing lexical, chỉ tạo candidate |
| Panel UI trong Harness | BLOCKED_UI_API_UNVERIFIED |
| Smoke registry 0.4.1 trong `pfe-test` | **ĐÃ CHẠY** 2026-11-20: 6 lần boot thật, 7/7 tool gọi được, policy/abort/timeout đúng (`artifacts/review/*-dsh-smoke.json`) |
| Model tự chọn tool | **CHƯA CHẠY**: profile không có API key; probe gọi registry, không qua model |
| Ngôn ngữ ngoài danh sách pattern | Go, Rust, C#, Kotlin chỉ có symbol/route cơ bản |

Tài liệu tri thức: [references/code-knowledge-schema.json](references/code-knowledge-schema.json) (schema),
[references/code-knowledge-examples.md](references/code-knowledge-examples.md) (fact thật từ index).

Quyết định kiến trúc: [ARCHITECTURE_DECISION.md](ARCHITECTURE_DECISION.md).
Báo cáo: [TEST_REPORT.md](TEST_REPORT.md), [FINAL_REPORT.md](FINAL_REPORT.md),
[UI_VERIFICATION_REPORT.md](UI_VERIFICATION_REPORT.md), [IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md).