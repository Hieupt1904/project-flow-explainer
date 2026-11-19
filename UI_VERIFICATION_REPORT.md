# UI_VERIFICATION_REPORT — 0.4.0

Kiểm tra bằng trình duyệt thật (CDP), mở trực tiếp file://. Máy đọc:
[artifacts/review/20261119-ui.json](artifacts/review/20261119-ui.json).

| Mục | Giá trị |
|---|---|
| Thời điểm | 2026-11-19 |
| Sample | shop (6 node), self (13 node), empty (2 node) |
| Viewport | 1440×900 · 1280×800 · 768×1024 · 375×812 |
| Tổ hợp | 12, mỗi tổ hợp đo **Simple view** và **Technical view** |
| Cách đo | getBoundingClientRect cho card/nhãn; performance resource cho request ngoài; window.__pfeErrors cho lỗi |

## 1. Simple view (mặc định)

| Chỉ số | Kết quả |
|---|---|
| Số stage | 3–7 tuỳ flow (shop 4, self 7, empty 3) |
| Tràn ngang | 0/12 |
| Console error | 0/12 |
| Request ngoài file:// | 0/12 |
| Stage bấm được | 12/12 (mở panel chi tiết) |
| Bàn phím | focus + Enter mở panel (test tự động) |
| Search | "báo cáo" → 1/4 stage; xoá query → 4/4 |

## 2. Technical view (sau khi bấm tab Kỹ thuật)

| Chỉ số | Kết quả |
|---|---|
| Card chồng nhau | 0/12 |
| Nhãn cạnh đè card | 0/12 |
| Header bị cắt | 0/12 |
| Zoom khởi đầu | 102% (1440/1280), 94% (768), 55% (375) |
| Zoom in | 102% → 119% |
| Toàn cảnh (chủ động) | 40% với flow 6 node |

## 3. Hành vi

| Hành động | Kết quả |
|---|---|
| Mở file | vào Simple view, canvas ẩn |
| Chọn stage / card | panel phải đổi sang "Chi tiết bước đang chọn" |
| Chuyển Kỹ thuật → Đơn giản | giữ nguyên, không lỗi |
| Search khi không khớp | hiện tất cả stage + "Không có bước khớp" |
| Kéo / zoom / Toàn cảnh | hoạt động ở Technical view |

## 4. Vấn đề còn lại

| ID | Hiện tượng | Trạng thái |
|---|---|---|
| UI-002 | Nút "Toàn cảnh" co còn 40% với flow 6 node | **đã ghi nhận**, đây là hành động chủ động của người dùng; Simple view là mặc định nên không cần fit |

Không có lỗi layout nào khác trong lần chạy này.

## 5. Ảnh chụp

| File | Nội dung |
|---|---|
| [shop-375x812.png](artifacts/ui-verification/shop-375x812.png) | Simple view trên mobile |
| [shop-1440x900.png](artifacts/ui-verification/shop-1440x900.png) | Simple view desktop |
| [self-1440x900.png](artifacts/ui-verification/self-1440x900.png) | flow 13 node |
| [empty-375x812.png](artifacts/ui-verification/empty-375x812.png) | flow rỗng (no-evidence) |
