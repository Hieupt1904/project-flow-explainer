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
| Model tự chọn tool trong DSH | **ĐÃ XÁC MINH**: model gọi `project_code_index` rồi `project_context_pack` trong session thật | — |
| Panel UI trong Harness | **BLOCKED_UI_API_UNVERIFIED** | chưa có code UI (không nằm trong scope) |
| DSH native Config schema | **ĐÃ TRIỂN KHAI**, xác minh bằng probe tiến trình con (xem dưới) | `dsh-plugin/index.js`, `dsh-plugin/tests/lifecycle.test.mjs` |
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

### Dùng nhanh: `/project-flow-explainer`

Người dùng gõ thẳng trong Web UI, không cần nhờ model chọn tool:

```text
/project-flow-explainer từ lúc bấm xuất báo cáo đến khi nhận được file
/project-flow-explainer xuất Excel --repo /duong/dan/khac
```

Lệnh chạy cùng core, cùng `allowedRoots`, cùng chỗ ghi artifact; kết quả hiện trong UI và
**không vào lịch sử model** nên không tốn token. Cài đặt và chi tiết:
[dsh-plugin/README.md](dsh-plugin/README.md#lệnh-người-dùng-project-flow-explainer).

Plugin cũng đăng ký 7 tool và gọi lại core qua subprocess (không shell, không network):

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
dsh plugin --profile pfe-test add "$PWD/dist/dsh-project-flow-explainer-0.7.8.tgz"
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

### Chỉnh cấu hình trong UI

Mở **Plugins** → card `dsh-project-flow-explainer` → bấm **Configure** ở dòng
`project-flow-explainer`. Trang cấu hình có 5 trường (`allowedRoots`, `pythonPath`,
`coreRoot`, `timeoutMs`, `maxOutputBytes`), nút **Lưu cấu hình** và **Khôi phục mặc định**.

Vì sao phải mở từ dòng: trang bundle gọi `formFor(pkg.name)`, còn namespace settings dùng
row id (`project-flow-explainer`), nên form chỉ có ở trang cấu hình của row.

Lưu xong, Host phát `settings/document-updated`; plugin cập nhật giá trị tại chỗ nên lần gọi
kế tiếp dùng cấu hình mới, không cần restart. Schema là `Config` native (schemastery):
giá trị sai kiểu bị từ chối ngay khi mount.

Sau khi cài hoặc nâng cấp bundle, **khởi động lại DSH** để nạp module mới; đổi cấu hình
trong UI thì không cần restart.

## Provenance của bản phát hành

Bốn khái niệm khác nhau, đừng dùng lẫn:

| Khái niệm | Nghĩa | Giá trị hiện tại |
|---|---|---|
| `source_commit` | commit của **code** mà manifest mô tả | `a306dc1512bc` |
| `evidence_commit` | commit **chứa manifest** này | `a306dc1512bc` |
| `HEAD` khi ghi | HEAD lúc chạy `record_release.py` | `a306dc1512bc` |
| `working_tree_dirty` | cây nguồn có file chưa commit | `False` |

Hai cây chỉ khác nhau ở `artifacts/review/` — `record_release.py` chứng minh bằng
`git diff --name-only` chứ không tự khai.

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

### Smoke model: khi nào một session là bằng chứng

`scripts/run_model_smoke.py` chỉ ghi `status: verified` khi có quan sát dương tính.
Thiếu lỗi **không** phải bằng chứng, vì ba trạng thái sau đều "không có lỗi":

| Trạng thái | Dấu hiệu | Kết luận |
|---|---|---|
| Session bị chấm nhầm | `selected_tools` rỗng nhưng context vẫn "đủ" | `partial` — record chuyển sang `artifacts/review/attempts/` |
| Harness không expose tool | probe in `HAS_PFE=không` hoặc `TOOLS=24` | `partial`, blocked ghi rõ probe |
| Model thấy tool nhưng không gọi | probe `HAS_PFE=có` và vẫn không có `tool/call` | `partial`, quy cho model |

Probe chạy trước session task và chỉ đọc danh sách tool. Một workspace có rule layer
sinh sẵn (ví dụ `~/.dsh/AGENTS.md`) có thể khiến model trả lời "không có tool" dù
harness đã expose; trong trường hợp đó `core` vẫn chạy được nhưng session không phải
bằng chứng về việc model tự chọn tool.

Luật định danh session:

1. Session phải chứa marker trong event `user/message` của chính lần boot đó.
2. Profile chỉ "khớp" khi event `session` hoặc `request/header` ghi tên profile;
   không ghi tên thì ghi `ambiguous`, không đoán từ đĩa.

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
python3 -m unittest discover -s tests -v                # core + knowledge + regression (209 test)
node --test dsh-plugin/tests/plugin.test.mjs            # adapter (16 test)
node --test dsh-plugin/tests/knowledge.test.mjs         # tool tri thức (9 test)
node --test dsh-plugin/tests/lifecycle.test.mjs         # mount/dispose/remount + native Config (8 test)
node --test dsh-plugin/tests/client.test.mjs            # settings UI client (10 test)
node --test dsh-plugin/tests/settings.test.mjs          # binding settings (5 test)
node --test dsh-plugin/tests/arguments.test.mjs         # hợp đồng tham số (9 test)
node --test dsh-plugin/tests/description.test.mjs       # hợp đồng mô tả tool (18 test)
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
tests/                   209 unittest + fixture web/desktop
artifacts/               bằng chứng: samples, review, ui-verification
```

## Giới hạn đã biết

| Giới hạn | Trạng thái |
|---|---|
| Call graph đầy đủ (type-aware) | **CHƯA CÓ**; `calls` trong index chỉ là call site đọc theo lexical |
| Vector ngữ nghĩa thật | **CHƯA CÓ**; backend mặc định là hashing lexical, chỉ tạo candidate |
| Panel UI trong Harness | BLOCKED_UI_API_UNVERIFIED |
| Smoke registry trong `pfe-test` | **ĐÃ CHẠY** trên 0.7.6: 0/0 check (gồm `profile_identity`), 0 tool (`artifacts/review/`) |
| Model tự chọn tool | **CHƯA CHẠY**: profile không có API key; probe gọi registry, không qua model |
| Ngôn ngữ ngoài danh sách pattern | Go, Rust, C#, Kotlin chỉ có symbol/route cơ bản |

Tài liệu tri thức: [references/code-knowledge-schema.json](references/code-knowledge-schema.json) (schema),
[references/code-knowledge-examples.md](references/code-knowledge-examples.md) (fact thật từ index).

Quyết định kiến trúc: [ARCHITECTURE_DECISION.md](ARCHITECTURE_DECISION.md).
Báo cáo: [TEST_REPORT.md](TEST_REPORT.md), [FINAL_REPORT.md](FINAL_REPORT.md),
[UI_VERIFICATION_REPORT.md](UI_VERIFICATION_REPORT.md), [IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md).