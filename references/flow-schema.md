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

> Đây chỉ là **ví dụ định dạng**, không phải nhận định về một project cụ thể.

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

`python scripts/render_flow.py FLOW.json --out FLOW.html` sẽ tự xếp layout theo tầng trái → phải nếu không đặt x/y. Có thể tùy chỉnh x/y để nhóm node theo nhánh trên canvas như ví dụ mẫu.

Giới hạn khuyến nghị: 5–12 node/luồng; trường hợp phức tạp phân nhỏ thành nhiều luồng.
