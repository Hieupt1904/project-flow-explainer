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
node --test dsh-plugin/tests/plugin.test.mjs      # policy, artifact, abort, config
node --test dsh-plugin/tests/knowledge.test.mjs   # 6 tool tri thức + validation
node --test dsh-plugin/tests/lifecycle.test.mjs   # mount/dispose/remount, huỷ khi đang chạy
node --test dsh-plugin/tests/settings.test.mjs    # binding settings theo entry id và package name
node --test dsh-plugin/tests/arguments.test.mjs   # từ chối tham số không khai báo, cả 7 tool
node --test dsh-plugin/tests/pack.test.mjs        # pack + cài độc lập
```

## Đối chiếu với chuẩn plugin DSH

Rà theo gói tài liệu `dsh-plugin-dev` (bản dịch của docs.deepseekdocs.com) và đối chiếu
với chính bản cài đang chạy.

| Chuẩn | Trạng thái trong plugin này |
|---|---|
| `export const name` + `export function apply(ctx, config)` | **ĐẠT** (`index.js`) |
| `inject` khai báo trước khi dùng `ctx.<service>` | **ĐẠT**: `inject = ['tools']`; `settings` lấy qua `ctx.inject` tùy chọn |
| Tool có `output { schema, render }`, `timeoutMs`, `isConcurrencySafe` | **ĐẠT**: 7/7 tool có đủ ba trường |
| Tên tool không đụng `run_code` | **ĐẠT** |
| Config schema + người dùng chỉnh trong Settings | **ĐẠT**, nhưng nạp `@deepseek-ai/schemastery` qua resolver neo vào bản cài (xem dưới) |
| Bundle layer qua `dsh.bundle.patch` | **ĐẠT**: `cordis.patch.yml`, dòng `insert` id `project-flow-explainer` |
| Nửa client (nếu có UI) | **ĐẠT**: `dsh.client` + `client.js` đăng ký slot `plugins.bundle.config` / `plugins.row.config` |
| Hủy và dọn tài nguyên | **ĐẠT**: `exec.signal` → `AbortError`; `ctx.effect` dọn run đang bay |
| Env của người dùng đọc qua snapshot khởi chạy | **ĐẠT** (working tree, chưa phát hành): `PFE_CORE_ROOT` đọc qua `ctx.get('launchEnvironment')`, lùi về `process.env` khi host không có |
| Tham số được kiểm trước khi chạy | **ĐẠT** bằng `lib/validate.js` + `rejectUnknownKeys()` (tương đương phần mà `defineTool` lo) |
| `defineTool` từ `@deepseek-ai/dsh-tools` | **KHÔNG dùng, có chủ ý** — xem dưới |
| `ctx.invariants`, Typert, `deferLoading`, `presentationMeta` | **KHÔNG dùng**: không cần cho một plugin 7 tool cục bộ |

### Vì sao không dùng `defineTool`

`defineTool` là API chuẩn: nó chuyển `parameters` sang JSON Schema và **tự kiểm tham số trước
khi gọi `execute`**, ném `ToolArgsError`. Plugin này dựng thẳng object rồi `ctx.tools.register()`
vì `@deepseek-ai/dsh-tools` không resolve được từ thư mục plugin trong profile (kiểm bằng
`createRequire` từ `~/.dsh/profiles/web/node_modules/dsh-project-flow-explainer/`), và plugin
giữ cam kết "không import `@deepseek-ai/*`" để bản `link:`/tgz cài được ở mọi profile.

Cái mất khi bỏ `defineTool`: runtime **không** kiểm tham số theo schema, và lỗi sai tham số ra
dạng `InputError` của plugin thay vì `ToolArgsError`. Plugin tự bù đúng phần thiếu đó:

| `defineTool` cho gì | Plugin làm gì thay thế |
|---|---|
| chuyển `parameters` sang JSON Schema | khai báo thẳng JSON Schema trong định nghĩa tool |
| kiểm kiểu/giá trị theo schema trước `execute` | `lib/validate.js` kiểm từng trường với mã lỗi riêng (`repository_path_missing`, `top_k_out_of_range`, …) |
| `additionalProperties: false` được thực thi | `rejectUnknownKeys()` — từ chối khóa lạ bằng mã `unknown_arguments` (`tests/arguments.test.mjs`) |
| lỗi là `ToolArgsError` | lỗi là `InputError` với `code` ổn định, cộng `hint` |

Nếu muốn đúng chuẩn tuyệt đối, thêm `@deepseek-ai/dsh-tools` vào `peerDependencies` rồi bọc
`defineTool`, và chấp nhận rằng profile phải resolve được gói đó.

### Chi phí prompt của 7 tool

Mô tả tool được tính vào system prompt **mỗi bước** của model. Sau khi rút gọn còn 4 dòng/tool,
tổng `description` giảm từ 3 492 xuống 2 586 ký tự (−26%); cả `description` + `parameters` là
5 219 ký tự (khoảng 1 500 token). Thêm tool mới thì phải trả chi phí này mỗi bước — ưu tiên gộp
tool hơn là thêm tool.

### Hợp đồng id của settings

`ctx.settings.describe()` trả row theo **id của dòng trong profile**, không phải tên package.
Plugin nhận cả hai: `project-flow-explainer` (id trong `cordis.patch.yml`) và
`dsh-project-flow-explainer` (tên package, dùng khi mount tay). Không so khớp theo chuỗi con.
Nếu dòng settings chưa xuất hiện lúc mount, lần `settings/document-updated` kế tiếp sẽ đọc lại.
