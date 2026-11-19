# FINAL_REPORT — Hybrid Project Flow Explainer × DSH

Trạng thái pass review: **PARTIALLY_COMPLETED**.
Lý do duy nhất: **TASK 4 (smoke trong DSH thật) đang BLOCKED** vì bước cài bundle vào profile
`pfe-test` cần phê duyệt. Mọi blocker khác của pass review đã sửa và có test chứng minh.

| Mục | Giá trị |
|---|---|
| Commit code + test của pass review | `797401a61f9b` |
| Commit báo cáo | commit kế tiếp (chỉ sửa tài liệu) |
| DSH đã kiểm chứng | `0.2.2-rc.2`, profile `web` (chỉ đọc, không cài gì) |
| Python / Node | 3.12.3 / v24.22.3 (và ma trận Node 20 trong CI) |

## 1. Kết quả theo task review

| Task | Nội dung | Trạng thái | Bằng chứng |
|---|---|---|---|
| TASK 1 | Siết `allowedRoots` (deny-by-default) | **DONE** | `dsh-plugin/lib/paths.js` (`resolveAllowedRoots`, `resolveRepository`); 5 test Node: thiếu root, root rỗng, ngoài root, symlink escape, relative path |
| TASK 2 | Artifact chỉ trong `<repo>/artifacts/flows` | **DONE** | `resolveArtifactRoot` + `validate_out_dir`; 5 test Python + 2 test Node cho `.`, `src`, repo root, `../outside`, symlink; test "không ghi trước khi containment check" |
| TASK 3 | Bundle cài độc lập | **DONE** | `dsh-plugin/scripts/pack.mjs` copy core vào `vendor/core` lúc pack; `pack.test.mjs` extract tarball vào thư mục không có checkout, resolve core nguồn `vendor`, chạy end-to-end ra 4 file |
| TASK 4 | Smoke trong DSH thật | **BLOCKED** | Chưa cài; lệnh + phạm vi + rollback đã chuẩn bị ở mục 6, chờ duyệt |
| TASK 5 | Semantics abort | **DONE** | Adapter ném `Error{name:'AbortError'}`; runtime map thành `code: ABORTED` (`dsh-tools/src/pipeline.ts:700-707,770-780`); test phân biệt abort / `core_timeout` / `core_failed` |
| TASK 6 | Độ chính xác graph | **DONE** | Builder tách 3 tầng bằng chứng; chỉ nối theo route/import/call; fixture decoy `routes/preview.js` nằm trong `related`, không thành node; `overview.md` có cột "Bằng chứng thành viên" |
| TASK 7 | Dọn artifact & provenance | **DONE** | Xoá `artifacts/qa/**` lồng nhau; sample regenerate từ HEAD; artifact không còn absolute path; `scripts/check_repo_policy.py` chặn `/home/`, `\Users\`, `artifacts/…/artifacts`, secret-shape |
| TASK 8 | CI + regression | **DONE** | `.github/workflows/ci.yml`; GitHub Actions run `44505483840`: 4/4 job success (core py3.12 · adapter node 20 · adapter node 24 · bundle manifest), log core xác nhận `Ran 32 tests … OK` |

Chi tiết test: [TEST_REPORT.md](TEST_REPORT.md) · UI: [UI_VERIFICATION_REPORT.md](UI_VERIFICATION_REPORT.md) ·
quyết định kiến trúc: [ARCHITECTURE_DECISION.md](ARCHITECTURE_DECISION.md).

## 2. Thay đổi chính của pass review

### Policy đọc (TASK 1)

```text
allowedRoots thiếu/rỗng        → InputError('allowed_roots_unconfigured')   [fail closed]
path ngoài allowedRoots        → InputError('repository_outside_allowed_roots')
symlink trỏ ra ngoài root      → realpath rồi mới kiểm tra → bị từ chối
```

`cordis.patch.yml` **không** mang sẵn `allowedRoots`: cài xong mà chưa cấu hình thì tool từ chối
mọi lần gọi, kèm hint cấu hình. Đây là lựa chọn deny-by-default thay vì "cho phép tất cả".

### Policy ghi (TASK 2)

```text
<repo>/artifacts/flows/<slug>/     ✅
<repo> (root), src, docs, tmp, ../outside, symlink artifacts → artifacts_symlink_escape / invalid_artifact_root ❌
```

Kiểm tra chạy **trước** khi `mkdir`; test `test_no_write_before_containment_check` khẳng định
`artifacts/` không được tạo khi input sai. CLI luôn trả JSON `{status:"error", code, message, hint}`
và không để traceback rơi ra ngoài (`report_error`, exit 3 cho `internal_error`).

### Đóng gói (TASK 3)

`node dsh-plugin/scripts/pack.mjs` → `dist/dsh-project-flow-explainer-0.2.0.tgz` (35 613 byte, 8 file),
bên trong có `vendor/core/scripts/{build_flow.py,render_flow.py}` và `vendor/core/assets/workflow_template.html`.
Thứ tự dò core: `config.coreRoot` → `PFE_CORE_ROOT` → `vendor/core` → thư mục cha (chỉ để dev).

### Bằng chứng của graph (TASK 6)

| Khái niệm | Trước | Sau |
|---|---|---|
| location evidence | `path` + `start_line` | giữ nguyên |
| flow membership | suy ra từ thứ tự điểm số | chỉ `route` / `import` / `call`; cạnh mang `evidence` + ghi chú |
| file chỉ khớp keyword | bị nối vào chuỗi | đưa vào `meta.related`, không thành node |
| độ tin cậy | `verified` cho mọi bước | `verified` = vị trí thật **và** có cạnh chứng minh; còn lại `partial`/`inferred` |

Fixture phản chứng: `tests/fixtures/shop-app/routes/preview.js` có route `/api/legacy/preview` trả CSV,
không được `server.js` import → test `test_keyword_only_file_is_not_chained_into_the_flow` khẳng định
nó nằm trong `related` và không xuất hiện trong `nodes`. `jobs/export_worker.py` (Python worker) cũng vậy.

## 3. Kết quả kiểm chứng

```text
python3 -m unittest discover -s tests -v      → 32 test OK
node --test dsh-plugin/tests/plugin.test.mjs  → 16 pass, 0 fail
node --test dsh-plugin/tests/pack.test.mjs    →  2 pass, 0 fail
python3 scripts/check_repo_policy.py          → OK: 30 file, không absolute path / nested artifacts / secret
python3 -m compileall -q scripts tests        → OK
node dsh-plugin/scripts/pack.mjs              → tarball 8 file, có vendor/core
```

UI (7 ảnh, 3 viewport × 3 sample): 0 console error, 0 request ngoài `file://`, 0 tràn ngang,
0 card chồng; zoom khởi đầu 102% / 94% / 55%.

## 4. Cách dùng

```bash
# CLI (không cần DSH, không cần cấu hình root)
python3 scripts/build_flow.py --repo /duong/dan/repo \
  --request "Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file" --json
# → /duong/dan/repo/artifacts/flows/<slug>/{flow.json,flow.html,overview.md,run.json}
```

Trong DSH, sau khi cài (xem mục 6), tool `project_flow_explain` yêu cầu profile khai báo
`allowedRoots`:

```yaml
config:
  allowedRoots: ['/duong/dan/workspace']
```

## 5. Còn lại / giới hạn

| Mục | Trạng thái |
|---|---|
| Smoke trong DSH thật (cài `pfe-test`, gọi tool, unload/reload, remove) | **BLOCKED** — chờ duyệt |
| Panel UI trong Harness | `BLOCKED_UI_API_UNVERIFIED` (ngoài phạm vi, không đổi) |
| GitHub Actions | Đã chạy: run `44505483840` success toàn bộ 4 job |
| Call graph đa ngôn ngữ đầy đủ | Chưa có; đã ghi rõ trong `limits` của mọi kết quả |
| "Toàn cảnh" 34% với flow dài | Trade-off đã ghi (UI-002) |

## 6. Yêu cầu phê duyệt TASK 4 (chưa chạy)

1. **Lệnh**: `dsh plugin --profile pfe-test add <repo>/dist/dsh-project-flow-explainer-0.2.0.tgz`
2. **Package/profile**: `dsh-project-flow-explainer@0.2.0` → profile `pfe-test` (mới; **không** đụng `web`).
3. **File thay đổi**: tạo `~/.dsh/profiles/pfe-test/{package.json,cordis.patch.yml,node_modules,…}`; thêm 1 dependency + 1 tên trong `dsh.profile.bundles`; thêm row config `allowedRoots` cho bundle này.
4. **Mạng**: có — lần tạo profile cần `pnpm install` bundle nền của template. Tarball tự nó không có dependency.
5. **Install script**: tarball của mình không có `postinstall`; pnpm chỉ chạy bước cài chuẩn của nó.
6. **Rollback**: `dsh plugin --profile pfe-test remove dsh-project-flow-explainer` hoặc `rm -rf ~/.dsh/profiles/pfe-test`. Profile `web` không bị chạm.

Sau khi duyệt, chuỗi kiểm chứng sẽ chạy đúng 10 bước đã nêu trong đề bài (dump-config → boot →
tool xuất hiện → gọi fixture → kiểm 4 file → không có secret → unload/reload → remove).

## 7. Bảng task gốc

| ID | Task | Trạng thái |
|---|---|---|
| HYB-00 | Preflight runtime | DONE |
| HYB-01 | Baseline core | DONE |
| HYB-02 | Architecture decision | DONE (đã cập nhật cho pass review) |
| HYB-03 | Adapter skeleton | DONE |
| HYB-04 | Core runner | DONE (abort/timeout phân biệt) |
| HYB-05 | Tool registration | DONE (in-process) |
| HYB-06 | Security boundary | DONE (allowedRoots + artifact root) |
| HYB-07 | Bundle packaging | DONE (pack + cài độc lập) |
| HYB-08 | Smoke trong DSH | **BLOCKED** |
| HYB-09 | Harness UI | BLOCKED_UI_API_UNVERIFIED |
| HYB-10 | Visual QA | DONE (regenerate từ HEAD) |
| HYB-11 | Tài liệu + bằng chứng | DONE |
