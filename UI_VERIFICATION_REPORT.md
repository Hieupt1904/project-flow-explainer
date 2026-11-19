# UI_VERIFICATION_REPORT — `flow.html`

Phương pháp: mở file HTML thật trong ego browser (Chromium), đổi viewport bằng CDP `Emulation.setDeviceMetricsOverride`, chụp screenshot, đọc DOM để đo, và đăng ký collector `window.__pfe` trước khi load để bắt console error / unhandled rejection. Trạng thái ngày 2026-11-19.

Kết luận: **PASS** cho ba viewport bắt buộc, sau khi sửa một lỗi layout thật (UI-001).

## 1. Ma trận đo được (sau khi sửa)

| Viewport | Case | Zoom khởi đầu | Tràn ngang trang | Tiêu đề bị cắt | Card chồng nhau | Search | Panel chi tiết | Console error | Request ngoài |
|---|---|---|---|---|---|---|---|---|---|
| 375×812 | shop (8 node) | 55% | 0 px | không | không | `6/8` | 3 section | 0 | 0 |
| 768×1024 | shop (8 node) | 94% | 0 px | không | không | `6/8` | 3 section | 0 | 0 |
| 1440×900 | shop (8 node) | 102% | 0 px | không | không | `6/8` | 3 section | 0 | 0 |
| 375×812 | self (7 node, tiêu đề dài) | 55% | 0 px | không | không | `0/7` | 3 section | 0 | 0 |
| 1440×900 | self (7 node) | 102% | 0 px | không | không | `0/7` | 3 section | 0 | 0 |
| 375×812 | empty (2 node, không bằng chứng) | 55% | 0 px | không | không | `0/2` | 3 section | 0 | 0 |
| 768×1024 | empty | 94% | 0 px | không | không | `0/2` | 3 section | 0 | 0 |
| 1440×900 | empty | 102% | 0 px | không | không | `0/2` | 3 section | 0 | 0 |

Tương tác đã thực thi thật (không mô phỏng): click card → panel đổi sang "Chi tiết bước đang chọn" với 3 section (việc gì / thông tin kỹ thuật / bằng chứng), gõ search → `#search-count` cập nhật và card không khớp bị làm mờ, `+` / `−` / "Toàn cảnh" đổi `#zoom-level` (102% → 47% → 40% ở một lần thử), pan bằng pointer drag.

Bằng chứng panel chi tiết (node "Nhận yêu cầu /api/reports/export"):

```text
HÀNH ĐỘNG · ĐÃ KIỂM CHỨNG | Nhận yêu cầu /api/reports/export
BƯỚC NÀY THỰC HIỆN VIỆC GÌ? | Khớp chủ đề: code:export, route.
THÔNG TIN KỸ THUẬT (DÀNH CHO DEVELOPER) | server.js
CHỨNG CỨ TRONG MÃ NGUỒN | server.js:16 | Symbol: /api/reports/export
```

## 2. Lỗi phát hiện và xử lý

### UI-001 — Card kế tiếp bị cắt ở cạnh canvas ngay khi mở

- Viewport: 768×1024 (thấy rõ), 375×812.
- Trạng thái: initial.
- Mong đợi: bước mở đầu và các bước kề nó nằm trọn trong khung nhìn.
- Thực tế (trước sửa): card 2 bị cắt giữa chữ ở mép phải canvas; người đọc thấy như lỗi layout chứ không phải gợi ý "còn nội dung bên phải".
- Nguyên nhân: `initialView()` trong `assets/workflow_template.html` chỉ tính scale theo chiều cao (`scaleY`) rồi neo `tx = 57 - minX*scale`, không ràng buộc chiều ngang, nên cặp card vượt quá `viewport.clientWidth`.
- Sửa: tính thêm `scaleX = (vw-46)/(maxX-minX)` với `maxX = max(x + NODE_W)` của entry + hàng xóm, lấy `scale = clamp(0.55, 1.02, min(scaleY, scaleX))`, neo `tx = 24 - minX*scale`.
- Retest: 768×1024 → **0 card bị cắt** (trước: 1), zoom 94% (trước 102%); 375×812 → 55% (sàn legibility giữ nguyên, xem UI-002).

| Trước | Sau |
|---|---|
| [768x1024-initial.png](artifacts/ui-verification/768x1024-initial.png) | [shop-768x1024-after.png](artifacts/ui-verification/shop-768x1024-after.png) |
| [375x812-initial-before.png](artifacts/ui-verification/375x812-initial-before.png) | [shop-375x812-after.png](artifacts/ui-verification/shop-375x812-after.png) |

### UI-002 — "Toàn cảnh" thu nhỏ còn 34% với flow dài

- Viewport: 1440×900, graph 8 node xếp chuỗi ngang.
- Trạng thái: sau khi bấm "Toàn cảnh".
- Thực tế: `#zoom-level` = 34%; chữ trong card không đọc được ở mức đó.
- Đánh giá: **chấp nhận như trade-off thiết kế**, không phải lỗi. "Toàn cảnh" là chế độ xem tổng thể; người dùng bấm `+` hoặc cuộn để đọc. Sàn 55% chỉ áp cho khung nhìn khởi đầu.
- Khuyến nghị (backlog): bố trí serpentine 2 hàng cho chuỗi dài, hoặc thêm mức zoom "vừa đủ đọc" bên cạnh "toàn cảnh".
- Bằng chứng: [1440x900-fit.png](artifacts/ui-verification/1440x900-fit.png).

### Không phải lỗi

- Vệt tối ở góc trên trái trong vài screenshot là HUD của ego browser ("DeepSeek · PROJECT FLOW EXPLAINER / …"), không phải nội dung trang.
- Card thứ ba trở đi bị cắt ở mép canvas là chủ ý: canvas kéo được, có hint "Kéo để di chuyển · Cuộn để phóng to" ở đáy.

## 3. Checklist nội dung

| Mục | Kết quả |
|---|---|
| Flow ngắn (2 node) và dài (8 node) | Đã xem, không tràn, không chồng |
| Tiêu đề / nhãn dài | Tiêu đề 2–3 dòng ở 375, không tràn ngang, `h1.scrollWidth == clientWidth` |
| Kết quả có phần chưa xác minh | Card đỏ "Không tìm thấy mã nguồn liên quan" + cảnh báo "Mức xác minh: Chưa xác minh" trong panel |
| Sơ đồ khớp phần giải thích | Panel đọc đúng title/summary/technical/refs của node được chọn |
| Chữ bị cắt / chồng | Không có sau UI-001; chip "Phạm vi" dùng ellipsis có chủ ý |
| Nút và điều hướng | `+`, `−`, "Toàn cảnh", search, click card đều hoạt động |
| Nội dung repo hiển thị như dữ liệu | Template dùng `textContent`; test `test_html_escapes_script_boundary` xác nhận `</script>` bị escape thành `\u003c/script\u003e` |
| Mở offline | 0 request ngoài `file://`; không script/link/CDN ngoài |
| Tràn ngang toàn trang | 0 px ở cả 3 viewport |

## 4. Ảnh bằng chứng

`artifacts/ui-verification/`:

- `1440x900-initial.png` (trước sửa), `1440x900-initial-after.png`, `1440x900-fit.png`, `1440x900-header-clip.png`, `shop-1440x900-detail-after.png`
- `768x1024-initial.png` (trước sửa), `768x1024-detail.png`, `shop-768x1024-after.png`
- `375x812-initial-before.png`, `shop-375x812-after.png`
- `self-1440x900-after.png`, `self-375x812-after.png`
- `empty-1440x900-after.png`, `empty-768x1024-after.png`, `empty-375x812-after.png`

## 5. Giới hạn của lần kiểm tra này

- Chỉ kiểm tra HTML output của core. **Không** kiểm tra panel trong DSH — trạng thái `BLOCKED_UI_API_UNVERIFIED`, nằm ngoài MVP.
- Trình duyệt dùng để kiểm tra là ego browser (Chromium) trên Ubuntu 24.04; chưa thử Firefox/Safari.
- Chưa đo với repo sinh ra hàng trăm node (giới hạn schema là 250 node, builder cắt ở 12 bước).
