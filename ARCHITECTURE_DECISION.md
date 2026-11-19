# ARCHITECTURE_DECISION — Hybrid Project Flow Explainer × DeepSeek Harness

Trạng thái: **CHỐT** (2026-11-19). Hướng: Hybrid — core độc lập + plugin DSH là lớp tích hợp.

## 1. Quyết định của chủ repo (Q1–Q6)

| Câu | Quyết định đã chốt |
|---|---|
| Q1 Đầu vào | Chỉ `local path` trong MVP. Không `git clone`/`fetch`/network. GitHub URL → backlog. Xác minh tồn tại, quyền đọc, chuẩn hóa realpath, chặn symlink thoát root. |
| Q2 Flow request | Bắt buộc, mô tả tiếng Việt thông thường; thiếu thì lỗi validation kèm ví dụ. Không tự chọn journey. Mỗi bước gắn bằng chứng; nhãn `verified`/`partial`/`inferred`/`unknown` (core dùng `unknown`, tài liệu gọi là "chưa xác minh"). Ghi commit + trạng thái dirty của source đã phân tích. |
| Q3 Đầu ra | `flow.json` + `flow.html` + `overview.md` + đường dẫn. Panel trong Harness: **hoãn**, ghi `BLOCKED_UI_API_UNVERIFIED`. |
| Q4 Quyền | A. Repo PFE: được sửa (adapter/test/tài liệu). B. Repo được phân tích: **chỉ đọc**. C. Artifact: `<approved-root>/artifacts/flows/<slug>/`, không ghi đè, loại chính thư mục artifact khỏi input, không commit/push. |
| Q5 Dữ liệu | Coi repo là dữ liệu riêng tư. Tool không network. Loại trừ `.env`, credentials, key, dump, log, thư mục phụ thuộc. Không chép nội dung source vào output/log/screenshot. Tool result chỉ trả trạng thái + đường dẫn + số liệu. |
| Q6 Cài đặt | Profile thử `pfe-test`, không đụng `web`. Chuẩn bị bundle + test trước; xin duyệt một lần trước khi cài. |

## 2. Ranh giới core ↔ adapter

```text
DSH tool (project_flow_explain)
  ↓ validate: absolute path, quyền đọc, allowedRoots, artifact trong repo
dsh-plugin/index.js  (adapter, zero dependency)
  ↓ spawn(python3, [build_flow.py, --repo, R, --request, Q, --json], {shell:false, signal})
scripts/build_flow.py  (CORE: đọc source → graph có bằng chứng)
  ↓ gọi trực tiếp (import) render_flow.validate / assign_positions / render_json
scripts/render_flow.py (CORE: schema + HTML)
  ↓
flow.json · flow.html · overview.md · run.json
  ↓ parse JSON, map sang output schema
DSH tool result (chỉ metadata + đường dẫn)
```

### Core sở hữu

- schema + validation (`scripts/render_flow.py`),
- layout + template HTML (`assets/workflow_template.html`),
- luật evidence/confidence,
- prompt/reference (`references/`, `SKILL.md`),
- CLI: `build_flow.py`, `render_flow.py`,
- test của core.

### Adapter sở hữu

- đăng ký tool + schema input/output,
- kiểm tra đường dẫn/quyền/`allowedRoots`,
- gọi core qua subprocess argv (không shell),
- timeout + huỷ (chuyển `exec.signal` → kill child),
- map kết quả sang output schema,
- lifecycle cleanup (`ctx.effect` huỷ các run đang chạy khi unload).

### Bất biến kiến trúc

1. Xoá `dsh-plugin/` → `python3 scripts/build_flow.py ...` và `render_flow.py` vẫn chạy y như baseline.
2. Adapter không chứa logic validate graph hay render HTML; nó không biết `flow.json` có trường gì ngoài metadata nó đọc.
3. Core không import gì của DSH, không đọc biến môi trường DSH, không phụ thuộc Node.
4. Không sửa DSH core, không sửa file profile bằng tay.

## 3. Điểm khác so với prompt gốc (có lý do kỹ thuật)

| Prompt gốc | Thực tế đã làm | Lý do |
|---|---|---|
| Adapter `src/*.ts` | `index.js` + `lib/*.js` ESM thuần | Profile không resolve được `@deepseek-ai/*` (đã thử: `MODULE_NOT_FOUND`). TS sẽ cần build + dependency; JS thuần chạy trực tiếp, không cần bước build, không tải gói mạng khi cài. |
| `import { defineTool } from '@deepseek-ai/dsh-tools'` | Object `ToolDefinition` dựng tay | `ctx.tools.register(definition)` chỉ yêu cầu `output.schema` + `output.render` (`dsh-tools/src/index.ts:128-153`), không bắt buộc qua `defineTool`. |
| Adapter "chỉ gọi core" | Adapter + **một script core mới** `build_flow.py` | Core cũ chỉ có renderer: chưa có bước "repo → flow.json". Không viết script này thì tool không thể sinh ba file. Đây là bổ sung core, không phải rewrite; renderer và schema giữ nguyên. |
| `plugin_manager` | CLI `dsh plugin --profile pfe-test add` | `plugin_manager` không mount trong profile `web` (không có trong `dsh.profile.bundles`). |
| `cordis_inspect_*` | Đọc source package đã cài + `--dump-config` | Tool inspect không được expose cho phiên; bằng chứng thay thế là source của chính runtime đang chạy. |

## 4. Ánh xạ nhãn tin cậy

| Yêu cầu | Core | Ghi chú |
|---|---|---|
| `verified` | `verified` | Bắt buộc có `source_refs` với `path` + `start_line`; renderer từ chối nếu thiếu. |
| `inferred` | `inferred` | Suy luận trong phạm vi flow được yêu cầu. |
| `unresolved` | `unknown` | Không đổi schema core; tài liệu và UI hiển thị "Chưa xác minh". |

## 5. Chính sách dữ liệu — kiểm tra bằng hành vi

- Không network: adapter chỉ `spawn` python; core chỉ đọc file. Bằng chứng: `performance.getEntriesByType('resource')` ngoài `file://` = rỗng; test `test_html_is_self_contained`.
- Không rò secret: test `test_secrets_never_reach_output` (Python) và `tool result never carries source secrets` (Node) chèn secret vào `.env` + `config.py` rồi khẳng định chuỗi secret không xuất hiện trong 4 file output và trong JSON tool result.
- Không đưa source vào hội thoại model: `output.render` chỉ in đường dẫn + số đếm; `run.json`/`overview.md` chỉ chứa path, số dòng, tên hàm.

## 6. Policy chốt trong pass review

| Chủ đề | Quyết định | Hệ quả |
|---|---|---|
| Đọc | Deny-by-default: `allowedRoots` bắt buộc, so sánh sau `realpath` | Thiếu/rỗng → `allowed_roots_unconfigured`; ngoài root → `repository_outside_allowed_roots` |
| Ghi | Chỉ `<repo>/artifacts/flows/<slug>/` | `invalid_artifact_root` / `artifact_symlink_escape`; kiểm tra trước mọi lệnh ghi |
| Đóng gói | Core đi kèm bundle dưới `vendor/core` (sinh lúc `pack.mjs`) | Bản cài từ tarball không cần checkout; thứ tự dò: config → env → vendor → thư mục cha |
| Huỷ | `Error{name:'AbortError'}` sau khi dừng child | Runtime map `code: ABORTED`; timeout có mã riêng `core_timeout` |
| Bằng chứng | location / membership / role tách riêng | Cạnh mang `evidence`; file chỉ khớp keyword vào `meta.related`, không thành node |
| Provenance | Artifact không chứa đường dẫn tuyệt đối | `repository_name` thay cho path; policy check chặn `/home/`, `\Users\`, nested artifacts |
