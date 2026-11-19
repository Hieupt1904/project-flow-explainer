#!/usr/bin/env python3
"""Build an evidence-backed flow graph from a repository and a flow request.

This is the CLI front end. The work lives in the pfe package so the same code
serves the DSH tool, the index and the retrieval layer:

    pfe.policy   path rules, artifact containment, atomic write
    pfe.facts    repository scan -> static facts (symbols, routes, imports, calls)
    pfe.flow     flow projection selected by the request
    pfe.emit     overview + public/internal output contract

Output (one analysis, four files, no disagreement between them):

    <repo>/artifacts/flows/<slug>/flow.json     public
    <repo>/artifacts/flows/<slug>/flow.html     public
    <repo>/artifacts/flows/<slug>/overview.md   public
    <repo>/artifacts/flows/<slug>/run.json      internal provenance

Read-only with respect to the analysed repository, no network, no repository
code execution, no source text copied into the artifacts.

Usage:
  python build_flow.py --repo /path/to/repo --request "giải thích luồng xuất báo cáo"
  python build_flow.py --repo R --request Q --json
No third-party packages required.
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for candidate in (str(HERE), str(ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import render_flow  # noqa: E402  (core renderer, same directory)
from pfe import emit, facts, flow as flow_mod, policy  # noqa: E402
from pfe.policy import BuildError  # noqa: E402,F401  (re-exported for callers)
from pfe.text import strip_diacritics, utc_now  # noqa: E402

SCHEMA_VERSION = flow_mod.SCHEMA_VERSION
SLUG_MAX = policy.SLUG_MAX
ARTIFACT_SUBDIR = policy.ARTIFACT_SUBDIR
MAX_STEPS = flow_mod.MAX_STEPS


def _require_text(value, field):
    if not isinstance(value, str):
        raise BuildError(
            "invalid_argument_type",
            field + " phải là chuỗi, nhận được " + type(value).__name__,
            "Truyền chuỗi mô tả flow, ví dụ: \"Giải thích từ lúc người dùng nhấn xuất báo cáo\".")
    return value


def make_slug(request, git, taken):
    base = policy.re.sub(r"[^a-z0-9]+", "-", strip_diacritics(request).lower()).strip("-")
    words = [word for word in base.split("-") if word][:6]
    digest = hashlib.sha1((request + "|" + str(git.get("commit"))).encode("utf-8")).hexdigest()[:6]
    slug = "-".join(words + [digest])[:SLUG_MAX].strip("-") or "flow"
    candidate, counter = slug, 2
    while candidate in taken:
        suffix = "-" + str(counter)
        candidate = (slug[: SLUG_MAX - len(suffix)] + suffix).strip("-")
        counter += 1
        if counter > 50:
            raise BuildError("slug_exhausted", "Không tạo được thư mục artifact không trùng tên")
    return candidate


def resolve_repository(repo):
    if not isinstance(repo, (str, os.PathLike)):
        raise BuildError(
            "invalid_argument_type",
            "repository phải là chuỗi đường dẫn, nhận được " + type(repo).__name__,
            "Truyền đường dẫn tuyệt đối tới thư mục repository.")
    root = Path(repo).expanduser()
    if not root.exists():
        raise BuildError("repository_not_found", "Không thấy repository: " + str(root),
                         "Kiểm tra lại đường dẫn tuyệt đối tới thư mục repository.")
    root = policy.real_dir(root, "repository_unreadable", "repository")
    if not os.access(root, os.R_OK | os.X_OK):
        raise BuildError("repository_unreadable", "Không có quyền đọc: " + str(root))
    return root


def run(repo, request, out_dir=None, slug=None, record_index=True):
    """Analyse one repository and write the flow artifacts. Returns a summary."""
    request = _require_text(request, "flow_request").strip()
    if not request:
        raise BuildError("missing_flow_request", "Thiếu mô tả flow cần phân tích.",
                         'Ví dụ: --request "Giải thích từ lúc người dùng nhấn xuất báo cáo"')
    root = resolve_repository(repo)
    artifacts_root = policy.validate_out_dir(root, out_dir)
    slug = policy.safe_slug(slug)

    files, excluded, budget = facts.scan_repository(root, include_tests=False)
    git = facts.git_state(root)
    basenames = facts.index_basenames(files)
    known = {item.rel for item in files}
    for item in files:
        item.imports = facts.find_imports(item.text(), item.rel, known, basenames)
        excluded["secret_lines"] += item.secret_lines

    graph, limits, warnings, related = flow_mod.build_graph(request, files, git)
    graph["meta"]["generated_at"] = utc_now()
    limits = list(limits) + list(budget.notes)
    graph["assumptions"] = list(graph.get("assumptions") or []) + list(budget.notes)

    if slug is None:
        slug = make_slug(request, git, policy.artifact_names(artifacts_root))
    graph["flow_id"] = slug
    graph["meta"]["files_scanned"] = len(files)
    graph["meta"]["scan_bytes"] = budget.total_bytes

    overview = emit.render_overview(
        graph, root.name, request, excluded, limits, warnings, related,
        files_scanned=len(files), scan_bytes=budget.total_bytes,
        budget_notes=budget.notes)

    counts = {"verified": 0, "partial": 0, "inferred": 0, "unknown": 0}
    for node in graph["nodes"]:
        counts[node["confidence"]] = counts.get(node["confidence"], 0) + 1

    run_meta = {
        "status": "ok",
        "schema_version": SCHEMA_VERSION,
        "flow_id": graph["flow_id"],
        "generated_at": graph["meta"]["generated_at"],
        "repository_name": root.name,
        "request": request,
        "source": git,
        "counts": counts,
        "limits": limits,
        "warnings": warnings,
        "related": related,
        "excluded": excluded,
        "files_scanned": len(files),
        "scan_bytes": budget.total_bytes,
        "budget_notes": budget.notes,
        "evidence_model": graph["meta"].get("evidence_model", {}),
        "files": list(emit.PUBLIC_FILES) + list(emit.INTERNAL_FILES),
    }

    artifacts_dir = artifacts_root / slug
    with policy.staging_directory(artifacts_root, slug,
                                  policy.artifact_names(artifacts_root)) as staging:
        try:
            paths = emit.write_flow_artifacts(staging, graph, overview, render_flow, run_meta)
        except render_flow.FlowError as error:
            raise BuildError("invalid_graph", "Sơ đồ sinh ra không hợp lệ: " + str(error))
        except OSError as error:
            raise BuildError("artifact_write_failed", "Không ghi được artifact: " + str(error))

    result = {
        "status": "ok",
        "schema_version": SCHEMA_VERSION,
        "slug": slug,
        "flow_id": graph["flow_id"],
        "repository": str(root),
        "repository_name": root.name,
        "artifacts_dir": str(artifacts_dir),
        "paths": {key: str(artifacts_dir / value.name) for key, value in paths.items()},
        "counts": counts,
        "limits": limits,
        "warnings": warnings,
        "related": related,
        "excluded": excluded,
        "source": git,
        "files_scanned": len(files),
        "scan_bytes": budget.total_bytes,
        "contract": {
            "public": list(emit.PUBLIC_FILES),
            "internal": list(emit.INTERNAL_FILES),
            "run_json": emit.RUN_JSON_CONTRACT,
        },
        "indexed": False,
    }
    if record_index:
        result["indexed"] = _record(root, graph, artifacts_dir)
    return result


def _record(root, graph, artifacts_dir):
    """Best effort: a missing/broken index never fails a flow run."""
    try:
        from pfe import index as index_mod
        if not index_mod.db_path(root).exists():
            return False
        index_mod.record_flow(root, graph, str(artifacts_dir))
        return True
    except Exception:  # noqa: BLE001 - provenance is optional, the flow is not
        return False


def report_error(error, as_json):
    """Structured error on stdout (--json) and stderr; stable exit code."""
    payload = {"status": "error", "code": error.code,
               "message": error.message, "hint": error.hint}
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
    print("ERROR [" + error.code + "]: " + error.message, file=sys.stderr)
    if error.hint:
        print("Gợi ý: " + error.hint, file=sys.stderr)
    return 3 if error.code == "internal_error" else 2


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Phân tích repository và sinh flow.json + flow.html + overview.md")
    parser.add_argument("--repo", required=True, type=Path, help="Đường dẫn repository cần phân tích")
    parser.add_argument("--request", required=True, help="Mô tả flow bằng tiếng Việt thông thường")
    parser.add_argument("--out-dir", default=None,
                        help="Chỉ chấp nhận <repo>/artifacts/flows")
    parser.add_argument("--slug", default=None, help="Tên thư mục artifact; bỏ trống để tự sinh")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="In một object JSON kết quả ra stdout")
    args = parser.parse_args(argv)
    try:
        result = run(args.repo, args.request, args.out_dir, args.slug)
    except BuildError as error:
        return report_error(error, args.as_json)
    except Exception as error:  # noqa: BLE001 - CLI contract: never leak a traceback
        return report_error(BuildError(
            "internal_error",
            "Lỗi nội bộ khi phân tích: " + type(error).__name__ + ": " + str(error),
            "Đây là lỗi của tool, không phải của repository; chạy lại với --json để lấy mã lỗi.",
        ), args.as_json)
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print("OK: " + result["flow_id"] + " · " + str(sum(result["counts"].values()))
              + " node (" + str(result["counts"]) + ") · "
              + str(result["files_scanned"]) + " file đã đọc")
        for key, value in result["paths"].items():
            print("  " + key + ": " + value)
        print("  public: " + ", ".join(result["contract"]["public"]))
        print("  internal: " + ", ".join(result["contract"]["internal"]))
        for warning in result["warnings"]:
            print("  cảnh báo: " + warning)
    return 0


if __name__ == "__main__":
    sys.exit(main())
