#!/usr/bin/env python3
"""Run the toolchain on one real project and write a scrubbed evidence record.

Why: "chạy được trên fixture" is not the same claim as "chạy được trên dự án thật".

Privacy rules applied to the record:
  * no absolute path, no relative path, no repository name;
  * repository identified by a hash of its canonical path;
  * symbol names, route labels and entry-point labels are kept — they are the
    evidence that the result is real, and the caller chose the repository;
  * everything is written to artifacts/review/<stamp>-real-project-<label>.json.

Usage:
  python3 scripts/run_real_project_check.py --repo <absolute-path> \
      --request "..." --label web [--copy]

--copy (default) copies the repository to a temp dir first, so the analysed
project keeps its working tree and git status untouched.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEW = ROOT / "artifacts" / "review"
sys.path.insert(0, str(ROOT))

from pfe import index as index_mod  # noqa: E402


def run_json(argv):
    started = time.time()
    completed = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True,
                               check=False)
    duration = round((time.time() - started) * 1000, 1)
    line = completed.stdout.strip().split("\n")[-1] if completed.stdout.strip() else ""
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        payload = {"status": "error", "code": "unparsable", "message": line[:300]}
    return payload, duration, completed


def brief(result, limit=5):
    return [{
        "kind": item["kind"],
        "symbol": item["symbol"],
        "start_line": item["start_line"],
        "confidence": item["confidence"],
        "location_confidence": item.get("location_confidence", ""),
        "relevance_confidence": item.get("relevance_confidence", ""),
        "relation": item["relation"][:4],
        "score": item["score"],
        "why_matched": item["why_matched"],
    } for item in result.get("results", [])[:limit]]


def slug(value):
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return cleaned or "project"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Real-project evidence run")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--task", default="")
    parser.add_argument("--label", default="real-project")
    parser.add_argument("--keep", action="store_true",
                        help="chạy trên chính repository, không copy")
    args = parser.parse_args(argv)
    source = Path(args.repo).expanduser().resolve()
    if not source.is_dir():
        raise SystemExit("không thấy repository: " + str(source))
    task = args.task or args.request

    work = None
    if args.keep:
        target = source
    else:
        work = Path(tempfile.mkdtemp(prefix="pfe-real-"))
        target = work / source.name
        shutil.copytree(source, target, symlinks=True, ignore=shutil.ignore_patterns(
            ".git", "node_modules", ".venv", "venv", "__pycache__", "artifacts", ".pfe"))
    record = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "label": args.label,
        "repository_id": hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:16],
        "request": args.request,
        "privacy": {
            "absolute_paths": "removed",
            "relative_paths": "removed",
            "repository_name": "removed",
            "symbols_routes": "kept (evidence)",
            "reason": "dự án riêng tư; chỉ giữ số liệu và định danh kỹ thuật",
        },
    }
    try:
        started = time.time()
        flow, _flow_ms, flow_run = run_json([
            sys.executable, str(ROOT / "scripts" / "build_flow.py"),
            "--repo", str(target), "--request", args.request, "--json"])
        record["flow"] = {
            "status": flow.get("status"),
            "counts": flow.get("counts"),
            "files_scanned": flow.get("files_scanned"),
            "scan_bytes": flow.get("scan_bytes"),
            "related_count": len(flow.get("related") or []),
            "warnings": flow.get("warnings") or [],
            "limits_count": len(flow.get("limits") or []),
            "artifact_contract": flow.get("contract"),
            "duration_ms": round((time.time() - started) * 1000, 1),
            "exit_code": flow_run.returncode,
        }

        full, full_ms, _ = run_json([sys.executable, str(ROOT / "tools" / "pfe_cli.py"),
                                     "index", "--repo", str(target), "--mode", "full"])
        record["index_full"] = {
            "status": full.get("status"), "mode": full.get("mode"),
            "files_indexed": full.get("files_indexed"),
            "symbols_indexed": full.get("symbols_indexed"),
            "routes_indexed": full.get("routes_indexed"),
            "tests_indexed": full.get("tests_indexed"),
            "entities": full.get("entities"), "facts": full.get("facts"),
            "index_version": full.get("index_version"),
            "duration_ms": full.get("duration_ms"), "wall_ms": full_ms,
        }

        started = time.time()
        incremental, _, _ = run_json([sys.executable, str(ROOT / "tools" / "pfe_cli.py"),
                                      "index", "--repo", str(target),
                                      "--mode", "incremental"])
        record["index_incremental"] = {
            "mode": incremental.get("mode"),
            "files_parsed": incremental.get("files_parsed"),
            "files_reused": incremental.get("files_reused"),
            "duration_ms": incremental.get("duration_ms"),
            "wall_ms": round((time.time() - started) * 1000, 1),
            "warnings": incremental.get("warnings") or [],
        }

        # Entry points actually found, grouped by kind (0.4.0 schema).
        entry_counts = {}
        route_labels = []
        with index_mod.connect(target, create=False) as connection:
            index_mod._ensure_schema(connection)
            # Count with GROUP BY: a LIMIT on the row list silently truncates the
            # kinds that sort last, which once made the report look like the
            # index had lost entry points.
            for row in connection.execute(
                    "SELECT kind, COUNT(*) AS c FROM entry_points GROUP BY kind"):
                entry_counts[row["kind"]] = row["c"]
            for row in connection.execute(
                    "SELECT label FROM entry_points WHERE kind = 'http_route' "
                    "AND label <> '' ORDER BY path, start_line LIMIT 8"):
                route_labels.append(row["label"])
            files_with_entry = connection.execute(
                "SELECT COUNT(DISTINCT path) AS c FROM entry_points").fetchone()["c"]
        record["entry_points"] = {
            "kinds": entry_counts,
            "files_with_entry_point": files_with_entry,
            "route_labels_sample": route_labels,
        }

        queries = [args.request, "export", "cập nhật dữ liệu"]
        record["search"] = []
        for query in queries:
            payload, wall, _ = run_json([sys.executable, str(ROOT / "tools" / "pfe_cli.py"),
                                         "search", "--repo", str(target),
                                         "--query", query, "--top-k", "5"])
            record["search"].append({
                "query": query,
                "channels": payload.get("channels"),
                "stale": payload.get("stale"),
                "warnings": payload.get("warnings"),
                "top": brief(payload),
                "wall_ms": wall,
            })

        pack, _, _ = run_json([sys.executable, str(ROOT / "tools" / "pfe_cli.py"),
                               "context-pack", "--repo", str(target),
                               "--task", task, "--max-files", "8"])
        pack_kinds = {}
        for entry in pack.get("entry_points") or []:
            pack_kinds[entry["kind"]] = pack_kinds.get(entry["kind"], 0) + 1
        record["context_pack"] = {
            "analysis_kind": pack.get("analysis_kind"),
            "intent": pack.get("intent"),
            "entry_point_kinds": pack_kinds,
            "entry_points": len(pack.get("entry_points") or []),
            "routes": [item.get("route") for item in (pack.get("routes") or [])][:5],
            "likely_files": [
                {"path_kind": item.get("kind"), "symbol": item.get("symbol"),
                 "start_line": item.get("start_line"),
                 "location_confidence": item.get("location_confidence"),
                 "relevance_confidence": item.get("relevance_confidence")}
                for item in (pack.get("likely_files") or [])[:5]
            ],
            "dependencies": [
                {"kind": item.get("kind"), "relation": item.get("relation"),
                 "has_line": bool(item.get("start_line")),
                 "confidence": item.get("confidence"),
                 "why_included": item.get("why_included")}
                for item in (pack.get("dependencies") or [])[:5]
            ],
            "dependency_count": len(pack.get("dependencies") or []),
            "external_dependencies": len(pack.get("external_dependencies") or []),
            "related_tests": len(pack.get("related_tests") or []),
            "limitations": (pack.get("limitations") or [])[:4],
            "snippets_included": pack.get("snippets_included"),
            "stale": pack.get("stale"),
        }

        with index_mod.connect(target, create=False) as connection:
            index_mod._ensure_schema(connection)
            changed = [row["path"] for row in connection.execute(
                "SELECT path FROM entities WHERE kind = 'file' LIMIT 1")]
        if changed:
            impact, _, _ = run_json([sys.executable, str(ROOT / "tools" / "pfe_cli.py"),
                                     "impact", "--repo", str(target),
                                     "--changed", changed[0]])
            record["impact"] = {
                "risk_level": impact.get("risk_level"),
                "risk_reasons": impact.get("risk_reasons"),
                "affected_routes": len(impact.get("affected_routes") or []),
                "affected_symbols": len(impact.get("affected_symbols") or []),
                "related_tests": len(impact.get("related_tests") or []),
                "downstream_modules": len(impact.get("downstream_modules") or []),
                "suggested_verification": len(impact.get("suggested_verification") or []),
            }

        verified, _, _ = run_json([sys.executable, str(ROOT / "tools" / "pfe_cli.py"),
                                   "verify", "--repo", str(target)])
        record["verify"] = {
            "static_verdict": verified.get("static_verdict"),
            "overall_verdict": verified.get("overall_verdict"),
            "gates": verified.get("gates"),
            "not_verified": verified.get("not_verified"),
            "checks": {item["check"]: item["status"] for item in verified.get("checks") or []},
            "ui_verified": verified.get("ui_verified"),
            "runtime_verified": verified.get("runtime_verified"),
        }
        record["status"] = "ok"
    except Exception as error:  # noqa: BLE001 - evidence must record the failure
        record["status"] = "error"
        record["error"] = type(error).__name__ + ": " + str(error)
    finally:
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    REVIEW.mkdir(parents=True, exist_ok=True)
    path = REVIEW / (stamp + "-real-project-" + slug(args.label) + ".json")
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "record": path.relative_to(ROOT).as_posix(),
        "status": record["status"],
        "flow": record.get("flow", {}).get("counts"),
        "index_files": record.get("index_full", {}).get("files_indexed"),
        "entry_kinds": record.get("entry_points", {}).get("kinds"),
        "routes": record.get("context_pack", {}).get("routes"),
        "verify": record.get("verify", {}).get("overall_verdict"),
    }, ensure_ascii=False))
    return 0 if record["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
