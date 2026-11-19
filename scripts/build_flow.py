#!/usr/bin/env python3
"""Build an evidence-backed flow graph from a repository and a flow request.

Produces three files from ONE analysis result, so they cannot disagree:
  flow.json   machine-readable graph, validated by render_flow.validate
  flow.html   self-contained offline diagram rendered from that same graph
  overview.md Vietnamese explanation, including the evidence level per step

Read-only with respect to the analysed repository. Artifacts go to exactly
``<repo>/artifacts/flows/<slug>/`` — nowhere else, ever. The script never uses
the network, never executes repository code and never copies matched source
text into its output; it records file, line and symbol only.

Evidence model (see AGENTS-style rule in references/flow-schema.md):
  location evidence   the symbol/route really exists at path:line
  membership evidence the step is reachable from the entry through a route
                      body, an import edge or a call edge — keyword matches are
                      NOT membership evidence
  inferred role       what the step does for the flow, when only structure says so

Usage:
  python build_flow.py --repo /path/to/repo --request "giải thích luồng xuất báo cáo"
  python build_flow.py --repo R --request Q --json      # machine-readable result
No third-party packages required.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import render_flow  # noqa: E402  (sibling module, same directory)

SCHEMA_VERSION = 2
MAX_FILE_BYTES = 256 * 1024
MAX_FILES_SCANNED = 20000
MAX_STEPS = 12
SLUG_MAX = 48
ARTIFACT_SUBDIR = ("artifacts", "flows")

EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "vendor", "bower_components",
    "__pycache__", ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "dist", "build", "target", "out", "coverage", ".next", ".nuxt",
    ".cache", ".gradle", ".idea", ".vscode", "artifacts", ".artifacts",
    "site-packages", "Pods", "DerivedData",
}

EXCLUDED_NAME_PATTERNS = [
    r"^\.env(\..*)?$", r"\.env$", r"(?i)credentials?", r"(?i)secrets?",
    r"(?i)\.pem$", r"(?i)\.key$", r"(?i)\.p12$", r"(?i)\.pfx$",
    r"(?i)^id_(rsa|dsa|ecdsa|ed25519)", r"(?i)\.keystore$",
    r"(?i)\.dump$", r"(?i)\.sql\.gz$", r"(?i)\.bak$", r"(?i)\.log$",
    r"(?i)\.min\.js$", r"(?i)\.map$", r"(?i)package-lock\.json$", r"(?i)pnpm-lock\.yaml$",
    r"(?i)yarn\.lock$", r"(?i)\.csv$", r"(?i)\.xlsx$", r"(?i)\.pdf$",
]

TEST_DIR_PATTERN = re.compile(
    r"(?i)(?:^|/)(?:tests?|specs?|__tests__|__mocks__|fixtures?|samples?|examples?|demo)(?:/|$)")

SOURCE_SUFFIXES = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".svelte",
    ".php", ".java", ".kt", ".rb", ".go", ".rs", ".cs", ".sql", ".sh",
}

SECRET_LINE = re.compile(
    r"(?i)(api[_-]?key|secret|passwd|password|token|private[_-]?key|access[_-]?key)"
    r"\s*[:=]\s*['\"]?[A-Za-z0-9/+_\-]{8,}")

# Facets turn a Vietnamese/English sentence into code-search terms. They are
# only used to rank candidates and to read a route body; they never decide by
# themselves that a file belongs to the flow.
FACETS = [
    {
        "id": "export",
        "label": "xuất / tải dữ liệu",
        "keywords": ["xuat", "xuat bao cao", "bao cao", "tai xuong", "tai ve", "export",
                     "download", "report", "excel", "csv", "pdf", "in an", "print"],
        "code": [r"(?i)\bxlsx\b", r"(?i)\bcsv\b", r"(?i)\bpdf\b", r"(?i)content-disposition",
                 r"(?i)send_file", r"(?i)file_response", r"(?i)streaming_response",
                 r"(?i)to_excel", r"(?i)excelwriter", r"(?i)to_csv", r"(?i)workbook",
                 r"(?i)\bdownload\b", r"(?i)attachment;"],
        "path": [r"(?i)export", r"(?i)report", r"(?i)download", r"(?i)invoice"],
    },
    {
        "id": "auth",
        "label": "đăng nhập / xác thực",
        "keywords": ["dang nhap", "dang ky", "xac thuc", "login", "signin", "sign in",
                     "auth", "token", "session", "otp", "mat khau", "password", "jwt"],
        "code": [r"(?i)\blogin\b", r"(?i)\bsignin\b", r"(?i)authenticate", r"(?i)\bbcrypt\b",
                 r"(?i)\bjwt\b", r"(?i)\bsession\b", r"(?i)\bpassword\b", r"(?i)\botp\b"],
        "path": [r"(?i)auth", r"(?i)login", r"(?i)user", r"(?i)account", r"(?i)session"],
    },
    {
        "id": "upload",
        "label": "tải tệp lên",
        "keywords": ["tai len", "upload", "dinh kem", "attach", "tep", "file"],
        "code": [r"(?i)multipart", r"(?i)\bmulter\b", r"(?i)\bupload\b", r"(?i)files?\[",
                 r"(?i)formdata", r"(?i)file\.save"],
        "path": [r"(?i)upload", r"(?i)attachment", r"(?i)media"],
    },
    {
        "id": "payment",
        "label": "thanh toán / đơn hàng",
        "keywords": ["thanh toan", "payment", "hoa don", "invoice", "don hang", "order",
                     "gio hang", "cart", "checkout"],
        "code": [r"(?i)\bpayment\b", r"(?i)\binvoice\b", r"(?i)\bcheckout\b", r"(?i)\bvnpay\b",
                 r"(?i)\bmomo\b", r"(?i)\bstripe\b", r"(?i)\border\b"],
        "path": [r"(?i)payment", r"(?i)invoice", r"(?i)order", r"(?i)checkout"],
    },
    {
        "id": "search",
        "label": "tìm kiếm / lọc",
        "keywords": ["tim kiem", "search", "loc", "filter", "tra cuu", "query"],
        "code": [r"(?i)\bsearch\b", r"(?i)\bfilter\b", r"(?i)\bwhere\(", r"(?i)\bselect\b",
                 r"(?i)\bquery\b"],
        "path": [r"(?i)search", r"(?i)query", r"(?i)filter"],
    },
    {
        "id": "notify",
        "label": "gửi thông báo",
        "keywords": ["thong bao", "email", "sms", "notification", "gui mail", "push"],
        "code": [r"(?i)\bsmtp\b", r"(?i)\bemail\b", r"(?i)\bsms\b", r"(?i)\bnotification\b",
                 r"(?i)\bpush\b", r"(?i)sendmail"],
        "path": [r"(?i)mail", r"(?i)notif", r"(?i)sms"],
    },
    {
        "id": "persist",
        "label": "ghi dữ liệu",
        "keywords": ["luu", "ghi du lieu", "database", "db", "insert", "update", "commit",
                     "luu tru", "persist"],
        "code": [r"(?i)\binsert\b", r"(?i)\bupdate\b", r"(?i)\bcommit\(", r"(?i)\bbulk",
                 r"(?i)\.save\(", r"(?i)\bcreate\(", r"(?i)\btransaction"],
        "path": [r"(?i)model", r"(?i)repo", r"(?i)store", r"(?i)db", r"(?i)migration"],
    },
]

ROUTE_PATTERNS = [
    re.compile(r"(?i)\b(?:app|router|server|api)\s*\.\s*(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)"),
    re.compile(r"@\w*(?:app|router|blueprint)\w*\.(?:route|get|post|put|delete)\s*\(\s*['\"]([^'\"]+)"),
    re.compile(r"(?i)@(?:Get|Post|Put|Delete|Request)Mapping\s*\(\s*(?:value\s*=\s*)?['\"]([^'\"]+)"),
    re.compile(r"(?i)Route::(?:get|post|put|delete)\s*\(\s*['\"]([^'\"]+)"),
]

ENTRY_PATTERNS = [
    (r"(?i)def\s+(main)\s*\(", "entry"),
    (r"(?i)function\s+(main)\s*\(", "entry"),
]

SYMBOL_PATTERNS = [
    r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(",
    r"^\s*class\s+([A-Za-z_]\w*)",
    r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_]\w*)\s*\(",
    r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?\(",
    r"^\s*(?:export\s+)?class\s+([A-Za-z_]\w*)",
    r"^\s*(?:public|private|protected)\s+(?:static\s+)?(?:async\s+)?[A-Za-z_<>\[\], ]+\s+([A-Za-z_]\w*)\s*\(",
    r"^\s*function\s+([A-Za-z_]\w*)\s*\(",
]
SYMBOL_RE = [re.compile(p) for p in SYMBOL_PATTERNS]

ERROR_MARKERS = [
    (re.compile(r"^\s*try\s*[{(:]", re.M), "try"),
    (re.compile(r"^\s*except\b", re.M), "except"),
    (re.compile(r"(?i)\bcatch\s*\(", re.M), "catch"),
    (re.compile(r"(?i)\brescue\b", re.M), "rescue"),
]

RESPONSE_PATTERNS = [
    re.compile(r"(?i)\bres\.(json|send|sendFile|download|render)\s*\("),
    re.compile(r"(?i)\breturn\s+(JsonResponse|HttpResponse|Response|jsonify)\s*\("),
    re.compile(r"(?i)\bJSONResponse\b"),
    re.compile(r"(?i)\bresponse\.(json|send)\b"),
]

IMPORT_PATTERNS = [
    re.compile(r"""(?i)(?:require|from)\s*\(?\s*['"](\.[^'"]+)['"]"""),
    re.compile(r"""(?i)^\s*from\s+(\.[\w.]*)\s+import\b""", re.M),
    re.compile(r"""(?i)^\s*import\s+([\w.]+)\b""", re.M),
    re.compile(r"""(?i)^\s*from\s+([\w.]+)\s+import\b""", re.M),
]

PREFERRED_SYMBOL = re.compile(
    r"(?i)^(main|run|apply|execute|handler|handle|export|process|start|generate|build_flow|build)$")

EVIDENCE_MEMBERSHIP = {
    "entry": "điểm vào do yêu cầu + khai báo route xác định",
    "import": "file trước import trực tiếp file này",
    "call": "hàm của file này được file trước gọi theo tên",
    "route_body": "cùng file với khai báo route",
}


class BuildError(Exception):
    """A request the builder refuses to analyse, with a stable code."""

    def __init__(self, code, message, hint=""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


# --------------------------------------------------------------------------
# text helpers
# --------------------------------------------------------------------------

def strip_diacritics(text):
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def normalize_text(text):
    return re.sub(r"\s+", " ", strip_diacritics(text).lower()).strip()


def utc_now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def is_excluded_name(name):
    return any(re.search(pattern, name) for pattern in EXCLUDED_NAME_PATTERNS)


# --------------------------------------------------------------------------
# path policy: repository root and the single artifact root
# --------------------------------------------------------------------------

def real_dir(path, code, label):
    try:
        resolved = Path(os.path.realpath(str(path)))
    except OSError as error:
        raise BuildError(code, f"Không đọc được {label}: {path}", str(error))
    if not resolved.exists():
        raise BuildError(code, f"Không thấy {label}: {resolved}")
    if not resolved.is_dir():
        raise BuildError(code, f"{label} không phải thư mục: {resolved}")
    return resolved


def is_inside(root, target):
    root = str(root)
    target = str(target)
    return target == root or target.startswith(root + os.sep)


def artifact_root_for(root):
    """Return <root>/artifacts/flows and refuse a symlink pointing outside."""
    real_root = Path(os.path.realpath(str(root)))
    candidate = real_root.joinpath(*ARTIFACT_SUBDIR)
    # Walk the existing prefix: a symlinked `artifacts` or `flows` that escapes
    # the repository must be refused before anything is created.
    probe = real_root
    for part in ARTIFACT_SUBDIR:
        probe = probe / part
        if probe.is_symlink():
            target = Path(os.path.realpath(str(probe)))
            if not is_inside(real_root, target):
                raise BuildError(
                    "artifact_symlink_escape",
                    f"Thư mục artifact là symlink ra ngoài repository: {probe} → {target}",
                    f"Chỉ cho phép artifact dưới {real_root.joinpath(*ARTIFACT_SUBDIR)}",
                )
    resolved = Path(os.path.realpath(str(candidate))) if candidate.exists() else candidate
    if not is_inside(real_root, resolved):
        raise BuildError(
            "invalid_artifact_root",
            f"Artifact root phải nằm trong repository: {resolved}",
            f"Dùng đúng {real_root.joinpath(*ARTIFACT_SUBDIR)}",
        )
    return candidate


def validate_out_dir(root, out_dir):
    """The only accepted artifact root is <repo>/artifacts/flows."""
    expected = artifact_root_for(root)
    if out_dir is None:
        return expected
    raw = Path(out_dir).expanduser()
    candidate = raw if raw.is_absolute() else Path(root) / raw
    resolved = Path(os.path.realpath(str(candidate)))
    expected_real = Path(os.path.realpath(str(expected)))
    if resolved != expected_real:
        raise BuildError(
            "invalid_artifact_root",
            f"output directory không hợp lệ: {out_dir}",
            f"Chỉ chấp nhận {expected} (artifact không được ghi vào repo root, src, docs, tmp hay ngoài repo).",
        )
    if expected.is_symlink():
        raise BuildError("artifact_symlink_escape", f"Artifact root là symlink: {expected}")
    return expected


def safe_slug(slug):
    if slug is None:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(slug)).strip("-")
    if not cleaned or cleaned in {".", ".."} or cleaned != str(slug).strip():
        raise BuildError(
            "invalid_slug",
            f"slug không hợp lệ: {slug!r}",
            "slug chỉ nhận chữ, số, dấu chấm, gạch dưới, gạch ngang.",
        )
    return cleaned[:SLUG_MAX]


# --------------------------------------------------------------------------
# scanning
# --------------------------------------------------------------------------

def git_state(root):
    def run(*args):
        try:
            out = subprocess.run(["git", "-C", str(root), *args],
                                 capture_output=True, text=True, timeout=10, check=False)
            return out.stdout.strip() if out.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""

    commit = run("rev-parse", "--short=12", "HEAD")
    branch = run("rev-parse", "--abbrev-ref", "HEAD")
    porcelain = run("status", "--porcelain")
    return {
        "commit": commit or None,
        "branch": branch or None,
        "dirty": bool(porcelain),
        "dirty_files": len([line for line in porcelain.splitlines() if line.strip()]),
    }


def collect_files(root, excluded):
    files = []
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if any(part in EXCLUDED_DIRS for part in Path(rel).parts):
                excluded["directory"] += 1
                continue
            if TEST_DIR_PATTERN.search(rel):
                excluded["test_dir"] += 1
                continue
            if is_excluded_name(name):
                excluded["sensitive_name"] += 1
                continue
            if path.suffix.lower() not in SOURCE_SUFFIXES:
                excluded["suffix"] += 1
                continue
            real = Path(os.path.realpath(str(path)))
            if not is_inside(root, real):
                excluded["symlink_escape"] += 1
                continue
            try:
                if real.stat().st_size > MAX_FILE_BYTES:
                    excluded["too_large"] += 1
                    continue
            except OSError:
                excluded["unreadable"] += 1
                continue
            files.append(real)
            if len(files) >= MAX_FILES_SCANNED:
                return files
    return files


def read_text(path):
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None
    return raw.decode("utf-8", errors="replace")


def find_symbols(text):
    symbols = []
    for number, line in enumerate(text.splitlines(), start=1):
        for regex in SYMBOL_RE:
            hit = regex.match(line)
            if hit:
                symbols.append({
                    "name": hit.group(1),
                    "line": number,
                    "kind": "class" if re.search(r"\bclass\b", line) else "function",
                })
                break
    return symbols


def pick_symbol(symbols, after_line=0):
    if not symbols:
        return None
    later = [item for item in symbols if item["line"] >= after_line] or symbols
    callables = [item for item in later if item.get("kind") != "class"] or later
    public = [item for item in callables if not item["name"].startswith("_")]
    named = public or [item for item in callables if not item["name"].startswith("__")] or callables
    preferred = [item for item in named if PREFERRED_SYMBOL.match(item["name"])]
    return (preferred or named)[0]


def find_routes(text):
    routes = []
    for number, line in enumerate(text.splitlines(), start=1):
        for regex in ROUTE_PATTERNS:
            hit = regex.search(line)
            if hit:
                groups = hit.groups()
                label = groups[-1]
                method = groups[0] if len(groups) > 1 else ""
                routes.append({"line": number, "label": label, "method": method})
                break
    return routes


def find_entries(text):
    entries = []
    for number, line in enumerate(text.splitlines(), start=1):
        for pattern, kind in ENTRY_PATTERNS:
            hit = re.search(pattern, line)
            if hit:
                entries.append({"line": number, "kind": kind, "label": hit.group(1)})
    return entries


def find_imports(text, rel, known):
    """Resolve import specifiers to repository-relative source paths.

    Three shapes are supported: relative specs (``./x``, ``../x``), dotted
    absolute specs (``src._api``), and flat specs that only work because the
    entry file extends ``sys.path`` (``import _api``). The last one is matched
    by unique basename; an ambiguous basename is left unresolved rather than
    guessed.
    """
    targets = []
    directory = Path(rel).parent

    def resolve_relative(spec):
        base = (directory / spec).as_posix()
        parts = []
        for part in base.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                if parts:
                    parts.pop()
                continue
            parts.append(part)
        return "/".join(parts)

    def candidates_for(stem):
        for suffix in ("", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue",
                       ".py", ".php", ".rb"):
            for candidate in (f"{stem}{suffix}", f"{stem}/index{suffix}", f"{stem}/__init__.py"):
                if candidate in known and candidate != rel:
                    yield candidate

    for regex in IMPORT_PATTERNS:
        for hit in regex.finditer(text):
            spec = hit.group(1)
            if re.match(r"^\.", spec):
                stem = resolve_relative(spec)
                style = "relative"
            elif "/" in spec:
                stem = spec.lstrip("/")
                style = "relative"
            elif "." in spec:
                stem = spec.replace(".", "/")
                style = "dotted"
            else:
                stem = spec
                style = "flat"
            found = list(candidates_for(stem))
            if not found and style == "flat":
                # sys.path-style import: match by unique basename anywhere.
                matches = sorted(path for path in known
                                 if Path(path).stem == spec and path != rel)
                if len(matches) == 1:
                    found = matches
                    style = "flat-basename"
            for target in found:
                targets.append({"path": target, "style": style})
    deduped = {}
    for item in targets:
        deduped.setdefault((item["path"], item["style"]), item)
    return [deduped[key] for key in sorted(deduped)]


def response_lines(text):
    lines = set()
    for pattern in RESPONSE_PATTERNS:
        for hit in pattern.finditer(text):
            lines.add(text.count("\n", 0, hit.start()) + 1)
    return sorted(lines)


def has_error_handling(text):
    for pattern, _kind in ERROR_MARKERS:
        hit = pattern.search(text)
        if hit:
            return text.count("\n", 0, hit.start()) + 1
    return None


def match_facets(request_norm):
    active = [(facet, [kw for kw in facet["keywords"] if kw in request_norm])
              for facet in FACETS]
    active = [(facet, hits) for facet, hits in active if hits]
    if not active:
        active.append(({
            "id": "generic",
            "label": "luồng xử lý chung",
            "keywords": [],
            "code": [r"(?i)\bhandler\b", r"(?i)\bservice\b", r"(?i)\bcontroller\b"],
            "path": [r"(?i)src", r"(?i)app", r"(?i)services?"],
        }, []))
    return active


def score_window(window, active_facets):
    score = 0
    for facet, _hits in active_facets:
        for pattern in facet["code"]:
            score += 2 * len(re.findall(pattern, window))
    return score


def route_body(text_lines, routes, index):
    start = routes[index]["line"]
    end = routes[index + 1]["line"] - 1 if index + 1 < len(routes) else len(text_lines)
    return "\n".join(text_lines[start - 1:end])


# --------------------------------------------------------------------------
# graph
# --------------------------------------------------------------------------

def build_graph(root, request, inventory, git, limits, excluded):
    request_norm = normalize_text(request)
    active = match_facets(request_norm)
    known = {item["rel"] for item in inventory}

    for item in inventory:
        excluded["secret_lines"] += len(SECRET_LINE.findall(item["text"]))
        item["imports"] = find_imports(item["text"], item["rel"], known)

    # Rank only to choose the entry; ranking never puts a file into the flow.
    def rank(item):
        lines = item["text"].splitlines()
        best = 0
        best_route = None
        for index, route in enumerate(item["routes"]):
            body = route_body(lines, item["routes"], index)
            score = score_window(body, active)
            for facet, _hits in active:
                for pattern in facet["path"]:
                    if re.search(pattern, route["label"] or ""):
                        score += 6
            if score > best:
                best = score
                best_route = route
        return (best, len(item["symbols"]), item["rel"]), best_route

    ranked = []
    for item in inventory:
        score, route = rank(item)
        if score[0] > 0 or item["routes"] or item["entries"]:
            ranked.append((score, route, item))
    ranked.sort(key=lambda row: (-row[0][0], -row[0][1], row[0][2]))

    facet_labels = ", ".join(facet["label"] for facet, _ in active)
    nodes = []
    edges = []
    warnings = []
    related = []

    def add_node(node_id, title, node_type, summary, confidence, refs, **extra):
        node = {"id": node_id, "title": title, "type": node_type, "summary": summary,
                "confidence": confidence, "source_refs": refs}
        node.update(extra)
        nodes.append(node)

    def ref(rel, line, symbol=None):
        item = {"path": rel, "start_line": int(line)}
        name = (symbol or "").strip()
        if name:
            item["symbol"] = name
        return item

    def add_edge(source, target, label, kind, evidence, technical):
        edges.append({"from": source, "to": target, "label": label, "kind": kind,
                      "technical": technical, "evidence": evidence})

    add_node("start", "Bắt đầu từ yêu cầu", "start",
             f"Yêu cầu: “{request.strip()}”. Nhóm chủ đề: {facet_labels}.",
             "partial", [],
             details="Điểm vào của sơ đồ do yêu cầu quyết định, không phải một dòng code cụ thể.",
             technical="entry=request")

    if not ranked:
        add_node("no-evidence", "Không tìm thấy mã nguồn liên quan", "error",
                 "Không file nào trong phạm vi đọc khớp với yêu cầu. Sơ đồ dừng ở đây "
                 "thay vì mô tả một luồng không có bằng chứng.",
                 "unknown", [],
                 details="Cần mô tả flow cụ thể hơn, hoặc repository chưa chứa phần xử lý tương ứng.")
        add_edge("start", "no-evidence", "không khớp mã nguồn", "error", "none", "no-match")
        limits.append("Không tìm được bằng chứng nào cho yêu cầu này.")
        return _finish(nodes, edges, limits, warnings, related, active, request, git)

    # Entry: a route body that matches the request; otherwise a file that
    # declares an entry point. Keyword match alone is never enough.
    entry = None
    for score, route, item in ranked:
        if route is not None and score[0] > 0:
            entry = (item, route, "route")
            break
    if entry is None:
        for score, route, item in ranked:
            if item["entries"]:
                entry = (item, item["entries"][0], "entry")
                break
    if entry is None:
        limits.append(
            "Không xác định được điểm vào: không có route/handler nào khớp yêu cầu, nên không "
            "dựng chuỗi bước từ điểm số keyword (như vậy là bịa quan hệ).")
        add_node("no-entry", "Không xác định được điểm vào", "error",
                 "Có file khớp từ khoá nhưng không có route/handler để bắt đầu luồng. "
                 "Sơ đồ không nối các file đó thành một chuỗi giả.",
                 "unknown", [],
                 details="Cần chỉ rõ endpoint hoặc hàm bắt đầu luồng.")
        add_edge("start", "no-entry", "không có điểm vào", "error", "none", "no-entry")
        related = [{"path": score[2], "reason": "khớp từ khoá, không có liên kết tới điểm vào"}
                   for score, _route, _item in ranked[:5]]
        return _finish(nodes, edges, limits, warnings, related, active, request, git)

    entry_item, entry_route, entry_kind = entry
    entry_lines = entry_item["text"].splitlines()
    entry_symbol = pick_symbol(entry_item["symbols"], after_line=(
        entry_route["line"] if entry_kind == "route" else 0))
    entry_line = entry_route["line"]
    entry_label = entry_route.get("label") or (entry_symbol or {}).get("name") or ""

    add_node("step-1", f"Nhận yêu cầu {entry_label}" if entry_kind == "route"
             else f"Bắt đầu tại {entry_label}", "action",
             f"{'Điểm vào HTTP' if entry_kind == 'route' else 'Điểm vào'} — "
             f"`{entry_item['rel']}` (dòng {entry_line}).",
             "verified",
             [ref(entry_item["rel"], entry_line, entry_label)],
             details=f"Bằng chứng thành viên: {EVIDENCE_MEMBERSHIP['entry']}.",
             technical=entry_item["rel"], actor="Hệ thống")
    add_edge("start", "step-1", "bắt đầu xử lý", "success", "entry",
             f"route khai báo tại {entry_item['rel']}:{entry_line}")

    # Walk structural edges only: import, then call-by-name. Keyword matches
    # never add a node; they only appear under `related`.
    by_rel = {item["rel"]: item for item in inventory}
    visited = {entry_item["rel"]}
    flow_steps = [(entry_item, entry_line, entry_label)]
    queue = [entry_item]
    while queue:
        current = queue.pop(0)
        for edge in current["imports"]:
            target_rel = edge["path"]
            if target_rel in visited or target_rel not in by_rel:
                continue
            target = by_rel[target_rel]
            visited.add(target_rel)
            symbol = pick_symbol(target["symbols"])
            flow_steps.append((target, (symbol or {}).get("line") or 1,
                               (symbol or {}).get("name") or ""))
            queue.append(target)
            if len(flow_steps) >= MAX_STEPS:
                break
        if len(flow_steps) >= MAX_STEPS:
            break

    counter = 1
    previous_item, previous_id = flow_steps[0][0], "step-1"
    branch_done = False
    edge_evidence_seen = set()

    def emit_branch(source_id, source_item, next_id, next_label):
        """Insert decision + error nodes between source and the next step."""
        suffix = re.sub(r"[^A-Za-z0-9_-]+", "-", source_item["rel"])[:60]
        decision_id = f"decision-{suffix}"
        error_id = f"error-{suffix}"
        line = source_item["error_line"]
        add_node(decision_id, "Có lỗi trong bước này?", "decision",
                 "Bước xử lý có nhánh bắt lỗi; sơ đồ tách nhánh thành công và thất bại.",
                 "partial", [ref(source_item["rel"], line)],
                 details="Nhánh lỗi suy ra từ việc có xử lý ngoại lệ; mã lỗi chưa xác minh.")
        add_node(error_id, "Trả lỗi cho người gọi", "error",
                 "Lỗi được bắt và trả về lớp gọi thay vì kết thúc im lặng.",
                 "partial", [ref(source_item["rel"], line)],
                 details="Chưa xác minh nội dung thông báo và mã lỗi.")
        add_edge(source_id, decision_id, "vào bước xử lý", "normal", "import",
                 f"cùng bước `{source_item['rel']}`")
        add_edge(decision_id, next_id, next_label, "success", "structure",
                 "đường đi tiếp khi không lỗi")
        add_edge(decision_id, error_id, "có lỗi", "error", "structure",
                 "khối xử lý ngoại lệ trong file")

    for item, line, symbol_name in flow_steps[1:]:
        counter += 1
        node_id = f"step-{counter}"
        module = Path(item["rel"]).stem
        add_node(node_id, f"Xử lý tại {symbol_name}" if symbol_name else f"Module {module}",
                 "action",
                 f"Bước xử lý — `{item['rel']}` (dòng {line}).",
                 "verified", [ref(item["rel"], line, symbol_name)],
                 details=f"Bằng chứng thành viên: import từ `{previous_item['rel']}`.",
                 technical=item["rel"], actor="Hệ thống")
        add_edge(previous_id, node_id, "dùng module", "normal", "import",
                 f"`{previous_item['rel']}` import `{item['rel']}`"
                 + (" (qua sys.path)" if edge["style"] == "flat-basename" else ""))
        edge_evidence_seen.add("import")
        if previous_item["error_line"] and not branch_done:
            emit_branch(previous_id, previous_item, node_id, "không lỗi")
            branch_done = True
        previous_item, previous_id = item, node_id

    if len(visited) >= MAX_STEPS:
        warnings.append(f"Luồng có từ {MAX_STEPS} bước trở lên; sơ đồ đã cắt bớt.")

    if len(visited) == 1:
        limits.append(
            "Không có cạnh import/gọi hàm nào từ điểm vào: chưa có call graph thật, "
            "nên sơ đồ chỉ có bước mở đầu thay vì nối các file khớp từ khoá.")

    # Keyword matches outside the reachable set are reported, never chained.
    for item in inventory:
        if item["rel"] in visited:
            continue
        keyword = 0
        for facet, _hits in active:
            for pattern in facet["code"]:
                keyword += len(re.findall(pattern, item["text"]))
            for pattern in facet["path"]:
                if re.search(pattern, item["rel"]):
                    keyword += 3
        if keyword > 0:
            related.append({
                "path": item["rel"],
                "reason": "khớp từ khoá nhưng không nối được tới điểm vào bằng import/gọi hàm",
            })
    related.sort(key=lambda entry: entry["path"])

    # Response node: first response call at/after the entry line, in flow order.
    response_pick = None
    for index, (item, line, _symbol) in enumerate(flow_steps):
        candidates = [candidate for candidate in item["response_lines"]
                      if candidate >= (line if index == 0 else 1)]
        if candidates:
            response_pick = (item, candidates[0])
            break
    if response_pick:
        response_item, response_line = response_pick
        add_node("end", "Trả kết quả", "end",
                 f"Kết quả được trả về từ `{response_item['rel']}`.",
                 "verified", [ref(response_item["rel"], response_line)],
                 details="Điểm kết thúc xác định theo lời gọi trả kết quả trong code.")
    else:
        add_node("end", "Kết thúc xử lý", "end",
                 "Không tìm thấy lời gọi trả kết quả rõ ràng; điểm kết thúc suy ra từ bước cuối.",
                 "inferred", [], details="Chưa xác minh nơi trả kết quả cho người dùng.")
        limits.append("Không tìm thấy điểm trả kết quả rõ ràng; node kết thúc là suy luận.")
    add_edge(previous_id, "end", "hoàn tất", "success",
             "call" if edge_evidence_seen else "entry",
             "bước cuối của luồng" if counter > 1 else "điểm vào trả kết quả")
    if previous_item["error_line"] and not branch_done:
        emit_branch(previous_id, previous_item, "end", "không lỗi")
        branch_done = True

    if not edge_evidence_seen:
        limits.append("Chưa có call graph thật: chỉ xác minh được file và dòng của từng bước.")

    return _finish(nodes, edges, limits, warnings, related, active, request, git)


def _finish(nodes, edges, limits, warnings, related, active, request, git):
    title_topic = re.sub(r"(?i)^\s*(?:luồng|luong|quy trình|quy trinh|flow)\s*[:\-–]?\s*",
                         "", request.strip())
    title_topic = (title_topic or request.strip())[:120]
    graph = {
        "flow_id": "",
        "title": f"Luồng: {title_topic}",
        "description": (
            f"Sơ đồ dựng từ phân tích tĩnh theo yêu cầu: {request.strip()}. "
            "Mỗi bước trỏ tới file và dòng thật; bước chỉ khớp từ khoá được tách riêng "
            "thay vì nối vào luồng."),
        "audience": "Người không đọc code, BA, kiểm thử",
        "scope": f"Đọc source trong repository · {', '.join(f['label'] for f, _ in active)}",
        "entry_node": "start",
        "nodes": nodes,
        "edges": edges,
        "assumptions": limits + warnings,
        "notes": ("Phân tích tĩnh, không chạy code của repository, không dùng network. "
                  "`verified` = vị trí có thật + có bằng chứng thành viên (route/import/call). "
                  "`partial`/`inferred` = suy luận từ cấu trúc. Không chép nội dung source."),
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "generated_at": utc_now(),
            "source": git,
            "request": request.strip(),
            "facets": [facet["id"] for facet, _ in active],
            "related": related,
        },
    }
    return graph, warnings


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------

def make_slug(request, git, taken):
    base = re.sub(r"[^a-z0-9]+", "-", strip_diacritics(request).lower()).strip("-")
    words = [word for word in base.split("-") if word][:6]
    digest = hashlib.sha1(f"{request}|{git.get('commit')}".encode("utf-8")).hexdigest()[:6]
    slug = "-".join(words + [digest])[:SLUG_MAX].strip("-") or "flow"
    candidate, counter = slug, 2
    while candidate in taken:
        suffix = f"-{counter}"
        candidate = (slug[: SLUG_MAX - len(suffix)] + suffix).strip("-")
        counter += 1
        if counter > 50:
            raise BuildError("slug_exhausted", "Không tạo được thư mục artifact không trùng tên")
    return candidate


def render_overview(graph, repo_name, request, excluded, limits, warnings, related):
    rows = []
    for index, node in enumerate(graph["nodes"], start=1):
        refs = node.get("source_refs") or []
        location = "—"
        if refs:
            location = f"`{refs[0]['path']}`"
            if refs[0].get("start_line"):
                location += f":{refs[0]['start_line']}"
        membership = next(
            (edge["evidence"] for edge in graph["edges"] if edge["to"] == node["id"]), "—")
        rows.append(f"| {index} | {node['title']} | {node['type']} | {location} | "
                    f"{membership} | {node['confidence']} |")

    edge_rows = [
        f"| {edge['from']} → {edge['to']} | `{edge['label']}` | {edge['kind']} | "
        f"{edge.get('evidence', '—')} | {edge.get('technical', '—')} |"
        for edge in graph["edges"]
    ]
    related_rows = [f"- `{item['path']}` — {item['reason']}" for item in related] or \
                   ["- Không có file nào bị loại khỏi luồng."]
    excluded_lines = "\n".join(f"- {key}: {value}" for key, value in sorted(excluded.items()) if value) \
        or "- Không có mục nào bị loại."
    limits_lines = "\n".join(f"- {item}" for item in limits) or "- Không có giới hạn bổ sung."
    warnings_lines = "\n".join(f"- {item}" for item in warnings) or "- Không có cảnh báo."
    source = graph["meta"]["source"]

    return f"""# {graph['title']}

Sinh tự động: {graph['meta']['generated_at']} · `scripts/build_flow.py` (schema {SCHEMA_VERSION}).

## Yêu cầu

> {request.strip()}

## Repository được phân tích

| Mục | Giá trị |
|---|---|
| Tên | `{repo_name}` |
| Nhánh | `{source.get('branch') or 'không có git'}` |
| Commit | `{source.get('commit') or 'không có git'}` |
| Thay đổi chưa commit | {'có — ' + str(source.get('dirty_files')) + ' file' if source.get('dirty') else 'không'} |

Đường dẫn tuyệt đối không được ghi vào artifact để tránh lộ cấu trúc máy cá nhân.

## Luồng xử lý

{graph['description']}

| # | Bước | Loại | Vị trí | Bằng chứng thành viên | Tin cậy |
|---|---|---|---|---|---|
{chr(10).join(rows)}

## Quan hệ giữa các bước

| Cạnh | Nhãn | Loại | Bằng chứng | Ghi chú |
|---|---|---|---|---|
{chr(10).join(edge_rows)}

## File khớp từ khoá nhưng KHÔNG thuộc luồng

{chr(10).join(related_rows)}

## Giới hạn và phần chưa xác minh

{limits_lines}

{warnings_lines}

## Phạm vi đọc và loại trừ

Chỉ đọc file source trong repository. Các mục sau bị loại:

{excluded_lines}

Không gọi network, không chạy code của repository, không sửa file nguồn, không chép nội dung source.

## Tệp sinh ra

- `flow.json` — dữ liệu có cấu trúc, dùng lại được cho lần render sau
- `flow.html` — sơ đồ mở offline
- `overview.md` — tài liệu này
"""


def write_outputs(graph, artifacts_dir, repo_name, request, excluded, limits, warnings, related):
    flow_json = artifacts_dir / "flow.json"
    flow_html = artifacts_dir / "flow.html"
    overview_md = artifacts_dir / "overview.md"
    run_json = artifacts_dir / "run.json"

    info = render_flow.validate(graph)
    render_flow.assign_positions(graph, info)
    flow_json.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    flow_html.write_text(render_flow.render_json(graph), encoding="utf-8")
    overview_md.write_text(
        render_overview(graph, repo_name, request, excluded, limits, warnings, related),
        encoding="utf-8")
    counts = {"verified": 0, "partial": 0, "inferred": 0, "unknown": 0}
    for node in graph["nodes"]:
        counts[node["confidence"]] = counts.get(node["confidence"], 0) + 1
    run_json.write_text(json.dumps({
        "status": "ok",
        "schema_version": SCHEMA_VERSION,
        "flow_id": graph["flow_id"],
        "generated_at": graph["meta"]["generated_at"],
        "repository_name": repo_name,
        "request": request,
        "source": graph["meta"]["source"],
        "counts": counts,
        "limits": limits,
        "warnings": warnings,
        "related": related,
        "excluded": excluded,
        "files": [flow_json.name, flow_html.name, overview_md.name, run_json.name],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"counts": counts, "paths": {
        "flow_json": flow_json, "flow_html": flow_html,
        "overview": overview_md, "run": run_json}}


def run(repo, request, out_dir=None, slug=None):
    request = (request or "").strip()
    if not request:
        raise BuildError("missing_flow_request", "Thiếu mô tả flow cần phân tích.",
                         'Ví dụ: --request "Giải thích từ lúc người dùng nhấn xuất báo cáo"')
    root = Path(repo).expanduser()
    if not root.exists():
        raise BuildError("repository_not_found", f"Không thấy repository: {root}",
                         "Kiểm tra lại đường dẫn tuyệt đối tới thư mục repository.")
    root = real_dir(root, "repository_unreadable", "repository")
    if not os.access(root, os.R_OK | os.X_OK):
        raise BuildError("repository_unreadable", f"Không có quyền đọc: {root}")

    artifacts_root = validate_out_dir(root, out_dir)
    slug = safe_slug(slug)

    excluded = {"directory": 0, "test_dir": 0, "sensitive_name": 0, "suffix": 0,
                "symlink_escape": 0, "too_large": 0, "unreadable": 0, "secret_lines": 0}
    files = collect_files(root, excluded)
    git = git_state(root)
    limits = [
        "Phân tích tĩnh trên source; hành vi runtime và dữ liệu thật chưa được kiểm chứng.",
        "Chỉ đọc source trong repository; file bí mật, dump, log và thư mục phụ thuộc bị loại.",
        "Thư mục test/fixture/example/sample/demo bị bỏ qua.",
        "Chưa có call graph đầy đủ: quan hệ bước dựa trên route, import và lời gọi theo tên.",
        "Thứ tự bước phản ánh quan hệ import/gọi hàm, không phải thứ tự thực thi tại runtime.",
    ]
    inventory = []
    for path in files:
        text = read_text(path)
        if text is None:
            continue
        rel = path.relative_to(root).as_posix()
        inventory.append({
            "rel": rel, "text": text, "lines": text.splitlines(),
            "symbols": find_symbols(text), "routes": find_routes(text),
            "entries": find_entries(text), "error_line": has_error_handling(text),
            "response_lines": response_lines(text),
        })

    graph, warnings = build_graph(root, request, inventory, git, limits, excluded)
    related = graph["meta"].get("related", [])

    taken = {entry.name for entry in artifacts_root.iterdir() if entry.is_dir()} \
        if artifacts_root.exists() else set()
    slug = slug or make_slug(request, git, taken)
    if slug in taken:
        raise BuildError("artifact_exists", f"Thư mục artifact đã tồn tại: {slug}",
                         "Bỏ --slug để tự sinh tên mới, hoặc chọn slug khác.")
    artifacts_dir = artifacts_root / slug
    if artifacts_dir.exists():
        raise BuildError("artifact_exists", f"Đường dẫn artifact đã tồn tại: {artifacts_dir}")
    artifacts_root.mkdir(parents=True, exist_ok=True)
    try:
        artifacts_dir.mkdir(parents=False, exist_ok=False)
    except FileExistsError as error:  # concurrent run
        raise BuildError("artifact_exists", f"Thư mục artifact vừa được tạo: {slug}") from error
    except OSError as error:
        raise BuildError("artifact_write_failed", f"Không tạo được thư mục artifact: {error}")

    graph["flow_id"] = slug
    try:
        result = write_outputs(graph, artifacts_dir, root.name, request, excluded,
                               limits, warnings, related)
    except render_flow.FlowError as error:
        raise BuildError("invalid_graph", f"Sơ đồ sinh ra không hợp lệ: {error}") from error
    except OSError as error:
        raise BuildError("artifact_write_failed", f"Không ghi được artifact: {error}")

    return {
        "status": "ok",
        "schema_version": SCHEMA_VERSION,
        "slug": slug,
        "flow_id": graph["flow_id"],
        "repository": str(root),
        "repository_name": root.name,
        "artifacts_dir": str(artifacts_dir),
        "paths": {key: str(value) for key, value in result["paths"].items()},
        "counts": result["counts"],
        "limits": limits,
        "warnings": warnings,
        "related": related,
        "excluded": excluded,
        "source": git,
        "files_scanned": len(files),
    }


def report_error(error, as_json):
    """Structured error on stdout (--json) and stderr; stable exit code."""
    payload = {"status": "error", "code": error.code,
               "message": error.message, "hint": error.hint}
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
    print(f"ERROR [{error.code}]: {error.message}", file=sys.stderr)
    if error.hint:
        print(f"Gợi ý: {error.hint}", file=sys.stderr)
    return 3 if error.code == "internal_error" else 2


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Phân tích repository và sinh flow.json + flow.html + overview.md")
    parser.add_argument("--repo", required=True, type=Path, help="Đường dẫn repository cần phân tích")
    parser.add_argument("--request", required=True, help="Mô tả flow bằng tiếng Việt thông thường")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="Chỉ chấp nhận <repo>/artifacts/flows")
    parser.add_argument("--slug", default=None, help="Tên thư mục artifact; bỏ trống để tự sinh")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="In một object JSON kết quả ra stdout")
    args = parser.parse_args(argv)
    try:
        result = run(args.repo, args.request, args.out_dir, args.slug)
    except BuildError as error:
        return report_error(error, args.as_json)
    except Exception as error:  # noqa: BLE001 - CLI contract: never leak a traceback
        return report_error(BuildError(
            "internal_error",
            f"Lỗi nội bộ khi phân tích: {type(error).__name__}: {error}",
            "Đây là lỗi của tool, không phải của repository; chạy lại với --json để lấy mã lỗi.",
        ), args.as_json)
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"OK: {result['flow_id']} · {sum(result['counts'].values())} node "
              f"({result['counts']}) · {result['files_scanned']} file đã đọc")
        for key, value in result["paths"].items():
            print(f"  {key}: {value}")
        for warning in result["warnings"]:
            print(f"  cảnh báo: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
