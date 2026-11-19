# ARCHITECTURE_DECISION — Hybrid Project Flow Explainer × DeepSeek Harness

Trạng thái: **CHỐT** (cập nhật 2026-11-19 cho 0.3.0). Hướng: Hybrid — core độc lập + adapter DSH.

## 0. Bổ sung 0.3.0: vì sao thêm lớp tri thức code

Flow diagram chỉ trả lời "một luồng đi qua đâu". Agent sửa code cần ba câu khác:
"chỗ này nằm ở đâu", "sửa nó ảnh hưởng gì", "sửa xong kiểm tra bằng gì". Ba câu đó cần
fact ổn định, không phải một hình vẽ. Vì vậy core được tách thành:

```text
pfe.facts      đọc source -> fact tĩnh (file, symbol, route, import, call site, error site)
pfe.ontology   từ vựng entity/relation/evidence/confidence + validate
pfe.knowledge  fact -> entity + fact có bằng chứng
pfe.index      SQLite + FTS5, tăng dần, cache parse theo content hash
pfe.vectors    backend local-only, mặc định hashing; không có thì fallback FTS
pfe.retrieval  parse query -> exact -> vector candidate -> graph -> rerank -> pack
pfe.impact     thay đổi -> flow/route/symbol/test/risk
pfe.verify     graph/artifact/UI tĩnh/privacy/test mapping
pfe.flow       projection: chọn một luồng từ fact
pfe.emit       overview + contract public/internal + ghi atomic
```

Quyết định kỹ thuật, kèm lý do:

| Quyết định | Lý do | Hệ quả |
|---|---|---|
| SQLite + FTS5 thay vì Neo4j/Qdrant | zero dependency, chạy offline, một file, backup bằng copy | không có truy vấn graph phân tán; đổi lại không cần service |
| Flow là **projection** của fact, không phải nguồn riêng | một nguồn sự thật, flow và search không thể lệch nhau | flow_request vẫn bắt buộc; không tự chọn luồng |
| Index cache parse theo content hash | "file không đổi thì không parse lại" đo được | file đổi 1 byte → parse lại cả file đó, không parse cả repo |
| Vector mặc định là hashing bag-of-words, local | không có embedding runtime local trong môi trường này; gọi remote bị cấm | vector chỉ tạo candidate; kết quả vector không bao giờ `verified` |
| Ghi artifact qua staging rồi rename | lỗi giữa chừng không để lại artifact dở | rename là kiểm tra concurrency; hai lời gọi cùng slug chỉ một thắng |
| `run.json` là internal provenance | cần dấu vết lần chạy nhưng không được giả làm public output | contract ghi trong file và trong test |
| `calls` chỉ phát khi có call site | "call graph" từ import là bịa | ontology từ chối fact `calls` thiếu `call_site` |

## 1. Quyết định của chủ repo (Q1–Q6)

| Câu | Quyết định đã chốt |
|---|---|
| Q1 Đầu vào | Chỉ local absolute path. Không clone/fetch/network. GitHub URL nằm ở backlog. Chuẩn hoá realpath, chặn symlink thoát root. |
| Q2 Flow request | Bắt buộc, mô tả tiếng Việt thông thường; thiếu thì lỗi validation kèm ví dụ. Không tự chọn journey. Mỗi bước gắn bằng chứng; nhãn `verified`/`partial`/`inferred`/`unknown`. Ghi commit + trạng thái dirty của source. |
| Q3 Đầu ra | `flow.json` + `flow.html` + `overview.md` (public) + `run.json` (internal provenance). Panel trong Harness: **hoãn**, ghi `BLOCKED_UI_API_UNVERIFIED`. |
| Q4 Quyền | A. Repo PFE: được sửa. B. Repo được phân tích: **chỉ đọc**. C. Artifact: `<repo>/artifacts/flows/<slug>/`, không ghi đè, loại chính thư mục artifact khỏi input. |
| Q5 Dữ liệu | Repo là dữ liệu riêng tư. Không network. Loại `.env`, credential, key, dump, log, dependency. Không chép nội dung source vào output/log. Tool result chỉ trả trạng thái + đường dẫn + số liệu. |
| Q6 Cài đặt | Profile thử `pfe-test`, không đụng `web`. Cài bundle cần npm/pnpm trong profile → phải xin phép trước bước cài. |

## 2. Ranh giới core ↔ adapter

```text
DSH tool (7 tool)
  ↓ validate: absolute path, allowedRoots, artifact root, kiểu tham số
dsh-plugin/index.js + lib/tools.js   (adapter, zero dependency)
  ↓ spawn(python, [script, ...args], {shell:false, signal})
tools/pfe_cli.py                     (một object JSON cho mỗi subcommand)
  ↓ gọi trực tiếp (import)
pfe.*                                (CORE: facts, ontology, index, retrieval, flow)
  ↓
flow.json · flow.html · overview.md · run.json(internal) · .pfe/index/knowledge.sqlite
```

### Core sở hữu

- schema + validation (`scripts/render_flow.py`),
- layout + template HTML (`assets/workflow_template.html`),
- luật evidence/confidence,
- ontology + index + retrieval + impact + verify,
- prompt/reference (`references/`, `SKILL.md`),
- CLI (`scripts/build_flow.py`, `tools/pfe_cli.py`),
- toàn bộ test của core.

### Adapter sở hữu

- đăng ký tool + JSON schema input/output,
- kiểm tra đường dẫn/quyền/`allowedRoots`,
- gọi core qua subprocess argv (không shell),
- timeout + huỷ (chuyển `exec.signal` → kill child),
- map kết quả sang output schema, gắn nhãn `path_visibility`,
- lifecycle cleanup (`ctx.effect` huỷ run đang chạy khi unload).

### Bất biến kiến trúc

1. Xoá `dsh-plugin/` → CLI Python và toàn bộ unittest vẫn chạy.
2. Adapter không chứa logic validate graph, render HTML, hay tính điểm retrieval.
3. Core không import DSH, không đọc biến môi trường DSH, không phụ thuộc Node.
4. Không sửa DSH core, không sửa file profile bằng tay.

## 3. Điểm khác so với prompt gốc (có lý do kỹ thuật)

| Prompt gốc | Thực tế | Lý do |
|---|---|---|
| Adapter `src/*.ts` | `index.js` + `lib/*.js` ESM thuần | Profile không resolve được `@deepseek-ai/*`; TS cần build + dependency |
| `defineTool` từ package | Object `ToolDefinition` dựng tay | `ctx.tools.register` chỉ cần `output.schema` + `output.render` |
| Neo4j / Qdrant | SQLite + FTS5 + bảng vector | Không service, không network, một file |
| Embedding model thật | Hashing bag-of-words local | Không có runtime embedding local; gọi remote bị cấm |
| Panel UI | Hoãn | Chưa xác minh register API của slot |

## 4. Ánh xạ nhãn tin cậy

| Yêu cầu | Core | Ghi chú |
|---|---|---|
| `verified` | `verified` | Bắt buộc `source_refs` có `path` + `start_line`; renderer từ chối nếu thiếu |
| `inferred` | `inferred` | Suy luận trong phạm vi flow được yêu cầu |
| `unresolved` | `unknown` | Không đổi schema; UI hiển thị "Chưa xác minh" |
| `runtime_verified` | chỉ khi có `evidence.runtime` | Lớp tĩnh không bao giờ sinh nhãn này |

## 5. Chính sách dữ liệu — kiểm tra bằng hành vi

- Không network: adapter chỉ spawn python; core chỉ đọc file. Bằng chứng: bộ đếm resource của trình duyệt ngoài `file://` rỗng trên 12 tổ hợp UI, và test `test_html_is_self_contained`.
- Không rò secret: test Python `test_secrets_never_reach_output`, `test_secret_values_never_reach_the_graph`, test Node `tool result never carries source secrets`. File chứa secret-shaped line **không** vào index.
- Không đưa source vào hội thoại model: `output.render` in đường dẫn + số đếm; search trả path/symbol/line; snippet chỉ khi `include_snippets` bật rõ.

## 6. Policy chốt

| Chủ đề | Quyết định | Hệ quả |
|---|---|---|
| Đọc | Deny-by-default, so sánh sau `realpath` | thiếu/rỗng → `allowed_roots_unconfigured`; ngoài root → `repository_outside_allowed_roots` |
| Ghi | Chỉ `<repo>/artifacts/flows/<slug>/`, staging + rename | `invalid_artifact_root` / `artifact_symlink_escape` / `artifact_exists` |
| Index | `<repo>/.pfe/index/knowledge.sqlite`, đã gitignore | không commit index; file secret không vào index |
| Đóng gói | Core trong `vendor/core/{scripts,assets,tools,pfe}` | cài từ tarball chạy được không cần checkout |
| Huỷ | `Error{name:'AbortError'}` | runtime map `ABORTED`; timeout có mã riêng `core_timeout` |
| Bằng chứng | location / membership / role tách riêng | cạnh mang `evidence`; file keyword-only vào `meta.related` |
| Provenance | artifact không chứa absolute path | `check_repo_policy.py` chặn home, Users, tmp, Documents, Windows user path |
