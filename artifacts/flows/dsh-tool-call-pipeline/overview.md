# Luồng: Một lần gọi tool `project_flow_explain` — từ yêu cầu đến `flow.html`

Dựng tay từ call site thật · 2026-11-20 (Asia/Bangkok) · commit `6b6524b` · schema 2.

## Mục đích

Giải thích chuyện gì thật sự xảy ra khi agent gọi tool này: ai kiểm quyền, ai đọc file,
chỗ nào chống bịa quan hệ, và bốn file đầu ra được ghi an toàn thế nào.

## Điểm vào và điểm kết thúc

| Mục | Giá trị |
|---|---|
| Bắt đầu | agent gọi tool với `repository_path` + `flow_request` (`dsh-plugin/index.js`:242) |
| Điểm vào cụ thể | `execute()` kiểm lại tham số rồi kiểm quyền đọc (`dsh-plugin/index.js`:372) |
| Kết thúc | agent nhận đường dẫn tương đối tới `flow.html`/`flow.json`/`overview.md` (`dsh-plugin/index.js`:428) |
| Độ dài | 13 node, 14 cạnh, 2 nhánh lỗi, 2 điểm rẽ nhánh |
| Người đọc | người dùng tool, reviewer, người không đọc code |

## Các bước

| # | Bước | Loại | Vị trí | Tin cậy |
|---|---|---|---|---|
| 1 | Agent nhận yêu cầu giải thích một luồng | start | `dsh-plugin/index.js`:242 | verified |
| 2 | Nhận yêu cầu và kiểm tham số bắt buộc | action | `dsh-plugin/index.js`:372 | verified |
| 3 | Repository này có được phép đọc không? | decision | `dsh-plugin/lib/paths.js`:101 | verified |
| 4 | Gọi core Python bằng subprocess, không qua shell | external | `dsh-plugin/lib/core-runner.js`:156 | verified |
| 5 | CLI nhận lệnh flow và chuyển cho lõi | action | `tools/pfe_cli.py`:66 | verified |
| 6 | Quét source thành dữ kiện tĩnh, bỏ secret và test | data | `pfe/facts.py`:488 | verified |
| 7 | Chọn điểm vào và dựng từng bước có bằng chứng | action | `pfe/flow.py`:157 | verified |
| 8 | Có route hoặc handler nào làm điểm vào không? | decision | `pfe/flow.py`:222 | verified |
| 9 | Dừng và nói rõ lý do, không bịa quan hệ | error | `pfe/flow.py`:232 | verified |
| 10 | Kiểm schema trước khi ghi ra đĩa | action | `pfe/emit.py`:161 | verified |
| 11 | Ghi bốn file vào thư mục tạm rồi đổi tên một lần | data | `pfe/emit.py`:152 | verified |
| 12 | Trả lỗi có mã ổn định cho người gọi | error | `dsh-plugin/index.js`:421 | verified |
| 13 | Agent nhận đường dẫn tương đối và số node | end | `dsh-plugin/index.js`:428 | verified |

## Vì sao thiết kế như vậy

- **Kiểm quyền trước khi đọc.** `allowedRoots` rỗng nghĩa là không cho phép repository nào.
  Đường dẫn tương đối bị từ chối trước khi chạm đĩa (`paths.js`:107).
- **Node không chạy code của repository.** Node chỉ `spawn` Python với argv dạng mảng,
  `shell: false`, môi trường thu hẹp, stdout có trần dung lượng (`core-runner.js`:69).
- **Chống bịa quan hệ.** Không có call-site parser cho flow, nên `add_edge` ném
  `AssertionError` nếu ai gắn `evidence='call'` (`pfe/flow.py`:195). File chỉ khớp từ khoá
  nằm ở `meta.related`, không thành node.
- **Không có điểm vào thì vẫn ghi artifact.** Người dùng nhận sơ đồ dừng sớm có ghi chú
  giới hạn, thay vì trang trắng hay một luồng tưởng tượng (`pfe/flow.py`:230-240).
- **Ghi nguyên tử.** Cả bộ bốn file ghi vào `.staging-*` rồi `os.rename` sang `<slug>`;
  đổi tên là phép kiểm tranh chấp hai lần chạy cùng slug (`pfe/policy.py`:129-160).
- **Đường dẫn trả về là tương đối.** `relative()` cắt đường dẫn tuyệt đối trước khi trả cho
  model (`index.js`:433). Không có nội dung source trong kết quả.

## Phân biệt "từ code xác nhận" và "suy luận"

- **Từ code xác nhận:** mọi vị trí trong bảng trên và toàn bộ mệnh đề ở mục thiết kế.
  Trường `technical` của từng node/cạnh ghi file:dòng để người đọc tự kiểm lại.
- **Suy luận:** nhánh timeout và abort không vẽ. `core-runner.js` có xử lý chúng, nhưng chưa
  có test đầu-cuối nào trong phiên bản này chứng minh hành vi đó.

## Giới hạn

- `verified` nghĩa là vị trí có thật và quan hệ đọc được từ import/call site. Nó **không**
  nghĩa là đã chạy runtime.
- Sơ đồ tả một lần gọi thành công. Ba mã lỗi `core_timeout`, `Aborted`, `artifact_exists`
  chỉ được nhắc trong ghi chú, không thành node.
- Không mô tả sáu tool tri thức (`project_code_index`, `project_code_search`,
  `project_context_pack`, `project_impact_analysis`, `project_verify_flow`,
  `project_knowledge_refresh`). Chúng dùng chung `pfe_cli.py` nhưng khác nhánh xử lý.

## Kiểm tra đã chạy

| Việc | Kết quả |
|---|---|
| `scripts/render_flow.py` validate graph | 13 node, 14 cạnh, entry `start` |
| `tools/pfe_cli.py verify` (static) | pass: graph_evidence, ui_self_contained, privacy; `test_mapping` blocked vì index cục bộ đã xoá theo policy |
| `scripts/check_repo_policy.py` | pass — 105 file, không absolute path, không nested artifact, không secret |
| Mở `flow.html` trong Chrome | 13 `.node-card`, 14 `.edge-set`, panel chi tiết hiện nguồn `pfe/flow.py`:157-200 |

## Tệp sinh ra

- `flow.json` — dữ liệu có cấu trúc, render lại được
- `flow.html` — sơ đồ tương tác, mở offline, không CDN
- `overview.md` — tài liệu này
