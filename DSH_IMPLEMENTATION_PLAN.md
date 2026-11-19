# DSH_IMPLEMENTATION_PLAN — Hybrid Project Flow Explainer × DeepSeek Harness

Trạng thái 0.3.0: **core + adapter DONE; smoke registry 0.3.0 CHƯA CHẠY** (cần xin phép cài).

Cập nhật: 2026-11-19 · commit nguồn `13a2c49e4942` + thay đổi chưa commit · nhánh `main`.

## 1. Ma trận runtime (đo thật)

| Hạng mục | Giá trị |
|---|---|
| OS | Ubuntu 24.04 · x86_64 |
| DSH | `0.2.2-rc.2`, profile `web` đang chạy phiên này |
| Node / npm | v24.22.3 / 11.19.1 |
| Python | `python3` = 3.12.3 |
| SQLite | 3.45.1, có FTS5 |
| Profile thử | `pfe-test`, còn bundle 0.2.2 (chưa nâng cấp 0.3.0) |
| API key trong profile thử | không có |

## 2. Quyết định đã chốt

Q1 local path · Q2 bắt buộc flow request · Q3 ba file public + run.json internal · Q4 source chỉ đọc,
artifact trong `<repo>/artifacts/flows/<slug>/` · Q5 không network, không đưa source vào model ·
Q6 profile `pfe-test`.
Chi tiết: [ARCHITECTURE_DECISION.md](ARCHITECTURE_DECISION.md).

## 3. Task list

| ID | Phạm vi | Trạng thái | Điều kiện DONE | Bằng chứng |
|---|---|---|---|---|
| HYB-00 | Preflight runtime | **DONE** | version/profile/tool ghi kèm nguồn | manifest |
| HYB-01 | Baseline core | **DONE** | unittest + render mẫu chạy | log python |
| HYB-02 | Architecture decision | **DONE** | tài liệu nêu boundary + bất biến | ARCHITECTURE_DECISION |
| HYB-03 | Adapter skeleton | **DONE** | xoá adapter core vẫn chạy | test core độc lập |
| HYB-04 | Core runner | **DONE** | argv array, `shell:false`, cap output, kill theo signal/timeout | `lib/core-runner.js` |
| HYB-05 | Tool registration | **DONE** | 7 tool, schema chặt, execute end-to-end | 16 + 9 test Node |
| HYB-06 | Security boundary | **DONE** | traversal/absolute/symlink/allowedRoots/secret fail-safe | test Python + Node |
| HYB-07 | Bundle packaging | **DONE** | manifest đúng, vendor core đầy đủ | `pack.test.mjs` |
| HYB-08 | Smoke trong DSH thật (0.2.x) | **DONE (lịch sử)** | tool trong registry thật, disable/enable/remove | pass 0.2.x; log cũ đã xoá cùng báo cáo cũ |
| HYB-08b | Smoke registry 0.3.0 | **BLOCKED_PENDING_APPROVAL** | cài tarball 0.3.0 vào `pfe-test`, gọi 7 tool | chưa có — phải xin phép trước bước cài |
| HYB-09 | Harness UI | **BLOCKED_UI_API_UNVERIFIED** | chỉ mở khi xác minh register API | ngoài phạm vi |
| HYB-10 | Visual QA HTML | **DONE** | 3 sample × 4 viewport, 0 lỗi | UI report + JSON |
| HYB-11 | Tài liệu + bằng chứng | **DONE** | 7 tài liệu + manifest sinh tự động | `scripts/regen_evidence.py` |
| KNW-01 | Ontology + schema | **DONE** | schema validate được, khớp ontology | 6 test schema |
| KNW-02 | Index tăng dần | **DONE** | full/inc/change/delete/rename/version | 12 test |
| KNW-03 | FTS + hybrid retrieval | **DONE** | symbol/route/tiếng Việt đều tìm đúng | 6 test search |
| KNW-04 | Vector tùy chọn | **PARTIAL** | interface + mismatch + fallback | backend hashing, không ngữ nghĩa |
| KNW-05 | 6 tool tri thức | **DONE (adapter)** | schema chặt, mã lỗi ổn định, không trả source | 9 test |

## 4. Vòng kiểm tra đã áp dụng

@@text
STATIC → UNIT → SECURITY → GRAPH → DETERMINISM → PACKAGING → PROVENANCE → UI
@@

Sự cố đã sửa trong vòng lặp (mỗi lỗi một lần sửa, không tắt test):

| Lỗi | Nguyên nhân | Sửa | Retest |
|---|---|---|---|
| `evidence=call` không có call site | builder gắn nhãn theo import | xoá claim call; ontology từ chối fact thiếu call site | 20 test evidence |
| Decision sinh từ try/catch của route khác | quét cả file | cửa sổ route body / symbol body | `test_other_route_exception…` |
| Artifact dở dang khi lỗi | ghi trực tiếp vào slug | staging + rename + cleanup | 3 test |
| `commit` là từ khoá SQLite | đặt tên cột trùng keyword | đổi thành `commit_sha` | index test |
| Entity id route có dấu cách bị từ chối | pattern quá chặt | cho phép khoảng trắng đơn, chuẩn hoá id | ontology test |
| `export_report` không khớp `exportReport` | tokenizer không tách camelCase | index thêm biến thể tên | search test |
| Query tiếng Việt không tới được code Anh | thiếu bridge thuật ngữ | lexicon hai chiều + prefix match | search test |
| Hub (repository) chiếm top kết quả | cộng dồn điểm graph | đổi sang max(base) + bonus, bỏ hub | search test |
| `đ` không được fold | NFD không tách `đ` | map `đ`/`Đ` → `d`/`D` | facet match |
| `tested_by` phát ngược chiều (`test` → `file`) | ontology từ chối subject `test`; chỉ lộ khi repo có thư mục test | đổi sang `file` → `test` | 2 regression test + chạy lại dự án thật |
| `ru_maxrss` báo 700 MB cho 200 file | kế thừa high-water mark tiến trình cha | đọc `VmHWM` trong `/proc/self/status` | benchmark 27.9 MB đúng |


## 6. Pass 0.4.0 — T0…T9

| Task | Trạng thái | Ghi chú |
|---|---|---|
| T0 CLI flow import | **DONE** | nguyên nhân: thiếu `scripts` trong sys.path; có 4 test subprocess |
| T1 Cache incremental | **DONE** | cache thiếu/hỏng không còn làm mất file; có invariant + 5 test |
| T2 Context pack | **DONE** | route thật, entry_kind, dependency path/line, rerank theo ý định |
| T3 Conflict persist | **DONE** | cột `contradicted`; index version 2 |
| T4 Config/lifecycle | **PARTIAL** | `inFlight` dùng chung; **BLOCKED_DSH_CONFIG_NATIVE** |
| T5 Tool surface | **PARTIAL** | 7 tool giữ nguyên; description 6 mục; **BLOCKED_TOOL_VISIBILITY** |
| T6 Verify semantics | **DONE** | static/overall tách, gates, next_action |
| T7 Vector/privacy | **DONE** | hashing-lexical, vector off, canonical output relative |
| T8 Simple UI | **DONE** | Simple view mặc định 3–7 stage; 12 tổ hợp × 2 chế độ sạch |
| T9 Evidence | **DONE** | `record_release.py` chứng minh cây nguồn sạch |

### Vì sao vẫn BLOCKED

- **DSH smoke**: cài bundle chạy npm/pnpm trong profile `pfe-test`; hành động này chưa được cho phép.
- **Native Config**: `@deepseek-ai/schemastery` resolve được từ cài đặt DSH nhưng **không** từ profile
  (`MODULE_NOT_FOUND`), nên plugin không thể `import` schema thật; giữ validate tay + test.
- **Tool visibility**: tài liệu DSH mô tả preset/presentation nhưng chưa có API visibility đã xác minh
  cho bundle bên thứ ba; giữ 7 tool và cải thiện description thay vì đoán API.

## 5. Việc còn lại

1. **Chờ duyệt**: cài tarball 0.3.0 vào `pfe-test` → chạy smoke 7 tool (index/search/context/impact/verify/refresh + flow).
2. Model-driven smoke: cần API key.
3. Panel Harness: giữ `BLOCKED_UI_API_UNVERIFIED`.
4. Backlog: xem [IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md).