# FINAL_REPORT — 0.3.0

Trạng thái pass 0.3.0: **PARTIAL** — code và test đã pass; smoke registry trong
`pfe-test` cho 0.3.0 và đường model **CHƯA CHẠY** vì cần cài bundle (npm/pnpm trong profile)
và profile không có API key.

| Mục | Giá trị |
|---|---|
| Commit nguồn khi sinh bằng chứng | `bd02147` (commit code 0.3.0); commit kế tiếp chỉ chứa bằng chứng |
| Package version | `0.3.0` |
| `engines.dsh` | `0.2.2-rc.2` |
| DSH đã cài (chưa nâng cấp) | `0.2.2-rc.2`, profile `pfe-test` còn bundle 0.2.2 |
| Python / Node | 3.12.3 / v24.22.3 |
| Tarball | `dsh-project-flow-explainer-0.3.0.tgz` · 84 670 byte · 25 entry · sha256 `b3647435…20bf581c` |
| Test | 116 Python · 16 adapter · 9 knowledge tool · 2 pack — **0 fail** |

## 1. Bảng task

### PHẦN A — ổn định bản hiện tại

| Task | Trạng thái | Lệnh / bằng chứng | Known limitation |
|---|---|---|---|
| A0 Baseline | **DONE** | `artifacts/review/evidence-manifest.json` (sinh bởi `scripts/regen_evidence.py`) | `files_scanned` do `run.json` + result trả về, có test |
| A1 Đồng bộ release evidence | **DONE** | manifest là nguồn duy nhất; báo cáo cũ đã xoá, không sửa tay | không có log 0.2.x giữ lại (đã ghi lý do trong REVIEW_PACKET) |
| A2 Sửa graph evidence | **DONE** | hướng an toàn: bỏ claim call; `pfe/flow.py` ném lỗi nếu ai gắn `evidence=call`; ontology từ chối `calls` thiếu call site | `calls` trong index là lexical call site, không type-aware |
| A3 Sửa error branch | **DONE** | `test_decision_has_no_direct_success_bypass`; `verify` phát hiện bypass | — |
| A4 Giới hạn error detection | **DONE** | window = route body / symbol body; `test_other_route_exception_does_not_create_a_decision` | heuristic theo dòng khai báo, không parse AST |
| A5 Sửa DSH patch doc | **DONE** | `cordis.patch.yml` + plugin README dùng override row; CI đếm đúng 1 row | chưa chạy lại trên profile thật (xem A7) |
| A6 DSH config schema | **PARTIAL** | validate tay trong `normalizeConfig` + `lib/validate.js`; test config sai; profile không boot nửa vời | **không** export `Config` native: profile không resolve `@deepseek-ai/schemastery` → đã ghi trade-off |
| A7 Structured error qua pipeline | **PARTIAL** | code ổn định + hint; kiểm qua adapter in-process và CLI; `core_timeout` ≠ `core_failed` ≠ `ABORTED` | chưa đi qua pipeline runtime thật của DSH trong profile (cần cài bundle) |
| A8 Privacy và path policy | **DONE** | `check_repo_policy.py` bắt home, Users, tmp, tilde, Windows; `test_absolute_path_in_artifact_is_detected`; tool result khai báo `path_visibility` | chưa quét metadata ảnh chụp |
| A9 Atomic artifact write | **DONE** | staging + rename; 3 test (lỗi, retry, 3 luồng cùng slug) | rename cùng filesystem; khác filesystem sẽ lỗi rõ ràng |
| A10 Input validation | **DONE** | `invalid_argument_type`, `*_missing`, `invalid_slug`, `top_k_out_of_range`; 20 test Python + 14 case Node | schema JSON do DSH validate trước, đây là lớp 2 |
| A11 Symlink/Git/root hardening | **DONE** | `classify_source` loại symlink ra ngoài, symlink tới `.env`, symlink tới artifact; git read-only tắt hook/fsmonitor | root quá rộng chỉ bị cảnh báo qua chính sách, không tự từ chối |
| A12 Output contract | **DONE** | `run.json` = `internal-provenance`; test + policy check + README | — |
| A13 Performance/memory | **DONE** | `scripts/bench_index.py`: 2 001 file → 1.42 s, 68 MB; ngân sách byte/file/tổng | chưa benchmark > 20 000 file |

### PHẦN B — lớp tri thức code

| Task | Trạng thái | Bằng chứng | Known limitation |
|---|---|---|---|
| B1 Ontology nhẹ | **DONE** | `pfe/ontology.py` + `references/code-knowledge-schema.json`; 6 test schema khoá hai bên | `returns` khai báo nhưng không phát |
| B2 Tách static facts khỏi flow | **DONE** | `pfe/facts.py` + `pfe/flow.py`; CLI cũ giữ nguyên; core chạy khi xoá `dsh-plugin` | flow vẫn là projection mới, chưa tách thành `pfe/scan.py` riêng |
| B3 Index tăng dần | **DONE** | `pfe/index.py`; 12 test (full/inc/change/delete/rename/version/sensitive/symlink/budget) | rename nhận qua content hash, không dùng git rename detection |
| B4 Exact search FTS5 | **DONE** | `test_symbol_search_finds_the_function`, `test_route_search_finds_the_declaration`, `test_flow_summary_is_searchable` | tokenizer `unicode61` + fold dấu; không có hình thái học |
| B5 Vector tùy chọn | **PARTIAL** | interface backend, model/version lưu, mismatch → tắt, không local → fallback | backend mặc định là hashing bag-of-words, **không** ngữ nghĩa |
| B6 Hybrid retrieval | **DONE** | parse → exact → vector → graph → rerank → pack; `test_exact_match_outranks_vector_candidate`, `test_stale_index_is_reported` | trọng số là heuristic cố định, chưa học từ dữ liệu |
| B7 Thêm 6 DSH tool | **DONE (adapter)** | 7 tool trong `index.js`; 9 test Node end-to-end | registry-runtime 0.3.0 **CHƯA XÁC MINH** |

## 2. Vòng kiểm tra đã chạy

```text
STATIC   compileall (scripts, tests, pfe, tools) · node --check 6 file · JSON schema
UNIT     116 Python · 16 adapter · 9 knowledge · 2 pack
SECURITY allowedRoots missing/empty/outside · symlink escape · symlink .env · symlink artifact
         invalid output dir · invalid slug · malformed args · secret-shape · private path
GRAPH    no call evidence · no decision bypass · selected route only · related not node
         verified có source_ref · evidence khớp loại cạnh
DETERMINISM 2 lần chạy cùng commit: node/edge/counts khớp; index content hash theo file
PACKAGING tarball · manifest · giải nén nơi không có checkout · index + search từ vendor
PROVENANCE commit · version · engines.dsh · tarball · sha256 · test count · generated_at
UI       12 tổ hợp (3 sample × 4 viewport) + tương tác search/click/zoom/fit
```

## 2b. Chạy trên dự án thật trước khi phát hành

Đã chạy trên một dự án desktop riêng tư (27 file Python) bằng
%%BQ%%scripts/run_real_project_check.py%%BQ%%; bản ghi đã scrub path và tên repo:
[20261119-2307-real-project.json](artifacts/review/20261119-2307-real-project.json).

| Bước | Kết quả |
|---|---|
| flow | 12 node (10 verified / 1 partial / 1 inferred), 17 file, 149 ms |
| index full | 26 file · 207 symbol · 10 test · 568 entity · 575 fact |
| index incremental | parse lại 0 file |
| verify | pass (7/7) |

Lỗi thật phát hiện và đã sửa: %%BQ%%tested_by%%BQ%% phát ngược chiều làm %%BQ%%index%%BQ%% lỗi trên repo có thư mục test.
Thêm fixture %%BQ%%tests/fixtures/shop-app/tests/%%BQ%% và 2 regression test. Hướng dẫn dùng:
[USAGE_GUIDE.md](USAGE_GUIDE.md).

## 3. Phân loại kết quả

| Mức | Nội dung |
|---|---|
| **Code đã pass** | 116 unittest, 27 test Node, compileall, node --check, policy, determinism |
| **Runtime đã pass** | adapter in-process (execute qua Context giả) và CLI thật; index/retrieval/impact/verify chạy trên fixture và trên repo này |
| **Model-driven** | **CHƯA CHẠY** — profile không có API key |
| **UI đã pass** | 12 tổ hợp layout sạch (overflow 0, card chồng 0, nhãn đè card 0, console error 0, request ngoài 0) |
| **Static inference** | flow membership theo import/route; `calls` trong index là call site lexical; vector là lexical |
| **Còn BLOCKED** | panel UI Harness (`BLOCKED_UI_API_UNVERIFIED`), smoke registry 0.3.0, model-driven smoke |

## 4. Điều phải nói rõ (không tô hồng)

1. `verified` nghĩa là **xác minh tĩnh vị trí + quan hệ**, không phải đã chạy code.
2. Không có cạnh `call` nào trong flow; index có `calls` nhưng chỉ khi đọc được call site.
3. Vector không ngữ nghĩa. Nó chỉ mở rộng recall; kết quả vẫn phải qua exact/graph.
4. Tool tri thức trả đường dẫn **tương đối**; tool flow trả đường dẫn tuyệt đối và khai báo `host-only`.
5. Smoke registry 0.3.0 chưa chạy: bước cài bundle chạy npm/pnpm trong profile, phải xin phép trước.
6. Báo cáo 0.2.x đã bị thay thế; log cũ đã xoá thay vì sửa số, và điều đó được ghi lại ở đây.