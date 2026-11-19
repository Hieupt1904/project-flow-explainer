#!/usr/bin/env python3
"""Machine-facing CLI for the Project Flow Explainer code-knowledge layer.

Every subcommand prints exactly one JSON object on stdout and never leaks a
traceback. The DSH adapter calls this file; it is also the human CLI.

Subcommands:

    flow           build one flow projection (same contract as build_flow.py)
    index          build/refresh the local knowledge index
    search         hybrid retrieval (exact + vector candidate + graph + rerank)
    context-pack   context pack for a coding task
    impact         impact analysis for changed files
    verify         verify graph evidence, artifacts, UI, privacy, test mapping
    refresh        incremental refresh (changed/deleted/renamed detection)
    status         index status and staleness

Rules shared by all subcommands: local absolute path only, no network, no
repository code execution, no raw source in output unless explicitly asked and
allowed by the caller's mode.
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPTS = ROOT / "scripts"
# The flow subcommand reuses scripts/build_flow.py, which imports its sibling
# render_flow as a top-level module. Both directories must be importable no
# matter which working directory the caller used (repo root, elsewhere, DSH).
for candidate in (str(HERE), str(ROOT), str(SCRIPTS)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from pfe.policy import BuildError  # noqa: E402


def _json(payload):
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def _fail(code, message, hint="", exit_code=2):
    print(json.dumps({"status": "error", "code": code, "message": message,
                      "hint": hint}, ensure_ascii=False))
    return exit_code


def _repository(value):
    if not isinstance(value, str) or not value.strip():
        raise BuildError("repository_path_missing", "Thiếu repository_path.",
                         "Truyền đường dẫn tuyệt đối tới thư mục repository.")
    if not Path(value).is_absolute():
        raise BuildError("repository_path_relative",
                         "repository_path phải là đường dẫn tuyệt đối: " + value,
                         "Dùng đường dẫn bắt đầu bằng / (không dùng ~ hay đường dẫn tương đối).")
    if not Path(value).exists():
        raise BuildError("repository_not_found", "Không thấy repository: " + value,
                         "Tool không tự clone hay tải repository.")
    return value


def cmd_flow(args):
    try:
        import build_flow
    except ImportError as error:
        # Never let a broken installation look like a successful run: report the
        # missing module as a tool error with its own code.
        raise BuildError(
            "core_import_failed",
            "Không import được scripts/build_flow.py: " + str(error),
            "Chạy CLI từ checkout của repo hoặc cài bundle có vendor/core đầy đủ.")
    result = build_flow.run(args.repo, args.request, args.out_dir, args.slug)
    result.pop("repository", None)
    return _json(result)


def cmd_index(args):
    from pfe import index
    root = _repository(args.repo)
    summary = index.build_index(root, mode=args.mode,
                                include_vectors=bool(args.include_vectors))
    return _json(summary)


def cmd_search(args):
    from pfe import retrieval
    root = _repository(args.repo)
    filters = {}
    if args.kind:
        filters["kind"] = args.kind
    if args.language:
        filters["language"] = args.language
    payload = retrieval.retrieve(root, args.query, top_k=args.top_k, filters=filters,
                                 use_vectors=not args.no_vectors)
    return _json(payload)


def cmd_context(args):
    from pfe import retrieval
    root = _repository(args.repo)
    payload = retrieval.context_pack(root, args.task, max_files=args.max_files,
                                     include_snippets=bool(args.include_snippets))
    return _json(payload)


def cmd_impact(args):
    from pfe import impact
    root = _repository(args.repo)
    payload = impact.impact_analysis(root, changed_files=args.changed,
                                     diff=args.diff)
    return _json(payload)


def cmd_verify(args):
    from pfe import verify
    root = _repository(args.repo)
    return _json(verify.verify_repository(root))


def cmd_refresh(args):
    from pfe import impact
    root = _repository(args.repo)
    return _json(impact.refresh(root, mode=args.mode,
                                include_vectors=bool(args.include_vectors)))


def cmd_status(args):
    from pfe import index
    root = _repository(args.repo)
    return _json(index.status(root))


def build_parser():
    parser = argparse.ArgumentParser(description="Project Flow Explainer code-knowledge CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    flow = sub.add_parser("flow", help="dựng một flow projection")
    flow.add_argument("--repo", required=True)
    flow.add_argument("--request", required=True)
    flow.add_argument("--out-dir", default=None)
    flow.add_argument("--slug", default=None)
    flow.set_defaults(handler=cmd_flow)

    index = sub.add_parser("index", help="xây index tri thức")
    index.add_argument("--repo", required=True)
    index.add_argument("--mode", default="incremental", choices=["full", "incremental"])
    index.add_argument("--include-vectors", action="store_true", dest="include_vectors")
    index.set_defaults(handler=cmd_index)

    search = sub.add_parser("search", help="truy hồi hybrid")
    search.add_argument("--repo", required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--top-k", type=int, default=10, dest="top_k")
    search.add_argument("--kind", default=None)
    search.add_argument("--language", default=None)
    search.add_argument("--no-vectors", action="store_true", dest="no_vectors")
    search.set_defaults(handler=cmd_search)

    context = sub.add_parser("context-pack", help="gom context cho một task")
    context.add_argument("--repo", required=True)
    context.add_argument("--task", required=True)
    context.add_argument("--max-files", type=int, default=12, dest="max_files")
    context.add_argument("--include-snippets", action="store_true", dest="include_snippets")
    context.set_defaults(handler=cmd_context)

    impact = sub.add_parser("impact", help="phân tích tác động")
    impact.add_argument("--repo", required=True)
    impact.add_argument("--changed", action="append", default=[])
    impact.add_argument("--diff", default=None)
    impact.set_defaults(handler=cmd_impact)

    verify = sub.add_parser("verify", help="kiểm tra graph/artifact/UI/privacy")
    verify.add_argument("--repo", required=True)
    verify.set_defaults(handler=cmd_verify)

    refresh = sub.add_parser("refresh", help="refresh index tăng dần")
    refresh.add_argument("--repo", required=True)
    refresh.add_argument("--mode", default="incremental", choices=["full", "incremental"])
    refresh.add_argument("--include-vectors", action="store_true", dest="include_vectors")
    refresh.set_defaults(handler=cmd_refresh)

    status = sub.add_parser("status", help="trạng thái index")
    status.add_argument("--repo", required=True)
    status.set_defaults(handler=cmd_status)
    return parser


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exit_error:  # argparse: bad flags, not a crash
        return int(exit_error.code or 2)
    try:
        return args.handler(args)
    except BuildError as error:
        return _fail(error.code, error.message, error.hint)
    except Exception as error:  # noqa: BLE001 - CLI contract: one JSON object, no traceback
        from pfe import index as index_mod
        if isinstance(error, index_mod.IndexError_):
            return _fail(error.code, error.message, error.hint)
        return _fail("internal_error",
                     "Lỗi nội bộ: " + type(error).__name__ + ": " + str(error),
                     "Đây là lỗi của tool, không phải của repository.", 3)


if __name__ == "__main__":
    sys.exit(main())
