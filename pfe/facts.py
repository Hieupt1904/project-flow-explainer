"""Static facts extracted from a repository: the single scanner for every layer.

The scanner is read-only, network-free and content-preserving: it records file
paths, line numbers, symbol names, import specifiers, call sites and error
sites. It never executes repository code, never copies matched source text into
an output document and never indexes a sensitive file.

Budgets are enforced here so both the flow projection and the knowledge index
degrade the same way: file count, per-file size and total source bytes. Every
truncation is reported in ScanBudget.notes and therefore appears in
limits/warnings instead of silently shrinking the analysis.
"""

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .policy import BuildError, artifact_root_for, is_inside

BACKTICK = chr(96)

MAX_FILE_BYTES = 256 * 1024
MAX_TOTAL_SOURCE_BYTES = 32 * 1024 * 1024
MAX_FILES_SCANNED = 20000
MAX_DOC_CHARS = 4000

EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "vendor", "bower_components",
    "__pycache__", ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "dist", "build", "target", "out", "coverage", ".next", ".nuxt",
    ".cache", ".gradle", ".idea", ".vscode", "artifacts", ".artifacts", ".pfe",
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

LANGUAGES = {
    ".py": "python", ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".vue": "vue", ".svelte": "svelte", ".php": "php", ".java": "java",
    ".kt": "kotlin", ".rb": "ruby", ".go": "go", ".rs": "rust", ".cs": "csharp",
    ".sql": "sql", ".sh": "shell",
}

SECRET_LINE = re.compile(
    r"(?i)(api[_-]?key|secret|passwd|password|token|private[_-]?key|access[_-]?key)"
    r"\s*[:=]\s*['\"]?[A-Za-z0-9/+_\-]{8,}")

ROUTE_PATTERNS = [
    re.compile(r"(?i)\b(?:app|router|server|api)\s*\.\s*(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)"),
    re.compile(r"@\w*(?:app|router|blueprint)\w*\.(?:route|get|post|put|delete)\s*\(\s*['\"]([^'\"]+)"),
    re.compile(r"(?i)@(?:Get|Post|Put|Delete|Request)Mapping\s*\(\s*(?:value\s*=\s*)?['\"]([^'\"]+)"),
    re.compile(r"(?i)Route::(?:get|post|put|delete)\s*\(\s*['\"]([^'\"]+)"),
    # Flask/FastAPI blueprint decorators: the object is often named `bp` or
    # `api_blueprint`, which the named forms above do not catch. The decorator
    # line itself is the evidence; nothing is inferred from the function name.
    re.compile(r"^\s*@[A-Za-z_][\w.]*\.(?:route|get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)"),
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
    (re.compile(r"^\s*try\s*[{(:]"), "try"),
    (re.compile(r"^\s*except\b"), "except"),
    (re.compile(r"(?i)\bcatch\s*\("), "catch"),
    (re.compile(r"(?i)\brescue\b"), "rescue"),
]

RAISE_MARKERS = [
    (re.compile(r"^\s*raise\s+([A-Za-z_][\w.]*)"), "python-raise"),
    (re.compile(r"(?i)\bthrow\s+new\s+([A-Za-z_][\w.]*)"), "js-throw"),
    (re.compile(r"(?i)\bthrow\s+([A-Za-z_][\w.]*)\s*\("), "js-throw"),
]

RESPONSE_PATTERNS = [
    re.compile(r"(?i)\bres\.(json|send|sendFile|download|render)\s*\("),
    re.compile(r"(?i)\breturn\s+(JsonResponse|HttpResponse|Response|jsonify)\s*\("),
    re.compile(r"(?i)\bJSONResponse\b"),
    re.compile(r"(?i)\bresponse\.(json|send)\b"),
]

IMPORT_PATTERNS = [
    re.compile(r"""(?i)(?:require|from)\s*\(?\s*['"](\.[^'"]+)['"]"""),
    re.compile(r"""^\s*from\s+(\.[\w.]*)\s+import\b""", re.M),
    re.compile(r"""^\s*import\s+([\w.]+)\b""", re.M),
    re.compile(r"""^\s*from\s+([\w.]+)\s+import\b""", re.M),
]

EXTERNAL_IMPORT_PATTERNS = [
    re.compile(r"""(?i)(?:require|from)\s*\(?\s*['"]([^.'"][^'"]*)['"]"""),
    re.compile(r"""^\s*import\s+([A-Za-z_][\w.]*)\b""", re.M),
    re.compile(r"""^\s*from\s+([A-Za-z_][\w.]*)\s+import\b""", re.M),
]

CALL_RE = re.compile(r"(?<![\w.$])([A-Za-z_]\w*)\s*\(")
CALL_KEYWORDS = {
    "if", "for", "while", "switch", "catch", "return", "function", "def", "class",
    "new", "typeof", "await", "async", "with", "print", "super", "self", "throw",
    "else", "elif", "except", "yield", "lambda", "import", "from", "require",
}

SQL_READ = re.compile(r"(?i)\bselect\b[\s\S]{0,200}?\bfrom\s+([A-Za-z_][\w.]*)")
SQL_WRITE = re.compile(r"(?i)\b(?:insert\s+into|update|replace\s+into|delete\s+from)\s+([A-Za-z_][\w.]*)")

EXPORT_PATTERNS = [
    re.compile(r"(?i)module\.exports\s*=\s*\{?([^}\n]*)"),
    re.compile(r"(?i)^\s*export\s+(?:async\s+)?(?:function|class|const|let|var)\s+([A-Za-z_]\w*)", re.M),
    re.compile(r"""__all__\s*=\s*\[([^\]]*)\]"""),
]

COMMENT_LINE = re.compile(r"^\s*(?:#|//|/\*|\*|<!--)")

# Entry points are recognised from a registration line, never from a name.
# Each pattern proves *how* control enters the code; a function merely called
# "handle_click" is not an entry point without a binding or a decorator.
ENTRY_POINT_PATTERNS = [
    (re.compile(r"^\s*if\s+__name__\s*==\s*['\"]__main__['\"]"), "main"),
    (re.compile(r"^\s*if\s+__name__\s*==\s*['\"]__main__['\"]\s*:"), "main"),
    (re.compile(r"\.add_parser\s*\(\s*['\"]([\w.-]+)['\"]"), "cli_command"),
    (re.compile(r"^\s*@(?:click|typer)\.(?:command|group)\b"), "cli_command"),
    (re.compile(r"\bcommand\s*=\s*([A-Za-z_][\w.]*)"), "gui_event"),
    (re.compile(r"\.clicked\.connect\s*\(\s*([A-Za-z_][\w.]*)"), "button_click"),
    (re.compile(r"\.bind\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*([A-Za-z_][\w.]*)"), "gui_event"),
    (re.compile(r"^\s*@[\w.]*\btask\b"), "worker"),
    (re.compile(r"\.addEventListener\s*\(\s*['\"]([^'\"]+)['\"]"), "callback"),
    (re.compile(r"\bafter\s*\(\s*\d+\s*,"), "callback"),
    (re.compile(r"\bcallback\s*=\s*([A-Za-z_][\w.]*)"), "callback"),
]

# Only an explicit public list is a public API declaration. `module.exports` is
# a module boundary every JavaScript file has, so counting it as an entry point
# would put every file in the context pack.
PUBLIC_API_LINE = re.compile(r"^\s*__all__\s*=")


BARE_MAIN_RE = re.compile(r"^\s*(?:async\s+)?def\s+(main)\s*\(")
MAIN_GUARD_RE = re.compile(r"^\s*if\s+__name__\s*==\s*['\"]__main__['\"]")


def find_entry_points(lines):
    """Return entry points with the evidence quality that proves them.

    Only registration syntax counts as `observed`: a decorator, a binding, a
    parser registration, an export list, a `__main__` guard. A bare `def main()`
    is *likely* an entry point — plenty of files define one and never call it, or
    call it only from a guard that lives elsewhere — so it is reported as
    `structural` unless the same file also has the guard.
    """
    guarded = any(MAIN_GUARD_RE.search(line) for line in lines)
    found = []
    seen = set()
    for number, line in enumerate(lines, start=1):
        for regex, kind in ENTRY_POINT_PATTERNS:
            match = regex.search(line)
            if not match:
                continue
            label = ""
            for group in match.groups():
                if group:
                    label = group
                    break
            key = (kind, number, label)
            if key in seen:
                continue
            seen.add(key)
            found.append({"kind": kind, "line": number, "label": label,
                          "evidence_kind": "observed"})
        if PUBLIC_API_LINE.search(line):
            found.append({"kind": "public_api", "line": number, "label": "",
                          "evidence_kind": "observed"})
        bare = BARE_MAIN_RE.search(line)
        if bare:
            key = ("main", number, bare.group(1) or "")
            if key not in seen:
                seen.add(key)
                found.append({"kind": "main", "line": number, "label": "main",
                              "evidence_kind": "observed" if guarded else "structural"})
    return found


def is_excluded_name(name):
    return any(re.search(pattern, name) for pattern in EXCLUDED_NAME_PATTERNS)


def is_excluded_dir(name):
    return name in EXCLUDED_DIRS


def language_of(path):
    return LANGUAGES.get(Path(path).suffix.lower(), "unknown")


@dataclass
class ScanBudget:
    notes: list = field(default_factory=list)
    total_bytes: int = 0
    truncated_files: bool = False
    truncated_bytes: bool = False
    symlinks_blocked: int = 0

    def note(self, message):
        if message not in self.notes:
            self.notes.append(message)


@dataclass
class FileFacts:
    """Everything the flow projection and the knowledge index need for one file."""

    rel: str
    real: str
    size: int
    language: str
    lines: list
    content_hash: str
    symbols: list = field(default_factory=list)
    routes: list = field(default_factory=list)
    entries: list = field(default_factory=list)
    imports: list = field(default_factory=list)
    external_imports: list = field(default_factory=list)
    call_sites: list = field(default_factory=list)
    response_lines: list = field(default_factory=list)
    error_sites: list = field(default_factory=list)
    raise_sites: list = field(default_factory=list)
    exports: list = field(default_factory=list)
    reads: list = field(default_factory=list)
    writes: list = field(default_factory=list)
    doc: str = ""
    secret_lines: int = 0
    is_test: bool = False
    last_commit: str = ""
    identifiers: list = field(default_factory=list)
    entry_points: list = field(default_factory=list)

    @property
    def line_count(self):
        return len(self.lines)

    def text(self):
        return "\n".join(self.lines)

    def window(self, start, end=None):
        """1-based inclusive line window as text (route/handler bodies)."""
        end = self.line_count if end is None else min(end, self.line_count)
        return "\n".join(self.lines[max(start, 1) - 1: max(end, 0)])

    def symbol_at(self, line):
        candidates = [item for item in self.symbols if item["line"] <= line]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item["line"])

    def body_range(self, line):
        """Body of the symbol that owns this line: (start, end) or None."""
        symbol = self.symbol_at(line)
        if symbol is None:
            return None
        following = [item["line"] for item in self.symbols if item["line"] > symbol["line"]]
        end = (min(following) - 1) if following else self.line_count
        return (symbol["line"], end)

    def route_range(self, index):
        start = self.routes[index]["line"]
        end = self.routes[index + 1]["line"] - 1 if index + 1 < len(self.routes) else self.line_count
        return (start, end)


def read_lines(path):
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None
    return raw.decode("utf-8", errors="replace").split("\n")


def _scan_window(lines, patterns):
    hits = []
    for number, line in enumerate(lines, start=1):
        for regex, kind in patterns:
            if regex.search(line):
                hits.append({"line": number, "kind": kind})
                break
    return hits


def find_symbols(lines):
    symbols = []
    for number, line in enumerate(lines, start=1):
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


def find_routes(lines):
    routes = []
    for number, line in enumerate(lines, start=1):
        for regex in ROUTE_PATTERNS:
            hit = regex.search(line)
            if hit:
                groups = hit.groups()
                routes.append({"line": number, "label": groups[-1],
                               "method": groups[0] if len(groups) > 1 else ""})
                break
    return routes


def find_entries(lines):
    entries = []
    for number, line in enumerate(lines, start=1):
        for pattern, kind in ENTRY_PATTERNS:
            hit = re.search(pattern, line)
            if hit:
                entries.append({"line": number, "kind": kind, "label": hit.group(1)})
    return entries


def find_imports(text, rel, known, basenames=None):
    """Resolve import specifiers to repository-relative source paths.

    Three shapes are supported: relative specs, dotted absolute specs, and flat
    specs that only work because the entry file extends sys.path. The flat shape
    is matched by unique basename; an ambiguous basename stays unresolved rather
    than guessed. basenames is precomputed once per scan, so resolution never
    walks the whole known-path set again.
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
            for candidate in (stem + suffix, stem + "/index" + suffix, stem + "/__init__.py"):
                if candidate in known and candidate != rel:
                    yield candidate

    for regex in IMPORT_PATTERNS:
        for hit in regex.finditer(text):
            spec = hit.group(1)
            if re.match(r"^\.", spec):
                stem, style = resolve_relative(spec), "relative"
            elif "/" in spec:
                stem, style = spec.lstrip("/"), "relative"
            elif "." in spec:
                stem, style = spec.replace(".", "/"), "dotted"
            else:
                stem, style = spec, "flat"
            found = list(candidates_for(stem))
            if not found and style == "flat" and basenames is not None:
                matches = sorted(path for path in basenames.get(spec, ()) if path != rel)
                if len(matches) == 1:
                    found, style = matches, "flat-basename"
            line = text.count("\n", 0, hit.start()) + 1
            for target in found:
                targets.append({"path": target, "style": style, "line": line, "spec": spec})
    deduped = {}
    for item in targets:
        deduped.setdefault((item["path"], item["style"]), item)
    return [deduped[key] for key in sorted(deduped)]


def find_external_imports(text):
    found = set()
    for regex in EXTERNAL_IMPORT_PATTERNS:
        for hit in regex.finditer(text):
            spec = hit.group(1)
            if spec.startswith("."):
                continue
            parts = spec.split("/")
            found.add("/".join(parts[:2]) if spec.startswith("@") else parts[0])
    return sorted(found)


def find_call_sites(lines, symbols):
    """Call sites with the enclosing symbol and the line performing the call.

    This is a lexical call-site reader, not a type-aware call graph: a call is
    attributed to the nearest preceding declaration in the same file. Every hit
    keeps its line so an edge can point at the call itself instead of at the
    callee declaration.
    """
    sites = []
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//", "*", "/*")):
            continue
        for hit in CALL_RE.finditer(line):
            name = hit.group(1)
            if name in CALL_KEYWORDS or name.startswith("__"):
                continue
            owner = None
            for symbol in symbols:
                if symbol["line"] <= number:
                    owner = symbol
                else:
                    break
            sites.append({"name": name, "line": number,
                          "caller": owner["name"] if owner else ""})
    return sites


def find_exports(text, symbols):
    exported = set()
    for regex in EXPORT_PATTERNS:
        for hit in regex.finditer(text):
            for token in re.split(r"[,{}\s]+", hit.group(1)):
                token = token.strip().strip("'\"")
                if token and re.match(r"^[A-Za-z_]\w*$", token):
                    exported.add(token)
    lines = text.split("\n")
    for symbol in symbols:
        if symbol["name"] in exported:
            continue
        index = symbol["line"] - 1
        if 0 <= index < len(lines) and re.search(r"(?i)\bexport\b", lines[index]):
            exported.add(symbol["name"])
    return sorted(exported)


def find_sql(text):
    strip_chars = '"[]' + BACKTICK
    reads = sorted({match.group(1).strip(strip_chars) for match in SQL_READ.finditer(text)})
    writes = sorted({match.group(1).strip(strip_chars) for match in SQL_WRITE.finditer(text)})
    return reads, writes


def collect_doc(lines):
    """Comment/docstring text used for search only; never returned raw."""
    chunks = []
    total = 0
    for line in lines:
        stripped = line.strip()
        if COMMENT_LINE.match(line) or stripped.startswith('"""') or stripped.startswith("'''"):
            cleaned = re.sub(r"^\s*(?:#|//|/\*+|\*+|<!--)\s?", "", line).strip()
            cleaned = cleaned.strip('"')
            cleaned = cleaned.strip("'")
            cleaned = re.sub(r"\s*(?:\*/|-->)\s*$", "", cleaned)
            if cleaned and len(cleaned) < 400:
                chunks.append(cleaned)
                total += len(cleaned)
                if total >= MAX_DOC_CHARS:
                    break
    return " ".join(chunks)[:MAX_DOC_CHARS]


def scrub_secret_lines(lines):
    """Blank secret-shaped lines so no value can enter an index document."""
    return ["" if SECRET_LINE.search(line) else line for line in lines]


def scan_repository(root, *, include_tests=False, max_files=MAX_FILES_SCANNED,
                    max_file_bytes=MAX_FILE_BYTES, max_total_bytes=MAX_TOTAL_SOURCE_BYTES):
    """Read the repository and return (files, excluded, budget).

    A symlinked file is accepted only when its canonical target is inside the
    repository, lives outside artifact/index directories, is not a test/example
    directory when tests are excluded, and its resolved name is not sensitive.
    Otherwise the link is counted in excluded and dropped.
    """
    root = Path(os.path.realpath(str(root)))
    artifacts = None
    try:
        artifacts = Path(os.path.realpath(str(artifact_root_for(root).parent)))
    except BuildError:
        artifacts = None
    index_root = root / ".pfe"

    excluded = {"directory": 0, "test_dir": 0, "sensitive_name": 0, "suffix": 0,
                "symlink_escape": 0, "symlink_sensitive": 0, "too_large": 0,
                "unreadable": 0, "secret_lines": 0, "budget_files": 0, "budget_bytes": 0}
    budget = ScanBudget()
    files = []
    total = 0

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not is_excluded_dir(d))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                excluded["symlink_escape"] += 1
                continue
            if any(part in EXCLUDED_DIRS for part in Path(rel).parts):
                excluded["directory"] += 1
                continue
            is_test = bool(TEST_DIR_PATTERN.search(rel))
            if is_test and not include_tests:
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
                budget.symlinks_blocked += 1
                continue
            if real.is_symlink() and is_excluded_name(real.name):
                excluded["symlink_sensitive"] += 1
                budget.symlinks_blocked += 1
                continue
            if (artifacts is not None and is_inside(artifacts, real)) or is_inside(index_root, real):
                excluded["symlink_sensitive"] += 1
                budget.symlinks_blocked += 1
                continue
            try:
                size = real.stat().st_size
            except OSError:
                excluded["unreadable"] += 1
                continue
            if size > max_file_bytes:
                excluded["too_large"] += 1
                budget.note("Bỏ qua file lớn hơn " + str(max_file_bytes // 1024) + " KB: " + rel)
                continue
            if len(files) >= max_files:
                excluded["budget_files"] += 1
                budget.truncated_files = True
                continue
            if total + size > max_total_bytes:
                excluded["budget_bytes"] += 1
                budget.truncated_bytes = True
                continue
            lines = read_lines(real)
            if lines is None:
                excluded["unreadable"] += 1
                continue
            total += size
            budget.total_bytes = total
            files.append(_facts_from(rel, str(real), lines, size, is_test))
    if budget.truncated_files:
        budget.note("Dừng ở " + str(max_files) + " file (ngân sách đọc); phần còn lại chưa được phân tích.")
    if budget.truncated_bytes:
        budget.note("Dừng ở " + str(max_total_bytes // (1024 * 1024)) + " MB source (ngân sách bộ nhớ).")
    return files, excluded, budget


def classify_source(root, rel, name, is_test, real, artifacts, index_root):
    """One classification authority for every walker in the package.

    Returns (ok, reason). Reasons are stable strings so excluded counts stay
    explainable and a regression test can prove the two walkers agree.
    """
    if any(part in EXCLUDED_DIRS for part in Path(rel).parts):
        return False, "directory"
    if is_test:
        return False, "test_dir"
    if is_excluded_name(name):
        return False, "sensitive_name"
    if is_excluded_name(Path(real).name):
        # A symlink with an innocent name pointing at .env / a key file.
        return False, "symlink_sensitive"
    if Path(rel).suffix.lower() not in SOURCE_SUFFIXES:
        return False, "suffix"
    if not is_inside(root, real):
        return False, "symlink_escape"
    if Path(real).is_symlink() and is_excluded_name(Path(real).name):
        return False, "symlink_sensitive"
    if (artifacts is not None and is_inside(artifacts, real)) or is_inside(index_root, real):
        return False, "symlink_sensitive"
    return True, ""


@dataclass
class SourceEntry:
    """A file that survived classification, before any parsing happens."""

    rel: str
    real: str
    size: int
    mtime_ns: int
    is_test: bool


def walk_sources(root, *, include_tests=False, max_files=MAX_FILES_SCANNED,
                 max_file_bytes=MAX_FILE_BYTES, max_total_bytes=MAX_TOTAL_SOURCE_BYTES):
    """Walk the repository and classify files without parsing them.

    Parsing is deliberately separate: the incremental index only hashes here, so
    an unchanged file is never re-parsed (no symbol, route or call extraction).
    """
    root = Path(os.path.realpath(str(root)))
    try:
        artifacts = Path(os.path.realpath(str(artifact_root_for(root).parent)))
    except BuildError:
        artifacts = None
    index_root = root / ".pfe"
    excluded = {"directory": 0, "test_dir": 0, "sensitive_name": 0, "suffix": 0,
                "symlink_escape": 0, "symlink_sensitive": 0, "too_large": 0,
                "unreadable": 0, "budget_files": 0, "budget_bytes": 0}
    budget = ScanBudget()
    entries = []
    total = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not is_excluded_dir(d))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                excluded["symlink_escape"] += 1
                continue
            real = Path(os.path.realpath(str(path)))
            is_test = bool(TEST_DIR_PATTERN.search(rel))
            if is_test and not include_tests:
                excluded["test_dir"] += 1
                continue
            ok, reason = classify_source(root, rel, name, False, real, artifacts, index_root)
            if not ok:
                excluded[reason] = excluded.get(reason, 0) + 1
                if "symlink" in reason:
                    budget.symlinks_blocked += 1
                continue
            try:
                stat = real.stat()
            except OSError:
                excluded["unreadable"] += 1
                continue
            if stat.st_size > max_file_bytes:
                excluded["too_large"] += 1
                budget.note("Bỏ qua file lớn hơn " + str(max_file_bytes // 1024) + " KB: " + rel)
                continue
            if len(entries) >= max_files:
                excluded["budget_files"] += 1
                budget.truncated_files = True
                continue
            if total + stat.st_size > max_total_bytes:
                excluded["budget_bytes"] += 1
                budget.truncated_bytes = True
                continue
            total += stat.st_size
            budget.total_bytes = total
            entries.append(SourceEntry(rel=rel, real=str(real), size=stat.st_size,
                                       mtime_ns=stat.st_mtime_ns, is_test=is_test))
    if budget.truncated_files:
        budget.note("Dừng ở " + str(max_files) + " file (ngân sách đọc).")
    if budget.truncated_bytes:
        budget.note("Dừng ở " + str(max_total_bytes // (1024 * 1024)) + " MB source (ngân sách bộ nhớ).")
    return entries, excluded, budget


def hash_file(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return ""


def parse_entry(entry):
    """Parse one walked file into FileFacts (this is what incremental reuses)."""
    lines = read_lines(Path(entry.real))
    if lines is None:
        return None
    return _facts_from(entry.rel, entry.real, lines, entry.size, entry.is_test)


def _facts_from(rel, real, lines, size, is_test):
    text = "\n".join(lines)
    symbols = find_symbols(lines)
    facts = FileFacts(
        rel=rel, real=real, size=size, language=language_of(rel), lines=lines,
        content_hash=hashlib.sha256(text.encode("utf-8", "replace")).hexdigest(),
        symbols=symbols, routes=find_routes(lines), entries=find_entries(lines),
        entry_points=find_entry_points(lines),
        external_imports=find_external_imports(text),
        call_sites=find_call_sites(lines, symbols),
        response_lines=response_lines(lines),
        error_sites=_scan_window(lines, ERROR_MARKERS),
        raise_sites=_scan_window(lines, RAISE_MARKERS),
        exports=find_exports(text, symbols),
        doc=collect_doc(scrub_secret_lines(lines)),
        secret_lines=sum(1 for line in lines if SECRET_LINE.search(line)),
        is_test=is_test,
        identifiers=sorted({token for token in re.findall(r"[A-Za-z_]\w{2,}", text)
                            if len(token) > 3})[:8000] if is_test else [],
    )
    facts.reads, facts.writes = find_sql(text)
    return facts


def response_lines(lines):
    found = set()
    text = "\n".join(lines)
    for pattern in RESPONSE_PATTERNS:
        for hit in pattern.finditer(text):
            found.add(text.count("\n", 0, hit.start()) + 1)
    return sorted(found)


def error_site_in_window(facts, start, end):
    """First error marker inside an inclusive line window, or None.

    Restricting the window is what keeps a try/catch from a different route in
    the same file from becoming a decision node of the selected flow.
    """
    for site in facts.error_sites:
        if start <= site["line"] <= end:
            return site
    return None


def index_basenames(files):
    mapping = {}
    for item in files:
        mapping.setdefault(Path(item.rel).stem, []).append(item.rel)
    return mapping


def _git_env():
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", ""),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_ASKPASS": "/bin/true",
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }


def git_state(root):
    """Read-only git provenance; no hooks, no fsmonitor, no network, no write."""
    import subprocess

    base = ["git", "-C", str(root), "-c", "core.fsmonitor=false",
            "-c", "core.hooksPath=/dev/null", "-c", "gc.auto=0"]

    def run(*args):
        try:
            out = subprocess.run(base + list(args), capture_output=True, text=True,
                                 timeout=10, check=False, env=_git_env())
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
        "read_only": True,
    }


def git_file_commits(root, limit=200):
    """Map repository-relative path -> last commit that touched it (one git call)."""
    import subprocess

    try:
        out = subprocess.run(
            ["git", "-C", str(root), "-c", "core.fsmonitor=false",
             "-c", "core.hooksPath=/dev/null", "log", "--format=%H", "--name-only",
             "-n" + str(int(limit))],
            capture_output=True, text=True, timeout=20, check=False, env=_git_env())
    except (OSError, subprocess.SubprocessError):
        return {}
    if out.returncode != 0:
        return {}
    mapping = {}
    current = None
    for raw in out.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.fullmatch(r"[0-9a-f]{40}", line):
            current = line[:12]
            continue
        if current and line not in mapping:
            mapping[line] = current
    return mapping
