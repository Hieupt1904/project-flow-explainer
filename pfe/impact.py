"""Impact analysis and knowledge refresh.

The impact report answers one question with evidence: after touching these
files, which flows, routes, symbols and tests are in the blast radius, and what
should be verified before calling the change safe.

Risk is a rule, not a feeling:

    high    changed file declares a route, or a flow member, or is imported by
            two or more other modules
    medium  changed file defines symbols that are called elsewhere
    low     changed file is a leaf with no inbound import/call edge
"""

import re

from . import index as index_mod

DIFF_FILE_RE = re.compile(r"^\+\+\+ b/(.+)$", re.M)


def changed_files_from_diff(diff):
    if not diff:
        return []
    return sorted(set(DIFF_FILE_RE.findall(diff)))


def impact_analysis(root, changed_files=(), diff=None, max_items=25):
    root_path = root
    files = sorted({item.strip() for item in (changed_files or []) if str(item).strip()}
                   | set(changed_files_from_diff(diff)))
    if not files:
        raise index_mod.IndexError_(
            "no_changed_files",
            "Cần ít nhất một file thay đổi (changed_files hoặc diff).",
            'Truyền changed_files: ["src/app.py"] hoặc một unified diff.')
    if not index_mod.db_path(root_path).exists():
        raise index_mod.IndexError_(
            "index_missing", "Repository chưa có index.",
            "Chạy project_code_index mode=full trước khi phân tích tác động.")

    unknown, routes, symbols, downstream, tests, flows, warnings = [], [], [], [], [], [], []
    high = False
    with index_mod.connect(root_path, create=False) as connection:
        index_mod._ensure_schema(connection)
        commit = index_mod._meta(connection, "source_commit", "")
        for rel in files:
            entity_id = "file:" + rel
            entity = index_mod.entity(connection, entity_id)
            if entity is None:
                unknown.append(rel)
                warnings.append("File chưa có trong index: " + rel + " (file mới hoặc index cũ).")
                continue
            seen_symbols = set()
            for row in index_mod.list_entities(connection, path=rel, limit=200):
                if row["kind"] == "route":
                    routes.append({"route": row["name"], "path": rel,
                                   "start_line": row["start_line"]})
                    high = True
                elif row["kind"] in {"function", "class", "symbol"}:
                    key = (row["name"], rel)
                    if key in seen_symbols:
                        continue
                    seen_symbols.add(key)
                    symbols.append({"symbol": row["name"], "path": rel,
                                    "start_line": row["start_line"]})
            importers = connection.execute(
                "SELECT subject, evidence FROM facts WHERE predicate = 'imports' AND object = ?",
                ("module:" + _module_of(rel),)).fetchall()
            for row in importers:
                downstream.append({"file": row["subject"].split(":", 1)[-1],
                                   "relation": "imports", "path": rel})
            if len(importers) >= 2:
                high = True
            callers = connection.execute(
                "SELECT DISTINCT subject FROM facts WHERE predicate = 'calls' AND object LIKE ?",
                ("symbol:" + rel + "#%",)).fetchall()
            for row in callers:
                downstream.append({"file": row["subject"].split(":", 1)[-1],
                                   "relation": "calls", "path": rel})
            for row in connection.execute(
                    "SELECT predicate, object, confidence FROM facts "
                    "WHERE subject = ? AND predicate IN ('belongs_to_flow', 'tested_by')",
                    (entity_id,)):
                if row["predicate"] == "belongs_to_flow":
                    flows.append({"flow_id": row["object"].split(":", 1)[-1],
                                  "confidence": row["confidence"], "path": rel})
                    high = True
                else:
                    tests.append({"test": row["object"].split(":", 1)[-1], "path": rel})
        dedup = lambda items, key: list({tuple(sorted(item.items())): item for item in items}.values())
        downstream = dedup(downstream, "file")[:max_items]
        stale = index_mod.staleness(root_path)
        flow_rows = index_mod.list_flows(root_path)

    if high:
        risk = "high"
    elif downstream or symbols:
        risk = "medium"
    else:
        risk = "low"
    verification = []
    for test in tests[:max_items]:
        verification.append("chạy " + test["test"])
    if routes:
        verification.append("gọi lại route: " + ", ".join(item["route"] for item in routes[:5]))
    if flows:
        verification.append("render lại flow: " + ", ".join(item["flow_id"] for item in flows[:5]))
    if not verification:
        verification.append("chạy bộ test của repository và render lại flow liên quan")

    return {
        "status": "ok",
        "source_commit": commit,
        "changed_files": files,
        "affected_flows": flows[:max_items],
        "affected_routes": routes[:max_items],
        "affected_symbols": symbols[:max_items],
        "related_tests": tests[:max_items],
        "downstream_modules": downstream,
        "risk_level": risk,
        "risk_reasons": _risk_reasons(risk, routes, flows, downstream, symbols),
        "unknown_files": unknown,
        "stale_artifacts": [{"flow_id": row["flow_id"], "generated_at": row["generated_at"],
                             "artifact_dir": row["artifact_dir"]} for row in flow_rows[:5]],
        "index_stale": stale["stale"],
        "stale_files": stale["files"][:20],
        "suggested_verification": verification,
        "warnings": warnings,
        "evidence_refs": [{"path": item["path"], "start_line": item["start_line"],
                           "relation": ["handles_route"], "confidence": "observed"}
                          for item in routes[:10]]
                         + [{"path": item["path"], "start_line": item["start_line"],
                             "relation": ["defines"], "confidence": "observed"}
                            for item in symbols[:10]],
        "raw_source_included": False,
    }


def _module_of(rel):
    from pathlib import Path
    parts = list(Path(rel).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _risk_reasons(risk, routes, flows, downstream, symbols):
    reasons = []
    if routes:
        reasons.append("file thay đổi khai báo " + str(len(routes)) + " route")
    if flows:
        reasons.append("file là thành viên của " + str(len(flows)) + " flow đã render")
    if len(downstream) >= 2:
        reasons.append("có " + str(len(downstream)) + " module/file phụ thuộc")
    if symbols and risk == "medium":
        reasons.append("định nghĩa " + str(len(symbols)) + " symbol có thể bị gọi")
    if not reasons:
        reasons.append("không thấy route, flow hay phụ thuộc ngược trong index")
    return reasons


def refresh(root, mode="incremental", include_vectors=False):
    """Detect changed/deleted/renamed files and refresh only what moved."""
    before = index_mod.status(root)
    summary = index_mod.build_index(root, mode=mode, include_vectors=include_vectors)
    after = index_mod.status(root)
    return {
        "status": "ok",
        "before": {"source_commit": before.get("source_commit", ""),
                   "files_indexed": before.get("files_indexed", 0)},
        "after": {"source_commit": after.get("source_commit", ""),
                  "files_indexed": after.get("files_indexed", 0)},
        "mode": summary["mode"],
        "files_parsed": summary["files_parsed"],
        "files_reused": summary["files_reused"],
        "changed": summary["changed"],
        "added": summary["added"],
        "deleted": summary["deleted"],
        "renamed": summary["renamed"],
        "stale_files": summary["stale_files"],
        "warnings": summary["warnings"],
        "no_full_rebuild": summary["mode"] != "full",
    }
