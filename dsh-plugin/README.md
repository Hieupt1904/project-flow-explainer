# dsh-project-flow-explainer (DSH adapter)

Adapter mỏng đăng ký tool `project_flow_explain` trong DeepSeek Harness và gọi lại core Python
của [Project Flow Explainer](../README.md). Core không phụ thuộc DSH; gỡ thư mục này thì CLI
Python vẫn chạy nguyên vẹn.

## Yêu cầu

| Thành phần | Giá trị |
|---|---|
| Node | `>= 20` (đã test 24.22.3) |
| DSH | `0.2.2-rc.2` (`engines.dsh`) |
| Python | `3.12` (chỉ standard library) |
| Mạng | Không cần cho lúc chạy; chỉ cần khi cài bundle lần đầu vào profile mới |

## Cài đặt

### Từ checkout (dev)

```bash
dsh plugin --profile pfe-test add /duong/dan/project-flow-explainer/dsh-plugin
```

### Từ tarball (độc lập, không cần checkout)

```bash
node dsh-plugin/scripts/pack.mjs          # -> dist/dsh-project-flow-explainer-0.2.1.tgz
dsh plugin --profile pfe-test add /duong/dan/project-flow-explainer/dist/dsh-project-flow-explainer-0.2.1.tgz
```

Tarball chứa `vendor/core/{scripts,assets}` do script pack sinh ra từ checkout hiện tại, nên bản
cài độc lập vẫn tìm được `build_flow.py` và `workflow_template.html` mà không cần thư mục cha.

## Cấu hình bắt buộc: `allowedRoots`

Tool **deny-by-default**. Không khai báo `allowedRoots` thì mọi lần gọi trả lỗi
`allowed_roots_unconfigured`. Thêm vào row của bundle trong profile patch:

```yaml
- insert:
    - id: project-flow-explainer
      name: dsh-project-flow-explainer
      config:
        allowedRoots:
          - /home/ban/workspace        # tuyệt đối, tồn tại, đọc được
          - /home/ban/du-an-khac
        pythonPath: python3            # tùy chọn
        timeoutMs: 180000              # tùy chọn
```

| Key | Mặc định | Ý nghĩa |
|---|---|---|
| `allowedRoots` | không có → từ chối mọi path | Danh sách thư mục gốc được phép đọc. Repository truyền vào phải nằm trong một root (so sánh sau `realpath`). |
| `pythonPath` | `python3` | Interpreter gọi core |
| `coreRoot` | tự dò (`vendor/core` → thư mục cha) | Chỉ đặt khi core nằm ở nơi khác; sai đường dẫn là lỗi `core_not_found` |
| `timeoutMs` | `180000` | Ngân sách mỗi lần gọi |
| `maxOutputBytes` | `1048576` | Giới hạn stdout/stderr của child |

Không có cấu hình nào cho phép ghi artifact ra ngoài `<repo>/artifacts/flows` — đây là quy tắc cứng.

## Ghi chú khi cài vào profile `headless`

Template `headless` không có API key và yêu cầu preset permission tường minh. Trước khi boot, thêm
vào patch layer của profile:

```yaml
- id: permission
  config:
    defaultPreset: workspace-write
- id: project-flow-explainer
  config:
    allowedRoots: ['/duong/dan/workspace']
```

Nếu thiếu `defaultPreset`, DSH dừng với `permission: composed sandbox and approval defaults match no
preset; configure defaultPreset explicitly`.

## Gỡ cài đặt

```bash
dsh plugin --profile pfe-test remove dsh-project-flow-explainer
# hoặc xoá hẳn profile thử
rm -rf ~/.dsh/profiles/pfe-test
```

Profile `web` không bị chạm tới trong cả hai cách.

## Kiểm thử

```bash
node --test dsh-plugin/tests/plugin.test.mjs    # adapter + policy
node --test dsh-plugin/tests/pack.test.mjs      # pack + cài độc lập
```
