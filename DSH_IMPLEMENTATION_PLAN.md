# DSH_IMPLEMENTATION_PLAN — Hybrid Project Flow Explainer × DeepSeek Harness

Trạng thái: **core + adapter + QA xong; bước cài vào `pfe-test` chờ phê duyệt** (chi tiết: [FINAL_REPORT.md](FINAL_REPORT.md)).

Cập nhật: 2026-11-19T17:05+07:00 · nhánh `main` @ `7ab202a` + thay đổi chưa commit.

---

## 1. Ma trận runtime (HYB-00, đo thật)

Bằng chứng thô: [preflight log](artifacts/logs/20261119-1628-HYB-00-preflight.log).

| Hạng mục | Giá trị |
|---|---|
| OS | Ubuntu 24.04.4 LTS · kernel 6.14.0-37 · x86_64 |
| DSH | `0.2.2-rc.2`, profile `web`, `patchReload: live` |
| Node / npm / pnpm | v24.22.3 / 11.19.1 / 12.5.1 |
| Python | `python` và `python3` = `/usr/bin/python3.12.3` |
| Cordis / dsh-tools | 4.1.0 / 0.2.2-rc.2 |
| Repo root | 8 mục gốc, **không có `package.json`** |
| Skill `cordis-plugin-development` | KHÔNG CÀI |
| `cordis_inspect_list/query` | Có trong runtime (`dsh-tool-cordis`), **không expose cho phiên** |
| `plugin_manager` | Không mount trong `web` → dùng CLI `dsh plugin` |
| Browser + screenshot | Có (`ego_*`) |
| Slot UI web bundle | 117 key trong catalog (chỉ là đầu mối, chưa verify register API) |

---

## 2. Quyết định đã chốt

Q1 local path · Q2 bắt buộc flow request · Q3 ba file, hoãn panel · Q4 source chỉ đọc, artifact trong `<repo>/artifacts/flows/<slug>/` · Q5 không network, không đưa source vào model · Q6 profile `pfe-test`.

Nguyên văn và hệ quả kỹ thuật: [ARCHITECTURE_DECISION.md](ARCHITECTURE_DECISION.md).

---

## 3. Task list

| ID | Ưu tiên | Phạm vi | Trạng thái | Điều kiện DONE (đo được) | Bằng chứng |
|---|---|---|---|---|---|
| HYB-00 | P0 | Preflight runtime | **DONE** | version/profile/tool/skill được ghi kèm nguồn | preflight log |
| HYB-01 | P0 | Baseline core | **DONE** | unittest + `--check-only` + render mẫu đều chạy, log lưu | 2 log HYB-01, `artifacts/baseline/` |
| HYB-02 | P0 | Architecture decision | **DONE** | tài liệu nêu boundary + bất biến, có bảng lệch so với prompt | `ARCHITECTURE_DECISION.md` |
| HYB-03 | P0 | Adapter skeleton | **DONE** | thư mục riêng; xoá adapter core vẫn chạy | `dsh-plugin/`, test core độc lập |
| HYB-04 | P0 | Core runner | **DONE** | argv array, `shell:false`, cap output, kill theo signal/timeout | `lib/core-runner.js`, test abort |
| HYB-05 | P0 | Tool registration | **DONE (in-process)** | mount vào Context giả, schema đúng, execute end-to-end tạo 4 file | 11 test adapter |
| HYB-06 | P0 | Security boundary | **DONE** | traversal/absolute/symlink/allowedRoots/secret đều fail-safe | test Python + Node |
| HYB-07 | P1 | Bundle packaging | **DONE (chưa cài)** | manifest đúng format runtime | `package.json`, `cordis.patch.yml` |
| HYB-08 | P1 | Smoke trong DSH thật | **BLOCKED** | cài `pfe-test`, tool ACTIVE, gọi thật, unload/reload | chờ phê duyệt cài |
| HYB-09 | P1 | Harness UI | **BLOCKED_UI_API_UNVERIFIED** | chỉ mở khi register API của slot được xác minh | ngoài MVP |
| HYB-10 | P1 | Visual QA HTML | **DONE** | 3 viewport × 3 case, screenshot, console/network sạch | `UI_VERIFICATION_REPORT.md` |
| HYB-11 | P0 | Tài liệu + bằng chứng | **DONE** | 6 báo cáo + artifacts theo naming | `FINAL_REPORT.md` |

---

## 4. Vòng kiểm tra đã áp dụng

```text
IMPLEMENT → STATIC (py_compile, node --check ngầm qua import) → TEST (unittest 22, node --test 11)
→ RUNTIME in-process (mount + execute + abort + reload) → REGRESSION (chạy lại toàn bộ sau mỗi sửa)
→ UI (3 viewport, console, network) → EVIDENCE (log/ảnh/JSON)
```

Sự cố đã sửa trong vòng lặp (mỗi lỗi một lần sửa, không tắt test):

| Lỗi | Nguyên nhân | Sửa | Retest |
|---|---|---|---|
| Sinh graph lỗi `nodes[3].source_refs[0].symbol phải là chuỗi` | truyền `symbol: null` vào ref | helper `ref()` bỏ key rỗng | 22 test PASS |
| Entry chọn sai route (`/api/reports/:id` thay vì `/export`) | chọn route đầu file | chấm điểm body từng handler, cắt theo biên route kế tiếp | entry đúng route export |
| Tiêu đề node chứa `{'name': ...}` | dùng nhầm dict thay tên | lấy `symbol['name']` | title sạch |
| Fixture trong repo bị chọn làm entry khi self-analyze | route +10 điểm | loại hẳn thư mục test/fixture/example/sample/demo | entry = `scripts/build_flow.py` |
| Entry là `class BuildError` | symbol đầu file | `pick_symbol` ưu tiên hàm, tên entry-like | entry = `run` |
| Card kế tiếp bị cắt ở 768 (UI-001) | `initialView()` không fit ngang | thêm `scaleX` | 0 card bị cắt |
| `"Luồng: luồng …"` | nối chuỗi thô | bỏ tiền tố flow khỏi topic | tiêu đề sạch |

---

## 5. Việc còn lại

1. **Chờ duyệt**: cài bundle vào `pfe-test` → chạy smoke 12 bước (mục 8 của FINAL_REPORT).
2. Panel Harness: giữ `BLOCKED_UI_API_UNVERIFIED`, chỉ mở lại khi có `cordis_inspect_query`.
3. Backlog: xem [IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md).
