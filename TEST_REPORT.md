# TEST_REPORT

Sinh từ lần chạy thật trên commit nguồn và bằng chứng trong
[artifacts/review/evidence-manifest.json](artifacts/review/evidence-manifest.json).
Môi trường: Ubuntu 24.04 · Python 3.12.3 · Node v24.22.3 · DSH 0.2.2-rc.2 · 2026-11-19.

## 1. Tổng hợp

| Lệnh | Kết quả | Log |
|---|---|---|
| `python3 -m unittest discover -s tests` | **145 test OK** | `artifacts/review/*-python-tests.log` |
| `node --test dsh-plugin/tests/plugin.test.mjs` | **16 pass** | `*-node-adapter.log` |
| `node --test dsh-plugin/tests/knowledge.test.mjs` | **9 pass** | `*-node-knowledge.log` |
| `node --test dsh-plugin/tests/lifecycle.test.mjs` | **7 pass** | `*-node-lifecycle.log` |
| `node --test dsh-plugin/tests/client.test.mjs` | **10 pass** | `*-node-client.log` |
| `node --test dsh-plugin/tests/pack.test.mjs` | **2 pass** | `*-node-pack.log` |
| `node --test dsh-plugin/tests/settings.test.mjs` | **5 pass** | `*-node-settings.log` |
| `node --test dsh-plugin/tests/arguments.test.mjs` | **9 pass** | `*-node-arguments.log` |
| `node --test dsh-plugin/tests/description.test.mjs` | **18 pass** | `*-node-description.log` |
| `node --test dsh-plugin/tests/command.test.mjs` | **9 pass** | `*-node-command.log` |
| `python3 -m compileall -q scripts tests pfe tools` | OK | `*-compileall.log` |
| `python3 scripts/check_repo_policy.py` | OK | `*-policy.log` |
| UI (trình duyệt thật) | 12 tổ hợp × 2 chế độ, 0 lỗi | [20261119-ui.json](artifacts/review/20261119-ui.json) |
| Benchmark 2 000 file | full 1.5 s · incremental 0.46 s · 68 MB | `*-bench.json` |


Tarball phát hành:

| Mục | Giá trị |
|---|---|
| Tên | `dsh-project-flow-explainer-0.6.4.tgz` |
| Byte | 105516 |
| Entry | 27 (gồm `client.js` và `vendor/core/{scripts,assets,tools,pfe}`) |
| SHA-256 | `306f220bdff271d1498eb6f3ffc36c60496ac9ab104561320e74fb79efc02e70` |

## 2. Lỗi tái hiện được và đã sửa trong 0.4.x

| ID | Tái hiện | Nguyên nhân | Sửa | Test |
|---|---|---|---|---|
| T0 | `python3 tools/pfe_cli.py flow ...` → `internal_error: ModuleNotFoundError: build_flow` | `sys.path` chỉ có `tools` và repo root, thiếu `scripts` | thêm `scripts` vào path, bọc `ImportError` thành `core_import_failed` | 4 test CLI (repo root, cwd khác, repo sai, request rỗng) |
| T1 | xoá một dòng `file_cache` → chạy incremental → file biến mất khỏi graph | cache được đọc **sau** vòng parse; `changed.append` không được parse lại | đọc cache trước, đưa file thiếu/hỏng vào danh sách parse, thêm invariant "mọi file đều có trong graph" | 5 test (missing, malformed, equivalence, delete, rename) |
| T2 | `context_pack("export report")` trả route bằng tên file/symbol | dùng `result["symbol"]` làm route | resolve qua fact `handles_route` tới entity `route:` thật | 10 test context pack |
| T4 | dispose plugin không huỷ run của tool tri thức | `inFlight` chỉ được tool flow đăng ký | chia sẻ `inFlight` cho `knowledgeTools` | `dispose cancels an in-flight run` |
| (0.3.0) | `index` lỗi `tested_by không nhận subject test` | fact phát ngược chiều | phát `file → test` | 2 test mapping |

## 3. Test theo vùng

### 3.1 CLI và core (T0)

| Test | Kiểm chứng |
|---|---|
| `test_flow_from_repository_root` | chạy từ repo root, exit 0, đúng một JSON object, không có `ModuleNotFoundError` |
| `test_flow_from_another_working_directory` | chạy từ `/tmp` bằng đường dẫn tuyệt đối |
| `test_invalid_repository_keeps_stable_code` | `repository_not_found`, exit 2 |
| `test_missing_request_keeps_stable_code` | `missing_flow_request`, exit 2 |

### 3.2 Index tăng dần và cache (T1, T3)

| Test | Kiểm chứng |
|---|---|
| `test_missing_cache_row_is_repaired` | `files_parsed >= 1`, entity/fact của file không đổi |
| `test_malformed_cache_payload_is_repaired` | payload hỏng → parse lại, có cảnh báo |
| `test_graph_is_equivalent_after_repair` | danh sách entity + fact trước/sau bằng nhau |
| `test_deleted_and_renamed_still_work` | xoá file → `deleted`, entity về 0 |
| `test_conflict_metadata_is_written_and_read_back` | cột `contradicted` còn nguyên sau khi đọc lại index |

### 3.3 Context pack (T2)

| Test | Kiểm chứng |
|---|---|
| `test_route_is_a_real_route_entity_not_a_file_name` | route label bắt đầu bằng `/`, có path + line, confidence observed |
| `test_entry_points_carry_evidence_and_kind` | kind thuộc danh sách phát, có `evidence_refs` |
| `test_gui_cli_worker_entry_points` | fixture desktop có gui_event, cli_command, worker, main |
| `test_desktop_has_no_invented_http_route` | dự án desktop → `routes == []`, có limitation giải thích |
| `test_dependency_is_a_real_relation` | dependency chỉ dùng predicate thật |
| `test_error_intent_raises_error_case_priority` | task có "lỗi" → error_case xuất hiện; task thường → không |
| `test_seen_sets_are_separate` | seen.paths / entities / evidence tách riêng |

### 3.4 Verify (T6)

| Test | Kiểm chứng |
|---|---|
| `test_static_pass_ui_runtime_blocked_is_partial` | static pass + ui/runtime blocked → overall partial |
| `test_full_pass_requires_real_gate_evidence` | chỉ pass khi cả ba gate có bằng chứng |
| `test_static_failure_is_overall_failure` | static fail → overall fail |
| `test_no_artifact_is_blocked_not_pass` | không artifact → blocked, không pass |

### 3.5 Vector (T7)

| Test | Kiểm chứng |
|---|---|
| `test_hashing_backend_is_declared_lexical` | `semantic=False`, tên chứa "hash", local=True |
| `test_vectors_are_off_by_default` | `include_vectors=false` |
| `test_missing_vector_index_falls_back_with_warning` | thiếu vector → cảnh báo + FTS |

### 3.6 Lifecycle adapter (T4)

| Test | Kiểm chứng |
|---|---|
| `mount registers exactly the seven tools once` | 7 tool, không trùng |
| `dispose removes every tool and releases the names` | sau dispose còn 0 |
| `remount after dispose restores seven tools without duplicates` | remount trả lại đúng 7 |
| `mounting twice without dispose is rejected` | mount trùng bị từ chối |
| `dispose cancels an in-flight run` | child bị kill, lỗi là `AbortError` |
| `no native Config export is claimed` | `plugin.Config === undefined` (BLOCKED_DSH_CONFIG_NATIVE) |

### 3.7 Bằng chứng cũ (0.3.0) vẫn giữ

- 35 test core (đường đi chuẩn, policy artifact, secret, absolute path).
- 20 test evidence graph (không call giả, không bypass, scoped decision).
- 45 test ontology/knowledge/index/search.
- 11 test schema + consistency.

## 4. UI

12 tổ hợp (shop/self/empty × 1440×900, 1280×800, 768×1024, 375×812), mỗi tổ hợp đo cả
Simple view và Technical view: tràn ngang 0, card chồng 0, nhãn đè card 0, header bị cắt 0,
console error 0, request ngoài 0. Simple view có 3–7 stage tuỳ flow.
Chi tiết: [UI_VERIFICATION_REPORT.md](UI_VERIFICATION_REPORT.md).


## 4b. Chạy thật trên hai dự án (0.4.1)

Bản ghi đã scrub path và tên repo; chi tiết trong `evidence-manifest.json` mục `real_projects`.

| Chỉ số | Web project (Flask + UI) | Desktop project (tkinter) |
|---|---|---|
| File quét (flow) | 246 | 17 |
| File index | 224 | 26 |
| Symbol | 1 833 | 207 |
| Route khai báo | **47** | 0 (đúng: không có HTTP) |
| Test trong index | 0 | 10 |
| Entry point theo loại | http_route 47 · gui_event 52 · callback 26 · main 104 · public_api 12 | gui_event 6 · callback 2 · main 28 |
| File có entry point | 89 | 15 |
| Context pack route | `/data/publish-schedule` đầu tiên (khớp task) | `routes = []` + limitation giải thích |
| Dependency có path+line | 24, tất cả có `why_included` | 24 |
| verify | static pass · overall partial | static pass · overall partial |
| Index incremental | parse lại 0 file | parse lại 0 file |

Hai điểm đáng chú ý:

1. Lần chạy đầu, script đếm entry point bị `LIMIT 200` cắt nên báo thiếu `main`/`public_api`.
   Đã sửa sang `GROUP BY` — lỗi của script bằng chứng, không phải của index.
2. Repo web có 2 file > 256 KB bị bỏ qua và ghi trong `warnings`, đúng ngân sách công bố.

## 4c. DSH registry-runtime smoke (0.4.1)

Chạy bằng `python3 scripts/run_dsh_smoke.py` (harness ở `smoke/dsh-probe/`).
Bundle 0.4.1 được cài vào profile thử `pfe-test`; probe cài tạm, gỡ sau khi chạy.
Profile `web` không bị chạm; overlay nằm trong thư mục tạm, không sửa patch của profile.

| Check | Kết quả |
|---|---|
| Tool trong registry thật | **36** tool, 7/7 tool của plugin có mặt |
| flow qua registry | ok |
| context pack qua registry | ok |
| impact qua registry | ok |
| verify qua registry | ok, overall = partial (ui/runtime blocked) |
| search qua registry | ok |
| repository ngoài allowedRoots | `repository_outside_allowed_roots` |
| tham số thiếu | `flow_request_missing` |
| abort trước khi gọi | `AbortError` |
| `allowedRoots: []` | `allowed_roots_unconfigured` |
| `timeoutMs: 1` | `core_timeout` |
| `disabled: true` | không còn tool `project_*` trong registry |
| `exports["./client"]` | resolve được, client bundle vào web boot graph |
| `Config` + `.volatile()` | entry vào `settings.describe()`, `auto_generate=true` |

Giới hạn: probe gọi **registry thật** nhưng **không qua model**, nên
`model_driven = not_verified`. Panel UI vẫn `BLOCKED_UI_API_UNVERIFIED`.

## 4d. Settings UI trong DSH (0.5.4)

Bundle có `client.js` đăng ký slot `plugins.bundle.config` với key là package name.

| Kiểm chứng | Cách làm | Kết quả |
|---|---|---|
| Envelope của client bundle | `node:vm` chạy `client.js`, kiểm `window.__ModuleLoader__.load` | id khớp `package.json` |
| Đăng ký slot | gọi `apply(ctx)` với ctx giả | 1 entry `plugins.bundle.config`, key = package name |
| 5 trường cấu hình + 3 section | render cây React, tìm `id=pfe-*` và heading | đủ control, có "Thư mục được đọc"/"Runtime"/"Tool đã đăng ký" |
| Lưu | bấm nút, kiểm `form.mutate` | 1 batch, `allowedRoots` thành mảng, ô trống thành `unset` |
| Chặn ghi sai | root tương đối, timeout 0 | không gọi `mutate` |
| Khôi phục | bấm nút thứ hai | 5 lệnh `unset` |
| Host chặn ghi | `writable: false` | cả hai nút disabled |
| Root rỗng | render `view: "summary"` | nói rõ "Chưa cấu hình", không giả vờ đã cấu hình |
| Host không có form | `form: undefined` | hiện hướng dẫn dùng patch, không render form rỗng |
| Config native | boot thật với `allowedRoots: "oops"` | `ValidationError: $.allowedRoots expected array but got oops` |

10 test client (`dsh-plugin/tests/client.test.mjs`) + 2 check trong DSH smoke
(`invalid_config_rejected`, `client_subpath_resolves`) khoá hành vi này.


## 4e. Đối chiếu hướng dẫn chính thức của DSH

Tham chiếu: `deepseekdocs.com/en/docs/learn/dev/hello-plugin` và `config-publish`.

| Yêu cầu trong tài liệu | Trạng thái trong bundle |
|---|---|
| Module export `name` + `apply(ctx, config)` | Đã có |
| `dsh.bundle.patch` là một chuỗi đường dẫn | Đã có (`./cordis.patch.yml`) |
| Patch layer dạng `- insert: [{id, name}]` | Đã có, 1 row `project-flow-explainer` |
| `Config` là schemastery schema thật, có default | Đã có; boot sai kiểu trả `ValidationError` |
| Không export `Config` rỗng để lấy validation giả | Có fallback `undefined` khi thiếu schemastery |
| Tool khai báo `output { schema, render }` | Đã có cho 7 tool |
| `inject` khai báo service dùng (`tools`) | Đã có |
| Đóng gói: `files` gồm entry, lib, patch, client | Đã có; `client.js` từng bị thiếu, đã sửa |
| Cài bằng `dsh plugin add` (tarball/link/git) | Đã chạy với tarball |
| Kiểm composition bằng `--dump-config` | Đã chạy, exit 0, đúng 1 row |
| Settings UI: `Config` + trường `.volatile()` | **KHÔNG tự sinh** — xem giới hạn bên dưới |
| UI riêng cho bundle | Card ở `plugins.bundle.config` (đã test 6 ca) |

Ba lỗi thật trên đường đi tới Settings UI, đã đo và đã sửa:

| Lỗi | Triệu chứng đo được | Sửa |
|---|---|---|
| Thiếu `exports["./client"]` | `client-modules`: `declares dsh.client but exports no "./client" bundle`; `require.resolve('dsh-project-flow-explainer/client')` trả `ERR_PACKAGE_PATH_NOT_EXPORTED` | thêm `"./client": "./client.js"` vào `exports` |
| Schema lấy từ bản schemastery khác | trường `.volatile()` bị chiếu thành `{}` (`cfg {"allowedRoots":{},"pythonPath":{}}`) | nạp schemastery từ **gói cài DSH** (`realpath(process.argv[1])` → `dsh/anchor.js`), không dùng bản trong profile |
| Giá trị nằm ở settings, không ở `config` | sau khi bật volatile, patch `allowedRoots` không tới `apply()` | đọc `ctx.settings.describe()` qua `ctx.inject(['settings'])[]()`, cập nhật tại chỗ khi có `settings/document-updated` |

Kết quả sau sửa: entry `project-flow-explainer` xuất hiện trong `settings.describe()` với
`auto_generate: true` và `value.allowedRoots` đúng như patch; trang Plugins truyền `form` cho slot
nên trang cấu hình hoạt động.

## 4f. Settings UI chạy thật trong trình duyệt

Thực hiện trên một instance thứ hai của profile `web` (cổng 3099), không chạm phiên đang dùng:
mở **Plugins** → card `dsh-project-flow-explainer` → nút **Configure** ở dòng
`project-flow-explainer`.

| Kiểm chứng | Kết quả |
|---|---|
| `#pfe-allowedRoots` tồn tại | có, hai dòng: root làm việc của máy và root của fixture |
| Đủ 5 trường | `allowedRoots`, `pythonPath`, `coreRoot`, `timeoutMs`, `maxOutputBytes` |
| Section | "Runtime", "Tool đã đăng ký" (tiêu đề "Thư mục được đọc" của trang không bị lặp) |
| Nút | "Lưu cấu hình", "Khôi phục mặc định" |
| Fallback trên trang bundle | hiện hướng dẫn mở **Configure** ở dòng, không render form rỗng |

Ảnh: [dsh-settings-page.png](artifacts/ui-verification/dsh-settings-page.png) · 1 236 × 769 ·
sha256 `19e3feac…f6cc2` (manifest: `ui.settings_page_screenshot`).

Lý do phải mở từ dòng: trang bundle gọi `formFor(pkg.name)`, còn namespace settings dùng **row id**
(`project-flow-explainer`), nên form chỉ có ở trang cấu hình của row.

## 4g. Session model thật (ghi dưới 0.5.5)

Chạy trên profile `pfe-webcheck` (bản sao của `web`, cổng 3099), model `deepseek-flash`,
reasoning high. Prompt không nêu tên tool nào ngoài yêu cầu nghiệp vụ.

| Bước | Bằng chứng |
|---|---|
| Model tự suy luận | "Need to run project_code_index first." |
| Tool 1 | `project_code_index` · `<repo>` |
| Tool 2 | `project_context_pack` · `<repo>` |
| Trả lời | 9 entry point, 2 loại: `main` 8, `callback` 1 |
| File nên đọc | `dsh-plugin/scripts/pack.mjs`, `dsh-plugin/index.js` |
| Model tự nêu giới hạn | "phân tích tĩnh, chưa chạy test" |
| Bước tiếp theo model đề xuất | `project_impact_analysis` |
| Số bước / thời gian | 16 bước · 30 s · 1 turn |

Bản ghi: [20261120-005100-model-session.json](artifacts/review/20261120-005100-model-session.json) ·
ảnh: [dsh-model-session.png](artifacts/ui-verification/dsh-model-session.png).
Manifest: `smoke.model_driven = verified`.

## 5. Chưa kiểm chứng

| Hạng mục | Trạng thái | Lý do |
|---|---|---|
| Smoke registry 0.5.4 trong `pfe-test` | **ĐÃ CHẠY** — `artifacts/review/*-dsh-smoke.json` | 6 lần boot thật, 36 tool, 16/16 check pass |
| Model tự chọn tool | **ĐÃ CHẠY** — mục 4g | model gọi đúng 2 tool, trả lời bằng số liệu thật |
| Native `Config` | **ĐÃ XÁC MINH** | boot thật trả `ValidationError: $.allowedRoots expected array but got oops` |
| Tool visibility | **BLOCKED_TOOL_VISIBILITY** | chưa xác minh cơ chế presentation/visibility |
| Panel UI Harness | `BLOCKED_UI_API_UNVERIFIED` | panel riêng ngoài scope; settings card dùng slot `plugins.bundle.config` (đã có) |
| Embedding ngữ nghĩa | **CHƯA CÓ** | backend hashing là lexical |