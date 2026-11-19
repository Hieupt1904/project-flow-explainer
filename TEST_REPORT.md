# TEST_REPORT

Môi trường: Ubuntu 24.04.4 LTS · Python 3.12.3 · Node v24.22.3 · DSH 0.2.2-rc.2 (chỉ đọc, không cài) · 2026-11-19.

Trạng thái: **toàn bộ test tự động PASS**. Chỉ TASK 4 (smoke trong DSH thật) chưa chạy vì chờ duyệt cài.

## 1. Lệnh và kết quả

| Lệnh | Kết quả |
|---|---|
| `python3 -m unittest discover -s tests -v` | **OK — 32 test** (26 builder + 6 renderer) |
| `node --test dsh-plugin/tests/plugin.test.mjs` | **16 pass / 0 fail** |
| `node --test dsh-plugin/tests/pack.test.mjs` | **2 pass / 0 fail** |
| `python3 -m compileall -q scripts tests` | OK (không output) |
| `python3 scripts/check_repo_policy.py` | `OK: 30 file … không absolute path, nested artifacts hay secret` |
| GitHub Actions run `44505483840` | 4/4 job success; log core: `Ran 32 tests in 0.198s … OK`, policy OK |
| `node dsh-plugin/scripts/pack.mjs` | tarball 35 613 byte, 8 file, có `vendor/core/**` |
| `python3 scripts/render_flow.py assets/example_workflow.json --check-only` | `OK: 8 nodes, 8 edges, entry=welcome` |

## 2. Test core (Python) — 26 case

### Đường đi chuẩn

| Test | Kiểm chứng | Kết quả |
|---|---|---|
| `test_three_files_are_consistent` | 3 file tồn tại, `flow.json` qua `validate()`, `flow_id` khớp HTML, mọi title có trong overview | PASS |
| `test_all_artifacts_live_under_artifacts_flows` | cả 4 output nằm dưới `<repo>/artifacts/flows/` | PASS |
| `test_entry_is_the_export_route` | điểm vào là route `/api/reports/export`, không phải route đầu file | PASS |
| `test_counts_are_reported_and_match_graph` | `counts` khớp số node | PASS |
| `test_deterministic_graph_across_runs` | hai lần chạy cùng input → cùng node/edge | PASS |
| `test_html_is_self_contained` | không script/link/CDN ngoài | PASS |

### Bằng chứng graph (TASK 6)

| Test | Kiểm chứng | Kết quả |
|---|---|---|
| `test_keyword_only_file_is_not_chained_into_the_flow` | decoy `routes/preview.js` + `jobs/export_worker.py` nằm trong `related`, **không** trong `nodes` | PASS |
| `test_every_step_is_reached_by_a_structural_edge` | mọi node (trừ start/end) có cạnh vào với `evidence ∈ {entry,import,call,structure}`; ≥2 cạnh `import` | PASS |
| `test_verified_nodes_have_location_and_membership` | node `verified` có `path` + `start_line` | PASS |
| `test_no_entry_does_not_invent_a_chain` | repo chỉ có route không khớp → node `no-entry`, không có `step-2` | PASS |

### Artifact / repository policy (TASK 2)

| Test | Kiểm chứng | Kết quả |
|---|---|---|
| `test_output_directory_outside_artifacts_flows_is_rejected` | `.`, `src`, `docs`, `tmp`, `../outside`, path tuyệt đối ngoài → `invalid_artifact_root`; không thư mục nào được tạo | PASS |
| `test_repository_root_as_output_directory_is_rejected` | repo root bị từ chối, không sinh `*.html` ở root | PASS |
| `test_symlinked_artifact_directory_is_rejected` | `artifacts` là symlink ra ngoài → `artifact_symlink_escape`, thư mục ngoài rỗng | PASS |
| `test_invalid_slug_is_rejected` | `..`, `a/b`, `../x`, khoảng trắng → `invalid_slug` | PASS |
| `test_existing_slug_is_not_overwritten` | → `artifact_exists` | PASS |
| `test_no_write_before_containment_check` | input sai → `artifacts/` không được tạo | PASS |

### Dữ liệu & provenance (TASK 7)

| Test | Kiểm chứng | Kết quả |
|---|---|---|
| `test_source_files_are_untouched` | mtime+size toàn bộ file nguồn không đổi | PASS |
| `test_secrets_never_reach_output` | secret trong `.env` + `config.py` không có trong 4 output; `secret_lines ≥ 2` | PASS |
| `test_artifacts_contain_no_absolute_workstation_paths` | không `/home/`, `\Users\`, path tạm, `artifacts/…/artifacts` | PASS |
| `test_artifacts_are_not_reanalysed` | lần chạy 2 không tham chiếu `artifacts/` | PASS |
| `test_symlink_escape_is_skipped` | symlink nguồn ra `/etc/hostname` bị đếm và bỏ qua | PASS |

### Lỗi và CLI

| Test | Kết quả |
|---|---|
| `test_missing_request_rejected` → `missing_flow_request` | PASS |
| `test_missing_repository_rejected` → `repository_not_found` | PASS |
| `test_cli_json_mode_is_machine_readable` → stdout 1 object JSON | PASS |
| `test_cli_error_mode_is_machine_readable` → `status:error`, exit 2, **không Traceback** | PASS |

## 3. Test adapter (Node) — 16 case

| Test | Kiểm chứng | Kết quả |
|---|---|---|
| `exports a Cordis plugin shape with one tool` | `name`, `inject=['tools']`, schema required | PASS |
| `end-to-end: builds four artifacts` | 4 file, đường dẫn tuyệt đối, `artifacts_dir` đúng `<repo>/artifacts/flows/<slug>` | PASS |
| `tool result never carries source secrets` | secret không có trong tool result và 4 file | PASS |
| `adapter and direct core produce the same graph` | cùng node/edge với việc gọi CLI trực tiếp | PASS |
| `missing allowedRoots denies every call` | `allowed_roots_unconfigured`, không tạo `artifacts/` | PASS |
| `empty allowedRoots denies every call` | như trên | PASS |
| `repository outside allowedRoots is rejected` | `repository_outside_allowed_roots` | PASS |
| `symlink that escapes allowedRoots is rejected` | `repository_outside_allowed_roots` | PASS |
| `relative and missing repository paths` | `repository_path_relative` / `repository_not_found` | PASS |
| `output_directory must be exactly artifacts/flows` | `.`, `src`, `docs`, `tmp`, `../outside`, repo root → `invalid_artifact_root`; `artifacts/flows` → OK | PASS |
| `symlinked artifacts directory is rejected` | `artifact_symlink_escape` trước khi spawn core (~1 ms) | PASS |
| `abort surfaces as AbortError` | `error.name === 'AbortError'`, không phải `core_failed` | PASS |
| `timeout is reported as core_timeout` | `timeoutMs:1` → `core_timeout`, khác abort | PASS |
| `missing flow request …` | `flow_request_missing` | PASS |
| `unload removes the tool and reload registers it again` | disposer gỡ tool; mount trùng ném lỗi | PASS |
| `rejects invalid configuration at load time` | `timeoutMs`, `allowedRoots`, `coreRoot` sai | PASS |

## 4. Test đóng gói (Node) — 2 case

| Test | Kiểm chứng | Kết quả |
|---|---|---|
| `packed tarball carries the core and works without the checkout` | tarball có 8 entry gồm `vendor/core/**`; giải nén vào thư mục **không có repo xung quanh**; `resolveCoreRoot` trả `source: 'vendor'`; `apply` + `execute` tạo đủ 4 file | PASS |
| `packed manifest keeps metadata and drops checkout-only scripts` | `main`, `exports`, `files`, `engines.dsh`, `dsh.bundle.patch` còn; `scripts` bị bỏ | PASS |

## 5. Chưa kiểm chứng

| Hạng mục | Trạng thái | Lý do |
|---|---|---|
| Tool ACTIVE trong DSH thật | **CHƯA CHẠY** | TASK 4 chờ duyệt cài vào `pfe-test` |
| Gọi tool từ agent DSH | **CHƯA CHẠY** | phụ thuộc bước trên |
| GitHub Actions | Đã chạy: run `44505483840` — core py3.12, adapter node 20/24, manifest: success |
| Repo > 20 000 file | **CHƯA ĐO** | có giới hạn cứng, chưa benchmark |
| Panel UI Harness | `BLOCKED_UI_API_UNVERIFIED` | ngoài phạm vi |

## 6. Regression

Sau mỗi thay đổi: `python3 -m unittest discover -s tests` → `node --test dsh-plugin/tests/*.test.mjs`
→ `python3 scripts/check_repo_policy.py`. Lần chạy cuối: 32 / 16 / 2 pass, policy OK, trên commit
`797401a61f9b`.
