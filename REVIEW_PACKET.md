# REVIEW_PACKET — bàn giao để agent khác review

Tài liệu này để một reviewer độc lập kiểm chứng lại pass 0.3.0 mà không cần hỏi lại.
Mọi con số đều có log/artifact tương ứng, sinh từ cùng một commit.

| Mục | Giá trị |
|---|---|
| Repo | `https://github.com/Hieupt1904/project-flow-explainer` |
| Commit nguồn | `bd02147` (code 0.3.0); commit kế tiếp chỉ chứa bằng chứng |
| Package version | `0.3.0` (`engines.dsh: 0.2.2-rc.2`) |
| Tarball | `dsh-project-flow-explainer-0.3.0.tgz` · 84 670 byte · 25 entry · sha256 `b3647435…20bf581c` |
| Test | 116 Python · 16 adapter · 9 knowledge tool · 2 pack — 0 fail |
| Policy | `check_repo_policy.py` OK: không absolute path, nested artifact, secret-shape |
| UI | 12 tổ hợp (3 sample × 4 viewport) sạch; tương tác search/click/zoom/fit chạy |
| Trạng thái tổng | **PARTIAL**: code pass; registry-runtime 0.3.0 và model-driven **CHƯA CHẠY** |

Số liệu máy đọc: [artifacts/review/evidence-manifest.json](artifacts/review/evidence-manifest.json).
Sinh lại bằng một lệnh: `python3 scripts/regen_evidence.py`.

## 1. Kiến trúc trong 6 dòng

```text
core (Python, stdlib)  : pfe.{policy,facts,flow,ontology,knowledge,index,vectors,retrieval,impact,verify,emit}
flow CLI               : scripts/build_flow.py -> flow.json/html/overview.md (public) + run.json (internal)
knowledge CLI          : tools/pfe_cli.py -> index | search | context-pack | impact | verify | refresh | status
adapter (Node ESM, 0 dep): dsh-plugin/ đăng ký 7 tool, gọi core qua subprocess argv
boundary               : core không import DSH; xoá dsh-plugin thì CLI + 116 test vẫn chạy
policy                 : allowedRoots deny-by-default; artifact chỉ <repo>/artifacts/flows/<slug>/; index chỉ <repo>/.pfe/index/
```

Chi tiết quyết định: [ARCHITECTURE_DECISION.md](ARCHITECTURE_DECISION.md).

## 2. Chạy lại toàn bộ

```bash
python3 -m unittest discover -s tests -v                 # 116 test
python3 -m compileall -q scripts tests pfe tools
node --test dsh-plugin/tests/plugin.test.mjs             # 16 test
node --test dsh-plugin/tests/knowledge.test.mjs          # 9 test
node --test dsh-plugin/tests/pack.test.mjs               # 2 test
python3 scripts/check_repo_policy.py
python3 scripts/regen_evidence.py                         # sinh lại manifest + log
python3 scripts/bench_index.py --files 2000 --json        # benchmark
```

Smoke CLI:

```bash
python3 scripts/build_flow.py --repo <fixture-copy> \
  --request "Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file" --json
python3 tools/pfe_cli.py index --repo <fixture-copy> --mode full --include-vectors
python3 tools/pfe_cli.py search --repo <fixture-copy> --query "export_report"
python3 tools/pfe_cli.py verify --repo <fixture-copy>
```

Kết quả mong đợi: `status=ok`; flow 5 verified / 1 partial; `related = [jobs/export_worker.py, routes/preview.js]`;
index 6 file · search trả `exportReport`; verify verdict `pass` (test mapping `partial` nếu chưa index).

Smoke DSH (**cần xin phép trước khi cài**, vì bước cài chạy npm/pnpm trong profile):

```bash
dsh plugin --profile pfe-test add <tarball>
# patch layer cần:
#   - id: permission
#     config: { defaultPreset: workspace-write }
#   - id: project-flow-explainer        # override, KHÔNG insert lại
#     config: { allowedRoots: ['<workspace>'] }
dsh --profile pfe-test --dump-config | grep -A8 project-flow-explainer
```

## 3. Kết quả theo loop

| Loop | Kết quả | Bằng chứng |
|---|---|---|
| Static | compileall OK, `node --check` 6 file OK, schema JSON hợp lệ | `*-compileall.log`, manifest `static` |
| Unit | 116 / 16 / 9 / 2 pass | `*-python-tests.log`, `*-node-*.log` |
| Security | allowedRoots thiếu/rỗng/ngoài; symlink escape; symlink `.env`; symlink artifact; output sai; slug sai; args sai; secret-shape; private path | test Python + Node, policy log |
| Graph | không call giả; không bypass; chỉ route được chọn; related không thành node; verified có ref | `tests/test_flow_evidence.py` |
| Determinism | 2 lần chạy cùng commit khớp node/edge/counts; index tái dùng cache | `test_two_runs_agree…`, `test_full_then_incremental…` |
| Packaging | tarball 25 entry, giải nén nơi không có checkout, index + search chạy từ vendor | `pack.test.mjs` |
| Provenance | commit, version, `engines.dsh`, tarball, sha256, test count, `generated_at` | manifest |
| UI | 12 tổ hợp + tương tác | [20261119-ui.json](artifacts/review/20261119-ui.json) |

## 4. Bản đồ bằng chứng

```text
artifacts/review/evidence-manifest.json     nguồn số liệu duy nhất
artifacts/review/*-python-tests.log         unittest đầy đủ
artifacts/review/*-node-*.log               3 bộ test Node
artifacts/review/*-policy.log               policy artifact/provenance
artifacts/review/*-bench.json               benchmark index
artifacts/review/*-pack-build.log           tarball
artifacts/review/20261119-ui.json           12 tổ hợp layout + tương tác
artifacts/samples/{shop,self,empty}/        flow sinh từ HEAD (3 file public + run.json internal)
artifacts/ui-verification/*.png             ảnh chụp
artifacts/review/*-real-project.json        chạy thật trên dự án riêng tư (đã scrub path/tên)
USAGE_GUIDE.md                              hướng dẫn dùng hiệu quả + số đo thật
```

## 5. Những chỗ **chưa** làm được (đừng coi là đã xong)

| Mục | Trạng thái thật |
|---|---|
| Smoke registry 0.3.0 trong `pfe-test` | **CHƯA CHẠY**: cài bundle cần npm/pnpm trong profile → phải xin phép trước bước cài |
| Model tự chọn tool | **CHƯA CHẠY**: profile không có API key |
| Panel UI Harness | `BLOCKED_UI_API_UNVERIFIED` — chưa có code UI, chưa xác minh API |
| Config schema native của DSH | **KHÔNG LÀM ĐƯỢC**: profile không resolve `@deepseek-ai/schemastery`; validate tay + test là mức hiện tại |
| Embedding ngữ nghĩa | **CHƯA CÓ**: backend local mặc định là hashing bag-of-words |
| Call graph type-aware | **CHƯA CÓ**: chỉ call site lexical theo tên symbol duy nhất |
| Repo > 20 000 file | Chưa đo; có ngân sách cứng |
| Ảnh chụp UI | Chỉ chụp 2 viewport; phần còn lại đo bằng DOM |

Báo cáo 0.2.x trước đây đã bị **thay thế**, log cũ đã xoá thay vì sửa số liệu.
Không có log 0.2.x nào còn trong `artifacts/` để tránh hai nguồn sự thật.

## 6. Checklist tấn công cho reviewer

1. **allowedRoots**: symlink lồng nhiều lớp, root là `/`, root là chính repo, path có `..`, root không tồn tại, root tương đối.
2. **Artifact containment**: `artifacts` là symlink, `flows` là symlink, slug `..`, slug trùng, chạy song song cùng slug, lỗi giữa chừng.
3. **Rò dữ liệu**: secret trong `.env`, trong file source, trong tên file; kiểm cả `run.json` và `flow.html`; kiểm file cache index.
4. **Bằng chứng graph**: thêm file có route khớp từ khoá nhưng không được import → phải nằm ở `related`.
5. **Index**: sửa 1 byte → parse lại đúng 1 file; xoá file → entity mất; rename → cặp `from/to`; đổi `INDEX_VERSION` → rebuild full.
6. **Retrieval**: exact phải thắng vector; file chỉ khớp keyword phải bị hạ hạng; index stale phải cảnh báo.
7. **Packaging**: bỏ `vendor/core/pfe` khỏi `files` → `pack.test.mjs` phải fail.
8. **Abort/timeout**: abort trước khi gọi, abort giữa lúc chạy, `timeoutMs` rất nhỏ.
9. **Determinism**: chạy 2 lần cùng fixture, so node/edge.
10. **Core independence**: xoá `dsh-plugin/` rồi chạy CLI + unittest.

## 7. Bản đồ file

```text
pfe/                          core tri thức + flow projection
scripts/build_flow.py         CLI flow
scripts/render_flow.py        validate + render HTML
scripts/check_repo_policy.py  policy artifact/provenance/privacy
scripts/regen_evidence.py     sinh manifest từ lệnh thật
scripts/regen_samples.py      sinh lại 3 sample
scripts/bench_index.py        benchmark scan/index
tools/pfe_cli.py              CLI máy đọc 6 tool tri thức
dsh-plugin/index.js           7 tool + lifecycle
dsh-plugin/lib/paths.js       allowedRoots, artifact root, core resolution
dsh-plugin/lib/core-runner.js spawn argv, cap output, signal/timeout
dsh-plugin/lib/tools.js       6 tool tri thức + output schema
dsh-plugin/lib/validate.js    validate tham số, mã lỗi ổn định
dsh-plugin/scripts/pack.mjs   stage + vendor core (scripts/assets/tools/pfe)
assets/workflow_template.html UI offline
references/code-knowledge-schema.json  schema entity/relation/confidence/chunk
tests/                        116 unittest + fixture shop-app, two-routes-app, scope-app
dsh-plugin/tests/             16 adapter + 9 knowledge + 2 pack
.github/workflows/ci.yml      py3.12 + node 20/24 + manifest + policy
```