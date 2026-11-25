# Module 04 — Graph JSON contract

Một file JSON là một **luồng**, giữ bằng chứng tương ứng với từng node.

```json
{
  "flow_id": "customer-activation",
  "title": "Kích hoạt bảo hành",
  "description": "Người dùng nhập thông tin và nhận kết quả xác minh.",
  "audience": "Nhân viên CSKH, BA",
  "scope": "UI đăng ký → API kích hoạt → kiểm tra → kết quả",
  "entry_node": "start",
  "nodes": [
    {
      "id": "start",
      "title": "Mở trang đăng ký",
      "type": "start",
      "summary": "Người dùng mở biểu mẫu kích hoạt bảo hành.",
      "details": "Trang cho phép nhập thông tin cần thiết.",
      "technical": "Component registration page",
      "actor": "Người dùng",
      "confidence": "verified",
      "source_refs": [{"path": "src/pages/register.tsx", "start_line": 22, "end_line": 45, "symbol": "RegisterPage"}]
    }
  ],
  "edges": []
}
```

> Ví dụ này minh họa định dạng và không mô tả kho mã cụ thể.

## Bắt buộc

- `flow_id`, `title`, `description`, `entry_node`, `nodes`, `edges`.
- Node: `id`, `title`, `type`, `summary`, `confidence`. `type` thuộc `start|message|action|decision|data|end|error|external`. `confidence` thuộc `verified|partial|inferred|unknown|illustrative`.
- Edge: `from`, `to`, `label`, `kind`. `kind` thuộc `normal|condition|success|error|fallback|loop`.
- Mỗi `id` node là duy nhất; source và target của edge phải tồn tại. Tất cả node phải đi tới được từ `entry_node` (tính cả loop).
- `verified` phải có ít nhất một `source_ref` với `path` + `start_line`; không biết dòng thì dùng `partial`.
- Node có từ 2 edge ra trở lên phải có nhãn cho mọi cạnh; edge từ `decision` phải có nhãn ngay cả khi chỉ có một nhánh.
- Chu trình chỉ hợp lệ nếu có ít nhất một `kind=loop` trong chu trình; điều này cho phép auto-layout bỏ qua back-edge.

## Tùy chọn

- Flow: `audience`, `scope`, `notes` (chuỗi), `assumptions` (mảng chuỗi).
- Node: `details`, `technical`, `actor`, `source_refs`, `x`, `y`; `x/y` để đặt vị trí thủ công khi muốn giống một bố cục cụ thể.
- Ref: `path` (tương đối repo), `start_line` (int >0), `end_line` (int ≥ start), `symbol`.
- Edge: `id` (mặc định tạo), `technical` (mô tả dữ kiện để đi tiếp).

## Rendering

`python3 scripts/render_flow.py FLOW.json --out FLOW.html` dựng tệp HTML ngoại tuyến. Khi có Node.js, trình xem chính tự bố trí sơ đồ. Tọa độ `x` và `y` dùng cho giao diện dự phòng `--viewer classic`; trình xem chính không dựa vào các tọa độ này.

Giới hạn khuyến nghị: 5–12 node/luồng; trường hợp phức tạp phân nhỏ thành nhiều luồng.

## Hợp đồng output của lần chạy (0.3.0)

`scripts/build_flow.py` ghi bốn file vào `<repo>/artifacts/flows/<slug>/`:

| File | Loại | Ghi chú |
|---|---|---|
| `flow.json` | public | graph đã validate, render lại được |
| `flow.html` | public | một file, không CDN, không request ngoài |
| `overview.md` | public | bằng chứng từng bước + giới hạn |
| `run.json` | **internal provenance** | `contract: "internal-provenance"`, `public_outputs`, `internal_outputs` |

`run.json` không phải public output. Nó tồn tại để reviewer đọc lại lần chạy (số đếm, giới hạn,
trạng thái git) mà không cần mở lại repository. `scripts/check_repo_policy.py` từ chối mọi
`run.json` thiếu trường `contract`.

## Mô hình bằng chứng (bắt buộc từ 0.2.2)

- `evidence` trên cạnh thuộc `{entry, import, structure}`. **Không có `call`** khi chưa có call-site
  parser; `pfe/flow.py` ném lỗi nếu ai gắn `call` mà không kèm dấu vết call site.
- `verified` = vị trí thật + bằng chứng thành viên. Không có nghĩa là đã chạy code.
- Node decision/error chỉ sinh từ `try/catch` **nằm trong route body hoặc symbol body được chọn**.
- File chỉ khớp từ khoá nằm ở `meta.related`, không thành node.

## Lớp tri thức

Sơ đồ flow là một **projection** của `pfe.facts`. Cùng bộ fact đó nuôi index tri thức
(`pfe/index.py`), tìm kiếm (`pfe/retrieval.py`), phân tích tác động (`pfe/impact.py`).
Schema entity/relation/confidence/chunk: [references/code-knowledge-schema.json](code-knowledge-schema.json).
