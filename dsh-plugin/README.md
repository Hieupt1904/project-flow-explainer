# dsh-project-flow-explainer (DSH adapter)

Adapter mỏng đăng ký 7 tool trong DeepSeek Harness và gọi lại core Python qua subprocess.
Core không phụ thuộc DSH: xoá thư mục này thì CLI Python vẫn chạy nguyên vẹn.

## Yêu cầu

| Thành phần | Giá trị |
|---|---|
| Node | `>= 20` (đã test 24.22.3) |
| DSH | `0.2.2-rc.2` (`engines.dsh`) |
| Python | 3.12 (chỉ standard library) |
| Mạng | không cần lúc chạy; chỉ cần khi cài bundle lần đầu vào profile mới |

## Tool

| Tool | Quyền ghi | Ghi chú |
|---|---|---|
| `project_flow_explain` | có (artifact flow) | trả đường dẫn tuyệt đối, đánh dấu `host-only` |
| `project_code_index` | có (`.pfe/index`) | full hoặc incremental |
| `project_code_search` | không | chỉ trả đường dẫn tương đối |
| `project_context_pack` | không | mặc định không snippet |
| `project_impact_analysis` | không | cần index |
| `project_verify_flow` | không | verdict pass/partial/fail |
| `project_knowledge_refresh` | có (`.pfe/index`) | chỉ parse lại file đã đổi |

## Cài đặt

### Từ checkout (dev)

```bash
dsh plugin --profile pfe-test add /duong/dan/project-flow-explainer/dsh-plugin
```

### Từ tarball (độc lập, không cần checkout)

```bash
node dsh-plugin/scripts/pack.mjs                                  # -> dist/dsh-project-flow-explainer-0.3.0.tgz
dsh plugin --profile pfe-test add "$PWD/dist/dsh-project-flow-explainer-0.3.0.tgz"
```

Tarball chứa `vendor/core/{scripts,assets,tools,pfe}` do script pack sinh ra từ checkout.
Bản cài độc lập tìm được `scripts/build_flow.py` và `tools/pfe_cli.py` mà không cần thư mục cha.

## Cấu hình: override row, không insert lại

`cordis.patch.yml` của bundle **đã** insert row `project-flow-explainer`.
Profile chỉ cần override theo id; insert lại cùng id sẽ tạo duplicate loader entry:

```yaml
- id: project-flow-explainer
  config:
    allowedRoots:
      - /home/ban/workspace
    pythonPath: python3
    timeoutMs: 180000
    maxOutputBytes: 1048576
```

| Key | Mặc định | Ý nghĩa |
|---|---|---|
| `allowedRoots` | không có → từ chối mọi path | danh sách thư mục gốc được đọc, so sánh sau `realpath` |
| `pythonPath` | `python3` | interpreter gọi core |
| `coreRoot` | tự dò (`vendor/core` → thư mục cha) | chỉ đặt khi core ở nơi khác; sai là `core_not_found` |
| `timeoutMs` | `180000` | ngân sách mỗi lần gọi |
| `maxOutputBytes` | `1048576` | giới hạn stdout/stderr của child |

Không có cấu hình nào cho phép artifact ra ngoài `<repo>/artifacts/flows`.

### Profile template `headless`

Template này không có API key và cần preset permission tường minh. Thêm vào patch layer:

```yaml
- id: permission
  config:
    defaultPreset: workspace-write
- id: project-flow-explainer
  config:
    allowedRoots: ['/duong/dan/workspace']
```

Thiếu `defaultPreset` thì DSH dừng với lỗi composed sandbox/approval defaults.

## Mã lỗi ổn định

| Mã | Khi nào |
|---|---|
| `allowed_roots_unconfigured` | thiếu hoặc rỗng `allowedRoots` |
| `allowed_roots_invalid` | phần tử không phải chuỗi hoặc không tuyệt đối |
| `repository_outside_allowed_roots` | repo ngoài root sau realpath |
| `repository_path_missing` / `_invalid_type` / `_relative` | tham số sai |
| `invalid_artifact_root` / `artifact_symlink_escape` | output không phải `artifacts/flows` |
| `core_timeout` | vượt `timeoutMs` |
| `core_failed` / `core_spawn_failed` | core lỗi hoặc không chạy được |
| `core_cli_not_found` | bản core cũ không có `tools/pfe_cli.py` |
| `index_missing` | chưa chạy `project_code_index` |
| `no_changed_files` | impact thiếu `changed_files` và `diff` |
| `invalid_arguments` | tham số không phải object |
| `ABORTED` | runtime map từ `Error{name:'AbortError'}` |

## Gỡ cài đặt

```bash
dsh plugin --profile pfe-test remove dsh-project-flow-explainer
```

Profile `web` không bị chạm trong mọi bước.

## Kiểm thử

```bash
node --test dsh-plugin/tests/plugin.test.mjs      # 16 test: policy, artifact, abort, config
node --test dsh-plugin/tests/knowledge.test.mjs   # 9 test: 6 tool tri thức + validation
node --test dsh-plugin/tests/pack.test.mjs        # 2 test: pack + cài độc lập
```
