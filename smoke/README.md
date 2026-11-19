# DSH smoke harness

Thư mục này chỉ chứa **harness kiểm thử**, không nằm trong tarball phát hành.

`dsh-probe/` là một bundle tạm, được cài vào profile thử `pfe-test`, chạy trong một
lần boot DSH thật: nó đọc registry thật (`ctx.tools.definitions/get`) và gọi từng
tool đã cài. Đây là bằng chứng **registry-runtime**, không phải model-driven: model
không tham gia, nên kết quả không chứng minh model tự chọn tool.

Chạy lại toàn bộ:

```bash
python3 scripts/run_dsh_smoke.py
```

Script sẽ:

1. cài bundle phát hành (`dist/dsh-project-flow-explainer-<version>.tgz`) vào `pfe-test`;
2. cài probe, prebuild index bằng CLI;
3. boot 6 lần với overlay khác nhau: gọi tool, policy ngoài root, tham số sai, abort,
   `allowedRoots: []`, `timeoutMs: 1`, và `disabled: true`;
4. ghi `artifacts/review/<stamp>-dsh-smoke.json`;
5. gỡ probe khỏi profile (giữ bundle chính).

Profile `web` không bị chạm. Mọi overlay nằm trong thư mục tạm, không sửa
`cordis.patch.yml` của profile.
