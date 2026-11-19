# Luồng: Kiến trúc project-flow-explainer — hai lớp, một bộ sự thật

Bản đồ tổng quan dựng tay từ call site thật · 2026-11-20 (Asia/Bangkok) · commit `6b6524b`.

## Mục đích

Đọc project này trong một trang: nó có những lớp nào, lớp nào quyết định chất lượng câu trả lời,
và vì sao hai tính năng (dựng sơ đồ luồng, tra cứu tri thức code) không thể nói hai đằng hai nẻo.

## Điểm vào và điểm kết thúc

| Mục | Giá trị |
|---|---|
| Bắt đầu | câu hỏi "luồng này chạy thế nào?" (`SKILL.md`:1) |
| Bước đầu tiên | đọc file mô tả, entry point, cấu trúc thư mục (`SKILL.md`:13) |
| Kết thúc | sơ đồ HTML mở offline + `overview.md` + danh sách vị trí `path:dòng` (`SKILL.md`:20) |
| Độ dài | 10 node, 11 cạnh, một điểm rẽ nhánh duy nhất |

## Các lớp

| Lớp | Trạng thái | Thành phần | Node trong sơ đồ |
|---|---|---|---|
| Skill (tri thức cho agent) | **ĐÃ TRIỂN KHAI** | `SKILL.md`, `references/*` | Skill dạy cách đọc repo |
| Adapter DSH | **ĐÃ TRIỂN KHAI** | `dsh-plugin/`, 7 tool, `allowedRoots` | qua nhánh tra cứu và nhánh flow |
| Core sự thật tĩnh | **ĐÃ TRIỂN KHAI** | `pfe/facts.py` | Một bộ sự thật dùng chung |
| Lớp 1 — sơ đồ luồng | **ĐÃ TRIỂN KHAI** | `pfe/flow.py`, `pfe/emit.py`, `scripts/render_flow.py` | dựng sơ đồ → artifact |
| Lớp 2 — tri thức code | **ĐÃ TRIỂN KHAI**; vector tùy chọn, đang tắt | `pfe/index.py`, `pfe/retrieval.py`, `pfe/impact.py`, `pfe/verify.py` | index → tra cứu |
| Panel UI trong Harness | **BLOCKED_UI_API_UNVERIFIED** | chưa có code | không có node |

## Vì sao "một bộ sự thật" là điểm quan trọng nhất

`pfe/facts.py`:488 quét repository một lần thành symbol, route, import và test. Cả hai lớp đọc
cùng bộ đó: `scripts/build_flow.py`:98 lấy fact rồi `:104` dựng sơ đồ; `pfe/index.py`:182 ghi
cùng fact vào SQLite. Nhờ vậy, một dòng code hiện trong sơ đồ cũng tìm được bằng `search`, và
`verify` đối chiếu được cả hai.

## Từ code xác nhận và suy luận

- **Từ code xác nhận:** toàn bộ đường dẫn file:dòng trong bảng lớp và trong `technical` của
  từng node.
- **Suy luận:** thứ tự đọc project (skill → facts → flow/index) là cách project tự mô tả trong
  `SKILL.md`, không phải ràng buộc kỹ thuật; chạy `search` trước khi dựng sơ đồ vẫn hợp lệ.

## Giới hạn

- Đây là sơ đồ kiến trúc, không phải luồng nghiệp vụ. Luồng chi tiết của nhánh dựng sơ đồ nằm
  ở `../dsh-tool-call-pipeline/flow.html`.
- CI (`.github/workflows/ci.yml`) và 26 file test không vẽ thành node để giữ canvas ở mức kiến trúc.
- Vector backend là tùy chọn và đang tắt trong lần chạy này; không node nào phụ thuộc model.
