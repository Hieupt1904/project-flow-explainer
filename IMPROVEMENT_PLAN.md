# IMPROVEMENT_PLAN

Backlog sau MVP, xếp theo giá trị/chi phí. Không mục nào ở đây chặn việc dùng bản hiện tại.

## P1 — làm tiếp ngay khi có nhu cầu

| # | Việc | Vì sao | Cách kiểm chứng |
|---|---|---|---|
| 1 | Cài bundle vào `pfe-test` và chạy smoke 12 bước trong DSH thật | Điều kiện còn thiếu để gọi MVP là hoàn thành đầy đủ | `dsh --profile pfe-test --dump-config` có row plugin; gọi tool tạo 3 file; unload/reload |
| 2 | Bố cục serpentine cho chuỗi dài trong `assign_positions` | "Toàn cảnh" co còn 34% với 8 node (UI-002) | so screenshot 1440×900 trước/sau; đo `#zoom-level` sau fit |
| 3 | Phân tích call-graph thật (import/reference) để nối bước theo quan hệ gọi, không theo điểm số | Hiện tại thứ tự bước là heuristic theo score; một số repo sẽ ra thứ tự chưa đúng | fixture có 2 nhánh gọi chéo; so graph với grep thủ công |

## P2 — mở rộng đầu vào

| # | Việc | Ghi chú |
|---|---|---|
| 4 | Nhận GitHub URL (clone vào thư mục tạm, giới hạn dung lượng, xoá sau khi xong) | đã chốt hoãn ở Q1; cần thêm bước xin phép mạng rõ ràng |
| 5 | Nhiều flow trong một repo → `index.md` + nhiều cặp JSON/HTML | schema đã hỗ trợ tách subflow; chỉ cần điều phối |
| 6 | Hỗ trợ thêm ngôn ngữ (Go, Rust, C#, Kotlin) trong `SYMBOL_PATTERNS`/`ENTRY_PATTERNS` | thêm pattern + fixture, không đổi schema |

## P2 — chất lượng kết quả

| # | Việc | Ghi chú |
|---|---|---|
| 7 | Đọc `routes` khai báo động (router.use, file-based routing của Next/Nuxt) | giảm trường hợp `end` bị `inferred` |
| 8 | Gắn nhãn `partial` chi tiết hơn: tách "khớp chủ đề" và "suy ra vai trò" | hiện một node có thể vừa verified về vị trí, vừa suy luận về vai trò |
| 9 | Sinh `overview.md` có sơ đồ ASCII/Mermaid song song | hữu ích khi dán vào PR/issue |
| 10 | Cho phép `flow_request` tiếng Anh và trộn Việt–Anh tốt hơn | lexicon hiện tại đã có cả hai, nhưng ưu tiên tiếng Việt |

## P3 — vận hành

| # | Việc | Ghi chú |
|---|---|---|
| 11 | Benchmark repo lớn (chục nghìn file) và cache kết quả quét | hiện cắt ở 20 000 file, chưa đo thời gian |
| 12 | Ký/kiểm tra checksum cho `flow.json` để so sánh giữa hai lần chạy | hữu ích cho diff trong CI |
| 13 | Panel UI trong Harness | chỉ mở lại khi `cordis_inspect_query` xác nhận register API của slot; hiện `BLOCKED_UI_API_UNVERIFIED` |
| 14 | Đưa `build_flow.py` thành package cài được (`pipx`/`uv`) | giữ CLI tương thích |

## Nợ kỹ thuật đã biết

- `build_flow.py` là một file ~900 dòng; khi thêm ngôn ngữ nên tách `pfe/scan.py`, `pfe/score.py`, `pfe/graph.py`.
- `PREFERRED_SYMBOL` là danh sách tên cố định; nên chuyển sang scoring theo vị trí (đầu file, có route gọi tới).
- Adapter chưa có `Config` schema kiểu Cordis (đang validate tay) vì không import được `@deepseek-ai/schemastery`; nếu sau này profile resolve được thì chuyển sang schema chuẩn.
