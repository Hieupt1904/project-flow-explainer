#!/usr/bin/env python3
"""Model-driven release smoke (PHASE 0.6.6).

Runs one real model session against a synthetic fixture and records what the model
actually did — not what it said. Every field is captured from the runtime, so the
manifest can attribute the result to one build.

What it proves
  the model chose the documented workflow order (context_pack -> impact ->
  verify) on its own, through the real DSH registry, and the tool calls
  succeeded with the schema the adapter declares.

What it does not prove
  that the answer text is good. Wording is not checked: only whether the right
  tools ran, in an acceptable order, with results that satisfied their schema.

Attribution
  A record is only evidence for the build it ran on, so the record carries
  package_version and tarball_sha256. `regen_evidence.py` refuses any record
  whose hash or version does not match the release being described.

Usage
  python3 scripts/run_model_smoke.py [--json]
Needs
  DEEPSEEK_API_KEY (credentials store or env), the pfe-model profile, and the
  packed tarball for the current version. No private source is sent: the fixture
  is a synthetic shop app that lives in the repository.
"""

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEW = ROOT / "artifacts" / "review"
FIXTURE_SRC = ROOT / "tests" / "fixtures" / "shop-app"
PROFILE = "pfe-model"
PACKAGE = "dsh-project-flow-explainer"

# The documented order for "understand before you edit". Extra calls are allowed
# between them; the check is that each expected tool ran and their first
# occurrences are non-decreasing in this order.
EXPECTED_ORDER = ["project_context_pack", "project_impact_analysis", "project_verify_flow"]

FIXTURE_RUN = Path(tempfile.gettempdir()) / "mds-fixture"
PROMPT = (
    "Bạn đang kiểm tra một repository mẫu. Hãy làm đúng ba bước, dùng tool của plugin "
    "project-flow-explainer, và không đọc source bằng tay:\n"
    "1. Gom context trước khi sửa cho file services/report_service.js.\n"
    "2. Phân tích tác động sau khi sửa đúng file đó.\n"
    "3. Kiểm tra artifact/flow của repository.\n"
    "Repository: {repo}\n"
    "Trả lời ngắn: mỗi bước đã gọi tool nào và kết quả chính là gì."
)


def utc_now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(argv, timeout=600, env=None):
    started = time.time()
    completed = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True,
                               env={**os.environ, **(env or {})}, timeout=timeout,
                               check=False)
    return {
        "argv": argv,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "duration_ms": round((time.time() - started) * 1000, 1),
    }


def installed_version():
    """Version of the plugin actually loaded from the profile's node_modules."""
    package = (Path.home() / ".dsh" / "profiles" / PROFILE / "node_modules"
               / PACKAGE / "package.json")
    if not package.exists():
        return ""
    try:
        return json.loads(package.read_text(encoding="utf-8")).get("version", "")
    except (ValueError, OSError):
        return ""


def event_data(event):
    """`data` is a Python-repr string in older logs and a dict in newer ones."""
    data = event.get("data")
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        try:
            parsed = ast.literal_eval(data)
        except (ValueError, SyntaxError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def session_marker():
    """A token unique to this run, so the right session log is identified.

    Picking "the newest session with a project_ call" selected the agent's own
    session and produced an order that belonged to a different conversation.
    The marker rides inside the prompt and is only ever written by this run.
    """
    return "PFE-SMOKE-" + hashlib.sha256(
        (str(time.time()) + str(os.getpid())).encode("utf-8")).hexdigest()[:16]


def find_session(started, marker):
    """Locate the session log that contains this run's marker."""
    candidates = sorted((Path.home() / ".dsh" / "sessions").glob("*/*/session.v4.jsonl.zstd"),
                        key=lambda item: item.stat().st_mtime, reverse=True)
    for path in candidates[:40]:
        if path.stat().st_mtime < started - 30:
            continue
        raw = run(["zstdcat", str(path)], timeout=180)
        if raw["exit_code"] != 0:
            continue
        if marker in raw["stdout"]:
            return path, raw["stdout"]
    return None, ""


def tool_sequence(log_text):
    """Ordered project_* dispatches read from real `tool/call` events.

    Scanning the raw text for tool names counts the catalogue listing as a call;
    reading the structured event is the only honest way to know what ran.
    """
    sequence = []
    for line in log_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "tool/call":
            continue
        data = event_data(event)
        name = data.get("name") or ""
        if not name.startswith("project_"):
            continue
        sequence.append({"tool": name, "step": data.get("step"), "call": data.get("callId")})
    return sequence


def tool_outcomes(log_text):
    """Error codes per call id, taken from `tool/result` events."""
    outcomes = {}
    for line in log_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "tool/result":
            continue
        data = event_data(event)
        message = data.get("message") or {}
        call = data.get("callId") or message.get("toolCallId")
        if not call:
            continue
        # The error signal lives on the message, not in the JSON text: a schema
        # rejection is `isError: true` plus an `error` field. Searching the
        # serialized payload for a phrase reported every failure as success.
        failed = bool(data.get("error")) or message.get("isError") is True
        outcomes[call] = "error" if failed else "ok"
        if failed:
            content = message.get("content") or [{}]
            text = str(content[0].get("text") or "") if content else ""
            outcomes[call + ":detail"] = text[:300]
    return outcomes


def check_order(sequence):
    """Expected tools present, first occurrences in the documented order."""
    names = [item["tool"] for item in sequence]
    first_index = {}
    for index, name in enumerate(names):
        first_index.setdefault(name, index)
    missing = [name for name in EXPECTED_ORDER if name not in first_index]
    positions = [first_index[name] for name in EXPECTED_ORDER if name in first_index]
    ordered = positions == sorted(positions)
    return {"missing": missing, "ordered": ordered, "observed": names}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Model-driven release smoke")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    manifest_path = REVIEW / "evidence-manifest.json"
    if not manifest_path.exists():
        print("chưa có evidence-manifest.json", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = manifest["package_version"]
    tarball = ROOT / "dist" / (PACKAGE + "-" + version + ".tgz")
    if not tarball.exists():
        print("thiếu tarball: " + str(tarball), file=sys.stderr)
        return 1

    # Attribution guard: the profile may hold a different build than the one the
    # manifest describes (a repack without a reinstall, or the reverse). A record
    # naming a tarball the session never loaded is worse than no record, so stop.
    installed = installed_version()
    if installed != version:
        print("profile " + PROFILE + " đang cài " + (installed or "<không rõ>")
              + " nhưng manifest nói " + version
              + " — cài đúng bản trước khi chạy smoke model.", file=sys.stderr)
        return 1

    record = {
        "generated_at": utc_now(),
        "kind": "model-session",
        "package_version": version,
        "installed_version": installed_version(),
        "tarball_sha256": sha256_file(tarball),
        "requested_profile": PROFILE,
        "provider": "deepseek",
        "model": "deepseek-flash",
        "prompt_sha256": sha256_text(PROMPT),
        "fixture": "tests/fixtures/shop-app",
    }

    marker = session_marker()
    prompt = PROMPT.format(repo=str(FIXTURE_RUN)) + "\nMã phiên: " + marker
    started = time.time()
    result = run(["dsh", "--profile", PROFILE, prompt], timeout=900)
    record["wall_seconds"] = round(time.time() - started, 1)
    record["exit_code"] = result["exit_code"]
    record["stderr_tail"] = result["stderr"][-400:]
    record["stop_reason"] = ("error" if result["exit_code"] != 0 else "completed")

    if "MISSING_CREDENTIAL" in result["stderr"]:
        record["status"] = "blocked"
        record["blocked"] = "MISSING_CREDENTIAL: profile chưa có credential cho route"
        REVIEW.mkdir(parents=True, exist_ok=True)
        path = REVIEW / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-model-session.json")
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        print(json.dumps({"status": "blocked", "record": path.name}, ensure_ascii=False))
        return 2

    session_path, log_text = find_session(started, marker)
    sequence = tool_sequence(log_text)
    outcomes = tool_outcomes(log_text)
    for item in sequence:
        item["outcome"] = outcomes.get(item.get("call"), "unknown")
    order = check_order(sequence)

    record["session_file"] = session_path.name if session_path is not None else ""
    record["session_sha256"] = sha256_file(session_path) if session_path is not None else ""
    record["selected_tools"] = [item["tool"] for item in sequence]
    record["tool_sequence"] = sequence
    record["order"] = order
    record["prompt_sha256"] = sha256_text(prompt)
    record["session_marker"] = marker
    record["answer_excerpt"] = result["stdout"].strip()[:800]

    # Policy: the tools are read-mostly; a verify call must not be the only one,
    # and no tool may report an error code in the captured sequence.
    errors = [item["tool"] for item in sequence if item.get("outcome") == "error"]
    record["policy"] = {
        "tool_errors": errors,
        "expected_tools_ran": not order["missing"],
        "order_respected": order["ordered"],
    }

    schema_ok = not errors and not order["missing"] and order["ordered"]
    record["status"] = "verified" if schema_ok else "partial"
    if not schema_ok:
        reasons = []
        if order["missing"]:
            reasons.append("thiếu tool: " + ", ".join(order["missing"]))
        if not order["ordered"]:
            reasons.append("thứ tự không đúng: " + " -> ".join(order["observed"]))
        if errors:
            reasons.append("tool lỗi: " + ", ".join(errors))
        record["blocked"] = "; ".join(reasons)

    REVIEW.mkdir(parents=True, exist_ok=True)
    path = REVIEW / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-model-session.json")
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        "status": record["status"],
        "record": path.name,
        "package_version": version,
        "installed_version": installed_version(),
        "tarball_sha256": record["tarball_sha256"][:12],
        "tools": record["selected_tools"],
        "order_ok": order["ordered"],
        "missing": order["missing"],
        "wall_seconds": record["wall_seconds"],
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if record["status"] == "verified" else 2


if __name__ == "__main__":
    sys.exit(main())
