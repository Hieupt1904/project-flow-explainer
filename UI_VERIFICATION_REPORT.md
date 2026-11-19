# UI_VERIFICATION_REPORT — `flow.html`

Phương pháp: mở file HTML thật trong ego browser (Chromium), đổi viewport bằng CDP
`Emulation.setDeviceMetricsOverride`, chụp screenshot, đo DOM và đăng ký collector
`window.__pfe` trước khi load để bắt console error / unhandled rejection. Sample sinh lại từ HEAD
(`artifacts/samples/{shop,self,empty}`), ảnh lưu ở `artifacts/ui-verification/`.

Kết luận: **PASS** cho cả ba viewport; không phát hiện lỗi mới. UI-001 (đã sửa ở pass trước) vẫn giữ.

## 1. Ma trận đo được

| Viewport | Sample | Node | Zoom khởi đầu | Tràn ngang | Tiêu đề cắt | Card chồng | Search | Panel | Console error | Request ngoài |
|---|---|---|---|---|---|---|---|---|---|---|
| 1440×900 | shop | 8 | 102% | 0 px | không | không | `4/8` | 3 section | 0 | 0 |
| 768×1024 | shop | 8 | 94% | 0 px | không | không | `4/8` | 3 section | 0 | 0 |
| 375×812 | shop | 8 | 55% | 0 px | không | không | `4/8` | 3 section | 0 | 0 |
| 1440×900 | self | 6 | 102% | 0 px | không | không | `0/6` | 3 section | 0 | 0 |
| 375×812 | self | 6 | 55% | 0 px | không | không | `0/6` | 3 section | 0 | 0 |
| 1440×900 | empty | 2 | 102% | 0 px | không | không | `0/2` | 3 section | 0 | 0 |
| 375×812 | empty | 2 | 55% | 0 px | không | không | `0/2` | 3 section | 0 | 0 |

Tương tác đã thực thi thật: click card → panel "Chi tiết bước đang chọn" với 3 section; gõ search →
`#search-count` cập nhật, card không khớp bị làm mờ; `+`/`−`/`Toàn cảnh` đổi `#zoom-level`; pan bằng
pointer drag.

Chip "Phạm vi" giờ chỉ hiển thị `Đọc source trong repository · <chủ đề>` — không còn đường dẫn tuyệt đối
của máy cá nhân (trước đây là đường dẫn tuyệt đối của máy cá nhân), khớp policy TASK 7.

## 2. Lỗi và trade-off

### UI-001 — Card kế tiếp bị cắt ở cạnh canvas (đã sửa, giữ nguyên bản sửa)

`initialView()` trước đây chỉ fit theo chiều cao nên card thứ hai bị cắt giữa chữ ở 768×1024.
Bản sửa thêm `scaleX = (vw-46)/(maxX-minX)`; đo lại: 768×1024 zoom 94%, **0 card bị cắt**
(trước: 1 card).

### UI-002 — "Toàn cảnh" co còn 34% với chuỗi 8 node

Giữ nguyên đánh giá: trade-off thiết kế, không phải lỗi. "Toàn cảnh" là chế độ tổng quan; người dùng
bấm `+` hoặc cuộn để đọc. Sàn 55% chỉ áp cho khung nhìn khởi đầu. Đưa vào backlog (bố cục serpentine).

### Card thứ ba trở đi bị cắt ở mép canvas

Chủ ý: canvas kéo được, có hint "Kéo để di chuyển · Cuộn để phóng to". Không tính là lỗi.

## 3. Checklist nội dung

| Mục | Kết quả |
|---|---|
| Flow ngắn (2 node) và dài (8 node) | Đã xem, không tràn, không chồng |
| Tiêu đề dài | 2–3 dòng ở 375, `h1.scrollWidth == clientWidth` |
| Kết quả có phần chưa xác minh | Card đỏ "Không tìm thấy mã nguồn liên quan" + cảnh báo mức xác minh trong panel |
| Sơ đồ khớp phần giải thích | Panel hiển thị đúng summary/technical/evidence của node |
| Chữ cắt / chồng | Không (sau UI-001); chip dùng ellipsis có chủ ý |
| Nút và điều hướng | `+`, `−`, "Toàn cảnh", search, click card đều hoạt động |
| Nội dung repo hiển thị như dữ liệu | `textContent`; test `test_html_escapes_script_boundary` xác nhận escape `</script>` |
| Mở offline | 0 request ngoài `file://`; không script/link/CDN ngoài |
| Tràn ngang toàn trang | 0 px ở mọi tổ hợp |

## 4. Ảnh bằng chứng (`artifacts/ui-verification/`)

- shop: `shop-1440x900.png`, `shop-768x1024.png`, `shop-375x812.png`
- self: `self-1440x900.png`, `self-375x812.png`
- empty: `empty-1440x900.png`, `empty-375x812.png`

Ảnh cũ (`1440x900-initial.png`, `768x1024-initial.png`, `375x812-initial-before.png`) đã xoá cùng
đợt dọn TASK 7 vì chứa nội dung của bản build trước và chip đường dẫn tuyệt đối.

## 5. Giới hạn

- Chỉ kiểm tra HTML output của core. Panel trong DSH **không** kiểm tra — `BLOCKED_UI_API_UNVERIFIED`.
- Chỉ Chromium trên Ubuntu 24.04; chưa thử Firefox/Safari.
- Chưa đo với graph hàng trăm node (schema giới hạn 250 node, builder cắt ở 12 bước).
