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


def _dedup_downstream(items):
    """One row per (downstream file, relation); the first evidence wins.

    Keyed on fields rather than the whole dict: `evidence_refs` is a list and
    tuples of dict items are not hashable.
    """
    seen = set()
    out = []
    for item in items:
        key = (item.get("path") or item.get("file"), item.get("relation"), item.get("symbol"))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _evidence_of(row):
    """Parse a fact's evidence JSON, tolerating a missing or broken column."""
    import json as _json
    try:
        raw = row["evidence"]
    except (IndexError, KeyError):
        return {}
    if not raw:
        return {}
    try:
        parsed = _json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _entity_location(connection, entity_id, fallback_line=0):
    """(path, symbol, start_line) of an entity, or empty values when unknown.

    A file entity has no meaningful start_line (it is 0), so the caller passes the
    evidence line it already knows — a call site, an import line — instead of
    reporting 0 as if it were a location.
    """
    row = connection.execute(
        "SELECT path, symbol, name, start_line FROM entities WHERE id = ?",
        (entity_id,)).fetchone()
    if row is None:
        return "", "", fallback_line
    line = int(row["start_line"] or 0) or fallback_line
    return (row["path"] or "",
            row["symbol"] or row["name"] or "",
            line)


def _fact_ref(row, changed_rel):
    evidence = {}
    try:
        import json as _json
        evidence = _json.loads(row["evidence"]) if row["evidence"] else {}
    except (ValueError, TypeError):
        evidence = {}
    predicate = ""
    try:
        predicate = row["predicate"]
    except (IndexError, KeyError):
        predicate = ""
    return {"path": evidence.get("path") or changed_rel,
            "start_line": evidence.get("start_line") or 1,
            "relation": [predicate] if predicate else [],
            "confidence": row["confidence"] or "structural"}


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
                "SELECT subject, predicate, evidence, confidence FROM facts"
                " WHERE predicate = 'imports' AND object = ?",
                ("module:" + _module_of(rel),)).fetchall()
            for row in importers:
                # `path` is the DOWNSTREAM file's path, not the changed file's:
                # reporting the changed path here told the reader nothing about
                # where the blast radius actually lands.
                ev = _evidence_of(row)
                down_path, down_symbol, down_line = _entity_location(
                    connection, row["subject"], fallback_line=ev.get("start_line") or 0)
                downstream.append({
                    "file": down_path or row["subject"].split(":", 1)[-1],
                    "path": down_path or row["subject"].split(":", 1)[-1],
                    "symbol": down_symbol,
                    "relation": "imports",
                    "target": _module_of(rel) or rel,
                    "target_kind": "module",
                    "start_line": down_line,
                    "confidence": row["confidence"] or "structural",
                    "evidence_refs": [_fact_ref(row, rel)],
                    "changed_file": rel,
                })
            if len(importers) >= 2:
                high = True
            callers = connection.execute(
                "SELECT DISTINCT subject, predicate, confidence, evidence, object FROM facts"
                " WHERE predicate = 'calls' AND object LIKE ?",
                ("symbol:" + rel + "#%",)).fetchall()
            for row in callers:
                ev = _evidence_of(row)
                down_path, down_symbol, down_line = _entity_location(
                    connection, row["subject"], fallback_line=ev.get("start_line") or 0)
                downstream.append({
                    "file": down_path or row["subject"].split(":", 1)[-1],
                    "path": down_path or row["subject"].split(":", 1)[-1],
                    "symbol": down_symbol,
                    "relation": "calls",
                    "target": (row["object"] or "").split("#")[-1] if "object" in row.keys() else "",
                    "target_kind": "symbol",
                    "start_line": down_line,
                    "confidence": row["confidence"] or "structural",
                    "evidence_refs": [_fact_ref(row, rel)],
                    "changed_file": rel,
                })
            for row in connection.execute(
                    "SELECT predicate, object, confidence, evidence FROM facts "
                    "WHERE subject = ? AND predicate IN ('belongs_to_flow', 'tested_by')",
                    (entity_id,)):
                if row["predicate"] == "belongs_to_flow":
                    # Only a flow this file actually belongs to: the report used
                    # to append the first five flows in the repository instead,
                    # which is a list of everything rather than a blast radius.
                    flows.append({"flow_id": row["object"].split(":", 1)[-1],
                                  "confidence": row["confidence"],
                                  "path": rel,
                                  "evidence_refs": [_fact_ref(row, rel)]})
                    high = True
                else:
                    test_path, _symbol, test_line = _entity_location(connection, row["object"])
                    tests.append({"test": row["object"].split(":", 1)[-1],
                                  "path": test_path or rel,
                                  "start_line": test_line,
                                  "evidence_kind": ("file_level"
                                                    if not test_line or test_line <= 1
                                                    else "line_level"),
                                  "confidence": row["confidence"] or "structural",
                                  "evidence_refs": [_fact_ref(row, rel)]})
        downstream = _dedup_downstream(downstream)[:max_items]
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
        "stale_artifacts": [
            # Artifacts are informational unless the flow they render is in this
            # blast radius; listing the first five regardless made a stale
            # artifact look like a conclusion.
            {"flow_id": row["flow_id"], "generated_at": row["generated_at"],
             "artifact_dir": row["artifact_dir"],
             "source_commit": row.get("source_commit") or "",
             "relation": ("affected_flow"
                          if row["flow_id"] in {item["flow_id"] for item in flows}
                          else "informational"),
             "stale": bool(commit and row.get("source_commit")
                           and row["source_commit"] != commit)}
            for row in flow_rows[:5]],
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
