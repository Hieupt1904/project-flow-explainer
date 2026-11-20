"""Verification of what the tool produced: graph, evidence, artifacts, UI, privacy.

Every check returns a status from {pass, partial, blocked, fail} plus the
evidence that produced it. Nothing is reported as pass without an inspected
artifact, and a check that cannot run says blocked with the reason, never pass.
"""

import json
import os
import re
from pathlib import Path

from . import index as index_mod

ABSOLUTE_PATHS = [
    (re.compile(r"/home/(?!<)([A-Za-z0-9._-]+)"), "posix home path"),
    (re.compile(r"/Users/(?!<)([A-Za-z0-9._-]+)"), "macOS home path"),
    (re.compile(r"[A-Za-z]:\\Users\\"), "windows home path"),
    (re.compile(r"/tmp/(?!<)[A-Za-z0-9._-]+"), "tmp path"),
]
SECRET_SHAPES = [
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
PLACEHOLDER_USERS = {"ban", "you", "user", "example", "youruser", "me", "username"}
PUBLIC_FILES = {"flow.json", "flow.html", "overview.md"}
INTERNAL_FILES = {"run.json"}


def _check(name, status, detail, evidence=None):
    return {"check": name, "status": status, "detail": detail,
            "evidence": evidence or []}


def verify_repository(root, artifact_subdir=("artifacts", "flows"),
                      ui_verified=False, runtime_verified=False):
    """Run every verification that does not need a model or a network.

    Verdicts are split on purpose:

      static_verdict   only what was actually inspected here (graph, artifacts,
                       static HTML scan, privacy, test mapping);
      overall_verdict  'pass' only when a required gate outside this function
                       has real evidence too (browser render, executed tests).

    A green static scan is not a rendered page and not an executed test, so it
    must not read as an unqualified pass.
    """
    root = Path(os.path.realpath(str(root)))
    flows_root = root.joinpath(*artifact_subdir)
    checks = []
    flow_dirs = sorted([entry for entry in flows_root.iterdir()
                        if entry.is_dir() and not entry.name.startswith(".")]) \
        if flows_root.exists() else []

    checks.append(_check(
        "artifact_scope", "pass",
        "Artifact chỉ được đọc từ " + str(Path(*artifact_subdir)) + ".",
        [str(flows_root.relative_to(root)) if flows_root.exists() else "chưa có artifact"]))

    if not flow_dirs:
        checks.append(_check("flow_artifacts", "blocked",
                             "Chưa có thư mục flow nào để kiểm tra.", []))
        graph_check = _check("graph_evidence", "blocked", "Chưa có flow.json.", [])
        ui_check = _check("ui_self_contained", "blocked", "Chưa có flow.html.", [])
        privacy_check = _check("privacy", "partial", "Không có artifact để quét.", [])
    else:
        missing, present = [], []
        graph_problems, ui_problems, privacy_problems = [], [], []
        for directory in flow_dirs:
            names = {item.name for item in directory.iterdir() if item.is_file()}
            for required in sorted(PUBLIC_FILES):
                if required in names:
                    present.append(directory.name + "/" + required)
                else:
                    missing.append(directory.name + "/" + required)
            graph_problems.extend(_graph_problems(directory))
            ui_problems.extend(_ui_problems(directory))
            privacy_problems.extend(_privacy_problems(directory))
        checks.append(_check(
            "flow_artifacts", "pass" if not missing else "fail",
            "Mỗi flow có flow.json, flow.html, overview.md"
            + ("" if not missing else " — thiếu " + ", ".join(missing)), present))
        graph_check = _check(
            "graph_evidence", "pass" if not graph_problems else "fail",
            "Không có call-edge giả, không có nhánh bypass, verified có source_ref."
            if not graph_problems else "; ".join(graph_problems[:6]),
            [directory.name for directory in flow_dirs])
        ui_check = _check(
            "ui_self_contained", "pass" if not ui_problems else "fail",
            "flow.html không tải tài nguyên ngoài và không còn placeholder."
            if not ui_problems else "; ".join(ui_problems[:6]),
            [directory.name for directory in flow_dirs])
        privacy_check = _check(
            "privacy", "pass" if not privacy_problems else "fail",
            "Không có absolute path workstation hay secret-shape trong artifact."
            if not privacy_problems else "; ".join(privacy_problems[:6]),
            [directory.name for directory in flow_dirs])

    checks.extend([graph_check, ui_check, privacy_check])

    symlink_escape = []
    for part in artifact_subdir:
        probe = root
        for name in artifact_subdir:
            probe = probe / name
            if probe.is_symlink():
                target = Path(os.path.realpath(str(probe)))
                if not str(target).startswith(str(root)):
                    symlink_escape.append(probe.name + " -> ngoài repository")
                break
    checks.append(_check(
        "artifact_containment", "pass" if not symlink_escape else "fail",
        "Artifact root không phải symlink ra ngoài repository."
        if not symlink_escape else "; ".join(symlink_escape), []))

    index_status = index_mod.status(root)
    if index_status.get("status") == "missing":
        checks.append(_check("test_mapping", "blocked",
                             "Chưa có index nên chưa đối chiếu được test.", []))
    else:
        with index_mod.connect(root, create=False) as connection:
            index_mod._ensure_schema(connection)
            tests = connection.execute(
                "SELECT COUNT(*) AS c FROM entities WHERE kind = 'test'").fetchone()["c"]
            mappings = connection.execute(
                "SELECT COUNT(*) AS c FROM facts WHERE predicate = 'tested_by'").fetchone()["c"]
            stale = connection.execute(
                "SELECT COUNT(*) AS c FROM facts WHERE confidence = 'stale'").fetchone()["c"]
        checks.append(_check(
            "test_mapping", "pass" if mappings else "partial",
            str(tests) + " test trong index, " + str(mappings) + " quan hệ tested_by; "
            + str(stale) + " fact stale.",
            [index_status.get("index_id", "")]))

    failures = [item for item in checks if item["status"] == "fail"]
    blocked = [item for item in checks if item["status"] == "blocked"]
    static_verdict = "fail" if failures else ("partial" if blocked else "pass")
    gates = {
        "static": static_verdict,
        "ui": "pass" if ui_verified else "blocked",
        "runtime": "pass" if runtime_verified else "blocked",
    }
    if static_verdict == "fail":
        overall_verdict = "fail"
    elif all(value == "pass" for value in gates.values()):
        overall_verdict = "pass"
    else:
        overall_verdict = "partial"
    not_verified = [name for name, value in gates.items() if value != "pass"]
    return {
        "status": "ok",
        "static_verdict": static_verdict,
        "overall_verdict": overall_verdict,
        "verdict": overall_verdict,  # deprecated alias, identical value
        "gates": gates,
        "not_verified": not_verified,
        "repository_name": root.name,
        "source_commit": index_status.get("source_commit", ""),
        "flow_artifacts": len(flow_dirs),
        "checks": checks,
        "ui_verified": bool(ui_verified),
        "runtime_verified": bool(runtime_verified),
        "notes": [
            "static_verdict chỉ nói về những gì đã kiểm tra tại đây: graph, artifact, "
            "quét HTML tĩnh, privacy, test mapping.",
            "ui: " + ("đã xác minh bằng trình duyệt" if ui_verified
                     else "chưa mở trình duyệt — chỉ quét HTML tĩnh"),
            "runtime: " + ("đã chạy test" if runtime_verified
                          else "chưa chạy code/test của repository"),
        ],
        "next_action": (
            "mở flow.html trên trình duyệt và chạy test liên quan để nâng overall_verdict"
            if overall_verdict != "pass" else "không còn gate nào chờ"),
    }


def _graph_problems(directory):
    problems = []
    path = directory / "flow.json"
    if not path.exists():
        return ["thiếu flow.json"]
    try:
        graph = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return ["flow.json không đọc được: " + str(error)]
    outgoing = {}
    for edge in graph.get("edges", []):
        outgoing.setdefault(edge["from"], []).append(edge)
        evidence = edge.get("evidence")
        if evidence == "call":
            technical = edge.get("technical") or ""
            if not re.search(r":\d+", technical):
                problems.append(directory.name + ": cạnh call không có call site")
        if edge["kind"] == "success" and edge["from"].startswith("decision-"):
            pass
    decisions = {node["id"]: node for node in graph.get("nodes", [])
                 if node["type"] == "decision"}
    for decision_id in decisions:
        inbound = [edge for edge in graph.get("edges", []) if edge["to"] == decision_id]
        for edge in inbound:
            source = edge["from"]
            bypass = [other for other in outgoing.get(source, [])
                      if other["to"] != decision_id and other["kind"] == "success"]
            if bypass:
                problems.append(directory.name + ": " + source
                                + " vẫn có cạnh success trực tiếp (bypass " + decision_id + ")")
    for node in graph.get("nodes", []):
        if node["confidence"] == "verified":
            refs = node.get("source_refs") or []
            if not refs or not refs[0].get("start_line"):
                problems.append(directory.name + ": node verified thiếu source_ref "
                                + node["id"])
    for related in (graph.get("meta", {}) or {}).get("related", []):
        if any(node.get("technical") == related["path"] for node in graph.get("nodes", [])):
            problems.append(directory.name + ": file related cũng là node: " + related["path"])
    return problems


def _ui_problems(directory):
    path = directory / "flow.html"
    if not path.exists():
        return ["thiếu flow.html"]
    text = path.read_text(encoding="utf-8", errors="replace")
    problems = []
    if "__FLOW_JSON__" in text:
        problems.append(directory.name + ": còn placeholder __FLOW_JSON__")
    if "http://" in text.replace("http://www.w3.org", ""):
        problems.append(directory.name + ": flow.html tham chiếu http ngoài")
    if re.search(r"<script[^>]+src=", text):
        problems.append(directory.name + ": flow.html tải script ngoài")
    if re.search(r"<link[^>]+href=", text):
        problems.append(directory.name + ": flow.html tải stylesheet ngoài")
    return problems


def _privacy_problems(directory):
    problems = []
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.suffix not in {".json", ".html", ".md"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern, label in ABSOLUTE_PATHS:
            for hit in pattern.finditer(text):
                user = hit.group(1) if hit.groups() else None
                if user and user in PLACEHOLDER_USERS:
                    continue
                problems.append(directory.name + "/" + path.name + ": " + label)
        for pattern in SECRET_SHAPES:
            if pattern.search(text):
                problems.append(directory.name + "/" + path.name + ": secret-shape")
    return problems
