# TEST_REPORT

Môi trường: Ubuntu 24.04.4 LTS · Python 3.12.3 · Node v24.22.3 · DSH 0.2.2-rc.2 (profile `web`, chỉ đọc) · 2026-11-19.

Trạng thái: **toàn bộ test tự động PASS**; phần cài vào profile chưa chạy (chờ duyệt — xem FINAL_REPORT).

## 1. Lệnh và kết quả

| Lệnh | Kết quả |
|---|---|
| `python3 -m unittest discover -s tests -v` | **OK — 22 test** (6 renderer + 16 builder), 0 fail |
| `node --test dsh-plugin/tests/plugin.test.mjs` | **pass 11 / fail 0** |
| `python3 scripts/render_flow.py assets/example_workflow.json --check-only` | `OK: 8 nodes, 8 edges, entry=welcome`, exit 0 |
| `python3 scripts/render_flow.py assets/example_workflow.json --out artifacts/baseline/example_workflow.html` | 32 437 byte, exit 0, không còn `__FLOW_JSON__` |
| `python3 scripts/build_flow.py --repo tests/fixtures/shop-app --request "<flow>" --json` | `status=ok`, 8 node (6 verified / 2 partial), 5 file đọc |

Log: `artifacts/logs/20261119-1627-HYB-01-check-only.log`, `artifacts/logs/20261119-1627-HYB-01-render.log`, `artifacts/logs/20261119-1628-HYB-00-preflight.log`.

## 2. Test core (Python)

| Test | Điều kiện kiểm chứng | Kết quả |
|---|---|---|
| `test_three_files_are_consistent` | 3 file tồn tại; `flow.json` qua `validate()`; `flow_id` khớp cả HTML; mọi node title có trong `overview.md`; không còn placeholder | PASS |
| `test_entry_is_the_export_route` | Điểm vào là `server.js` route `/api/reports/export` (không phải route đầu file) | PASS |
| `test_counts_are_reported_and_match_graph` | `counts` trong kết quả khớp số node thật trong graph | PASS |
| `test_deterministic_graph_across_runs` | Hai lần chạy cùng input → cùng id/title/confidence/refs/edges | PASS |
| `test_html_is_self_contained` | Không `<script src=`, không `<link rel=stylesheet>`, không `cdn.`, không URL ngoài `w3.org` (namespace SVG) | PASS |
| `test_source_files_are_untouched` | mtime+size của toàn bộ file nguồn không đổi sau khi chạy | PASS |
| `test_secrets_never_reach_output` | Secret trong `.env` và `config.py` không xuất hiện trong 4 file output; `sensitive_name ≥ 1`, `secret_lines ≥ 2` | PASS |
| `test_artifacts_are_not_reanalysed` | Lần chạy 2 không tham chiếu `artifacts/` trong `source_refs`; slug khác nhau | PASS |
| `test_missing_request_rejected` | `code=missing_flow_request` | PASS |
| `test_missing_repository_rejected` | `code=repository_not_found` | PASS |
| `test_out_dir_outside_root_rejected` | `code=path_outside_root` | PASS |
| `test_existing_slug_is_not_overwritten` | `code=artifact_exists`, không ghi đè | PASS |
| `test_symlink_escape_is_skipped` | symlink ra `/etc/hostname` bị đếm `symlink_escape ≥ 1`, không đọc | PASS |
| `test_no_evidence_reports_limits_instead_of_inventing_a_flow` | Repo không khớp → node `no-evidence`, `limits` không rỗng, không bịa `step-2` | PASS |
| `test_cli_json_mode_is_machine_readable` | `--json` → stdout đúng 1 object JSON, `status=ok` | PASS |
| `test_cli_error_mode_is_machine_readable` | Lỗi vẫn trả JSON `status=error` + exit 2 | PASS |

## 3. Test adapter (Node)

| Test | Kết quả |
|---|---|
| `exports a Cordis plugin shape with one tool` — `name`, `inject=['tools']`, schema required, `isConcurrencySafe=false` | PASS |
| `end-to-end: builds three artifacts through the core CLI` — 4 file tồn tại, đường dẫn tuyệt đối, `flow_id == slug`, HTML chứa `flow_id` | PASS |
| `tool result never carries source secrets` — secret không có trong tool result và 4 file | PASS |
| `adapter and direct core produce the same graph` — node id/type/title/confidence/paths giống nhau giữa hai đường | PASS |
| `rejects a missing flow request before running the core` — lỗi + hint tiếng Việt | PASS |
| `rejects relative and missing repository paths` | PASS |
| `rejects an artifact directory outside the approved repository` — và không tạo thư mục ngoài | PASS |
| `honours allowedRoots pinning` | PASS |
| `an aborted call stops the child and reports cancellation` | PASS |
| `unload removes the tool and reload registers it again` (disposer + mount lại; mount trùng phải ném lỗi) | PASS |
| `rejects invalid configuration at load time` — `timeoutMs`, `allowedRoots`, `coreRoot` sai | PASS |

## 4. Chưa kiểm chứng (không được tính là PASS)

| Hạng mục | Trạng thái | Lý do |
|---|---|---|
| Tool xuất hiện trong registry của DSH thật | **CHƯA CHẠY** | Chưa cài bundle vào profile nào; chờ duyệt bước `dsh plugin --profile pfe-test add` |
| Gọi tool từ agent DSH thật | **CHƯA CHẠY** | Phụ thuộc bước trên |
| Panel UI trong Harness | **BLOCKED_UI_API_UNVERIFIED** | Ngoài phạm vi MVP; chưa verify register API của slot tại runtime |
| Hành vi trên repo lớn (>20 000 file) | **CHƯA ĐO** | Có giới hạn cứng `MAX_FILES_SCANNED=20000`; chưa benchmark |

## 5. Regression

Sau mỗi lần sửa adapter hoặc builder: chạy lại `python3 -m unittest discover -s tests` + `node --test dsh-plugin/tests/plugin.test.mjs`. Lần cuối: 22 OK / 11 pass, tại commit làm việc `7ab202a` + thay đổi chưa commit.
