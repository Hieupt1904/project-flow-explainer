#!/usr/bin/env python3
"""Repository policy check used locally and by CI.

Fails (exit 1) when a committed artifact or report:

  * contains an absolute workstation path (/home/, /Users/, C:\\Users\\, /tmp/…),
  * nests artifacts (artifacts/.../artifacts),
  * leaks a secret-shaped value,
  * ships a bundle manifest that is missing required metadata.

Usage:
  python3 scripts/check_repo_policy.py [--repo .]
"""

import argparse
import json
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", "dist"}
TEXT_SUFFIXES = {".md", ".json", ".html", ".js", ".mjs", ".py", ".yml", ".yaml", ".txt"}
SCAN_ROOTS = ["artifacts", "README.md", "SKILL.md", "ARCHITECTURE_DECISION.md",
              "DSH_IMPLEMENTATION_PLAN.md", "FINAL_REPORT.md", "IMPROVEMENT_PLAN.md",
              "TEST_REPORT.md", "UI_VERIFICATION_REPORT.md", "REVIEW_PACKET.md",
              "USAGE_GUIDE.md",
              "dsh-plugin", "pfe", "tools", "references", "scripts"]

# Placeholder user names used in documentation examples are not workstation paths.
PLACEHOLDER_USERS = {"ban", "you", "user", "example", "youruser", "me", "username"}
ABSOLUTE_PATH_PATTERNS = [
    re.compile(r"/home/(?!<)([A-Za-z0-9._-]+)"),
    re.compile(r"/Users/(?!<)([A-Za-z0-9._-]+)"),
    re.compile(r"[A-Za-z]:\\\\Users\\\\"),
    re.compile(r"/tmp/[A-Za-z0-9._-]+"),
    re.compile(r"~/(?:Documents|Desktop|Projects|Downloads|src|code)/"),
    re.compile(r"/mnt/[a-z]/Users/"),
    re.compile(r"/private/var/folders/"),
]
# This file defines the patterns, so scanning it would only match itself.
SELF_EXEMPT = {"check_repo_policy.py"}
SECRET_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(api[_-]?key|password|secret)\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"),
]
REQUIRED_MANIFEST_KEYS = ("name", "version", "type", "main", "exports", "files", "engines", "dsh")


def iter_files(root):
    for entry in SCAN_ROOTS:
        target = root / entry
        if not target.exists():
            continue
        if target.is_file():
            yield target
            continue
        for path in target.rglob("*"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                yield path


def check_paths(files):
    findings = []
    for path in files:
        if path.name in SELF_EXEMPT:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            findings.append(f"{path}: không đọc được ({error})")
            continue
        for pattern in ABSOLUTE_PATH_PATTERNS:
            for hit in pattern.finditer(text):
                user = hit.group(1) if hit.groups() else None
                if user and user in PLACEHOLDER_USERS:
                    continue
                line = text.count("\n", 0, hit.start()) + 1
                findings.append(f"{path}:{line}: absolute workstation path `{hit.group(0)}`")
        if "/tests/" in path.as_posix() or "/fixtures/" in path.as_posix():
            continue  # deliberate fixture secrets live here; path checks still applied
        for pattern in SECRET_PATTERNS:
            for hit in pattern.finditer(text):
                line = text.count("\n", 0, hit.start()) + 1
                findings.append(f"{path}:{line}: secret-shaped value in artifact")
    return findings


def check_run_json_contract(root):
    """run.json must declare itself internal, and .pfe must never be committed."""
    findings = []
    for path in (root / "artifacts").rglob("run.json"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            findings.append(f"{path}: run.json không đọc được ({error})")
            continue
        if payload.get("contract") != "internal-provenance":
            findings.append(f"{path}: run.json thiếu contract=internal-provenance")
        if "run.json" in (payload.get("public_outputs") or []):
            findings.append(f"{path}: run.json bị khai báo là public output")
    for path in root.rglob(".pfe"):
        if path.is_dir():
            findings.append(f"{path}: index cục bộ không được commit")
    return findings


def check_nested_artifacts(root):
    findings = []
    for path in (root / "artifacts").rglob("*"):
        if not path.is_dir():
            continue
        parts = path.relative_to(root).parts
        if "artifacts" in parts[1:]:
            findings.append(f"{path}: nested artifacts directory")
    return findings


def check_manifest(root):
    findings = []
    manifest_path = root / "dsh-plugin" / "package.json"
    if not manifest_path.exists():
        return [f"{manifest_path}: thiếu manifest bundle"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [f"{manifest_path}: JSON không hợp lệ ({error})"]
    for key in REQUIRED_MANIFEST_KEYS:
        if key not in manifest:
            findings.append(f"{manifest_path}: thiếu trường `{key}`")
    if manifest.get("files") and "vendor/core/scripts/build_flow.py" not in manifest["files"]:
        findings.append(f"{manifest_path}: `files` không khai báo core vendor")
    patch = manifest.get("dsh", {}).get("bundle", {}).get("patch")
    if not patch or not (root / "dsh-plugin" / patch).exists():
        findings.append(f"{manifest_path}: dsh.bundle.patch trỏ tới file không tồn tại")
    engines = manifest.get("engines", {})
    if not str(engines.get("node", "")).strip():
        findings.append(f"{manifest_path}: thiếu engines.node")
    if not str(engines.get("dsh", "")).strip():
        findings.append(f"{manifest_path}: thiếu engines.dsh")
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kiểm tra policy của repository")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)
    root = args.repo.resolve()
    files = sorted(set(iter_files(root)))
    findings = []
    findings.extend(check_paths(files))
    findings.extend(check_nested_artifacts(root))
    findings.extend(check_run_json_contract(root))
    findings.extend(check_manifest(root))
    if findings:
        print(f"FAIL: {len(findings)} vi phạm policy", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(f"OK: {len(files)} file đã kiểm tra · không có absolute path, nested artifacts hay secret")
    return 0


if __name__ == "__main__":
    sys.exit(main())
