# UI_VERIFICATION_REPORT — 0.3.0

Kiểm tra trên 3 sample sinh từ HEAD × 4 viewport, chạy bằng trình duyệt thật (CDP),
mở trực tiếp `file://`. Máy đọc: [artifacts/review/20261119-ui.json](artifacts/review/20261119-ui.json).

| Mục | Giá trị |
|---|---|
| Thời điểm | 2026-11-19 |
| Sample | `shop` (6 node), `self` (13 node), `empty` (2 node) |
| Viewport | 1440×900 · 1024×768 · 768×1024 · 375×812 |
| Tổ hợp | 12 |
| Cách đo | `getBoundingClientRect` cho card và nhãn cạnh; `performance.getEntriesByType('resource')` cho request ngoài; `window.__pfeErrors` cho lỗi |

## 1. Kết quả layout

| Chỉ số | Số tổ hợp vi phạm |
|---|---|
| Tràn ngang | 0 |
| Card chồng nhau | 0 |
| Nhãn cạnh đè lên card | 0 |
| Lỗi console / unhandled rejection | 0 |
| Request ra ngoài `file://` | 0 |
| Tiêu đề card bị cắt | 0 |

Zoom khởi đầu: 102% (1440), 80% (1024), 94% (768), 55% (375).

## 2. Tương tác (1440×900, sample `shop`)

| Hành động | Kết quả |
|---|---|
| Gõ "báo cáo" vào ô tìm | `Tìm thấy 1/6`, 5 card bị mờ đúng |
| Nhấn card đầu | panel phải đổi sang "Chi tiết bước đang chọn" |
| Zoom in ×2 | 102% → 140% |
| Bấm "Toàn cảnh" | 40% |
| Lỗi console sau toàn bộ thao tác | 0 |

## 3. Trường hợp biên đã kiểm bằng unit test

| Trường hợp | Test |
|---|---|
| Nội dung chứa `</script>` | `test_html_escapes_script_boundary` (escape thành `\u003c/script\u003e`) |
| Không tải script/link/CDN ngoài | `test_html_is_self_contained` |
| Flow không có node (no-evidence) | sample `empty` render 2 card, không lỗi |
| Flow dài 13 node | sample `self`: 0 card chồng, 0 nhãn đè |
| Toạ độ thiếu | `test_auto_layout_for_missing_coordinates` |

## 4. Vấn đề còn lại

| ID | Viewport | Hiện tượng | Nguyên nhân | Trạng thái |
|---|---|---|---|---|
| UI-002 | 1440×900 | "Toàn cảnh" co còn 40% với 6 node, 13 node còn nhỏ hơn | fit tính theo toàn bộ canvas một hàng | **đã ghi nhận**, chưa sửa; cần bố cục serpentine |

Không có lỗi nào khác được phát hiện trong lần chạy này.

## 5. Ảnh chụp

| File | Nội dung |
|---|---|
| [shop-375x812.png](artifacts/ui-verification/shop-375x812.png) | sample shop ở 375×812 (6 node) |
| [shop-1440x900.png](artifacts/ui-verification/shop-1440x900.png) | sample shop ở 1440×900 |
| [self-1440x900.png](artifacts/ui-verification/self-1440x900.png) | sample self ở 1440×900 (13 node) |
| [empty-375x812.png](artifacts/ui-verification/empty-375x812.png) | sample empty ở 375×812 (2 node) |

Ảnh chỉ là bằng chứng bổ sung; kết luận dựa trên số đo DOM ở mục 1 và 2.
