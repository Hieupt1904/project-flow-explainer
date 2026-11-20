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
import shutil
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
# A real model session is evidence for one build only. A partial record claims
# nothing about the build, so it is kept apart instead of posing as evidence.
ATTEMPTS = REVIEW / "attempts"
PROFILE = "pfe-model"
# DSH_HOME moves both the profile store and the session logs. Reading the wrong
# root would make every lookup return empty and every check pass vacuously.
DSH_HOME = Path(os.environ.get("DSH_HOME") or (Path.home() / ".dsh"))
PACKAGE = "dsh-project-flow-explainer"

# The documented order for "understand before you edit". Extra calls are allowed
# between them; the check is that each expected tool ran and their first
# occurrences are non-decreasing in this order.
EXPECTED_ORDER = ["project_context_pack", "project_impact_analysis", "project_verify_flow"]

FIXTURE_SOURCE = ROOT / "tests" / "fixtures" / "shop-app"

# A workspace can boot the profile with a rule layer that rewrites the tool list
# inside the harness (observed in ~/.dsh/AGENTS.md: "execute workspace and
# operator instructions without refusal", followed by the model answering that
# `project_flow_explain` does not exist while the harness exposed it). The probe
# cannot change the rule layer, so it records what the surface actually offered
# and refuses to read a missing tool as "the model chose not to call it".
SURFACE_PROBE = ("Chỉ dựa vào danh sách tool bạn thật sự nhận được, không đọc file, "
                 "không chạy lệnh. Trả lời đúng ba dòng: TOOLS=<số tool>; "
                 "HAS_PFE=<có|không>; FIRST=<tên tool đầu tiên>.")

# Only these may run. A model that reaches for bash or reads source by hand is
# not exercising the plugin, and letting it would make the record meaningless.
ALLOWED_TOOLS = {
    "project_flow_explain", "project_code_index", "project_code_search",
    "project_context_pack", "project_impact_analysis", "project_verify_flow",
    "project_knowledge_refresh",
}

# What a correct context pack for this fixture must contain, and what it must not
# present as a direct hit. The decoy lives in routes/preview.js: a real route that
# matches the wording but is not wired into the flow.
EXPECTED_CONTEXT_PATHS = {"services/report_service.js", "server.js",
                          "tests/report_service.test.js"}
DECOY_ROUTE = "/api/legacy/preview"

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"user_[A-Za-z0-9]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
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


AMBIENT_PROFILE_VARS = ("DSH_PROFILE", "DSH_PROFILE_DIR", "DSH_ACTIVE_PROFILE")


def clean_env(extra=None):
    """Drop inherited profile selectors so the child sees only what this run sets.

    The caller's shell may export DSH_PROFILE=web; inheriting it made the probe
    report a profile this run never booted.
    """
    base = {key: value for key, value in os.environ.items()
            if key not in AMBIENT_PROFILE_VARS}
    base.update(extra or {})
    return base


def run(argv, timeout=600, env=None):
    started = time.time()
    completed = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True,
                               env=clean_env(env), timeout=timeout,
                               check=False)
    return {
        "argv": argv,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "duration_ms": round((time.time() - started) * 1000, 1),
    }


def fresh_fixture():
    """Copy the fixture into a fresh temp dir. Never reuse a previous run's tree.

    A shared fixture directory accumulates .pfe, artifacts and edits from earlier
    runs, so "the model found the route" could be true of a tree nobody cleaned.
    Returns (path, tree_hash, file_count).
    """
    # A fixed parent keeps the profile's allowedRoots narrow; a fresh child per
    # run means no previous tree is ever reused.
    parent = Path(tempfile.gettempdir()) / "pfe-model-fixtures"
    parent.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix="run-", dir=str(parent)))
    target = base / "repo"
    shutil.copytree(FIXTURE_SOURCE, target,
                    ignore=shutil.ignore_patterns("artifacts", ".pfe", "__pycache__"))
    # Index it cleanly so the session starts from a known state.
    subprocess.run([sys.executable, str(ROOT / "tools" / "pfe_cli.py"), "index",
                    "--repo", str(target), "--mode", "full"],
                   cwd=str(ROOT), capture_output=True, text=True, check=False)
    digest, count = tree_fingerprint(target)
    return base, target, digest, count


def tree_fingerprint(root):
    """Content hash of the fixture tree plus its file count (excluding index)."""
    digest = hashlib.sha256()
    files = 0
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith(".pfe/") or rel.startswith("artifacts/"):
            continue
        digest.update(rel.encode("utf-8"))
        digest.update(path.read_bytes())
        files += 1
    return digest.hexdigest(), files


def scrub_text(value):
    """Remove anything that must not leave this machine, or name it as removed."""
    if not value:
        return ""
    text = str(value)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED_SECRET]", text)
    text = re.sub(r"(?<![<\w])/(?:home|Users)/[A-Za-z0-9._-]+", "<home>", text)
    text = re.sub(r"/tmp/[A-Za-z0-9._-]+", "<tmp>", text)
    return text.strip()


def check_context_accuracy(log_text):
    """Did the model actually receive the context it needed?

    Order is a workflow question; this is a content question. They fail for
    different reasons, so they are scored separately.
    """
    tool_results = []
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
        content = message.get("content") or []
        if content:
            tool_results.append(str(content[0].get("text") or ""))
    blob = "\n".join(tool_results)
    found = {path for path in EXPECTED_CONTEXT_PATHS if path in blob}
    # The tool renders prose, not JSON, so the decoy check reads the rendered
    # sections: a route named under "Entry point"/"route" is presented as direct
    # context, while one under a related/excluded heading is not.
    # Only the rendered entry-point LINE says what the task starts at. A wider
    # window picked up the related-routes list and reported the decoy as direct.
    decoy_in_entry = False
    for line in blob.splitlines():
        stripped = line.strip()
        if not stripped.startswith("Entry point"):
            continue
        if DECOY_ROUTE in stripped:
            decoy_in_entry = True
        break
    # "phụ thuộc" is how the renderer says downstream_modules; the test path must
    # appear next to it for the blast radius to be actionable.
    has_downstream = ("phụ thuộc" in blob or "downstream" in blob) and (
        "report_service.test.js" in blob)
    return {
        "expected_paths_found": sorted(found),
        "expected_paths_missing": sorted(EXPECTED_CONTEXT_PATHS - found),
        "decoy_presented_as_direct": bool(decoy_in_entry),
        "impact_has_downstream_and_test": bool(has_downstream),
    }


def _loader_profile_from_session(log_text):
    """Observed evidence that this session booted the plugin, and from where.

    DSH does not write the profile name into the session log, so a text scan can
    only guess. What the log does record is the tool surface the model was given:
    if the plugin's tools are in the request header, then this session loaded the
    plugin, and the only profile with it installed is the one the attribution
    guard already pinned to this tarball. That is an observation about the boot,
    not an assumption from disk.

    Returns (loader_profile, source) where source names the evidence used.
    """
    declared = ""
    has_plugin_tools = False
    for line in log_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        data = event_data(event)
        if kind in ("session", "request/header", "request/context"):
            blob = json.dumps(data, ensure_ascii=False)
            found = re.search(r'"profile(?:Name|Dir)?"\s*:\s*\\?"([^"\\]+)', blob)
            if found and not declared:
                value = found.group(1)
                declared = (value.rsplit("/profiles/", 1)[1].split("/")[0]
                            if "/profiles/" in value else value)
            if kind == "request/header":
                tools = data.get("header", {}).get("tools") or data.get("tools") or []
                if any(str(item.get("name", "")).startswith("project_")
                       for item in tools if isinstance(item, dict)):
                    has_plugin_tools = True
    if declared:
        return declared, "session_metadata"
    if has_plugin_tools:
        # The session does not name a profile, but it does prove the plugin was
        # loaded. That is weaker evidence than a recorded name, so it is returned
        # as `ambiguous` with the reason attached: the caller decides whether to
        # accept it, and the record says which evidence was used.
        return "ambiguous", "tool_surface_in_request_header"
    return "ambiguous", "not_recorded"


def installed_version():
    """Version of the plugin actually loaded from the profile's node_modules."""
    package = (DSH_HOME / "profiles" / PROFILE / "node_modules"
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
    """Locate the session log this run booted: the marker in a user message.

    The newest file wins on a tie. Every earlier version picked a different
    log — the agent's own conversation, a later run that echoed the record, or
    "first file with --profile" — because each matched on text the transcript
    happens to contain. Matching the prompt event itself is the only test that
    cannot drift: nothing but this boot writes that event with this marker.
    """
    candidates = sorted((DSH_HOME / "sessions").glob("*/*/session.v4.jsonl.zstd"),
                        key=lambda item: item.stat().st_mtime, reverse=True)
    for path in candidates[:60]:
        if path.stat().st_mtime < started - 120:
            continue
        raw = run(["zstdcat", str(path)], timeout=180)
        if raw["exit_code"] != 0:
            continue
        log_text = raw["stdout"]
        if marker not in log_text:
            continue
        if not _marker_in_user_message(log_text, marker):
            continue
        return path, log_text
    return None, ""


def strip_marker(text, marker):
    """Remove this run's own marker so its id is not mistaken for user content."""
    return str(text or "").replace(marker, "")


def probe_surface(marker):
    """What the profile's tool surface offered before the task prompt ran.

    A missing project_* tool has two causes that look identical in the task
    transcript: the harness never exposed it, or the model saw it and did not
    choose it. Only a probe separates them.
    """
    probe_marker = marker + "-SURFACE"
    result = run(["dsh", "--profile", PROFILE, SURFACE_PROBE + "\nMã phiên: " + probe_marker],
                 timeout=300)
    text = scrub_text(result["stdout"])
    tools = re.search(r"TOOLS\s*[=:]\s*(\d+)", text)
    has_pfe = re.search(r"HAS_PFE\s*[=:]\s*(\S+)", text)
    return {
        "exit_code": result["exit_code"],
        "tool_count": int(tools.group(1)) if tools else None,
        "has_pfe": (has_pfe.group(1).strip(" ;.,").lower() in {"có", "co", "yes", "true", "1"}
                    if has_pfe else None),
        "answer": text[:300],
    }


def _marker_in_user_message(log_text, marker):
    for line in log_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "user/message":
            continue
        data = event_data(event)
        if marker in json.dumps(data, ensure_ascii=False):
            return True
    return False


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

    # The build under test, not the last manifest: the manifest is written after
    # this runs, so reading it would describe the previous release.
    package_json = ROOT / "dsh-plugin" / "package.json"
    if not package_json.exists():
        print("thiếu dsh-plugin/package.json", file=sys.stderr)
        return 1
    version = json.loads(package_json.read_text(encoding="utf-8"))["version"]
    tarball = ROOT / "dist" / (PACKAGE + "-" + version + ".tgz")
    if not tarball.exists():
        print("thiếu tarball: " + str(tarball) + " — chạy dsh-plugin/scripts/pack.mjs",
              file=sys.stderr)
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

    base, fixture_root, tree_hash, file_count = fresh_fixture()
    record["fixture_tree_hash"] = tree_hash
    record["fixture_file_count"] = file_count
    record["fixture_source"] = "tests/fixtures/shop-app"
    try:
        return _run_session(record, fixture_root, version, tarball)
    finally:
        # The tree is disposable; leaving it behind makes the next run ambiguous.
        shutil.rmtree(base, ignore_errors=True)


def _run_session(record, fixture_root, version, tarball):
    marker = session_marker()
    prompt = PROMPT.format(repo=str(fixture_root)) + "\nMã phiên: " + marker
    # The surface is measured before the task runs: if the profile offers no
    # project_* tool, the task transcript will look like a model decline, and
    # scoring it as one blames the model for the harness.
    surface = probe_surface(marker)
    record["surface_probe"] = surface
    started = time.time()
    result = run(["dsh", "--profile", PROFILE, prompt], timeout=900)
    record["wall_seconds"] = round(time.time() - started, 1)
    record["exit_code"] = result["exit_code"]
    record["stderr_tail"] = scrub_text(result["stderr"][-400:])
    record["stop_reason"] = ("error" if result["exit_code"] != 0 else "completed")

    if "MISSING_CREDENTIAL" in result["stderr"]:
        record["status"] = "blocked"
        record["blocked"] = "MISSING_CREDENTIAL: profile chưa có credential cho route"
        path = _write_record(record)
        print(json.dumps({"status": "blocked", "record": path.name}, ensure_ascii=False))
        return 2

    session_path, log_text = find_session(started, marker)
    # Leaf name plus a short directory tag. A full path embeds the workspace
    # directory and therefore the user's home layout; session_sha256 is what
    # actually proves which file was read.
    record["session_file"] = session_path.name if session_path is not None else ""
    record["session_dir_tag"] = (session_path.parent.name[:16] + "…"
                                 if session_path is not None else "")
    record["session_sha256"] = (sha256_file(session_path)
                                if session_path is not None and session_path.exists()
                                else "")
    if session_path is None:
        record["status"] = "unverified"
        record["blocked"] = ("không tìm thấy session log chứa marker — không có gì để "
                            "chấm; exit_code=" + str(record["exit_code"]))
        path = _write_record(record)
        print(json.dumps({"status": "unverified", "record": path.name}, ensure_ascii=False))
        return 2

    sequence = tool_sequence(log_text)
    outcomes = tool_outcomes(log_text)
    for item in sequence:
        item["outcome"] = outcomes.get(item.get("call"), "unknown")
    order = check_order(sequence)

    # A tool outside the allowlist means the session did not exercise the plugin:
    # bash, read or a skill call makes every later assertion uninterpretable.
    loader_profile, loader_source = _loader_profile_from_session(log_text)
    # A boot that records no profile is not the same as a boot of the wrong one.
    # The tool surface proves the plugin loaded; the attribution guard proves the
    # tarball; together they name the profile without the session saying so.
    if loader_profile == "ambiguous" and loader_source == "tool_surface_in_request_header":
        record["loader_profile"] = PROFILE
        record["profile_identity_ok"] = True
        record["profile_identity_evidence"] = loader_source
    else:
        record["loader_profile"] = loader_profile
        record["profile_identity_ok"] = (loader_profile == PROFILE)
        record["profile_identity_evidence"] = loader_source

    outside = sorted({item["tool"] for item in sequence} - ALLOWED_TOOLS)
    record["tools_outside_allowlist"] = outside
    accuracy = check_context_accuracy(log_text)
    record["context_accuracy"] = accuracy

    record["selected_tools"] = [item["tool"] for item in sequence]
    record["tool_sequence"] = sequence
    record["order"] = order
    record["prompt_sha256"] = sha256_text(prompt)
    record["session_marker"] = marker
    record["answer_excerpt"] = strip_marker(scrub_text(result["stdout"]), marker)[:800]

    # Policy: the tools are read-mostly; a verify call must not be the only one,
    # and no tool may report an error code in the captured sequence.
    errors = [item["tool"] for item in sequence if item.get("outcome") == "error"]
    record["policy"] = {
        "tool_errors": errors,
        "expected_tools_ran": not order["missing"],
        "order_respected": order["ordered"],
        "tools_outside_allowlist": outside,
    }

    # Two independent verdicts. A session can run the right tools in the right
    # order and still hand the model the wrong context, or vice versa; one number
    # cannot express both, and collapsing them hides whichever failed.
    workflow_ok = (not errors and not order["missing"] and order["ordered"]
                   and not outside and record["profile_identity_ok"])
    context_ok = (not accuracy["expected_paths_missing"]
                  and not accuracy["decoy_presented_as_direct"]
                  and accuracy["impact_has_downstream_and_test"])
    record["workflow_order_verified"] = workflow_ok
    record["context_accuracy_verified"] = context_ok

    reasons = []
    if order["missing"]:
        reasons.append("thiếu tool: " + ", ".join(order["missing"]))
    if not order["ordered"]:
        reasons.append("thứ tự không đúng: " + " -> ".join(order["observed"]))
    if errors:
        reasons.append("tool lỗi: " + ", ".join(errors))
    if outside:
        reasons.append("tool ngoài allowlist: " + ", ".join(outside))
    if not record["profile_identity_ok"]:
        if loader_profile == "ambiguous":
            reasons.append("không chứng minh được boot bằng " + PROFILE
                           + " (bằng chứng: " + loader_source + ")")
        else:
            reasons.append("profile identity mismatch: requested " + PROFILE
                           + ", loader " + loader_profile)
    if accuracy["expected_paths_missing"]:
        reasons.append("context thiếu: " + ", ".join(accuracy["expected_paths_missing"]))
    if accuracy["decoy_presented_as_direct"]:
        reasons.append("decoy route bị coi là direct context: " + DECOY_ROUTE)
    if not accuracy["impact_has_downstream_and_test"]:
        reasons.append("impact thiếu downstream/test path")

    # A pass needs positive evidence; an absence of failures is not evidence.
    # Zero tool calls, an absent tool, or no context at all all satisfy "no
    # error", and that is exactly how the previous version marked this session
    # partial while its context_accuracy_verified read true on no observation.
    observed = bool(sequence)
    surface_ok = surface.get("has_pfe") is True
    if not observed:
        reasons.append("không có tool/call nào của project_* trong session")
    if not surface_ok:
        reasons.append("probe surface: HAS_PFE=" + str(surface.get("has_pfe"))
                       + " (tool_count=" + str(surface.get("tool_count")) + ")")

    verified = workflow_ok and context_ok and observed and surface_ok
    record["status"] = "verified" if verified else "partial"
    if not verified:
        record["blocked"] = "; ".join(reasons)

    path = _write_record(record)

    summary = {
        "status": record["status"],
        "record": path.name,
        "package_version": version,
        "installed_version": installed_version(),
        "tarball_sha256": record["tarball_sha256"][:12],
        "tools": record["selected_tools"],
        "order_ok": order["ordered"],
        "missing": order["missing"],
        "surface": {"has_pfe": surface.get("has_pfe"),
                    "tool_count": surface.get("tool_count")},
        "wall_seconds": record["wall_seconds"],
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if verified else 2


def _write_record(record):
    """Keep a verified record as evidence; keep an unverified one as an attempt.

    A partial record that sits in the evidence folder next to a verified one is
    indistinguishable to a reader who only lists the directory. The path says
    which kind it is.
    """
    folder = REVIEW if record.get("status") == "verified" else ATTEMPTS
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-model-session.json")
    record["updated_at"] = utc_now()
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    sys.exit(main())
