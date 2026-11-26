# Project Flow Explainer cho DeepSeek Harness

**ĐÃ TRIỂN KHAI** — Plugin DeepSeek Harness (DSH) dựng sơ đồ tương tác từ mã nguồn và trả vị trí làm căn cứ cho từng bước có bằng chứng. Gói chứa lõi Python và trình dựng bản đồ Node.js. Bạn dùng plugin mà không cần tải riêng kho mã Project Flow Explainer.

![Sơ đồ luồng với phần căn cứ và hướng dẫn đi theo nhánh](docs/flow-simple.jpg)

*Ảnh chụp sơ đồ HTML sinh từ kho mã mẫu.*

## Cài đặt

| Thành phần | Phiên bản |
|---|---|
| Node.js | `>=20` |
| DeepSeek Harness | Dải khai báo: `>=0.2.2-rc.2 <0.3.0`. |
| Python | Dùng Python 3.12. Lõi chỉ dùng thư viện chuẩn. |

Cài vào hồ sơ cần dùng. Ví dụ dưới đây dùng hồ sơ `pfe-test`:

```bash
dsh plugin --profile pfe-test add dsh-project-flow-explainer@latest
```

Để cài từ tệp gói, tải [bản phát hành GitHub mới nhất](https://github.com/Hieupt1904/project-flow-explainer/releases/latest) rồi chỉ định đường dẫn tệp đã tải:

```bash
dsh plugin --profile pfe-test add "$PWD/project-flow-explainer.tgz"
```

Để cài đúng bản ổn định `0.9.1`, thay `@latest` bằng `@0.9.1`. Bạn cũng có thể tải [gói GitHub của bản ổn định](https://github.com/Hieupt1904/project-flow-explainer/releases/tag/v0.9.1) hoặc dựng gói từ kho mã này:

```bash
node dsh-plugin/scripts/pack.mjs
dsh plugin --profile pfe-test add "$PWD/dist/dsh-project-flow-explainer-0.9.1.tgz"
```

Khởi động lại hồ sơ DSH sau khi cài hoặc nâng cấp. Các lệnh dựng bản đồ và phân tích luồng chạy tại máy, không gọi mô hình.

## Cấu hình

Trong giao diện web, mở **Plugins**. Tìm bundle rồi chọn **Configure** tại dòng `project-flow-explainer`. Thêm đường dẫn tuyệt đối vào **Thư mục được đọc** (`allowedRoots`), rồi chọn **Lưu cấu hình**.

| Trường | Giá trị mặc định hoặc cách dùng |
|---|---|
| `allowedRoots` | Rỗng. Điền đường dẫn tuyệt đối cho các thư mục plugin được đọc. |
| `pythonPath` | `python3`. Đổi nếu cần chọn trình thông dịch khác. |
| `coreRoot` | Plugin tự dò lõi. Chỉ đặt khi lõi nằm ở vị trí khác. |
| `timeoutMs` | `180000` ms cho mỗi lần gọi. |
| `maxOutputBytes` | `1048576` byte cho đầu ra của tiến trình con. |

Nếu dùng bản vá cấu hình, ghi đè dòng `project-flow-explainer` đã có thay vì chèn thêm dòng cùng định danh:

```yaml
- id: project-flow-explainer
  config:
    allowedRoots:
      - /duong/dan/workspace
    pythonPath: python3
```

## Sử dụng

Nhập lệnh trong giao diện web:

```text
/project-flow-explainer Giải thích luồng xuất báo cáo
/project-flow-explainer Giải thích luồng xuất báo cáo --repo /duong/dan/repo
/project-flow-explainer --map
/project-flow-explainer --refresh-map
/project-flow-explainer --blueprint
```

Nếu bỏ `--repo`, plugin dùng thư mục làm việc của phiên. Mở `flow.html` trong `<repo>/artifacts/flows/<slug>/` để xem sơ đồ. Plugin trả đường dẫn kết quả tính từ thư mục gốc của kho mã. Lệnh `--map` dựng `project-flow-explainer/index.html`. Lệnh `--blueprint` đọc `project-flow-explainer/plan.json` có sẵn. Cả chế độ luồng và các lệnh bản đồ dùng cùng phạm vi `allowedRoots`.

### Thanh Hỏi trên bản đồ

Chạy một trong hai lệnh sau từ thư mục gốc của kho mã đã dựng bản đồ. Sau đó, mở địa chỉ máy chủ in ra.

```bash
# Tra cứu dữ liệu bản đồ tại máy
node project-flow-explainer/serve.mjs --no-open

# Dùng mô hình của hồ sơ DSH headless đã cấu hình
node project-flow-explainer/serve.mjs --no-open --agent
```

1. Khi bật `--agent`, chọn cặp mô hình và nhà cung cấp cạnh thanh **Hỏi**. Danh sách lấy từ các mô hình khai báo trong hồ sơ `web`. Tải lại bản đồ sau khi thêm mô hình trong DSH.
2. Mỗi lần hỏi chạy qua `headless` với bản vá tạm. DSH tự lấy thông tin xác thực đã lưu. Công cụ không sửa hồ sơ hoặc trả giá trị khóa về trình duyệt.
3. Nếu dùng hồ sơ khác, đặt `PROJECT_FLOW_DSH_PROFILE` trước khi chạy máy chủ. Nếu máy có nhiều bản DSH, đặt `PROJECT_FLOW_DSH` thành đường dẫn tuyệt đối tới trình khởi chạy đã dùng để cấu hình mô hình.

Danh sách hiện hỗ trợ các mô hình khai báo trong bộ điều hợp `llm-pi-ai` và `llm-deepseek`. Khi danh sách trống hoặc chưa đọc được, thanh **Hỏi** dùng cấu hình mặc định của `headless`. Nếu gặp `MISSING_CREDENTIAL`, kiểm tra nhà cung cấp đã chọn hoặc dùng **Tra cứu bản đồ cục bộ**.

Mở trực tiếp `index.html` để xem bản đồ. Để hỏi, mở địa chỉ do máy chủ in ra.

| Công cụ | Dùng để |
|---|---|
| `project_flow_explain` | Dựng sơ đồ cho một luồng cụ thể. |
| `project_code_index` | Tạo hoặc cập nhật chỉ mục cục bộ. |
| `project_code_search` | Tìm theo tên hàm, tuyến xử lý hoặc từ khóa. |
| `project_context_pack` | Tìm điểm vào, tệp và kiểm thử liên quan trước khi sửa. |
| `project_impact_analysis` | Tìm luồng, hàm và kiểm thử có thể chịu tác động sau khi sửa. |
| `project_knowledge_refresh` | Cập nhật chỉ mục theo phần mã đã đổi. |
| `project_verify_flow` | Kiểm tra tĩnh sơ đồ và tệp kết quả; không chạy kiểm thử ứng dụng. |

### Lỗi thường gặp

| Mã lỗi | Cách khắc phục |
|---|---|
| `allowed_roots_unconfigured` | Điền ít nhất một thư mục tuyệt đối vào `allowedRoots`. |
| `repository_outside_allowed_roots` | Chọn kho mã nằm trong một thư mục đã khai báo. |
| `index_missing` | Chạy `project_code_index` trước khi tra cứu. |
| `core_cli_not_found` | Cài lại từ gói có thư mục `vendor/core/`. |
| `MISSING_CREDENTIAL` | Trong **Models** của DSH, lưu khóa cho nhà cung cấp mà hồ sơ `headless` đang dùng. Để tiếp tục ngay, chọn **Tra cứu bản đồ cục bộ** trong thanh Hỏi. |

## Đóng gói từ mã nguồn

Chạy từ thư mục gốc của kho mã Project Flow Explainer:

```bash
node dsh-plugin/scripts/pack.mjs
node --test dsh-plugin/tests/*.test.mjs
```

Script in đường dẫn tệp gói trong trường `tarball`. Khi phát hành lên npm, dùng tệp gói này. Đóng gói trực tiếp từ thư mục `dsh-plugin/` sẽ bỏ sót các tệp lõi trong `vendor/core/`.

Xem thêm [hướng dẫn sử dụng](https://github.com/Hieupt1904/project-flow-explainer/blob/main/USAGE_GUIDE.md) và [mã nguồn](https://github.com/Hieupt1904/project-flow-explainer).
