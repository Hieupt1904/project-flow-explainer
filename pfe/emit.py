"""Artifact emission: overview text, the public/internal contract, atomic writes.

Output contract (decided once, enforced here and in the adapter):

    public   flow.json  flow.html  overview.md
    internal run.json   provenance only: counts, limits, git state, contract tag

run.json is never called a public deliverable. It exists so a reviewer can read
what the run actually did without reopening the repository. Tests assert the
tag, so documentation cannot drift from behaviour.
"""

import json
from pathlib import Path

from .policy import BuildError

PUBLIC_FILES = ("flow.json", "flow.html", "overview.md")
INTERNAL_FILES = ("run.json",)
RUN_JSON_CONTRACT = "internal-provenance"

OVERVIEW_TEMPLATE = """# {title}

Sinh tự động: {generated} · `scripts/build_flow.py` (schema {schema}).

## Yêu cầu

> {request}

## Repository được phân tích

| Mục | Giá trị |
|---|---|
| Tên | `{repo}` |
| Nhánh | `{branch}` |
| Commit | `{commit}` |
| Thay đổi chưa commit | {dirty} |
| File đã đọc | {files} |
| Byte source đã đọc | {bytes_total} |
| Số ngân sách bị cắt | {budget_notes} |

Đường dẫn tuyệt đối không được ghi vào artifact để tránh lộ cấu trúc máy cá nhân.

## Luồng xử lý

{description}

| # | Bước | Loại | Vị trí | Bằng chứng thành viên | Tin cậy |
|---|---|---|---|---|---|
{nodes}

## Quan hệ giữa các bước

| Cạnh | Nhãn | Loại | Bằng chứng | Ghi chú |
|---|---|---|---|---|
{edges}

## Mô hình bằng chứng

- `verified` = {verified}
- `partial`  = {partial}
- `inferred` = {inferred}
- Có cạnh `call` trong sơ đồ: {calls}
- Có bằng chứng runtime: {runtime}

## File khớp từ khoá nhưng KHÔNG thuộc luồng

{related}

## Giới hạn và phần chưa xác minh

{limits}

{warnings}

## Phạm vi đọc và loại trừ

Chỉ đọc file source trong repository. Các mục sau bị loại:

{excluded}

Không gọi network, không chạy code của repository, không sửa file nguồn, không chép nội dung source.

## Tệp sinh ra

- `flow.json` — dữ liệu có cấu trúc, dùng lại được cho lần render sau (public)
- `flow.html` — sơ đồ mở offline (public)
- `overview.md` — tài liệu này (public)
- `run.json` — internal provenance, KHÔNG phải public output: chứa số đếm, giới hạn và trạng thái git của lần chạy
"""


def render_overview(graph, repo_name, request, excluded, limits, warnings, related,
                    files_scanned=0, scan_bytes=0, budget_notes=()):
    rows = []
    for index, node in enumerate(graph["nodes"], start=1):
        refs = node.get("source_refs") or []
        location = "—"
        if refs:
            location = "`" + refs[0]["path"] + "`"
            if refs[0].get("start_line"):
                location += ":" + str(refs[0]["start_line"])
        membership = next(
            (edge["evidence"] for edge in graph["edges"] if edge["to"] == node["id"]), "—")
        rows.append("| " + str(index) + " | " + node["title"] + " | " + node["type"]
                    + " | " + location + " | " + membership + " | " + node["confidence"] + " |")

    edge_rows = [
        "| " + edge["from"] + " → " + edge["to"] + " | " + edge["label"] + " | "
        + edge["kind"] + " | " + str(edge.get("evidence", "—")) + " | "
        + str(edge.get("technical", "—")) + " |"
        for edge in graph["edges"]
    ]
    related_rows = ["- " + item["path"] + " — " + item["reason"] for item in related] \
        or ["- Không có file nào bị loại khỏi luồng."]
    excluded_lines = "\n".join("- " + key + ": " + str(value)
                              for key, value in sorted(excluded.items()) if value) \
        or "- Không có mục nào bị loại."
    limits_lines = "\n".join("- " + item for item in limits) or "- Không có giới hạn bổ sung."
    warnings_lines = "\n".join("- " + item for item in warnings) or "- Không có cảnh báo."
    source = graph["meta"]["source"]
    evidence_model = graph["meta"].get("evidence_model", {})
    confidence = evidence_model.get("confidence", {})

    return OVERVIEW_TEMPLATE.format(
        title=graph["title"],
        generated=graph["meta"]["generated_at"],
        schema=graph["meta"]["schema_version"],
        request=request.strip(),
        repo=repo_name,
        branch=source.get("branch") or "không có git",
        commit=source.get("commit") or "không có git",
        dirty=("có — " + str(source.get("dirty_files")) + " file") if source.get("dirty") else "không",
        files=files_scanned,
        bytes_total=scan_bytes,
        budget_notes=("; ".join(budget_notes) if budget_notes else "không"),
        description=graph["description"],
        nodes="\n".join(rows),
        edges="\n".join(edge_rows),
        verified=confidence.get("verified", "vị trí thật + quan hệ thật"),
        partial=confidence.get("partial", "suy luận từ cấu trúc"),
        inferred=confidence.get("inferred", "suy luận"),
        calls="không" if not evidence_model.get("call_edges") else "có",
        runtime="không" if not evidence_model.get("runtime_verified") else "có",
        related="\n".join(related_rows),
        limits=limits_lines,
        warnings=warnings_lines,
        excluded=excluded_lines,
    )


def write_flow_artifacts(directory, graph, overview, render_flow, run_meta):
    """Write the four files into an already-created staging directory."""
    directory = Path(directory)
    flow_json = directory / "flow.json"
    flow_html = directory / "flow.html"
    overview_md = directory / "overview.md"
    run_json = directory / "run.json"
    info = render_flow.validate(graph)
    render_flow.assign_positions(graph, info)
    flow_json.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    flow_html.write_text(render_flow.render_json(graph), encoding="utf-8")
    overview_md.write_text(overview, encoding="utf-8")
    payload = dict(run_meta)
    payload.update({
        "contract": RUN_JSON_CONTRACT,
        "public_outputs": list(PUBLIC_FILES),
        "internal_outputs": list(INTERNAL_FILES),
    })
    run_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths = {"flow_json": flow_json, "flow_html": flow_html,
             "overview": overview_md, "run": run_json}
    if not all(path.is_file() and path.stat().st_size > 0 for path in paths.values()):
        raise BuildError("artifact_write_failed",
                         "Artifact ghi ra thiếu file hoặc rỗng; staging sẽ được dọn.")
    return paths
