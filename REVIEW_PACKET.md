# REVIEW_PACKET — bàn giao để agent khác review

Tài liệu này để một agent/reviewer độc lập kiểm chứng lại toàn bộ kết quả mà không cần hỏi lại.
Mọi con số dưới đây đều có log/ảnh tương ứng trong `artifacts/`.

| Mục | Giá trị |
|---|---|
| Repo | `https://github.com/Hieupt1904/project-flow-explainer` |
| HEAD code được test | `2606e88` (tag `v0.2.1`); commit chứa packet này là commit kế tiếp, chỉ thêm tài liệu + log |
| Release | `v0.2.1` — asset `dsh-project-flow-explainer-0.2.1.tgz` (37 589 byte, sha256 `733148d4…10e84`) |
| DSH đã kiểm chứng | `0.2.2-rc.2` |
| Python / Node | 3.12.3 / v24.22.3 (CI thêm Node 20) |
| Trạng thái tự test | **PASS** — 33 unittest, 16 adapter, 2 pack, policy OK, DSH smoke OK, UI 7/7 tổ hợp sạch |

## 1. Kiến trúc trong 5 dòng

```text
core (Python, stdlib)  : scripts/build_flow.py → graph có bằng chứng → render_flow.py → flow.json/html/overview.md
adapter (Node ESM, 0 dep): dsh-plugin/ đăng ký tool project_flow_explain, gọi core qua subprocess argv array
boundary              : core không import DSH; xoá dsh-plugin thì CLI vẫn chạy
policy                : allowedRoots deny-by-default; artifact chỉ <repo>/artifacts/flows/<slug>/
đóng gói              : dsh-plugin/scripts/pack.mjs chép core vào vendor/core rồi npm pack
```

Chi tiết quyết định: [ARCHITECTURE_DECISION.md](ARCHITECTURE_DECISION.md).

## 2. Chạy lại toàn bộ (copy-paste)

```bash
python3 -m unittest discover -s tests -v           # 33 test
python3 -m compileall -q scripts tests
node --test dsh-plugin/tests/plugin.test.mjs       # 16 test
node --test dsh-plugin/tests/pack.test.mjs         # 2 test (pack + cài độc lập)
python3 scripts/check_repo_policy.py               # policy artifact/provenance
node dsh-plugin/scripts/pack.mjs                   # tarball trong dist/
```

Smoke CLI:

```bash
cp -r tests/fixtures/shop-app /tmp/rev/shop-app && rm -rf /tmp/rev/shop-app/artifacts
python3 scripts/build_flow.py --repo /tmp/rev/shop-app \
  --request "Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file" --json
```

Kết quả mong đợi: `status=ok`, `5 verified / 3 partial`, `related = [jobs/export_worker.py, routes/preview.js]`,
4 file trong `/tmp/rev/shop-app/artifacts/flows/<slug>/`.

Smoke DSH (cần profile riêng, **không** dùng `web`):

```bash
dsh plugin --profile pfe-test add <tarball>
# thêm patch layer:
#   - id: permission
#     config: { defaultPreset: workspace-write }
#   - id: project-flow-explainer
#     config: { allowedRoots: ['/tmp/rev'] }
dsh --profile pfe-test --dump-config | grep -A6 project-flow-explainer
```

## 3. Kết quả tự test (log trong `artifacts/review/`)

| # | Hạng mục | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | Python unittest | **33 OK** | `*-self-test.log` §1 |
| 2 | compileall | OK | §2 |
| 3 | Adapter (Node) | **16 pass** | §3 |
| 4 | Pack + cài độc lập | **2 pass** (tarball 9 file) | §4, §6 |
| 5 | Policy | `OK: 31 file`, không absolute path / nested artifacts / secret | §5 |
| 6 | CLI trên fixture | `ok`, 5 verified / 3 partial, 2 file ngoài luồng, 4 artifact, **không lộ secret** | `*-cli-and-core.log` §7 |
| 7 | Core độc lập (không có `dsh-plugin/`) | `ok`, cùng kết quả | §8 |
| 8 | Artifact policy âm tính | `out-dir = .`, `src`, `../outside` → `invalid_artifact_root` | §9 |
| 9 | DSH thật với **bản phát hành 0.2.1** | tool trong registry, gọi `ok`, 4 artifact, không secret, `duplicates: []` | `*-dsh-smoke.log` §10 |
| 10 | UI `flow.html` | 7 tổ hợp (shop/self/empty × 3 viewport): `labelOverCard 0`, card chồng 0, tràn ngang 0, console error 0, request ngoài 0 | `*-ui.json` + `artifacts/ui-verification/*.png` |

## 4. Bản đồ bằng chứng

```text
artifacts/review/                 log tự test, UI measurements (JSON)
artifacts/logs/                   preflight runtime, baseline, TASK 4 smoke (log + JSON)
artifacts/samples/{shop,self,empty}/   flow.json + flow.html + overview.md + run.json (sinh từ HEAD)
artifacts/ui-verification/        7 ảnh 3 viewport + ảnh lỗi nhãn UI-003 + ảnh DSH (Trajectory, Plugins)
artifacts/baseline/               HTML renderer gốc
```

Báo cáo chi tiết: [TEST_REPORT.md](TEST_REPORT.md) · [UI_VERIFICATION_REPORT.md](UI_VERIFICATION_REPORT.md) ·
[FINAL_REPORT.md](FINAL_REPORT.md) · [DSH_IMPLEMENTATION_PLAN.md](DSH_IMPLEMENTATION_PLAN.md) ·
[IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md).

## 5. Những chỗ **chưa** làm được (đừng coi là đã xong)

| Mục | Trạng thái thật |
|---|---|
| Panel UI trong Harness | `BLOCKED_UI_API_UNVERIFIED` — không có code UI, không thử |
| Model tự chọn tool trong profile `headless` | Không chạy được: profile không có API key (`MISSING_CREDENTIAL`). Lời gọi trong smoke do plugin probe gọi qua registry thật, **không** qua model. Đường model chỉ được chứng minh gián tiếp ở UI `pfe-demo` (ảnh `demo-trajectory.png`) |
| Call graph đầy đủ | Chưa có; quan hệ bước dựa trên route/import/gọi-theo-tên. Mọi kết quả đều ghi rõ trong `limits` |
| Fit "Toàn cảnh" 34% | Trade-off đã ghi (UI-002), chưa sửa |
| Repo > 20 000 file | Chưa benchmark; có giới hạn cứng |

## 6. Gợi ý checklist cho reviewer

Nên tấn công theo thứ tự này; tất cả đều đã có test, nên nếu phá được thì đó là bug thật:

1. **allowedRoots**: symlink lồng nhiều lớp, root là `/`, root là chính repo, path có `..` đã chuẩn hoá, root không tồn tại.
2. **Artifact containment**: `artifacts` là symlink, `flows` là symlink, slug `..`, slug trùng, chạy song song hai lần cùng slug.
3. **Rò dữ liệu**: secret trong `.env`, trong file source, trong tên file; kiểm cả `run.json` và `flow.html`.
4. **Bằng chứng graph**: thêm một file có route khớp từ khoá nhưng không được import → phải nằm ở `related`, không thành node.
5. **Packaging**: sửa `dsh-plugin/package.json` bỏ `vendor/core` khỏi `files` → `pack.test.mjs` phải fail.
6. **Abort/timeout**: abort trước khi gọi, abort giữa lúc chạy (child phải chết), `timeoutMs` rất nhỏ.
7. **Determinism**: chạy 2 lần cùng fixture, so node/edge.
8. **Core independence**: xoá `dsh-plugin/` rồi chạy CLI + `python3 -m unittest discover -s tests`.

## 7. Bản đồ file

```text
scripts/build_flow.py              analyzer + CLI (core)
scripts/render_flow.py             validate + render (core, không đổi)
scripts/check_repo_policy.py       chặn absolute path / nested artifacts / secret / manifest
assets/workflow_template.html      UI offline (đã sửa UI-001 fit ngang, UI-003 nhãn không đè card)
dsh-plugin/index.js                tool project_flow_explain
dsh-plugin/lib/paths.js            allowedRoots, artifact root, core resolution
dsh-plugin/lib/core-runner.js      spawn argv, cap output, signal/timeout
dsh-plugin/scripts/pack.mjs        stage + vendor/core + npm pack
tests/                             33 unittest + fixture shop-app (có decoy routes/preview.js)
dsh-plugin/tests/                  16 adapter + 2 packaging
.github/workflows/ci.yml           py3.12 + node 20/24 + manifest
```
