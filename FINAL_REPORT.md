# FINAL_REPORT — Hybrid Project Flow Explainer × DSH (MVP)

Trạng thái: **PARTIALLY_COMPLETED** — core, adapter, test và QA HTML xong; **chưa cài** bundle vào profile `pfe-test` vì đang chờ phê duyệt thao tác cài (mục 8).

Ngày: 2026-11-19 · Repo: `/home/hieupt/Documents/Agent-skills-main/project-flow-explainer` · nhánh `main` @ `7ab202a` + thay đổi chưa commit.

## 1. Kiến trúc đã chọn

Hybrid, đúng như đã chốt: `core (Python) ← adapter (JS) ← DSH`. Chi tiết và bất biến: [ARCHITECTURE_DECISION.md](ARCHITECTURE_DECISION.md).

```text
tool project_flow_explain
  → dsh-plugin/index.js  (validate path, allowedRoots, artifact containment)
  → spawn python3 scripts/build_flow.py --repo R --request Q --json
  → core: graph có bằng chứng → render_flow.validate/assign_positions/render_json
  → artifacts/flows/<slug>/{flow.json, flow.html, overview.md, run.json}
  → tool result: status + đường dẫn + counts + source_version + limits/warnings
```

## 2. Thay đổi trong repo

| File | Loại | Nội dung |
|---|---|---|
| `scripts/build_flow.py` | mới (core) | Analyzer: quét source, khớp facet theo yêu cầu tiếng Việt, dựng graph có `source_refs` path+line, gọi renderer, ghi 4 file. 0 dependency, không network. |
| `dsh-plugin/index.js` | mới (adapter) | Tool `project_flow_explain`, schema input/output, gọi core, map kết quả, `ctx.effect` dọn run đang chạy. |
| `dsh-plugin/lib/paths.js` | mới | `resolveRepository`, `resolveArtifactRoot`, `resolveCoreRoot`, `isInside` — realpath + containment. |
| `dsh-plugin/lib/core-runner.js` | mới | `spawn` argv array, `shell:false`, env tối thiểu, cap output, kill theo `signal`/timeout. |
| `dsh-plugin/package.json`, `cordis.patch.yml` | mới | Bundle manifest theo format runtime (`dsh.bundle.patch`), 1 row insert. |
| `dsh-plugin/tests/plugin.test.mjs` | mới | 11 test, fake Context có kiểm tra trùng tên tool. |
| `tests/test_build_flow.py` | mới | 16 test cho analyzer + chính sách bảo mật. |
| `tests/fixtures/shop-app/` | mới | Fixture Express + job Python + `.env` (không commit) để test. |
| `assets/workflow_template.html` | sửa | `initialView()` fit cả chiều ngang (UI-001). Không đổi schema/HTML API. |
| `README.md`, `SKILL.md` | sửa | Thêm CLI `build_flow.py`, phần adapter DSH, chính sách dữ liệu. |

Không sửa: `scripts/render_flow.py`, `references/*` (thêm link ở SKILL.md), `tests/test_render_flow.py`, DSH core.

## 3. Baseline so với hiện tại

| Hạng mục | Baseline (trước) | Hiện tại |
|---|---|---|
| `python -m unittest discover -s tests` | 6 test OK | **22 test OK** |
| Renderer sample | 32 437 byte, 8 node | không đổi |
| Sinh `flow.json` từ repo | không có | 8 node / 5 file (fixture), 7 node (self-repo) |
| Adapter test | không có | **11 pass** |
| QA HTML 3 viewport | chưa có | pass, 0 console error, 0 request ngoài |

## 4. API DSH đã dùng và bằng chứng xác minh

| API | Cách xác minh |
|---|---|
| `ctx.tools.register(definition)` nhận object có `output.schema` + `output.render`, trả disposer theo lifecycle | `dsh-tools/src/index.ts:128-153` |
| Trùng tên tool bị chặn | `dsh-tools/src/index.ts:69-70` |
| `defineTool` là helper, không bắt buộc | `dsh-tools/src/schema.ts:483-580` |
| Plugin shape `export const name/inject` + `apply(ctx, config)` | `dsh-tool-cordis/src/index.ts:9-21`, `dsh-action-cards/src/index.ts:161-196` |
| `ctx.effect(fn)` — body chạy ngay, trả disposer | `cordis/src/fiber.ts:421-424` |
| `exec.signal` là `AbortSignal` bắt buộc | `dsh-tools/src/contracts.ts:201-202` |
| `timeoutMs` phải dương hữu hạn | `dsh-tools/src/schema.ts:576` |
| Bundle `dsh.bundle.patch` + row `- insert: [{id, name, config}]` | `dsh-acp-app/package.json`, `dsh-experimental-session-titles-bundle/cordis.patch.yml` |
| Profile gắn bundle qua `dependencies: link:` + `dsh.profile.bundles` | `~/.dsh/profiles/web/package.json` (`@local/mcp-web-api`) |
| Không resolve được `@deepseek-ai/*` từ profile | `createRequire('/home/hieupt/.dsh/profiles/web/package.json').resolve(...)` → `MODULE_NOT_FOUND` |

Tool đã đăng ký (trong test): **`project_flow_explain`**. Bundle manifest: `dsh-plugin/package.json` → `dsh-plugin/cordis.patch.yml`.

## 5. Kết quả kiểm chứng

Chi tiết: [TEST_REPORT.md](TEST_REPORT.md), [UI_VERIFICATION_REPORT.md](UI_VERIFICATION_REPORT.md).

- **Core**: 22 test PASS; gồm chặn traversal, chặn ghi đè slug, symlink escape, secret không rò, source không bị sửa, artifact không bị phân tích lại, không bịa flow khi không có bằng chứng.
- **Adapter**: 11 test PASS; gồm equivalence (adapter vs core trực tiếp cho cùng graph), abort, unload/reload không đăng ký trùng.
- **UI**: 8 tổ hợp case × viewport PASS; sửa 1 lỗi layout thật (UI-001), 1 trade-off được ghi nhận (UI-002).
- **Chưa chạy**: cài vào profile và gọi tool từ DSH thật → xem mục 8.

## 6. Cách dùng

### CLI (không cần DSH)

```bash
python3 scripts/build_flow.py \
  --repo /duong/dan/repo \
  --request "Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file" \
  --json
```

Kết quả trong `<repo>/artifacts/flows/<slug>/`: `flow.json`, `flow.html`, `overview.md`, `run.json`. Mở `flow.html` bằng trình duyệt, không cần mạng.

### Qua DSH (sau khi cài)

```text
project_flow_explain(
  repository_path = "/duong/dan/repo",
  flow_request    = "mô tả flow bằng tiếng Việt",
  output_directory= "artifacts/flows",   # tùy chọn, phải nằm trong repo
  slug            = "tuy-chon"
)
```

## 7. Phần còn thiếu / giới hạn

| Mục | Trạng thái |
|---|---|
| Cài bundle vào `pfe-test` và gọi tool thật | **CHƯA CHẠY** — chờ duyệt (mục 8) |
| Panel UI trong Harness | `BLOCKED_UI_API_UNVERIFIED`, ngoài MVP |
| Hỗ trợ GitHub URL | backlog |
| Phân tích sâu call-graph đa ngôn ngữ | heuristic hiện tại: route/symbol/facet; ghi rõ `partial`/`inferred` |
| "Toàn cảnh" 34% với flow dài | trade-off, đã ghi UI-002 |

## 8. Yêu cầu phê duyệt bước cài (chưa thực hiện)

1. **Lệnh và thư mục chạy**: `dsh plugin --profile pfe-test add /home/hieupt/Documents/Agent-skills-main/project-flow-explainer/dsh-plugin` (chạy từ `$HOME`).
2. **Package/bundle**: `dsh-project-flow-explainer@0.1.0`, cài vào profile **`pfe-test`** (profile mới, không đụng `web`).
3. **File/dependency thay đổi**: tạo `~/.dsh/profiles/pfe-test/package.json` + `cordis.patch.yml` + `node_modules`; thêm 1 dòng `dependencies` dạng `link:` và 1 tên trong `dsh.profile.bundles`.
4. **Cần mạng**: có — lần tạo profile mới cần `pnpm install` các bundle nền của template; bản thân plugin không có dependency ngoài.
5. **Install/lifecycle script**: không có `postinstall` trong package của chúng ta; chỉ pnpm thực hiện bước cài chuẩn. Nếu pnpm báo script của bên thứ ba, sẽ dừng và báo lại.
6. **Gỡ / khôi phục**: `dsh plugin --profile pfe-test remove dsh-project-flow-explainer`, hoặc xoá `~/.dsh/profiles/pfe-test`. Profile `web` không bị chạm tới nên rủi ro ảnh hưởng bằng 0.

Sau khi được duyệt, các bước chạy thử: `dsh --profile pfe-test --dump-config | grep project-flow` → boot profile → gọi tool với fixture → kiểm 3 file → tắt/bật lại plugin → xác nhận tool biến mất/xuất hiện lại, không còn process treo.

## 9. Bảng task

| ID | Task | Trạng thái | Bằng chứng |
|---|---|---|---|
| HYB-00 | Preflight runtime | DONE | `artifacts/logs/20261119-1628-HYB-00-preflight.log` |
| HYB-01 | Baseline core | DONE | log HYB-01, `artifacts/baseline/example_workflow.html` |
| HYB-02 | Architecture decision | DONE | `ARCHITECTURE_DECISION.md` |
| HYB-03 | Adapter skeleton | DONE | `dsh-plugin/` |
| HYB-04 | Core runner | DONE | `dsh-plugin/lib/core-runner.js` + test abort/timeout |
| HYB-05 | Tool registration | DONE (in-process) | `plugin.test.mjs` mount + execute |
| HYB-06 | Security boundary | DONE | 8 test path/secret + `test_source_files_are_untouched` |
| HYB-07 | Bundle packaging | DONE (chưa cài) | `package.json`, `cordis.patch.yml` |
| HYB-08 | Smoke trong DSH thật | **BLOCKED** | chờ duyệt cài |
| HYB-09 | Harness UI | BLOCKED_UI_API_UNVERIFIED | ngoài MVP |
| HYB-10 | Visual QA | DONE | `UI_VERIFICATION_REPORT.md` + 15 ảnh |
| HYB-11 | Tài liệu + bằng chứng | DONE | bộ 6 báo cáo + `artifacts/` |
