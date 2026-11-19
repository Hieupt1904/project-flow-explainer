# Module 02 — Flow Tracer

## Tư duy theo trạng thái và tác nhân

Một bước hợp lệ có: sự kiện/vào điều kiện → một hành động hoặc quyết định → kết quả/side effect → bước tiếp theo. Ghi actor (`user`, `browser`, `backend`, `database`, `worker`, `external`, `system`) khi rõ; có thể gộp các lệnh code vô nghĩa với nghiệp vụ vào một bước.

## Chuỗi cần kiểm tra

- UI: render → click/submit/input → state validation → API call → loading/error/success UI.
- Backend: route → auth middleware → validator → controller → service/domain → DB/cache → response.
- Async: publish/enqueue → consumer/worker → retries/backoff → dead-letter/failure → callback/webhook/status.
- Decision: mọi `if/switch/guard/exception handler` ảnh hưởng kết quả nghiệp vụ, không chỉ điều kiện điều hướng.
- Data: tạo/sửa/xóa/đọc dữ liệu thực tế; nêu điều kiện và hậu quả ở mức nghiệp vụ, tránh lộ dữ liệu nhạy cảm.

## Chứng cứ cho các cạnh

Ghi edge cùng căn cứ: từ file nào gọi/file nào nhận; nhãn điều kiện; sync/async; loại success/error/retry/normal. Với nhánh chưa tìm thấy đích, tạo node `unknown` thay vì giả định. Không ép luồng tuần tự cho code chạy song song.

## Nguyên tắc vẽ lại

- Một luồng chính 5–12 node; nếu 2 nhánh trở lên chứa logic dài, tách subflow.
- Tránh một node đại diện cả 3 quyết định quan trọng.
- Mọi cạnh từ decision node phải có nhãn cụ thể. Edge lặp phải có `kind=loop`, không gây lỗi topological layout.
- Endpoint có thể kết thúc ở response hoặc mở thêm subflow cho worker. Không vẽ mọi package/module bằng nhau.
