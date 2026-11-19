#!/usr/bin/env python3
"""Build a flow graph from a repository plus a natural-language flow request.

Produces three files from ONE analysis result, so they cannot disagree:
  flow.json   machine-readable graph, validated by render_flow.validate
  flow.html   self-contained offline diagram rendered from that same graph
  overview.md Vietnamese explanation of the same graph

Read-only with respect to the analysed repository: this script only reads
source files under the approved root and only writes inside
``<root>/artifacts/flows/<slug>/``. It never uses the network, never executes
repository code, and never copies matched source text into its output.

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

SCHEMA_VERSION = 1
MAX_FILE_BYTES = 256 * 1024
MAX_FILES_SCANNED = 20000
MAX_STEPS = 12
SLUG_MAX = 48

EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "vendor", "bower_components",
    "__pycache__", ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "dist", "build", "target", "out", "coverage", ".next", ".nuxt",
    ".cache", ".gradle", ".idea", ".vscode", "artifacts", ".artifacts",
    "site-packages", "Pods", "DerivedData",
}

EXCLUDED_NAME_PATTERNS = [
    r"^\.env(\..*)?$", r"\.env$", r"^\.env",
    r"(?i)credentials?", r"(?i)secrets?", r"(?i)\.pem$", r"(?i)\.key$", r"(?i)\.p12$",
    r"(?i)\.pfx$", r"(?i)^id_(rsa|dsa|ecdsa|ed25519)", r"(?i)\.keystore$",
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
    r"\s*[:=]\s*['\"]?[A-Za-z0-9/+_\-]{8,}"
)

# Facets turn a Vietnamese/English sentence into code-search terms.
# `code` patterns are language-agnostic on purpose: the builder must work on
# repos it has never seen, and a wrong guess is downgraded by confidence.
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

# Generic entry markers: every web/CLI flow starts at one of these.
ENTRY_PATTERNS = [
    (r"(?i)\b(?:app|router|server|api)\s*\.\s*(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)",
     "route"),
    (r"@\w*(?:app|router|blueprint)\w*\.(?:route|get|post|put|delete)\s*\(\s*['\"]([^'\"]+)", "route"),
    (r"(?i)@(?:Get|Post|Put|Delete|Request)Mapping\s*\(\s*(?:value\s*=\s*)?['\"]([^'\"]+)", "route"),
    (r"(?i)Route::(?:get|post|put|delete)\s*\(\s*['\"]([^'\"]+)", "route"),
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
    (re.compile(r"(?i)\bthrow\s+", re.M), "throw"),
    (re.compile(r"(?i)\braise\s+", re.M), "raise"),
]

RESPONSE_PATTERNS = [
    re.compile(r"(?i)\bres\.(json|send|sendFile|download|render)\s*\("),
    re.compile(r"(?i)\breturn\s+(JsonResponse|HttpResponse|Response|jsonify)\s*\("),
    re.compile(r"(?i)\bJSONResponse\b"),
    re.compile(r"(?i)\bresponse\.(json|send)\b"),
]


class BuildError(Exception):
    """Raised for a request the builder refuses to analyse."""

    def __init__(self, code, message, hint=""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


def strip_diacritics(text):
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def normalize_text(text):
    return re.sub(r"\s+", " ", strip_diacritics(text).lower()).strip()


def utc_now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def is_excluded_name(name):
    return any(re.search(pattern, name) for pattern in EXCLUDED_NAME_PATTERNS)


def resolve_within(root, candidate):
    """Return the real path when it stays inside root, else raise BuildError."""
    real_root = os.path.realpath(str(root))
    real = os.path.realpath(str(candidate))
    if real == real_root or real.startswith(real_root + os.sep):
        return Path(real)
    raise BuildError(
        "path_outside_root",
        f"Đường dẫn nằm ngoài phạm vi cho phép: {candidate}",
        f"Chỉ chấp nhận đường dẫn bên trong {real_root}",
    )


def git_state(root):
    def run(*args):
        try:
            out = subprocess.run(
                ["git", "-C", str(root), *args],
                capture_output=True, text=True, timeout=10, check=False,
            )
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


def collect_files(root, excluded_hits):
    files = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if any(part in EXCLUDED_DIRS for part in Path(rel).parts):
                excluded_hits["directory"] += 1
                continue
            # Example and fixture apps declare their own routes; analysing them
            # instead of the real implementation is a false positive.
            if TEST_DIR_PATTERN.search(rel):
                excluded_hits["test_dir"] += 1
                continue
            if is_excluded_name(name):
                excluded_hits["sensitive_name"] += 1
                continue
            if path.suffix.lower() not in SOURCE_SUFFIXES:
                excluded_hits["suffix"] += 1
                continue
            try:
                real = resolve_within(root, path)
            except BuildError:
                excluded_hits["symlink_escape"] += 1
                continue
            try:
                if real.stat().st_size > MAX_FILE_BYTES:
                    excluded_hits["too_large"] += 1
                    continue
            except OSError:
                excluded_hits["unreadable"] += 1
                continue
            files.append(real)
            if len(files) >= MAX_FILES_SCANNED:
                break
        if len(files) >= MAX_FILES_SCANNED:
            break
    return files


def read_text(path):
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None
    try:
        return raw.decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover - defensive
        return None


def match_facets(request_norm):
    active = []
    for facet in FACETS:
        hits = [kw for kw in facet["keywords"] if kw in request_norm]
        if hits:
            active.append((facet, hits))
    if not active:
        active.append(({
            "id": "generic",
            "label": "luồng xử lý chung",
            "keywords": [],
            "code": [r"(?i)\bhandler\b", r"(?i)\bservice\b", r"(?i)\bcontroller\b"],
            "path": [r"(?i)src", r"(?i)app", r"(?i)services?"],
        }, []))
    return active


def score_file(text, rel, active_facets):
    score = 0
    matched_terms = []
    for facet, _hits in active_facets:
        for pattern in facet["code"]:
            found = len(re.findall(pattern, text))
            if found:
                score += min(found, 6) * 2
                matched_terms.append(f"code:{facet['id']}")
        for pattern in facet["path"]:
            if re.search(pattern, rel):
                score += 3
                matched_terms.append(f"path:{facet['id']}")
    for pattern, kind in ENTRY_PATTERNS:
        if re.search(pattern, text):
            score += 10 if kind == "route" else 4
            matched_terms.append(kind)
    if re.search(r"(?i)\bservice\b|\bservice\.js|\bservices/", rel):
        score += 2
    # Test fixtures and samples declare routes too; without this penalty an
    # example app outranks the real implementation when analysing a repo that
    # ships its own fixtures.
    if re.search(r"(?i)(^|/)(tests?|specs?|__tests__|fixtures?|samples?|examples?|demo)(/|$)", rel):
        score -= 12
    return score, sorted(set(matched_terms))


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


PREFERRED_SYMBOL = re.compile(
    r"(?i)^(main|run|apply|execute|handler|handle|export|process|start|generate|build_flow|build)$")


def pick_symbol(symbols):
    """Prefer an entry-looking function over a class or helper declared first."""
    if not symbols:
        return None
    callables = [item for item in symbols if item.get("kind") != "class"]
    pool = callables or symbols
    preferred = [item for item in pool if PREFERRED_SYMBOL.match(item["name"])]
    if preferred:
        return preferred[0]
    return pool[0]


def find_entries(text):
    entries = []
    for number, line in enumerate(text.splitlines(), start=1):
        for pattern, kind in ENTRY_PATTERNS:
            hit = re.search(pattern, line)
            if hit:
                label = hit.group(hit.lastindex) if hit.lastindex else ""
                entries.append({"line": number, "kind": kind, "label": label})
    return entries


def find_first(text, patterns):
    for pattern in patterns:
        if isinstance(pattern, tuple):
            pattern = pattern[0]
        hit = pattern.search(text) if hasattr(pattern, "search") else re.search(pattern, text)
        if hit:
            line = text.count("\n", 0, hit.start()) + 1
            return line
    return None


def has_error_handling(text):
    for pattern, _kind in ERROR_MARKERS:
        hit = pattern.search(text)
        if hit:
            return text.count("\n", 0, hit.start()) + 1
    return None


def response_lines(text):
    """Every line holding a response call, in file order."""
    lines = set()
    for pattern in RESPONSE_PATTERNS:
        for hit in pattern.finditer(text):
            lines.add(text.count("\n", 0, hit.start()) + 1)
    return sorted(lines)


def route_body_score(text_lines, start_line, end_line, route_label, active_facets):
    """Score one handler body plus its route label against the requested facets."""
    body = "\n".join(text_lines[start_line - 1: end_line])
    score = 0
    for facet, _hits in active_facets:
        for pattern in facet["code"]:
            score += 2 * len(re.findall(pattern, body))
        for pattern in facet["path"]:
            if re.search(pattern, route_label or ""):
                score += 6
    return score


def redacted_summary(symbol, role, rel, line):
    """Describe a step without ever quoting source text."""
    if symbol:
        return f"{role} — hàm/khối `{symbol}` trong `{rel}` (dòng {line})."
    return f"{role} — trong `{rel}` (dòng {line})."


def build_graph(root, request, files, git, limits, excluded):
    request_norm = normalize_text(request)
    active = match_facets(request_norm)

    candidates = []
    for path in files:
        text = read_text(path)
        if text is None:
            continue
        # Count secret-shaped lines so the report can state what was present
        # without ever copying the value.
        excluded["secret_lines"] += len(SECRET_LINE.findall(text))
        rel = path.relative_to(root).as_posix()
        score, terms = score_file(text, rel, active)
        if score <= 0:
            continue
        entries = find_entries(text)
        symbols = find_symbols(text)
        candidates.append({
            "rel": rel,
            "score": score,
            "terms": terms,
            "entries": entries,
            "symbols": symbols,
            "error_line": has_error_handling(text),
            "response_lines": response_lines(text),
            "lines": text.splitlines(),
        })
    candidates.sort(key=lambda item: (-item["score"], item["rel"]))
    selected = candidates[:MAX_STEPS]

    facet_labels = ", ".join(facet["label"] for facet, _ in active)
    nodes = []
    edges = []
    warnings = []

    def add_node(node_id, title, node_type, summary, confidence, refs, **extra):
        node = {
            "id": node_id,
            "title": title,
            "type": node_type,
            "summary": summary,
            "confidence": confidence,
            "source_refs": refs,
        }
        node.update(extra)
        nodes.append(node)

    def add_edge(source, target, label, kind):
        edges.append({"from": source, "to": target, "label": label, "kind": kind})

    def ref(rel, line, symbol=None):
        """Source ref; omit keys the schema would reject when empty."""
        item = {"path": rel, "start_line": int(line)}
        name = (symbol or "").strip()
        if name:
            item["symbol"] = name
        return item

    add_node(
        "start", "Bắt đầu từ yêu cầu", "start",
        f"Người dùng yêu cầu phân tích luồng: “{request.strip()}”. "
        f"Nhóm chủ đề nhận diện được: {facet_labels}.",
        "partial", [],
        details="Điểm vào của sơ đồ do yêu cầu quyết định, không phải một dòng code cụ thể.",
        technical="entry=request",
    )

    if not selected:
        add_node(
            "no-evidence", "Không tìm thấy mã nguồn liên quan", "error",
            "Không file nào trong phạm vi đọc khớp với từ khoá của yêu cầu. "
            "Sơ đồ dừng ở đây thay vì mô tả một luồng không có bằng chứng.",
            "unknown", [],
            details="Cần mô tả flow cụ thể hơn, hoặc repository chưa chứa phần xử lý tương ứng.",
        )
        add_edge("start", "no-evidence", "không khớp mã nguồn", "error")
        limits.append("Không tìm được bằng chứng nào cho yêu cầu này; kết quả chỉ ghi nhận giới hạn.")
    else:
        # The entry is the first candidate that declares a route; a file that
        # only matches keyword patterns is a service, not a starting point.
        routes = []
        for item in selected:
            declared = sorted(
                (entry for entry in item["entries"] if entry["kind"] == "route"),
                key=lambda entry: entry["line"],
            )
            boundaries = [entry["line"] for entry in declared] + [len(item["lines"]) + 1]
            for position, route in enumerate(declared):
                body_end = boundaries[position + 1] - 1
                score = route_body_score(
                    item["lines"], route["line"], body_end, route["label"], active)
                routes.append((score, item, route))
        if routes:
            # A file can hold several endpoints; pick the one whose handler body
            # matches the request, not merely the first route in the file.
            routes.sort(key=lambda row: (-row[0], row[1]["rel"], row[2]["line"]))
            _score, entry_item, entry_route = routes[0]
        else:
            entry_item = next((item for item in selected if item["entries"]), selected[0])
            entry_route = None
        ordered = [entry_item] + [item for item in selected if item is not entry_item]
        entry_symbol = pick_symbol(entry_item["symbols"])
        entry_line = (entry_route or {}).get("line") or (entry_symbol or {}).get("line") or 1
        entry_label = (entry_route or {}).get("label") or (entry_symbol or {}).get("name") or ""

        if entry_route:
            title = f"Nhận yêu cầu {entry_label}"
            role = "Điểm vào HTTP"
        elif entry_symbol:
            title = f"Bắt đầu tại {entry_label}"
            role = "Điểm vào"
        else:
            title = f"Bắt đầu trong {entry_item['rel']}"
            role = "Điểm vào"

        add_node(
            "step-1", title, "action",
            redacted_summary(entry_label or None, role, entry_item["rel"], entry_line),
            "verified",
            [ref(entry_item["rel"], entry_line, entry_label)],
            details=f"Khớp chủ đề: {', '.join(entry_item['terms']) or 'điểm vào chung'}.",
            technical=entry_item["rel"],
            actor="Hệ thống",
        )
        add_edge("start", "step-1", "bắt đầu xử lý", "success")

        previous = "step-1"
        error_inserted = False
        for index, item in enumerate(ordered[1:], start=2):
            symbol = pick_symbol(item["symbols"]) or {}
            symbol_name = symbol.get("name") or ""
            line = (item["entries"][0]["line"] if item["entries"] else None) or \
                   symbol.get("line") or 1
            node_id = f"step-{index}"
            if symbol_name:
                title = f"Xử lý tại {symbol_name}"
            else:
                title = f"Bước trong {item['rel']}"
            add_node(
                node_id, title, "action",
                redacted_summary(symbol_name or None, "Bước xử lý", item["rel"], line),
                "verified",
                [ref(item["rel"], line, symbol_name)],
                details=f"Khớp chủ đề: {', '.join(item['terms']) or 'liên quan yêu cầu'}.",
                technical=item["rel"],
                actor="Hệ thống",
            )
            if item["error_line"] and not error_inserted:
                add_node(
                    "decision-error", "Có lỗi trong bước này?", "decision",
                    "Bước xử lý có nhánh bắt lỗi; sơ đồ tách nhánh thành công và thất bại.",
                    "verified",
                    [ref(item["rel"], item["error_line"])],
                    details="Nhánh lỗi được suy ra từ việc xuất hiện xử lý ngoại lệ trong file.",
                )
                add_node(
                    "error-branch", "Trả lỗi cho người gọi", "error",
                    "Lỗi được bắt và trả về cho lớp gọi thay vì kết thúc im lặng.",
                    "partial",
                    [ref(item["rel"], item["error_line"])],
                    details="Chưa xác minh nội dung thông báo lỗi và mã lỗi cụ thể.",
                )
                add_edge(previous, "decision-error", "vào bước xử lý", "normal")
                add_edge("decision-error", "error-branch", "có lỗi", "error")
                add_edge("decision-error", node_id, "không lỗi", "success")
                error_inserted = True
                previous = node_id
                continue
            add_edge(previous, node_id, "tiếp tục", "normal")
            previous = node_id

        response_pick = None
        for item in ordered:
            after = [line for line in item["response_lines"] if line >= (entry_line if item is entry_item else 1)]
            if after:
                response_pick = (item, after[0])
                break
        if response_pick:
            response_item, response_line = response_pick
            add_node(
                "end", "Trả kết quả", "end",
                f"Kết quả được trả về từ `{response_item['rel']}`.",
                "verified", [ref(response_item["rel"], response_line)],
                details="Điểm kết thúc xác định theo lời gọi trả kết quả trong code.",
            )
        else:
            add_node(
                "end", "Kết thúc xử lý", "end",
                "Không tìm thấy lời gọi trả kết quả rõ ràng; điểm kết thúc được suy ra từ bước cuối.",
                "inferred", [],
                details="Chưa xác minh được nơi trả kết quả cho người dùng.",
            )
            limits.append("Không tìm thấy điểm trả kết quả rõ ràng; node kết thúc là suy luận.")
        add_edge(previous, "end", "hoàn tất", "success")

        if len(candidates) > len(selected):
            warnings.append(
                f"Còn {len(candidates) - len(selected)} file khớp chủ đề nhưng vượt giới hạn "
                f"{MAX_STEPS} bước; sơ đồ chỉ phản ánh phần đã chọn."
            )
        if not entry_route:
            limits.append(
                "Không thấy khai báo route/handler cho yêu cầu này; điểm vào là hàm đầu tiên khớp chủ đề."
            )

    # "Luồng: luồng thanh toán" reads badly; drop a leading flow word.
    title_topic = re.sub(
        r"(?i)^\s*(?:luồng|luong|quy trình|quy trinh|flow)\s*[:\-–]?\s*", "", request.strip())
    title_topic = (title_topic or request.strip())[:120]

    graph = {
        "flow_id": "",
        "title": f"Luồng: {title_topic}",
        "description": (
            f"Sơ đồ dựng từ phân tích tĩnh repository {root.name or str(root)}, "
            f"theo yêu cầu: {request.strip()}. Mọi bước đều trỏ tới file và dòng thật; "
            f"phần chưa chứng minh được đánh dấu tin cậy thấp."
        ),
        "audience": "Người không đọc code, BA, kiểm thử",
        "scope": f"Đọc source trong {root} · {facet_labels}",
        "entry_node": "start",
        "nodes": nodes,
        "edges": edges,
        "assumptions": limits + warnings,
        "notes": (
            "Phân tích tĩnh, không chạy code của repository, không dùng network. "
            "Bước đánh dấu verified trỏ tới đúng file và dòng khai báo; "
            "bước partial/inferred là suy luận từ cấu trúc code."
        ),
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "generated_at": utc_now(),
            "source": git,
            "request": request.strip(),
            "facets": [facet["id"] for facet, _ in active],
            "files_scanned": len(files),
        },
    }
    return graph, warnings


def make_slug(request, root, git, taken):
    base = strip_diacritics(request).lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    words = [word for word in base.split("-") if word][:6]
    digest = hashlib.sha1(
        f"{root}|{request}|{git.get('commit')}".encode("utf-8")
    ).hexdigest()[:6]
    slug = "-".join(words + [digest])[:SLUG_MAX].strip("-")
    candidate = slug
    counter = 2
    while candidate in taken:
        suffix = f"-{counter}"
        candidate = (slug[: SLUG_MAX - len(suffix)] + suffix).strip("-")
        counter += 1
        if counter > 50:
            raise BuildError("slug_exhausted", "Không tạo được thư mục artifact không trùng tên")
    return candidate


def render_overview(graph, root, request, excluded, limits, warnings, artifacts):
    rows = []
    for index, node in enumerate(graph["nodes"], start=1):
        ref = (node.get("source_refs") or [{}])[0]
        evidence = "—"
        if ref.get("path"):
            evidence = f"`{ref['path']}`"
            if ref.get("start_line"):
                evidence += f":{ref['start_line']}"
        rows.append(
            f"| {index} | {node['title']} | {node['type']} | {node['confidence']} | {evidence} |"
        )

    excluded_lines = "\n".join(
        f"- {key}: {value}" for key, value in sorted(excluded.items()) if value
    ) or "- Không có mục nào bị loại."

    limits_lines = "\n".join(f"- {item}" for item in limits) or "- Không có giới hạn bổ sung."
    warnings_lines = "\n".join(f"- {item}" for item in warnings) or "- Không có cảnh báo."
    source = graph["meta"]["source"]

    return f"""# {graph['title']}

Sinh tự động: {graph['meta']['generated_at']} · công cụ: `scripts/build_flow.py` (schema {SCHEMA_VERSION}).

## Yêu cầu

> {request.strip()}

## Repository được phân tích

| Mục | Giá trị |
|---|---|
| Đường dẫn | `{root}` |
| Nhánh | `{source.get('branch') or 'không có git'}` |
| Commit | `{source.get('commit') or 'không có git'}` |
| Thay đổi chưa commit | {'có — ' + str(source.get('dirty_files')) + ' file' if source.get('dirty') else 'không'} |
| File đã đọc | {graph['meta']['files_scanned']} |

## Luồng xử lý

{graph['description']}

| # | Bước | Loại | Tin cậy | Bằng chứng |
|---|---|---|---|---|
{chr(10).join(rows)}

## Quan hệ giữa các bước

{chr(10).join(f"- {edge['from']} → {edge['to']} · `{edge['label']}` · {edge['kind']}" for edge in graph['edges'])}

## Thành phần chính

{chr(10).join(f"- `{node.get('technical') or (node.get('source_refs') or [{}])[0].get('path') or '—'}` — {node['title']}" for node in graph['nodes'] if node.get('technical') or node.get('source_refs'))}

## Giới hạn và phần chưa xác minh

{limits_lines}

{warnings_lines}

## Phạm vi đọc và loại trừ

Chỉ đọc file source trong root ở trên. Các mục sau bị loại khỏi phân tích:

{excluded_lines}

Tool không gọi network, không chạy code của repository, không sửa file nguồn. Nội dung source không được chép vào báo cáo này; chỉ tên file, số dòng và tên hàm/khối.

## Tệp sinh ra

- `flow.json` — dữ liệu có cấu trúc, dùng lại được cho lần render sau
- `flow.html` — sơ đồ mở offline
- `overview.md` — tài liệu này
"""


def write_outputs(graph, artifacts_dir, root, request, excluded, limits, warnings):
    flow_json = artifacts_dir / "flow.json"
    flow_html = artifacts_dir / "flow.html"
    overview_md = artifacts_dir / "overview.md"
    run_json = artifacts_dir / "run.json"

    info = render_flow.validate(graph)
    render_flow.assign_positions(graph, info)
    flow_json.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    flow_html.write_text(render_flow.render_json(graph), encoding="utf-8")
    overview_md.write_text(
        render_overview(graph, root, request, excluded, limits, warnings, artifacts_dir),
        encoding="utf-8",
    )
    counts = {"verified": 0, "partial": 0, "inferred": 0, "unknown": 0}
    for node in graph["nodes"]:
        counts[node["confidence"]] = counts.get(node["confidence"], 0) + 1
    run_json.write_text(json.dumps({
        "status": "ok",
        "flow_id": graph["flow_id"],
        "generated_at": graph["meta"]["generated_at"],
        "repository": str(root),
        "request": request,
        "source": graph["meta"]["source"],
        "counts": counts,
        "limits": limits,
        "warnings": warnings,
        "excluded": excluded,
        "files": [flow_json.name, flow_html.name, overview_md.name, run_json.name],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"counts": counts, "paths": {
        "flow_json": flow_json,
        "flow_html": flow_html,
        "overview": overview_md,
        "run": run_json,
    }}


def run(repo, request, out_dir=None, slug=None):
    request = (request or "").strip()
    if not request:
        raise BuildError(
            "missing_flow_request",
            "Thiếu mô tả flow cần phân tích.",
            'Ví dụ: --request "Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file"',
        )
    root = Path(repo).expanduser()
    if not root.exists():
        raise BuildError("repository_not_found", f"Không thấy repository: {root}",
                         "Kiểm tra lại đường dẫn tuyệt đối tới thư mục repository.")
    if not root.is_dir():
        raise BuildError("repository_not_directory", f"Đường dẫn không phải thư mục: {root}")
    if not os.access(root, os.R_OK | os.X_OK):
        raise BuildError("repository_unreadable", f"Không có quyền đọc thư mục: {root}")
    root = Path(os.path.realpath(str(root)))

    target_out = Path(out_dir).expanduser() if out_dir else root / "artifacts" / "flows"
    if not target_out.is_absolute():
        target_out = root / target_out
    artifacts_root = resolve_within(root, target_out)

    excluded = {"directory": 0, "sensitive_name": 0, "suffix": 0,
                "symlink_escape": 0, "too_large": 0, "unreadable": 0,
                "test_dir": 0, "secret_lines": 0}
    files = collect_files(root, excluded)
    git = git_state(root)
    limits = [
        "Phân tích tĩnh trên source; hành vi runtime, dữ liệu thật và cấu hình môi trường chưa được kiểm chứng.",
        "Không chép nội dung source vào kết quả; chỉ ghi tên file, số dòng và tên hàm/khối.",
        "Chỉ đọc file source trong repository; file cấu hình bí mật, dump, log và thư mục phụ thuộc bị loại trừ.",
        "Thư mục test/fixture/example/sample/demo bị bỏ qua để không phân tích nhầm ứng dụng mẫu.",
    ]
    graph, warnings = build_graph(root, request, files, git, limits, excluded)

    artifacts_root.mkdir(parents=True, exist_ok=True)
    taken = {entry.name for entry in artifacts_root.iterdir() if entry.is_dir()}
    slug = slug or make_slug(request, root, git, taken)
    if slug in taken:
        raise BuildError(
            "artifact_exists",
            f"Thư mục artifact đã tồn tại: {artifacts_root / slug}",
            "Bỏ --slug để tự sinh tên mới, hoặc chọn slug khác.",
        )
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", slug).strip("-")[:SLUG_MAX] or "flow"
    artifacts_dir = resolve_within(root, artifacts_root / slug)
    artifacts_dir.mkdir(parents=True, exist_ok=False)

    graph["flow_id"] = slug
    try:
        result = write_outputs(graph, artifacts_dir, root, request, excluded, limits, warnings)
    except render_flow.FlowError as error:
        raise BuildError("invalid_graph", f"Sơ đồ sinh ra không hợp lệ: {error}") from error

    return {
        "status": "ok",
        "slug": slug,
        "flow_id": graph["flow_id"],
        "repository": str(root),
        "artifacts_dir": str(artifacts_dir),
        "paths": {key: str(value) for key, value in result["paths"].items()},
        "counts": result["counts"],
        "limits": limits,
        "warnings": warnings,
        "excluded": excluded,
        "source": git,
        "files_scanned": len(files),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Phân tích repository và sinh flow.json + flow.html + overview.md")
    parser.add_argument("--repo", required=True, type=Path, help="Đường dẫn repository cần phân tích")
    parser.add_argument("--request", required=True, help="Mô tả flow bằng tiếng Việt thông thường")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="Thư mục gốc chứa artifact (mặc định <repo>/artifacts/flows)")
    parser.add_argument("--slug", default=None, help="Tên thư mục artifact; bỏ trống để tự sinh")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="In một object JSON kết quả ra stdout")
    args = parser.parse_args(argv)
    try:
        result = run(args.repo, args.request, args.out_dir, args.slug)
    except BuildError as error:
        payload = {"status": "error", "code": error.code, "message": error.message,
                   "hint": error.hint}
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False))
        print(f"ERROR [{error.code}]: {error.message}", file=sys.stderr)
        if error.hint:
            print(f"Gợi ý: {error.hint}", file=sys.stderr)
        return 2
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
