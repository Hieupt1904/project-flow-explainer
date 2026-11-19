# TEST_REPORT

Sinh từ lần chạy thật trên commit `bd02147` (code 0.3.0); commit kế tiếp chỉ chứa bằng chứng.
Máy đọc: [artifacts/review/evidence-manifest.json](artifacts/review/evidence-manifest.json).
Môi trường: Ubuntu 24.04 · Python 3.12.3 · Node v24.22.3 · DSH 0.2.2-rc.2 · 2026-11-19.

## 1. Tổng hợp

| Lệnh | Kết quả | Log |
|---|---|---|
| `python3 -m unittest discover -s tests` | **116 test OK** (35 core + 47 knowledge + 20 evidence + 14 schema/consistency) | `artifacts/review/*-python-tests.log` |
| `node --test dsh-plugin/tests/plugin.test.mjs` | **16 pass / 0 fail** | `*-node-adapter.log` |
| `node --test dsh-plugin/tests/knowledge.test.mjs` | **9 pass / 0 fail** | `*-node-knowledge.log` |
| `node --test dsh-plugin/tests/pack.test.mjs` | **2 pass / 0 fail** | `*-node-pack.log` |
| `python3 -m compileall -q scripts tests pfe tools` | OK, không output | `*-compileall.log` |
| `node --check` cho 6 file adapter | OK | manifest `static.node_syntax` |
| `python3 scripts/check_repo_policy.py` | `OK` — không absolute path, nested artifact, secret-shape; `run.json` đều khai báo internal | `*-policy.log` |
| `node dsh-plugin/scripts/pack.mjs` | `dsh-project-flow-explainer-0.3.0.tgz`, 25 entry, 84 670 byte | `*-pack-build.log` |
| `python3 scripts/bench_index.py --files 2000` | xem mục 6 | `*-bench.json` |

Tarball:

| Mục | Giá trị |
|---|---|
| Tên | `dsh-project-flow-explainer-0.3.0.tgz` |
| Byte | 84 670 |
| SHA-256 | `b3647435f63c1d7b98259a84740cecf11b6b3034e2634e1c9e8669e220bf581c` |
| Entry | 25 (gồm `vendor/core/{scripts,assets,tools,pfe}`) |

## 2. Core Python — 35 test

### Đường đi chuẩn

| Test | Kiểm chứng |
|---|---|
| `test_three_files_are_consistent` | 3 file public tồn tại, `flow.json` qua `validate()`, `flow_id` khớp HTML, title có trong overview |
| `test_all_artifacts_live_under_artifacts_flows` | cả 4 output nằm dưới `<repo>/artifacts/flows/` |
| `test_entry_is_the_export_route` | điểm vào là `/api/reports/export` |
| `test_counts_are_reported_and_match_graph` | `counts` khớp số node |
| `test_deterministic_graph_across_runs` | hai lần chạy cùng input → cùng node/edge |
| `test_html_is_self_contained` | không script/link/CDN ngoài |

### Policy artifact và repository

| Test | Kiểm chứng |
|---|---|
| `test_output_directory_outside_artifacts_flows_is_rejected` | `.`, `src`, `docs`, `tmp`, `../outside` → `invalid_artifact_root`, không tạo thư mục |
| `test_symlinked_artifact_directory_is_rejected` | `artifacts` là symlink ra ngoài → `artifact_symlink_escape` |
| `test_existing_slug_is_not_overwritten` | → `artifact_exists` |
| `test_no_write_before_containment_check` | input sai → chưa tạo `artifacts/` |
| `test_secrets_never_reach_output` | secret của fixture không có trong 4 file |
| `test_artifacts_contain_no_absolute_workstation_paths` | không home, tmp hay Windows path; không nested artifacts |

## 3. Bằng chứng graph — 20 test

| Test | Kiểm chứng |
|---|---|
| `test_no_edge_claims_call_without_call_site` | không cạnh `evidence=call` nào; `meta.evidence_model.call_edges == false` |
| `test_verified_never_means_runtime` | mô tả `verified` chứa "KHÔNG phải chạy runtime" |
| `test_decision_has_no_direct_success_bypass` | mọi cạnh vào decision không đi kèm cạnh success trực tiếp |
| `test_error_node_is_reachable_from_the_decision` | error node có cạnh `kind=error` |
| `test_decision_points_inside_the_selected_route` | decision trỏ đúng dòng `try` trong route được chọn |
| `test_other_route_exception_does_not_create_a_decision` | route khác có `try/catch` → không sinh decision |
| `test_related_file_is_never_a_node` | file keyword-only không nằm trong node |
| `test_failure_leaves_no_partial_artifact` | lỗi giữa chừng → không có slug, không còn `.staging-*` |
| `test_concurrent_same_slug_has_one_winner` | 3 luồng cùng slug → 1 thành công, 2 `artifact_exists` |
| `test_run_json_is_internal_provenance` | `contract=internal-provenance`, public không chứa `run.json` |
| `test_files_scanned_is_reported_and_never_null` | `files_scanned` là số nguyên > 0 và khớp `run.json` |
| `test_budget_note_reaches_limits` | ngân sách bị cắt → ghi vào `limits` và `assumptions` |
| `test_bad_request_values` / `test_bad_repository_values` / `test_bad_optional_values` | mã lỗi ổn định cho `None`, số, object, chuỗi rỗng |
| `test_two_runs_agree_on_nodes_edges_and_counts` | determinism |

## 4. Lớp tri thức — 45 test

| Nhóm | Test tiêu biểu | Kiểm chứng |
|---|---|---|
| Ontology | `test_call_without_call_site_is_rejected` | `calls` thiếu `call_site` → `evidence_kind_mismatch` |
| Ontology | `test_observed_without_location_is_rejected` | `observed` phải có path + line |
| Ontology | `test_runtime_confidence_requires_runtime_evidence` | không có bằng chứng chạy thì cấm `runtime_verified` |
| Ontology | `test_declared_only_relation_is_not_emittable` | `returns` bị từ chối |
| Ontology | `test_structural_never_replaces_observed` | observed thắng, bản yếu ghi vào `contradicted` |
| Knowledge | `test_call_facts_carry_a_call_site_line` | mọi fact `calls` có `evidence.kind=call_site` |
| Knowledge | `test_relation_kinds_match_entity_types` | subject/object đúng loại cho từng relation |
| Index | `test_full_then_incremental_reuses_parsed_files` | incremental parse 0 file |
| Index | `test_changed_file_is_reparsed` | sửa 1 file → parse đúng 1 file |
| Index | `test_deleted_file_is_removed` | xoá file → entity biến mất |
| Index | `test_renamed_file_is_reported` | rename → cặp `from/to` |
| Index | `test_index_version_change_forces_rebuild` | đổi version → rebuild full |
| Index | `test_sensitive_files_are_not_indexed` | `.env` và file chứa secret không vào index |
| Index | `test_symlink_to_env_is_not_indexed` | symlink trỏ `.env` bị loại |
| Index | `test_symlink_to_artifacts_is_not_indexed` | symlink trỏ artifact bị loại |
| Index | `test_budget_truncation_is_reported` | vượt ngân sách → note |
| Index | `test_two_walkers_classify_the_same_files` | hai walker không lệch nhau |
| Search | `test_symbol_search_finds_the_function` | `export_report` → `exportReport` |
| Search | `test_route_search_finds_the_declaration` | `/api/reports/export` → route |
| Search | `test_vietnamese_query_is_bridged_to_code_terms` | "xuất báo cáo ra excel" → symbol/route |
| Search | `test_flow_summary_is_searchable` | query tiếng Việt tìm được flow đã render |
| Search | `test_exact_match_outranks_vector_candidate` | exact > 1.0 trong khi vector không thể vượt |
| Vector | `test_vector_result_is_never_verified` | `verified=false`, `confidence=inferred` |
| Vector | `test_embedding_model_mismatch_disables_vectors` | đổi model → `embedding_model_mismatch` |
| Vector | `test_offline_backend_is_rejected` | backend không local → từ chối |
| Impact | `test_route_file_is_high_risk` | file có route → risk high |
| Impact | `test_unknown_file_is_reported_not_guessed` | file lạ → `unknown_files`, không đoán |
| Verify | `test_fabricated_call_edge_is_detected` | gắn `evidence=call` không có call site → `graph_evidence=fail` |
| Verify | `test_decision_bypass_is_detected` | thêm cạnh bypass → fail |
| Verify | `test_absolute_path_in_artifact_is_detected` | path máy cá nhân trong artifact → `privacy=fail` |
| Verify | `test_no_artifact_means_blocked_not_pass` | không có artifact → `blocked%%, verdict `partial` |

## 5. Adapter và đóng gói — 27 test Node

| Test | Kiểm chứng |
|---|---|
| `registers the flow tool and the six knowledge tools` | 7 tool, không trùng tên |
| `every knowledge tool declares a strict schema with a renderer` | `additionalProperties:false`, có `render` |
| `index → search → context pack → impact → verify → refresh end to end` | chuỗi đầy đủ, không lộ secret, không trả absolute path |
| `search reports index_missing … before indexing` | mã ổn định |
| `knowledge tools enforce allowedRoots deny-by-default` | thiếu root và ngoài root |
| `malformed arguments produce stable codes, never a TypeError` | 14 trường hợp tham số sai |
| `a core timeout keeps its own code` | `core_timeout` khác business failure |
| `abort surfaces as AbortError from a knowledge tool too` | giữ identity huỷ |
| `packed tarball carries the core and works without the checkout` | cài từ tarball, chạy index + search |
| `packed manifest keeps metadata and drops checkout-only scripts` | manifest gọn, đúng engine |

## 6. Benchmark index (A13)

`python3 scripts/bench_index.py --files 2000 --json`:

| Chỉ số | Giá trị |
|---|---|
| File sinh ra | 2 001 |
| Source | 942 071 byte |
| Scan | 637 ms |
| Index full | 1 422 ms |
| Index incremental | 471 ms |
| File parse lại (incremental) | 0 |
| Entity / fact | 20 003 / 20 001 |
| DB | 15 548 416 byte |
| Peak RSS | 68.2 MB |
| Ngân sách | 20 000 file · 32 MB source · 256 KB/file |

Đo bằng `/proc/self/status:VmHWM`, không dùng `ru_maxrss` (giá trị này bị kế thừa
high-water mark của tiến trình cha trong sandbox và cho số sai).

## 6b. Chạy trên dự án thật (không phải fixture)

Dự án desktop riêng tư, 27 file Python, git %%BQ%%3e852be66fa7%%BQ%%. Bản ghi đã loại path và tên repo:
[20261119-2307-real-project.json](artifacts/review/20261119-2307-real-project.json).

| Bước | Kết quả |
|---|---|
| flow | %%BQ%%ok%%BQ%%, 12 node (10 verified / 1 partial / 1 inferred), 17 file quét, 166 458 byte, 149 ms |
| index full | 26 file · 207 symbol · 10 test · 568 entity · 575 fact · 157 ms |
| index incremental | parse lại **0** file, dùng lại 26, 32 ms |
| search %%BQ%%write_xls%%BQ%% | top-1 đúng hàm ghi Excel, %%BQ%%observed%%BQ%%, score 1.3 |
| context pack | 4 file nên đọc, 0 entry point (dự án desktop, không bịa route) |
| verify | %%BQ%%pass%%BQ%% — 7/7 check, gồm %%BQ%%test_mapping%%BQ%% |

### Lỗi thật do lần chạy này phát hiện

| Lỗi | Triệu chứng | Sửa | Test khoá |
|---|---|---|---|
| %%BQ%%tested_by%%BQ%% phát ngược chiều | %%BQ%%index%%BQ%% trả %%BQ%%internal_error: OntologyError: tested_by không nhận subject test%%BQ%% trên repo có thư mục test | phát theo chiều %%BQ%%file:nguồn → test%%BQ%% | %%BQ%%test_tested_by_points_from_source_to_test%%BQ%%, %%BQ%%test_impact_lists_the_related_test%%BQ%% |

Fixture cũ không có thư mục test nên không lộ lỗi này. Đây là lý do phải chạy trên dự án thật trước khi phát hành.

### Kết quả search theo loại query

| Query | Top-1 | Ghi chú |
|---|---|---|
| %%BQ%%export_report%%BQ%% | %%BQ%%function exportReport%%BQ%% (1.25) | exact symbol |
| %%BQ%%/api/reports/export%%BQ%% | %%BQ%%route /api/reports/export%%BQ%% (1.4) | exact route |
| %%BQ%%xuất báo cáo ra excel%%BQ%% | %%BQ%%exportReport%%BQ%% / %%BQ%%loadReportRows%%BQ%% | bridge tiếng Việt |
| câu dài 12–16 từ | trả kèm cảnh báo **Query dài** | hướng dẫn dùng flow thay thế |

## 7. Chưa kiểm chứng

| Hạng mục | Trạng thái | Lý do |
|---|---|---|
| Smoke registry 0.3.0 trong `pfe-test` | **CHƯA CHẠY** | cài bundle chạy npm/pnpm trong profile → phải dừng trước bước cài và xin phép |
| Model tự chọn tool | **CHƯA CHẠY** | profile không có API key |
| Panel UI Harness | `BLOCKED_UI_API_UNVERIFIED` | chưa xác minh register API của slot |
| Embedding ngữ nghĩa | **CHƯA CÓ** | không có runtime local; mặc định hashing bag-of-words |
| Call graph type-aware | **CHƯA CÓ** | chỉ có call site lexical |
| `calls` xuyên file qua alias/namespace | **CHƯA XÁC MINH** | resolver chỉ nhận tên symbol duy nhất |