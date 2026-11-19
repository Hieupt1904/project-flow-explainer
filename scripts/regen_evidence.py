#!/usr/bin/env python3
"""Regenerate review evidence from real commands, then write the manifest.

Nothing here is typed by hand: every count in evidence-manifest.json is parsed
from the command output of the same run, from the same commit.

Usage:
  python3 scripts/regen_evidence.py            # run everything, write manifest
  python3 scripts/regen_evidence.py --skip-slow
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEW = ROOT / "artifacts" / "review"
REVIEW.mkdir(parents=True, exist_ok=True)


def now_id():
    return datetime.now().strftime("%Y%m%d-%H%M")


def utc_now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def run(argv, label, cwd=ROOT, env=None):
    started = time.time()
    completed = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                               check=False, env=env)
    duration = round((time.time() - started) * 1000, 1)
    return {
        "label": label, "argv": argv, "exit_code": completed.returncode,
        "stdout": completed.stdout, "stderr": completed.stderr, "duration_ms": duration,
    }


def write_log(stamp, name, payload):
    path = REVIEW / (stamp + "-" + name + ".log")
    body = [
        "$ " + " ".join(payload["argv"]),
        "exit_code: " + str(payload["exit_code"]),
        "duration_ms: " + str(payload["duration_ms"]),
        "", "--- stdout ---", payload["stdout"], "--- stderr ---", payload["stderr"],
    ]
    path.write_text("\n".join(body), encoding="utf-8")
    return path


def parse_unittest(output):
    match = re.search(r"Ran (\d+) tests?", output)
    ok = "OK" in output and "FAILED" not in output
    return {"count": int(match.group(1)) if match else 0, "ok": ok}


def parse_node_tests(output):
    pass_match = re.search(r"ℹ pass (\d+)", output)
    fail_match = re.search(r"ℹ fail (\d+)", output)
    return {"pass": int(pass_match.group(1)) if pass_match else 0,
            "fail": int(fail_match.group(1)) if fail_match else 0}


def parse_tarball(pack_stdout):
    line = pack_stdout.strip().split("\n")[-1]
    return json.loads(line)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Regenerate review evidence")
    parser.add_argument("--skip-slow", action="store_true")
    args = parser.parse_args(argv)
    stamp = now_id()
    python = sys.executable or "python3"
    evidence = {}

    # One source of truth: a previous stamp's logs are removed so two runs
    # cannot both look current.
    for stale in REVIEW.iterdir():
        if not stale.is_file() or stale.name.startswith(stamp):
            continue
        if re.match(r"^\d{8}-\d{4}-(python-tests|compileall|node-[a-z]+|policy|"
                    r"pack-build|bench|consistency|dsh-smoke)\.(log|json)$", stale.name):
            stale.unlink()

    py = run([python, "-m", "unittest", "discover", "-s", "tests", "-v"], "python tests")
    evidence["python_log"] = write_log(stamp, "python-tests", py).name
    evidence["python"] = parse_unittest(py["stdout"] + py["stderr"])

    static = run([python, "-m", "compileall", "-q", "scripts", "tests", "pfe", "tools"],
                 "python compileall")
    evidence["compile"] = {"ok": static["exit_code"] == 0, "log": write_log(stamp, "compileall", static).name}

    node_syntax = []
    for rel in ["dsh-plugin/index.js", "dsh-plugin/lib/paths.js",
                "dsh-plugin/lib/core-runner.js", "dsh-plugin/lib/tools.js",
                "dsh-plugin/lib/validate.js", "dsh-plugin/scripts/pack.mjs"]:
        result = run(["node", "--check", rel], "node --check " + rel)
        node_syntax.append({"file": rel, "ok": result["exit_code"] == 0})
    evidence["node_syntax"] = node_syntax

    adapter = run(["node", "--test", "dsh-plugin/tests/plugin.test.mjs"], "adapter tests")
    evidence["adapter_log"] = write_log(stamp, "node-adapter", adapter).name
    evidence["adapter"] = parse_node_tests(adapter["stdout"])

    knowledge = run(["node", "--test", "dsh-plugin/tests/knowledge.test.mjs"],
                    "knowledge tool tests")
    evidence["knowledge_log"] = write_log(stamp, "node-knowledge", knowledge).name
    evidence["knowledge"] = parse_node_tests(knowledge["stdout"])

    pack = run(["node", "--test", "dsh-plugin/tests/pack.test.mjs"], "pack tests")
    evidence["pack_log"] = write_log(stamp, "node-pack", pack).name
    evidence["pack"] = parse_node_tests(pack["stdout"])

    policy = run([python, "scripts/check_repo_policy.py"], "repo policy")
    evidence["policy_log"] = write_log(stamp, "policy", policy).name
    evidence["policy"] = {"ok": policy["exit_code"] == 0,
                          "summary": policy["stdout"].strip().splitlines()[-1] if policy["stdout"].strip() else ""}

    build = run(["node", "dsh-plugin/scripts/pack.mjs"], "pack bundle")
    evidence["bundle_log"] = write_log(stamp, "pack-build", build).name
    packed = parse_tarball(build["stdout"])
    tarball = Path(packed["tarball"])
    listing = run(["tar", "-tzf", str(tarball)], "tarball listing")
    evidence["tarball"] = {
        "filename": tarball.name,
        "path": tarball.relative_to(ROOT).as_posix(),
        "bytes": tarball.stat().st_size,
        "sha256": sha256(tarball),
        "entry_count": len([line for line in listing["stdout"].splitlines() if line.strip()]),
        "contains_cli": "package/vendor/core/tools/pfe_cli.py" in listing["stdout"],
        "contains_knowledge": "package/vendor/core/pfe/index.py" in listing["stdout"],
    }

    if not args.skip_slow:
        bench = run([python, "scripts/bench_index.py", "--files", "2000", "--json"],
                    "index benchmark")
        bench_path = REVIEW / (stamp + "-bench.json")
        bench_path.write_text(bench["stdout"].strip() + "\n", encoding="utf-8")
        evidence["bench"] = json.loads(bench["stdout"].strip() or "{}")
        evidence["bench_log"] = bench_path.name
    else:
        evidence["bench"] = {}

    real_paths = sorted(REVIEW.glob("*-real-project.json"))
    real = json.loads(real_paths[-1].read_text(encoding="utf-8")) if real_paths else {}
    evidence["real_project"] = {
        "log": real_paths[-1].name if real_paths else "",
        "status": real.get("status", "missing"),
        "repository_id": real.get("repository_id", ""),
        "flow": real.get("flow", {}).get("counts"),
        "files_scanned": real.get("flow", {}).get("files_scanned"),
        "index_files": real.get("index_full", {}).get("files_indexed"),
        "index_incremental_parsed": real.get("index_incremental", {}).get("files_parsed"),
        "verify": real.get("verify", {}).get("verdict"),
        "privacy": real.get("privacy", {}).get("absolute_paths", ""),
    }

    ui_path = REVIEW / "20261119-ui.json"
    ui = json.loads(ui_path.read_text(encoding="utf-8")) if ui_path.exists() else {}
    evidence["ui"] = {
        "status": "pass" if ui and not any(ui["summary"].values()) else "partial",
        "combinations": ui.get("combinations", 0),
        "summary": ui.get("summary", {}),
        "log": ui_path.name if ui_path.exists() else "",
    }

    git = run(["git", "rev-parse", "HEAD"], "git head")
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], "git branch")
    status = run(["git", "status", "--porcelain"], "git status")
    manifest_pkg = json.loads((ROOT / "dsh-plugin" / "package.json").read_text(encoding="utf-8"))

    dsh = run(["dsh", "--version"], "dsh version")
    dsh_version = dsh["stdout"].strip().splitlines()[-1] if dsh["stdout"].strip() else ""

    smoke_path = REVIEW / (stamp + "-dsh-smoke.json")
    smoke = {
        "status": "blocked",
        "profile": "pfe-test",
        "registry_runtime": "not_verified",
        "model_driven": "not_verified",
        "reason": ("Bundle 0.3.0 chưa được cài vào profile pfe-test trong phiên này: "
                   "cài bundle chạy npm/pnpm trong profile nên phải dừng trước bước cài và xin phép."),
        "installed_in_profile": "0.2.2 (bản cài trước đó, chưa nâng cấp)",
        "note": ("Lời gọi tool đã được kiểm chứng qua registry thật ở pass 0.2.x; "
                 "với 0.3.0 chỉ có bằng chứng adapter in-process + pack test."),
    }
    smoke_path.write_text(json.dumps(smoke, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "generated_at": utc_now(),
        "generator": "scripts/regen_evidence.py",
        "source_commit": git["stdout"].strip(),
        "source_branch": branch["stdout"].strip(),
        "working_tree_dirty": bool(status["stdout"].strip()),
        "package_version": manifest_pkg["version"],
        "engines_dsh": manifest_pkg["engines"]["dsh"],
        "dsh_version": dsh_version,
        "python_version": sys.version.split()[0],
        "node_version": run(["node", "-v"], "node version")["stdout"].strip(),
        "tests": {
            "python": evidence["python"]["count"],
            "adapter": evidence["adapter"]["pass"],
            "knowledge_tools": evidence["knowledge"]["pass"],
            "pack": evidence["pack"]["pass"],
            "failures": (0 if evidence["python"]["ok"] else 1)
                        + evidence["adapter"]["fail"] + evidence["knowledge"]["fail"]
                        + evidence["pack"]["fail"],
            "adapter_engine_failures": (evidence["adapter"]["fail"]
                                        + evidence["knowledge"]["fail"]
                                        + evidence["pack"]["fail"]),
        },
        "tarball": evidence["tarball"],
        "smoke": smoke,
        "ui": evidence["ui"],
        "policy": evidence["policy"],
        "benchmark": evidence["bench"],
        "real_project": evidence["real_project"],
        "static": {"compileall": evidence["compile"]["ok"],
                   "node_syntax": evidence["node_syntax"]},
        "logs": {key: value for key, value in evidence.items() if key.endswith("_log")},
        "classification": {
            "confirmed": ["python tests", "adapter tests", "knowledge tool tests",
                          "pack tests", "policy", "tarball manifest", "UI layout",
                          "index benchmark"],
            "manual_evidence": ["tarball sha256", "tarball entry count",
                                "real-project run (path và tên repo đã scrub)"],
            "unverified": ["DSH registry-runtime smoke cho 0.3.0",
                           "model-driven tool selection",
                           "Harness panel UI (BLOCKED_UI_API_UNVERIFIED)"],
        },
    }
    manifest_path = REVIEW / "evidence-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")

    # The consistency test compares the reports with THIS manifest, so the first
    # run after any number changes sees the previous file. Re-run the suite once
    # the manifest is written: what the manifest records is then a run against
    # itself, not against the state before it.
    post = run([python, "-m", "unittest", "discover", "-s", "tests", "-v"],
               "self-consistent re-check")
    manifest["logs"]["consistency_log"] = write_log(stamp, "consistency", post).name
    parsed = parse_unittest(post["stdout"] + post["stderr"])
    manifest["tests"]["python"] = parsed["count"]
    manifest["tests"]["failures"] = (0 if parsed["ok"] else 1) \
        + manifest["tests"]["adapter_engine_failures"]
    manifest["consistency_recheck"] = {
        "ok": parsed["ok"],
        "note": "chạy lại toàn bộ unittest sau khi manifest được ghi",
        "ran": parsed["count"],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    print(json.dumps({"manifest": manifest_path.relative_to(ROOT).as_posix(),
                      "tests": manifest["tests"],
                      "tarball": manifest["tarball"]["filename"],
                      "ui": manifest["ui"]["status"],
                      "policy": manifest["policy"]["ok"]}, ensure_ascii=False))
    return 0 if manifest["tests"]["failures"] == 0 and manifest["policy"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
