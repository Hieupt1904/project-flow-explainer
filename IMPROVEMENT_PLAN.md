# IMPROVEMENT_PLAN


> **Snapshot lịch sử — không phải trạng thái hiện tại.**
> Tài liệu này ghi lại thời điểm 0.3.0; số liệu bên dưới đúng ở thời điểm đó.
> Trạng thái hiện tại của bản `0.6.4`: xem [artifacts/review/evidence-manifest.json](artifacts/review/evidence-manifest.json) (`package_version`, `smoke.registry_runtime`, `smoke.model_driven`, `classification`).

Backlog sau 0.3.0. Không mục nào chặn việc dùng bản hiện tại.

## P0 — cần trước khi gọi 0.3.0 là phát hành đầy đủ

| # | Việc | Vì sao | Cách kiểm chứng |
|---|---|---|---|
| 1 | Cài tarball 0.3.0 vào `pfe-test` và chạy smoke 7 tool | Bước cài chạy npm/pnpm trong profile nên cần xin phép; hiện chỉ có bằng chứng adapter in-process | `dsh --profile pfe-test --dump-config` có 7 tool; gọi index → search → verify; disable/enable/remove |
| 2 | Chạy model-driven smoke khi có API key | Chứng minh model tự chọn tool, không chỉ registry probe | phiên có key gọi `project_context_pack` và ghi lại trajectory |

## P1 — chất lượng tri thức

| # | Việc | Ghi chú |
|---|---|---|
| 3 | Call graph có phân giải alias/namespace/DI | hiện chỉ nhận tên symbol duy nhất; thêm resolver theo import binding |
| 4 | Embedding ngữ nghĩa local (sentence-transformers hoặc ONNX) | giữ nguyên interface `EmbeddingBackend`; thêm `semantic=True` và test đổi model |
| 5 | Học trọng số rerank từ log sử dụng | hiện là hằng số; cần dữ liệu chọn kết quả |
| 6 | Parse `router.use` / file-based routing (Next, Nuxt) | giảm trường hợp `end` bị `inferred` |
| 7 | Ontology mở rộng: `returns` khi có type info (typed languages) | hiện khai báo nhưng không phát |

## P2 — vận hành

| # | Việc | Ghi chú |
|---|---|---|
| 8 | `detect-rename` bằng git thay vì content hash | chính xác hơn khi file đổi cả nội dung lẫn tên |
| 9 | Benchmark > 20 000 file và đo peak RSS theo bước | hiện đo tới 2 001 file |
| 10 | Nén index (FTS5 optimize + vacuum định kỳ) | DB 15 MB cho 2 000 file |
| 11 | Panel UI trong Harness | chỉ mở khi xác minh register API của slot |
| 12 | Nhận GitHub URL | cần bước xin phép mạng rõ ràng; hiện chỉ local path |

## Nợ kỹ thuật đã biết

- `pfe/facts.py` còn gộp scan + extract; nên tách `scan.py` / `extract.py` khi thêm ngôn ngữ.
- `pfe/flow.py` vẫn dùng điểm số facet để chọn route; nên chuyển sang xếp hạng theo graph + tên route.
- `pfe/retrieval.py` giữ bảng trọng số trong code; nên đưa ra file cấu hình có version.
- Adapter chưa có `Config` schema native (profile không resolve `@deepseek-ai/schemastery`); validate tay là mức hiện tại.
- Chi phí `quick_staleness` là O(số file đã index) mỗi query; với repo rất lớn nên cache theo thư mục.

## Đã xử lý trong 0.3.0

- Bỏ claim call graph khi chưa có call-site parser; ontology từ chối fact `calls` thiếu call site.
- Decision/error node chỉ lấy từ vùng code của route/hàm được chọn.
- Ghi artifact qua staging + rename; không còn artifact dở dang, không ghi đè khi chạy song song.
- `run.json` trở thành internal provenance, có test và policy check.
- allowedRoots deny-by-default giữ nguyên và áp cho cả 6 tool tri thức.
- File chứa secret-shaped line không vào index; symlink tới `.env`/artifact bị loại.
- `/tmp`/, `~/Documents`/ và Windows user path bị policy chặn; log cũ đã dọn.
- Thêm benchmark có số đo thật và ngân sách byte/file/tổng.
