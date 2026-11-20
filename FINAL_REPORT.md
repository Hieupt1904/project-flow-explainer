# FINAL_REPORT — 0.4.1

Trạng thái: **PARTIAL** — code, test, CLI, UI đã pass; smoke registry DSH cho 0.4.0,
model-driven, native Config và tool visibility **chưa chạy được** (ghi BLOCKED_*).

| Mục | Giá trị |
|---|---|
| Package version | `0.6.3` |
| `engines.dsh` | `0.2.2-rc.2` (khớp DSH đang cài) |
| Test | 145 Python · 16 adapter · 9 knowledge · 8 lifecycle · 10 client · 8 command · 5 settings · 9 arguments · 18 description · 2 pack — 0 fail |
| Bằng chứng | [evidence-manifest.json](artifacts/review/evidence-manifest.json) |
| Tarball | `dsh-project-flow-explainer-0.6.3.tgz` · 105 331 byte · sha256 `e60220a5…063f10` |

## 1. Bảng task T0–T9

| Task | Trạng thái | Thay đổi chính | Bằng chứng | Còn lại |
|---|---|---|---|---|
| T0 CLI flow | **DONE** | thêm `scripts` vào `sys.path`; `ImportError` → `core_import_failed`; argparse không trả 0 khi sai cờ | 4 test CLI chạy subprocess thật | — |
| T1 Incremental cache | **DONE** | đọc cache trước khi parse; cache thiếu/hỏng → parse lại; invariant "mọi file đều có trong graph" | 5 test | — |
| T2 Context pack | **DONE** | route thật qua `handles_route`; entry_kind có bằng chứng; rerank theo ý định; dependency đầy đủ; 3 tập seen tách; confidence tách | 10 test + fixture desktop | `export`/`command` khai báo nhưng chưa phát |
| T3 Conflict persistence | **DONE** | cột `contradicted` trong bảng `facts`; đọc lại qua `facts_about`/`neighbours` | 1 test round-trip qua SQLite | index version 1→2 buộc rebuild |
| T4 Config + lifecycle | **DONE** | `inFlight` dùng chung cho 7 tool; test mount/dispose/remount; registry-runtime verified trong `pfe-test` | 7 test lifecycle + 6 lần boot thật | `Config` native (schemastery) + `ValidationError` khi sai kiểu |
| T5 Tool surface | **PARTIAL** | 7 tool giữ nguyên tên; description 6 mục; renderer ngắn | test schema + review description | **BLOCKED_TOOL_VISIBILITY** |
| T6 Verify semantics | **DONE** | `static_verdict` / `overall_verdict` / `gates` / `not_verified` / `next_action`; `verdict` là alias | 4 test tổ hợp | — |
| T7 Vector/cache/privacy | **DONE** | backend `hashing-lexical` (`semantic=False`); vector mặc định tắt; canonical output dùng đường dẫn tương đối | 3 test + adapter test | boundary presentation chưa xác minh |
| T8 Simple UI | **DONE** | Simple view mặc định (3–7 stage), tab Kỹ thuật giữ canvas; search lọc stage; keyboard; không fit toàn bộ graph khi mở | 12 tổ hợp × 2 chế độ | nút Toàn cảnh vẫn co 40% (chủ động) |
| T9 Evidence | **DONE** | manifest tách `working_tree_dirty` và `evidence_files_changed`; `record_release.py` chứng minh hai cây chỉ khác `artifacts/review/` | manifest + log + CI | CI của commit bằng chứng ghi sau push |

## 2. Hành vi đã đổi (có migration)

| Trước | Sau | Lý do | Ảnh hưởng |
|---|---|---|---|
| Tool flow trả absolute path + `path_visibility: host-only` | trả đường dẫn tương đối, `path_base: "repository"`, `absolute_paths_returned: false` | chưa xác minh presentation boundary nên absolute path không được rời tool | tên field giữ nguyên, giá trị đổi |
| `verify` trả một `verdict` | thêm `static_verdict`, `overall_verdict`, `gates` | tránh "pass" mơ hồ | `verdict` = `overall_verdict` |
| `context_pack.entry_points[*].route` | thêm `kind`, `label`, `evidence_refs` | route cũ lấy từ symbol nên sai | giữ `route` |
| `dependencies` ngắn | thêm `start_line`, `end_line`, `why_included`, `evidence_refs` | agent cần vị trí | thêm field |
| index version 1 | 2 | cột `contradicted` + bảng `entry_points` | tự rebuild lần đầu |

Tên 7 tool không đổi.

## 3. Phân loại kết quả

| Mức | Nội dung |
|---|---|
| Code đã pass | 143 + 16 + 9 + 7 + 2 test, compileall, node --check, policy |
| Runtime đã pass (local) | CLI thật, index/context/impact/verify trên fixture web + desktop + dự án thật |
| UI đã pass (trình duyệt) | 12 tổ hợp × 2 chế độ, không overflow/overlap/console error/request ngoài |
| Model-driven | **CHƯA CHẠY** — không có API key (probe gọi registry, không qua model) |
| DSH registry-runtime | **đã xác minh** trong `pfe-test`: 6 lần boot, 36 tool, 14/14 check |
| Static inference | membership flow theo import/route; calls lexical; entry point theo dòng đăng ký |
| Blocked | native Config (BLOCKED_DSH_CONFIG_NATIVE), tool visibility (BLOCKED_TOOL_VISIBILITY), panel UI (BLOCKED_UI_API_UNVERIFIED), vector ngữ nghĩa; smoke và model-driven: **CHƯA CHẠY** |

## 4. Việc cố ý **không** làm

| Việc | Lý do |
|---|---|
| Vector DB / cloud embedding | không có bằng chứng cần; đang là lexical candidate |
| Plugin panel DSH | API runtime chưa xác minh |
| Adapter cho framework khác | ngoài scope, chưa có fixture |
| Thêm ontology relation mới | không có evidence thực tế |
| Đổi tên/xoá tool | phá compatibility |
| Cài bundle vào profile | chưa được cho phép |