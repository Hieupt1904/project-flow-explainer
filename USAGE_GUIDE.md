# Hướng dẫn sử dụng

Chọn **bản đồ toàn kho** để xem cấu trúc. Chọn **sơ đồ luồng** để lần theo một nghiệp vụ. Dùng **chỉ mục mã nguồn** để tìm vị trí cần đọc hoặc kiểm tra tác động của thay đổi.

## 1. Chọn công cụ

| Bạn đang có | Dùng | Vì sao |
|---|---|---|
| Tổng quan mô-đun, tệp và đường dẫn web | `project_map.mjs build` hoặc `/project-flow-explainer --map` | Dựng bản đồ toàn kho. |
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
python3 scripts/build_flow.py --repo "$R" \
  --request "Giải thích từ lúc người dùng bấm cập nhật dữ liệu đến khi có file Excel"

# 2) Tạo index để tra cứu
python3 tools/pfe_cli.py index --repo "$R" --mode full

# 3) Tra đúng chỗ
python3 tools/pfe_cli.py search --repo "$R" --query "write_xls"

# 4) Kiểm tra những gì đã sinh
python3 tools/pfe_cli.py verify --repo "$R"
```

## 3. Xem bản đồ toàn kho

Chạy các lệnh từ kho Project Flow Explainer. Đặt `R` thành đường dẫn tuyệt đối của kho mã cần xem.

```bash
node scripts/project_map.mjs build "$R"
node scripts/project_map.mjs status "$R"
```

Mở `<repo>/project-flow-explainer/index.html`. Chọn một phân hệ để xem chi tiết. Nhấp đúp để mở cấp mô-đun hoặc tệp khi thẻ có cấp con. Dùng phím `/` để tìm theo tên, mô tả, đường dẫn hoặc tuyến web.

| Mục | Cách dùng |
|---|---|
| **Bắt đầu** | Mở tour giới thiệu các phần chính. |
| **Luồng** | Chọn một luồng đã lưu hoặc yêu cầu tra cứu đường nối mới khi máy chủ đang chạy. |
| **Màn hình** | Xem các màn hình khi bộ quét nhận diện được. |
| **Sức khỏe** | Xem những mục bộ quét đã kiểm tra và những mục còn thiếu căn cứ. |
| **Việc gần đây** | Xem thay đổi giữa hai lần dựng hoặc ghi chú đã lưu. |

### Dữ liệu, cập nhật và chia sẻ

- Sửa `architecture.json` để điều chỉnh cách nhóm và mô tả phân hệ. Dùng `describe` để tạo phiếu bổ sung mô tả tệp và tuyến web.
- Chạy `node scripts/project_map.mjs refresh "$R"` sau khi mã nguồn thay đổi. Lệnh này khác `pfe_cli.py refresh`, vốn cập nhật chỉ mục mã nguồn.
- Chạy `node scripts/project_map.mjs export "$R"` để tạo `<repo>/project-flow-explainer/share.html`. Bản chia sẻ giữ dữ liệu hiển thị, chẳng hạn tên tệp và mô tả. Kiểm tra nội dung trước khi gửi.
- Để dựng bản phác, lưu `plan.json` theo [định dạng bản phác](vendor/project-flow-explainer/references/blueprint.md). Sau đó chạy `node scripts/project_map.mjs plan "$R"`. Bản phác mô tả hệ thống **DỰ KIẾN**; lệnh không tạo mã ứng dụng.

### Bật thanh Hỏi

Từ thư mục gốc của kho mã **đã có bản đồ**, chọn một chế độ và mở địa chỉ loopback mà máy chủ in ra. Để dừng máy chủ, nhấn `Ctrl+C` trong terminal đang chạy lệnh.

| Chế độ | Lệnh | Dữ liệu dùng để trả lời |
|---|---|---|
| Tra cứu cục bộ | `node project-flow-explainer/serve.mjs --no-open` | Tìm trong dữ liệu bản đồ. Không cần DSH hoặc khóa mô hình. |
| Hỏi qua DeepSeek Harness (DSH) | `node project-flow-explainer/serve.mjs --no-open --agent` | Chọn mô hình từ danh sách của hồ sơ `web`. Máy chủ gọi `dsh --profile headless --json --permission-mode read-only --approval-policy never -` và đưa câu hỏi qua stdin. |

Nếu bật `--agent`, chọn mô hình và nhà cung cấp cạnh thanh **Hỏi**. Danh sách lấy từ cấu hình đã khai báo trong hồ sơ `web`. Tải lại bản đồ sau khi thêm mô hình. Nếu máy chủ không tải được danh sách hoặc báo thiếu khóa, xem [hướng dẫn xử lý trong tài liệu plugin](dsh-plugin/README.md#thanh-hỏi-trên-bản-đồ). Để tra cứu trên máy, chạy lại máy chủ không kèm `--agent`. Bản mở trực tiếp từ tệp hoặc bản chia sẻ không gửi câu hỏi.

Trong một phiên DSH đã cài plugin, mô hình thấy skill `project-flow-explainer`. Skill đó chỉ cách chọn công cụ dựng sơ đồ và tra cứu. Lệnh `/project-flow-explainer` vẫn dành cho người dùng. Cài plugin và các cờ headless nằm trong [README plugin](dsh-plugin/README.md).

## 4. Đọc và dựng lại sơ đồ luồng

Trong trình xem chính, chọn **Dẫn qua luồng** để bắt đầu từ điểm vào. Chọn một nhánh để đi tiếp hoặc **Quay lại** để trở về bước vừa xem. Mở **Căn cứ** để đối chiếu tệp và dòng mã. Chọn **Tải HTML** để lưu bản sao.

Để giữ dữ liệu cũ và dùng giao diện mới, dựng lại HTML từ `flow.json`. Dùng một tên đầu ra khác để giữ tệp HTML cũ.

```bash
python3 scripts/render_flow.py path/to/flow.json --out path/to/flow-new.html
python3 scripts/render_flow.py path/to/flow.json --viewer classic --out path/to/flow-classic.html
```

Giao diện dự phòng mở ở **Bản đồ**. Chọn **Từng bước** để đọc danh sách và mở **Căn cứ** để xem mức độ xác minh. Nếu máy dựng thiếu Node.js, trình dựng dùng giao diện dự phòng.

## 5. Vòng lặp hằng ngày khi sửa code

```text
index (một lần)  →  search/context (hiểu chỗ sửa)  →  sửa code
      ↑                                                     ↓
      └── refresh (chỉ file đổi)  ←  impact (biết phải test gì)  ←  verify
```

```bash
# trước khi sửa: lấy context
python3 tools/pfe_cli.py context-pack --repo "$R" --task "sửa chức năng xuất Excel quyết toán"

# sau khi sửa: biết ảnh hưởng gì
python3 tools/pfe_cli.py impact --repo "$R" --changed src/_xls.py

# cập nhật index (chỉ file đã đổi)
python3 tools/pfe_cli.py refresh --repo "$R"

# kiểm tra lại artifact/flow nếu có đổi graph
python3 tools/pfe_cli.py verify --repo "$R"
```

`impact` trả `risk_level`, `affected_routes`, `affected_symbols`,
`related_tests`, `downstream_modules`, `suggested_verification`.
Đọc `risk_reasons` để biết vì sao high/medium/low, đừng chỉ nhìn nhãn.

## 6. Viết truy vấn tra cứu

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

## 7. Đọc kết quả cho đúng

Mỗi kết quả có: `path`, `symbol`, `start_line`–`end_line`, `relation`,
`confidence`, `score`, `why_matched`, `evidence_refs`, `source_commit`.

| Trường | Cách đọc |
|---|---|
| `confidence: observed` | có dòng thật; tin được vị trí |
| `confidence: structural` | suy ra từ import/test; đúng cấu trúc, chưa chắc runtime |
| `confidence: inferred` | Kết quả suy luận. Mở mã nguồn để xác nhận. |
| `relation: []` và `why_matched` ghi "chỉ khớp từ khoá" | **nghi ngờ**: đúng chữ nhưng không có quan hệ graph |
| `relation: ["calls"]` | có call site thật trong file nguồn |
| `stale: true` | index cũ hơn working tree → chạy `refresh` trước khi tin |
| `score` | chỉ để xếp hạng, không phải xác suất |

Ưu tiên kết quả `observed` có `relation`. Dùng `score` để xếp thứ tự đọc trong cùng một truy vấn, không dùng làm ngưỡng xác nhận.

## 8. Prompt mẫu cho agent trong DSH

```text
Trước khi sửa: gọi project_context_pack với task "..." và đọc likely_files + entry_points.
Nếu kết quả stale=true thì gọi project_knowledge_refresh trước.
Sau khi sửa: gọi project_impact_analysis với changed_files, đọc risk_reasons và
suggested_verification; chạy đúng test trong related_tests.
Cuối cùng gọi project_verify_flow; nếu verdict=partial thì nêu rõ check nào blocked.
Không đọc toàn bộ file nếu search đã trả đúng path:line.
```

## 9. Giới hạn phân tích

| Bẫy | Sự thật | Cách tránh |
|---|---|---|
| Coi `verified` là đã chạy | Nhãn chỉ xác nhận vị trí và quan hệ tĩnh. | Chạy kiểm thử liên quan để xác nhận hành vi. |
| Coi `calls` là call graph đầy đủ | chỉ call site đọc theo tên symbol duy nhất | alias/DI có thể thiếu |
| Coi vector là ngữ nghĩa | backend mặc định là hashing bag-of-words | bật vector chỉ để tăng recall |
| Query câu dài rồi tin top-1 | FTS cộng dồn theo từ khoá | dùng flow hoặc rút query |
| Quên refresh | index cũ, kết quả lệch | đọc `stale`/`warnings` mỗi lần |
| Repo không có route | flow trả `no-entry` (đúng, không bịa) | dùng index + search thay vì flow |
| Dự án desktop/CLI | `entry_points = 0` | đọc `likely_files` và `impacted_symbols` |

## 10. Mã lỗi thường gặp

| Mã | Nghĩa | Sửa |
|---|---|---|
| `index_missing` | chưa có `.pfe/index` | chạy `index --mode full` |
| `stale=true` | index cũ hơn file | chạy `refresh` |
| `no_changed_files` | impact thiếu đầu vào | truyền `--changed` hoặc `--diff` |
| `repository_outside_allowed_roots` | path ngoài root (DSH) | thêm root vào `allowedRoots` |
| `missing_flow_request` | thiếu mô tả flow | truyền `--request` |
| `artifact_exists` | slug đã tồn tại | bỏ `--slug` để tự sinh |
| `core_timeout` | vượt ngân sách | tăng `timeoutMs` hoặc thu hẹp phạm vi |

## 11. Đối chiếu trước khi dùng kết quả

1. `source_commit` trùng commit bạn đang làm việc.
2. `stale` bằng `false`.
3. Kết quả top có `confidence: observed` và ít nhất một `relation`.
4. Đã mở đúng `path:line` mà kết quả trỏ tới (không tin mà không mở).
5. Nếu là flow: đọc `limits` và `meta.related` trước khi kết luận luồng đã đủ.


## 12. Điểm vào trong gói ngữ cảnh

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

## 13. Đọc kết quả xác minh

| Trường | Nghĩa |
|---|---|
| `static_verdict` | chỉ những gì đã kiểm tại chỗ: graph, artifact, quét HTML tĩnh, privacy, test mapping |
| `overall_verdict` | `pass` chỉ khi cả `static`, `ui`, `runtime` đều pass |
| `gates` | trạng thái từng gate: pass/blocked |
| `not_verified` | gate còn thiếu bằng chứng |
| `next_action` | việc cần làm để nâng verdict |

Mặc định `ui` và `runtime` là **blocked**: tool không mở trình duyệt và không chạy test.
Nếu kiểm tra tĩnh đạt, `static_verdict=pass` và `overall_verdict=partial` vẫn là kết quả dự kiến.

## 14. Bằng chứng và số liệu lịch sử

Các số liệu dưới đây thuộc các lần chạy trước. Chúng không mô tả kết quả của bản hiện tại.

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
