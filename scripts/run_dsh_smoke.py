#!/usr/bin/env python3
"""Registry-runtime smoke for the DSH plugin.

What this proves (and what it does not):

  proves   the released tarball installs into a real profile, its 7 tools are in
           the real Tool registry, and each tool executes through that registry;
           policy codes, abort identity and timeout mapping survive the runtime;
           a disabled row removes the tools.
  does not prove model selection: the profile has no API key, so no model call
           happens. That stays BLOCKED_DSH_SMOKE / model_driven=not_verified.

The probe bundle lives in smoke/dsh-probe, is installed temporarily and removed
in a finally block. Profile "web" is never touched.

Usage:
  python3 scripts/run_dsh_smoke.py [--keep-probe] [--json]
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEW = ROOT / "artifacts" / "review"
PROBE = ROOT / "smoke" / "dsh-probe"
PROFILE = "pfe-test"
PACKAGE = "dsh-project-flow-explainer"      # npm package name
ROW_ID = "project-flow-explainer"            # loader row id targeted by overlays
EXPECTED = [
    "project_flow_explain", "project_code_index", "project_code_search",
    "project_context_pack", "project_impact_analysis", "project_verify_flow",
    "project_knowledge_refresh",
]


def run(argv, env=None, timeout=180, cwd=ROOT):
    started = time.time()
    completed = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                               env={**__import__("os").environ, **(env or {})},
                               timeout=timeout, check=False)
    return {
        "argv": argv, "exit_code": completed.returncode,
        "stdout": completed.stdout, "stderr": completed.stderr,
        "duration_ms": round((time.time() - started) * 1000, 1),
    }


def scrub(value, work):
    """Remove workstation paths before the record is committed.

    The raw command output is useful evidence, but it must not carry /home,
    /tmp working directories or the repository path into the public repo.
    """
    replacements = [
        (str(ROOT), "<repo>"),
        (str(work), "<work>"),
        (str(Path.home()), "<home>"),
    ]
    if isinstance(value, str):
        text = value
        for old, new in replacements:
            text = text.replace(old, new)
        text = __import__("re").sub(r"/tmp/[A-Za-z0-9._-]+", "<tmp>", text)
        text = __import__("re").sub(r"/home/[A-Za-z0-9._-]+", "<home>", text)
        text = __import__("re").sub(r"/Users/[A-Za-z0-9._-]+", "<user>", text)
        return text
    if isinstance(value, list):
        return [scrub(item, work) for item in value]
    if isinstance(value, dict):
        return {key: scrub(item, work) for key, item in value.items()}
    return value


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dsh(*args, **kwargs):
    return run(["dsh", *args], **kwargs)


def write_overlay(path, body):
    path.write_text(body, encoding="utf-8")


def call_result(record, label):
    call = (record.get("calls") or {}).get(label) or {}
    value = call.get("value") or {}
    return {
        "ok": bool(call.get("ok")),
        "code": call.get("code") or "",
        "error_name": call.get("name") or "",
        "status": value.get("status") or "",
        "overall_verdict": value.get("overall_verdict") or "",
        "registered": len(record.get("registered_tools") or []),
        "missing": record.get("missing_tools") or [],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="DSH registry-runtime smoke")
    parser.add_argument("--keep-probe", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    manifest = json.loads((ROOT / "dsh-plugin" / "package.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    tarball = ROOT / "dist" / f"dsh-project-flow-explainer-{version}.tgz"
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "profile": PROFILE,
        "package_version": version,
        "engines_dsh": manifest["engines"]["dsh"],
        "tarball": tarball.name,
        "tarball_sha256": sha256(tarball) if tarball.exists() else "",
        "expected_tools": EXPECTED,
        "steps": {},
        "blocked": {
            "model_driven": "not_verified: profile không có API key; probe gọi registry, không qua model",
            "panel_ui": "BLOCKED_UI_API_UNVERIFIED",
        },
        "status": "running",
    }
    work = Path(tempfile.mkdtemp(prefix="pfe-smoke-"))
    installed_probe = False
    try:
        if not tarball.exists():
            raise SystemExit("thiếu tarball: " + str(tarball))
        report["install"] = run(["dsh", "plugin", "--profile", PROFILE, "add", str(tarball)])
        # A re-run against an already-installed bundle exits non-zero; what
        # matters is that the row composes, which is checked below.
        report["install_already_present"] = "already" in (
            report["install"]["stdout"] + report["install"]["stderr"]).lower()
        report["probe_install"] = run(["dsh", "plugin", "--profile", PROFILE, "add", str(PROBE)])
        installed_probe = report["probe_install"]["exit_code"] == 0

        repo = work / "repo"
        shutil.copytree(ROOT / "tests" / "fixtures" / "shop-app", repo,
                        ignore=shutil.ignore_patterns("artifacts", ".pfe", "__pycache__"))
        (repo / ".env").write_text("API_KEY=fixture-secret-value-abc123\n", encoding="utf-8")
        report["prebuild_index"] = run([sys.executable, str(ROOT / "tools" / "pfe_cli.py"),
                                        "index", "--repo", str(repo), "--mode", "full"])

        overlays = {
            "normal": f"- id: {ROW_ID}\n  config:\n    allowedRoots:\n      - {work}\n"
                      "    timeoutMs: 120000\n",
            "empty": f"- id: {ROW_ID}\n  config:\n    allowedRoots: []\n    timeoutMs: 120000\n",
            "timeout": f"- id: {ROW_ID}\n  config:\n    allowedRoots:\n      - {work}\n"
                       "    timeoutMs: 1\n",
            "disabled": f"- id: {ROW_ID}\n  disabled: true\n",
            # A wrong type must be rejected by the native Config schema before
            # the tools mount at all.
            "invalid": f"- id: {ROW_ID}\n  config:\n    allowedRoots: \"oops\"\n",
        }
        for name, body in overlays.items():
            write_overlay(work / f"overlay-{name}.yml", body)

        report["composed_config"] = dsh("--profile", PROFILE, "--patch",
                                        str(work / "overlay-normal.yml"), "--dump-config")
        composed = report["composed_config"]["stdout"] or ""
        report["row_present"] = ROW_ID in composed
        report["overlay_applied"] = str(work) in composed
        if not report["row_present"] or not report["overlay_applied"]:
            raise SystemExit("plugin row/overlay not composed; refusing to run smoke")
        report["disabled_config"] = dsh("--profile", PROFILE, "--patch",
                                        str(work / "overlay-disabled.yml"), "--dump-config")

        batches = [
            ("a", "flow,context", "normal", 4000),
            ("b", "impact,verify", "normal", 4000),
            ("c", "search,outsideRoots,malformed,aborted", "normal", 4000),
            ("d", "flow", "empty", 4000),
            ("e", "flow", "timeout", 4000),
            ("f", "", "disabled", 300),
            ("g", "flow", "invalid", 2500),
        ]
        for key, steps, overlay, wait in batches:
            out = work / f"probe-{key}.json"
            result = dsh("--profile", PROFILE, "--patch", str(work / f"overlay-{overlay}.yml"),
                         "smoke",
                         env={"PFE_PROBE_OUT": str(out), "PFE_PROBE_STEPS": steps,
                              "PFE_PROBE_REPO": str(repo),
                              "PFE_PROBE_WAIT_MS": str(wait)},
                         timeout=180)
            record = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
            report["steps"][key] = {
                "overlay": overlay, "steps": steps,
                "boot_exit": result["exit_code"],
                "stderr": result["stderr"],
                "credential_error": "MISSING_CREDENTIAL" in result["stderr"],
                "probe": record,
            }

        a = report["steps"]["a"]["probe"]
        b = report["steps"]["b"]["probe"]
        c = report["steps"]["c"]["probe"]
        d = report["steps"]["d"]["probe"]
        e = report["steps"]["e"]["probe"]
        f = report["steps"]["f"]["probe"]
        g = report["steps"]["g"]["probe"]
        checks = {
            "tools_registered": len(a.get("registered_tools") or []) >= len(EXPECTED),
            "no_missing_tools": not (a.get("missing_tools") or []),
            "flow_ok": call_result(a, "flow")["status"] == "ok",
            "context_ok": call_result(a, "context")["ok"],
            "impact_ok": call_result(b, "impact")["ok"],
            "verify_ok": call_result(b, "verify")["ok"],
            "verify_partial_or_pass": call_result(b, "verify")["overall_verdict"] in {"partial", "pass"},
            "search_ok": call_result(c, "search")["ok"],
            "outside_roots_rejected": call_result(c, "outsideRoots")["code"] == "repository_outside_allowed_roots",
            "malformed_rejected": call_result(c, "malformed")["code"] == "flow_request_missing",
            "abort_identity": call_result(c, "aborted")["error_name"] == "AbortError",
            "empty_roots_rejected": call_result(d, "flow")["code"] == "allowed_roots_unconfigured",
            "timeout_code": call_result(e, "flow")["code"] == "core_timeout",
            "disabled_hides_tools": not any(
                name.startswith("project_") for name in (f.get("registered_tools") or [])),
            # The native schemastery Config rejects a wrong type at mount time.
            "invalid_config_rejected": (
                "ValidationError" in (report["steps"]["g"]["stderr"] or "")
                and not any(name.startswith("project_")
                            for name in (report["steps"]["g"]["probe"].get("registered_tools") or []))),
        }
        # Informational, not a gate: the generated Settings page only lists
        # entries whose volatile fields project through the loader's own
        # schemastery instance. Measured behaviour is recorded instead of
        # pretending the page exists.
        descriptor = (a.get("settings") or {})
        report["settings_page"] = {
            "auto_generated": bool(descriptor.get("present") and descriptor.get("auto_generate")),
            "reason": ("entry absent from settings.describe()" if not descriptor.get("present")
                       else "listed"),
            "namespaces_seen": descriptor.get("count"),
            "ui_provided_by": "client card in plugins.bundle.config",
        }
        report["checks"] = checks
        report["tool_count"] = len(a.get("registered_tools") or [])
        report["status"] = "verified" if all(checks.values()) else "partial"
        if all(checks.values()):
            report["registry_runtime"] = "verified"
        else:
            report["registry_runtime"] = "partial"
    except Exception as error:  # noqa: BLE001 - evidence must record the failure
        report["status"] = "error"
        report["error"] = type(error).__name__ + ": " + str(error)
        report["registry_runtime"] = "not_verified"
    finally:
        if installed_probe and not args.keep_probe:
            report["probe_remove"] = run(["dsh", "plugin", "--profile", PROFILE, "remove", "pfe-smoke-probe"])
        report["cleanup"] = {"probe_removed": installed_probe and not args.keep_probe,
                             "profile_patch_touched": False}
        shutil.rmtree(work, ignore_errors=True)

    report = scrub(report, work)
    REVIEW.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = REVIEW / (stamp + "-dsh-smoke.json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "record": path.relative_to(ROOT).as_posix(),
        "status": report["status"],
        "tool_count": report.get("tool_count", 0),
        "registry_runtime": report.get("registry_runtime"),
        "checks": report.get("checks", {}),
    }
    if args.as_json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        for key, value in summary.items():
            print(f"{key}: {value}")
    return 0 if report["status"] == "verified" else 1


if __name__ == "__main__":
    sys.exit(main())