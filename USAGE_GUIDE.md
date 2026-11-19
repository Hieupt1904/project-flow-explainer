# Hướng dẫn sử dụng hiệu quả

Tài liệu này nói **khi nào dùng công cụ nào, query viết thế nào, đọc kết quả ra sao**.
Số liệu trong đây lấy từ lần chạy thật ngày 2026-11-19: một dự án desktop riêng tư
(27 file Python, 17 file được quét) và chính repo này. Bằng chứng máy đọc:
[20261119-2307-real-project.json](artifacts/review/20261119-2307-real-project.json).

## 1. Chọn đúng công cụ trong 10 giây

| Bạn đang có | Dùng | Vì sao |
|---|---|---|
| Câu mô tả nghiệp vụ: "từ lúc bấm xuất Excel đến khi có file" | `project_flow_explain` / `build_flow.py` | chấm điểm theo facet + chọn route, phù hợp câu dài |
| Tên hàm, tên lớp, endpoint | `project_code_search` / `pfe_cli.py search` | exact match thắng, trả đúng dòng |
| "Sửa chỗ này thì phải đọc gì" | `project_context_pack` | gom entry point + file + test + phụ thuộc |
| "Tôi vừa sửa 3 file, ảnh hưởng gì" | `project_impact_analysis` | trả flow/route/symbol/test + risk |
| "Kết quả có đáng tin không" | `project_verify_flow` | kiểm graph, artifact, UI tĩnh, privacy, test mapping |
| "Vừa pull, index còn đúng không" | `project_knowledge_refresh` | chỉ parse lại file đã đổi |
| Lần đầu vào repo | `project_code_index` với `mode=full` | tạo index, sau đó chỉ dùng incremental |

Nguyên tắc: **câu dài → flow; định danh → search**. Đừng dùng search cho câu nghiệp vụ dài,
và đừng dùng flow cho câu "hàm này ở đâu".

## 2. Năm phút đầu với một repo lạ

```bash
R=/duong/dan/repo

# 1) Xem luồng nghiệp vụ trước (có sơ đồ để đọc)
python3 scripts/build_flow.py --repo $R \
  --request "Giải thích từ lúc người dùng bấm cập nhật dữ liệu đến khi có file Excel"

# 2) Tạo index để tra cứu
python3 tools/pfe_cli.py index --repo $R --mode full

# 3) Tra đúng chỗ
python3 tools/pfe_cli.py search --repo $R --query "write_xls"

# 4) Kiểm tra những gì đã sinh
python3 tools/pfe_cli.py verify --repo $R
```

Kết quả thật trên hai dự án (0.4.1, path và tên repo đã scrub):

| Bước | Desktop (tkinter) | Web (Flask + UI) |
|---|---|---|
| flow | 12 node: 10 verified / 1 partial / 1 inferred; 17 file | 20 node: 10 verified / 9 partial / 1 inferred; 246 file |
| index full | 26 file · 207 symbol · 10 test | 224 file · 1 833 symbol · 47 route |
| index incremental | parse lại 0 file | parse lại 0 file |
| entry point | gui_event 6 · callback 2 · main 28 | http_route 47 · gui_event 52 · main 104 |
| context pack | 4 entry point, `routes = []` (đúng) | route đầu: `/data/publish-schedule` |
| verify | static pass · overall partial | static pass · overall partial |

Desktop không có HTTP route nên `routes = []` là kết quả đúng, không phải lỗi.
Web có 47 route vì pattern nhận cả decorator blueprint (`@bp.route`), không chỉ `@app.route`.

## 3. Vòng lặp hằng ngày khi sửa code

```text
index (một lần)  →  search/context (hiểu chỗ sửa)  →  sửa code
      ↑                                                     ↓
      └── refresh (chỉ file đổi)  ←  impact (biết phải test gì)  ←  verify
```

```bash
# trước khi sửa: lấy context
python3 tools/pfe_cli.py context-pack --repo $R --task "sửa chức năng xuất Excel quyết toán"

# sau khi sửa: biết ảnh hưởng gì
python3 tools/pfe_cli.py impact --repo $R --changed src/_xls.py

# cập nhật index (chỉ file đã đổi)
python3 tools/pfe_cli.py refresh --repo $R

# kiểm tra lại artifact/flow nếu có đổi graph
python3 tools/pfe_cli.py verify --repo $R
```

`impact` trả `risk_level`, `affected_routes`, `affected_symbols`,
`related_tests`, `downstream_modules`, `suggested_verification`.
Đọc `risk_reasons` để biết vì sao high/medium/low, đừng chỉ nhìn nhãn.

## 4. Viết query hiệu quả (có số đo)

| Query | Kết quả thật | Kết luận |
|---|---|---|
| `export_report` | top-1 `function exportReport`, score 1.25 | dùng tên symbol, kể cả snake_case |
| `/api/reports/export` | top-1 `route /api/reports/export`, score 1.4 | dán nguyên endpoint |
| `xuất báo cáo ra excel` | `exportReport` / `loadReportRows` | tiếng Việt có dấu vẫn được fold và bridge sang từ khoá code |
| `write_xls` (dự án thật) | top-1 đúng hàm ghi Excel, score 1.3 | tên hàm luôn thắng |
| câu dài 12–16 từ | trả về kèm cảnh báo **"Query dài"** | **đừng dùng search**; dùng flow |

Quy tắc viết query:

1. Ưu tiên **định danh**: tên hàm, tên lớp, endpoint, tên bảng.
2. Nếu chỉ có nghiệp vụ: 2–3 từ khoá (`xuất excel quyết toán`), không viết cả câu.
3. Tên trong code là tiếng Anh thì query tiếng Anh; nghiệp vụ tiếng Việt thì query tiếng Việt —
   bộ bridge hai chiều lo phần còn lại (chỉ mở rộng recall, không quyết định đúng/sai).
4. Không nhồi 5 khái niệm vào một query. Mỗi lần một khái niệm, ghép kết quả bằng suy luận của bạn.

## 5. Đọc kết quả cho đúng

Mỗi kết quả có: `path`, `symbol`, `start_line`–`end_line`, `relation`,
`confidence`, `score`, `why_matched`, `evidence_refs`, `source_commit`.

| Trường | Cách đọc |
|---|---|
| `confidence: observed` | có dòng thật; tin được vị trí |
| `confidence: structural` | suy ra từ import/test; đúng cấu trúc, chưa chắc runtime |
| `confidence: inferred` | heuristic; phải mở file xác nhận |
| `relation: []` và `why_matched` ghi "chỉ khớp từ khoá" | **nghi ngờ**: đúng chữ nhưng không có quan hệ graph |
| `relation: ["calls"]` | có call site thật trong file nguồn |
| `stale: true` | index cũ hơn working tree → chạy `refresh` trước khi tin |
| `score` | chỉ để xếp hạng, không phải xác suất |

Luật thực dụng: **score > 1.0 + observed + có relation** là chỗ nên đọc trước.
Score dưới 0.6 hoặc chỉ khớp keyword thì coi là gợi ý, không phải kết luận.

## 6. Prompt mẫu cho agent trong DSH

```text
Trước khi sửa: gọi project_context_pack với task "..." và đọc likely_files + entry_points.
Nếu kết quả stale=true thì gọi project_knowledge_refresh trước.
Sau khi sửa: gọi project_impact_analysis với changed_files, đọc risk_reasons và
suggested_verification; chạy đúng test trong related_tests.
Cuối cùng gọi project_verify_flow; nếu verdict=partial thì nêu rõ check nào blocked.
Không đọc toàn bộ file nếu search đã trả đúng path:line.
```

## 7. Bẫy và giới hạn (đọc trước khi tin)

| Bẫy | Sự thật | Cách tránh |
|---|---|---|
| Coi `verified` là "đã chạy" | chỉ là xác minh tĩnh vị trí + quan hệ | muốn runtime thì phải chạy test |
| Coi `calls` là call graph đầy đủ | chỉ call site đọc theo tên symbol duy nhất | alias/DI có thể thiếu |
| Coi vector là ngữ nghĩa | backend mặc định là hashing bag-of-words | bật vector chỉ để tăng recall |
| Query câu dài rồi tin top-1 | FTS cộng dồn theo từ khoá | dùng flow hoặc rút query |
| Quên refresh | index cũ, kết quả lệch | đọc `stale`/`warnings` mỗi lần |
| Repo không có route | flow trả `no-entry` (đúng, không bịa) | dùng index + search thay vì flow |
| Dự án desktop/CLI | `entry_points = 0` | đọc `likely_files` và `impacted_symbols` |

## 8. Mã lỗi thường gặp

| Mã | Nghĩa | Sửa |
|---|---|---|
| `index_missing` | chưa có `.pfe/index` | chạy `index --mode full` |
| `stale=true` | index cũ hơn file | chạy `refresh` |
| `no_changed_files` | impact thiếu đầu vào | truyền `--changed` hoặc `--diff` |
| `repository_outside_allowed_roots` | path ngoài root (DSH) | thêm root vào `allowedRoots` |
| `missing_flow_request` | thiếu mô tả flow | truyền `--request` |
| `artifact_exists` | slug đã tồn tại | bỏ `--slug` để tự sinh |
| `core_timeout` | vượt ngân sách | tăng `timeoutMs` hoặc thu hẹp phạm vi |

## 9. Checklist trước khi tin một kết quả

1. `source_commit` trùng commit bạn đang làm việc.
2. `stale` bằng `false`.
3. Kết quả top có `confidence: observed` và ít nhất một `relation`.
4. Đã mở đúng `path:line` mà kết quả trỏ tới (không tin mà không mở).
5. Nếu là flow: đọc `limits` và `meta.related` trước khi kết luận luồng đã đủ.


## 11. Simple view và chế độ Kỹ thuật (0.4.0)

`flow.html` mở ở **Simple view**: 3–7 stage nghiệp vụ (bắt đầu, các bước xử lý, điều kiện,
kết thúc, nhánh lỗi, điểm cần kiểm tra). Nhấn một stage để xem giải thích + nguồn.
Cần thấy toàn bộ node và cạnh thì bấm tab **Kỹ thuật**.

| Muốn gì | Làm gì |
|---|---|
| Hiểu nhanh cho người không đọc code | để nguyên Simple view, đọc từ trên xuống |
| Kiểm tra thứ tự node/cạnh | tab Kỹ thuật, kéo/zoom, bấm "Toàn cảnh" |
| Tìm một bước | ô tìm kiếm lọc stage (Simple) hoặc làm mờ node (Kỹ thuật) |
| Xem nguồn của một bước | nhấn stage/card → panel phải |

## 12. Entry point và context pack (0.4.0)

`project_context_pack` trả `entry_points` có `kind`:

| kind | Bằng chứng bắt buộc |
|---|---|
| http_route | khai báo route (app.get/post, router...) |
| main | `if __name__ == "__main__"` hoặc `def main(` |
| cli_command | `add_parser("...")`, `@click.command` |
| gui_event | `command=...`, `.bind("<...>", ...)` |
| button_click | `.clicked.connect(...)` |
| callback | `addEventListener`, `after(...)`, `callback=...` |
| worker | decorator `@*.task` |
| public_api | danh sách `__all__` |

`export` và `command` được khai báo nhưng **chưa phát** vì chưa có bằng chứng đủ chắc
(module.exports là ranh giới của mọi file JS).

Đọc kết quả: mỗi dependency có `path`, `start_line`, `relation`, `why_included`,
`evidence_refs`. Nếu `external_dependencies` xuất hiện, đó là bảng/gói ngoài — không có
path trong repo, đừng cố mở.

## 13. Verify: đọc verdict cho đúng (0.4.0)

| Trường | Nghĩa |
|---|---|
| `static_verdict` | chỉ những gì đã kiểm tại chỗ: graph, artifact, quét HTML tĩnh, privacy, test mapping |
| `overall_verdict` | `pass` chỉ khi cả `static`, `ui`, `runtime` đều pass |
| `gates` | trạng thái từng gate: pass/blocked |
| `not_verified` | gate còn thiếu bằng chứng |
| `next_action` | việc cần làm để nâng verdict |

Mặc định `ui` và `runtime` là **blocked**: tool không mở trình duyệt và không chạy test.
Vì vậy một repo sạch sẽ cho `static_verdict=pass`, `overall_verdict=partial`. Đó là kết quả đúng,
không phải lỗi.

## 10. Bằng chứng của chính hướng dẫn này

| Bằng chứng | File |
|---|---|
| Chạy thật trên dự án desktop | `artifacts/review/*-real-project-desktop-project.json` |
| Chạy thật trên dự án web (47 route) | `artifacts/review/*-real-project-web-project.json` |
| Tổng hợp hai lần chạy | `evidence-manifest.json` mục `real_projects` |
| Test khoá hành vi query ngắn/dài | `tests/test_knowledge.py` — `test_long_natural_query_is_flagged`, `test_short_query_has_no_long_query_warning` |
| Test khoá thứ hạng exact > vector | `test_exact_match_outranks_vector_candidate` |
| UI và tương tác | [20261119-ui.json](artifacts/review/20261119-ui.json) |
| Toàn bộ số liệu pass | [evidence-manifest.json](artifacts/review/evidence-manifest.json) |

Cách tái lập trên repo của bạn:

```bash
python3 scripts/run_real_project_check.py --repo <duong/dan/repo> \
  --request "mô tả flow bạn muốn hiểu"
```

Script copy repo sang thư mục tạm, chạy đủ 6 bước, rồi ghi báo cáo đã loại path và tên repo.