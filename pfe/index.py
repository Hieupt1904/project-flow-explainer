"""Local incremental code index: SQLite + FTS5, no network, no services.

Layout (default, inside the analysed repository):

    <repo>/.pfe/index/knowledge.sqlite

What the index stores:

  * file rows with content hash, git commit, dirty flag, language, size;
  * entities and evidence facts in the ontology vocabulary;
  * a FTS5 table for exact text search (diacritics folded, so a Vietnamese
    query matches an accent-free symbol and vice versa);
  * an optional vector table (see pfe.vectors) that records the embedding
    model and version, so two models can never be mixed;
  * flow rows for the rendered projections;
  * a parse cache, so an unchanged file is never re-parsed.

Incremental rules:

  * unchanged hash -> reuse stored entities/facts, no parse;
  * changed hash   -> delete that file's rows, re-parse, re-index;
  * deleted path   -> rows removed, reported as deleted;
  * new path with a hash that used to belong to a deleted path -> renamed;
  * index version or embedding model change -> full rebuild of the affected part.
"""

import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from . import facts as facts_mod
from . import knowledge as knowledge_mod
from . import ontology
from .text import normalize_text, sha256_text, strip_diacritics, utc_now

INDEX_VERSION = 2
INDEX_DIR = (".pfe", "index")
DB_NAME = "knowledge.sqlite"
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS files (
        path TEXT PRIMARY KEY, language TEXT, size INTEGER, mtime_ns INTEGER,
        content_hash TEXT, commit_sha TEXT, dirty INTEGER, is_test INTEGER,
        sensitive INTEGER, indexed_at TEXT, parse_ms REAL)""",
    """CREATE TABLE IF NOT EXISTS entities (
        id TEXT PRIMARY KEY, kind TEXT, name TEXT, path TEXT, start_line INTEGER,
        end_line INTEGER, symbol TEXT, language TEXT, doc TEXT, flow_ids TEXT,
        content_hash TEXT)""",
    """CREATE TABLE IF NOT EXISTS facts (
        subject TEXT, predicate TEXT, object TEXT, path TEXT, evidence TEXT,
        confidence TEXT, source_commit TEXT, generated_by TEXT,
        contradicted TEXT,
        PRIMARY KEY (subject, predicate, object))""",
    """CREATE TABLE IF NOT EXISTS flows (
        flow_id TEXT PRIMARY KEY, title TEXT, request TEXT, entry_node TEXT,
        artifact_dir TEXT, generated_at TEXT, confidence TEXT, counts TEXT)""",
    """CREATE TABLE IF NOT EXISTS file_cache (
        path TEXT PRIMARY KEY, content_hash TEXT, payload TEXT)""",
    """CREATE TABLE IF NOT EXISTS entry_points (
        path TEXT, kind TEXT, label TEXT, symbol TEXT, start_line INTEGER,
        evidence_kind TEXT, confidence TEXT,
        PRIMARY KEY (path, kind, start_line, label))""",
    """CREATE TABLE IF NOT EXISTS vectors (
        entity_id TEXT, model TEXT, version TEXT, dim INTEGER, vector BLOB,
        PRIMARY KEY (entity_id, model, version))""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(
        entity_id UNINDEXED, kind, path, name, doc,
        tokenize='unicode61 remove_diacritics 2')""",
]
INDEXED_KINDS = {"file", "module", "symbol", "function", "class", "route",
                 "data_model", "test", "flow", "error_case", "artifact"}


class IndexError_(Exception):
    """Stable index failure with a machine code."""

    def __init__(self, code, message, hint=""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

    def as_dict(self):
        return {"status": "error", "code": self.code, "message": self.message,
                "hint": self.hint}


def index_root(root):
    return Path(os.path.realpath(str(root))).joinpath(*INDEX_DIR)


def db_path(root):
    return index_root(root) / DB_NAME


@contextmanager
def connect(root, create=True):
    path = db_path(root)
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    elif not path.exists():
        raise IndexError_("index_missing",
                          "Repository chưa có index: " + str(path),
                          "Chạy project_code_index với mode=full trước.")
    connection = sqlite3.connect(str(path), timeout=10)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        yield connection
    finally:
        connection.close()


def _ensure_schema(connection, force=False):
    """Create the schema. Returns True when the stored content must be rebuilt.

    A version change rebuilds everything (the shape of a row is not stable
    across versions). An explicit `force` also clears the parse cache, so
    "mode=full" really re-parses every file instead of silently reusing it.
    """
    exists = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'meta'").fetchone()
    version = _meta(connection, "index_version") if exists else None
    if force or version != str(INDEX_VERSION):
        for table in ("meta", "files", "entities", "facts", "flows",
                      "file_cache", "entry_points", "vectors", "search"):
            connection.execute("DROP TABLE IF EXISTS " + table)
        for statement in SCHEMA:
            connection.execute(statement)
        _set_meta(connection, "index_version", str(INDEX_VERSION))
        return True
    for statement in SCHEMA:
        connection.execute(statement)
    return False


def _meta(connection, key, default=None):
    row = connection.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return default if row is None else row["value"]


def _set_meta(connection, key, value):
    connection.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))


# --------------------------------------------------------------------------
# parse cache
# --------------------------------------------------------------------------

CACHE_FIELDS = ("rel", "size", "language", "content_hash", "symbols", "routes",
                "entries", "imports", "external_imports", "call_sites",
                "response_lines", "error_sites", "raise_sites", "exports",
                "reads", "writes", "doc", "secret_lines", "is_test", "identifiers",
                "entry_points")


def _payload(item):
    return json.dumps({field: getattr(item, field) for field in CACHE_FIELDS},
                      ensure_ascii=False, separators=(",", ":"))


def _from_payload(payload, real=""):
    data = json.loads(payload)
    data.setdefault("identifiers", [])
    data.setdefault("entry_points", [])
    data["lines"] = []
    data["real"] = real
    return facts_mod.FileFacts(**data)


# --------------------------------------------------------------------------
# build / refresh
# --------------------------------------------------------------------------

def build_index(root, mode="incremental", include_vectors=False, vector_backend=None,
                max_files=facts_mod.MAX_FILES_SCANNED,
                max_total_bytes=facts_mod.MAX_TOTAL_SOURCE_BYTES):
    """Build or refresh the index. Returns a summary dict (no source text)."""
    started = time.time()
    root = Path(os.path.realpath(str(root)))
    warnings = []
    full = mode != "incremental"
    entries, excluded, budget = facts_mod.walk_sources(
        root, include_tests=True, max_files=max_files, max_total_bytes=max_total_bytes)
    git = facts_mod.git_state(root)
    commit = git.get("commit") or ""
    dirty = bool(git.get("dirty"))

    with connect(root) as connection:
        rebuilt = _ensure_schema(connection, force=full)
        if rebuilt:
            full = True
        previous_commit = _meta(connection, "source_commit", "")
        if previous_commit and commit and previous_commit != commit and not full:
            # A checkout moved under the index: facts about the old commit are
            # not silently kept as current. Files that actually changed are
            # re-parsed below, and the rest are marked as carried over.
            warnings.append("Index được xây ở commit " + previous_commit[:12]
                            + ", HEAD hiện tại " + commit[:12]
                            + "; file không đổi được giữ nguyên và ghi rõ nguồn gốc.")

        stored = {row["path"]: dict(row) for row in
                  connection.execute("SELECT path, content_hash, size, mtime_ns, "
                                     "commit_sha FROM files")}
        current = {}
        for entry in entries:
            current[entry.rel] = (entry, facts_mod.hash_file(entry.real))

        added, changed, unchanged = [], [], []
        for rel, (entry, digest) in current.items():
            row = stored.get(rel)
            if row is None:
                added.append(rel)
            elif row["content_hash"] != digest:
                changed.append(rel)
            else:
                unchanged.append(rel)
        deleted = sorted(set(stored) - set(current))
        hashes = {rel: current[rel][1] for rel in current}
        renamed = []
        remaining = list(deleted)
        for rel in sorted(added):
            match = next((old for old in remaining
                          if stored[old]["content_hash"] == hashes[rel]), None)
            if match is not None:
                renamed.append({"from": match, "to": rel})
                remaining.remove(match)
        removed = [rel for rel in remaining]

        sensitive_content = []

        def purge(rel):
            connection.execute("DELETE FROM entities WHERE path = ?", (rel,))
            connection.execute("DELETE FROM facts WHERE path = ?", (rel,))
            connection.execute("DELETE FROM search WHERE path = ?", (rel,))
            connection.execute("DELETE FROM file_cache WHERE path = ?", (rel,))
            connection.execute("DELETE FROM entry_points WHERE path = ?", (rel,))
            connection.execute("DELETE FROM files WHERE path = ?", (rel,))

        parse_ms = {"total": 0.0, "count": 0}
        parsed = {}
        # Resolve the cache BEFORE parsing: a file whose cache row is missing or
        # unreadable must be re-parsed, not silently dropped from the graph.
        reusable = {}
        needs_parse = []
        for rel in unchanged:
            row = connection.execute(
                "SELECT content_hash, payload FROM file_cache WHERE path = ?", (rel,)).fetchone()
            if row is None:
                warnings.append("Cache thiếu cho " + rel + "; parse lại.")
                needs_parse.append(rel)
                continue
            try:
                reusable[rel] = _from_payload(row["payload"], current[rel][0].real)
            except (ValueError, TypeError, KeyError) as error:
                warnings.append("Cache hỏng cho " + rel + " (" + type(error).__name__
                                + "); parse lại.")
                needs_parse.append(rel)
                continue
            connection.execute(
                "UPDATE files SET mtime_ns = ?, commit_sha = ?, dirty = ?, indexed_at = ?"
                " WHERE path = ?",
                (current[rel][0].mtime_ns, commit, int(dirty), utc_now(), rel))

        for rel in added + changed + needs_parse:
            entry, digest = current[rel]
            if rel in {item["from"] for item in renamed} or rel in needs_parse:
                purge(rel)
            stamp = time.time()
            item = facts_mod.parse_entry(entry)
            parse_ms["total"] += (time.time() - stamp) * 1000
            if item is None:
                warnings.append("Không đọc được file: " + rel)
                purge(rel)
                continue
            item.content_hash = digest
            if item.secret_lines > 0:
                # Never index a file whose content holds a secret-shaped value:
                # its structure is not worth the risk of carrying the value.
                sensitive_content.append(rel)
                purge(rel)
                continue
            parsed[rel] = item
            parse_ms["count"] += 1
            purge(rel)
            connection.execute(
                "INSERT OR REPLACE INTO files(path, language, size, mtime_ns, content_hash,"
                " commit_sha, dirty, is_test, sensitive, indexed_at, parse_ms)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (rel, item.language, item.size, entry.mtime_ns, digest, commit,
                 int(dirty), int(item.is_test), int(item.secret_lines > 0),
                 utc_now(), 0.0))
            connection.execute(
                "INSERT OR REPLACE INTO file_cache(path, content_hash, payload)"
                " VALUES(?,?,?)", (rel, digest, _payload(item)))

        for rel in removed:
            purge(rel)

        for rel, item in list(reusable.items()):
            if item.secret_lines > 0:
                sensitive_content.append(rel)
                purge(rel)
                reusable.pop(rel)
        all_files = dict(reusable)
        all_files.update(parsed)

        # Invariant: every file the index claims to know is in the graph. A hole
        # here means a file row survives while its entities disappear, which is
        # exactly the failure mode this repair exists for.
        missing = [rel for rel in current if rel not in all_files
                   and rel not in sensitive_content]
        for rel in missing:
            entry, digest = current[rel]
            item = facts_mod.parse_entry(entry)
            if item is None:
                continue
            item.content_hash = digest
            if item.secret_lines > 0:
                sensitive_content.append(rel)
                purge(rel)
                continue
            parsed[rel] = item
            parse_ms["count"] += 1
            all_files[rel] = item
            connection.execute(
                "INSERT OR REPLACE INTO files(path, language, size, mtime_ns, content_hash,"
                " commit_sha, dirty, is_test, sensitive, indexed_at, parse_ms)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (rel, item.language, item.size, entry.mtime_ns, digest, commit,
                 int(dirty), int(item.is_test), 0, utc_now(), 0.0))
            connection.execute(
                "INSERT OR REPLACE INTO file_cache(path, content_hash, payload)"
                " VALUES(?,?,?)", (rel, digest, _payload(item)))
        if missing:
            warnings.append("Đã parse bù " + str(len(missing))
                            + " file bị thiếu khỏi graph (cache thiếu/hỏng).")
        for rel in deleted:
            if rel in {item["from"] for item in renamed} and rel not in all_files:
                all_files[rel] = None
        live_files = [item for item in all_files.values() if item is not None]

        # Entry points are additive evidence: routes come from route entities,
        # everything else from a registration line in the file. Nothing here is
        # inferred from a function name.
        connection.execute("DELETE FROM entry_points")
        for item in live_files:
            for route in item.routes:
                connection.execute(
                    "INSERT OR REPLACE INTO entry_points(path, kind, label, symbol,"
                    " start_line, evidence_kind, confidence) VALUES(?,?,?,?,?,?,?)",
                    (item.rel, "http_route", route["label"], route["label"],
                     route["line"], "observed", "observed"))
            for entry in item.entry_points:
                connection.execute(
                    "INSERT OR REPLACE INTO entry_points(path, kind, label, symbol,"
                    " start_line, evidence_kind, confidence) VALUES(?,?,?,?,?,?,?)",
                    (item.rel, entry["kind"], entry.get("label") or "",
                     entry.get("label") or "", entry["line"], "observed", "observed"))

        # Knowledge is rebuilt from the in-memory fact set: parse cache keeps
        # unchanged files out of the parser, not out of the graph.
        commits = facts_mod.git_file_commits(root) if commit else {}
        knowledge = knowledge_mod.build_knowledge(root, live_files, git, commits=commits)

        if parsed or removed or renamed or full:
            connection.execute("DELETE FROM entities")
            connection.execute("DELETE FROM facts")
            connection.execute("DELETE FROM search")
            for entity in knowledge["entities"]:
                row = dict(entity)
                connection.execute(
                    "INSERT OR REPLACE INTO entities(id, kind, name, path, start_line,"
                    " end_line, symbol, language, doc, flow_ids, content_hash)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (row["id"], row["kind"], row.get("name", ""), row.get("path"),
                     row.get("start_line"), row.get("end_line"), row.get("symbol"),
                     row.get("language"), row.get("doc"), json.dumps(row.get("flow_ids") or []),
                     row.get("content_hash")))
                if row["kind"] in INDEXED_KINDS:
                    connection.execute(
                        "INSERT INTO search(entity_id, kind, path, name, doc)"
                        " VALUES(?,?,?,?,?)",
                        (row["id"], row["kind"], row.get("path") or "",
                         _fold(name_variants(row.get("name") or row.get("symbol") or "")),
                         _fold(row.get("doc") or "")))
            for fact in knowledge["facts"]:
                evidence = fact.get("evidence") or {}
                connection.execute(
                    "INSERT OR REPLACE INTO facts(subject, predicate, object, path, evidence,"
                    " confidence, source_commit, generated_by, contradicted)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (fact["subject"], fact["predicate"], fact["object"],
                     evidence.get("path") or "", json.dumps(evidence, ensure_ascii=False),
                     fact["confidence"], fact.get("source_commit") or "",
                     fact.get("generated_by") or "",
                     # Never drop a known conflict: an agent that trusts the
                     # stronger fact must still see that a weaker one existed.
                     json.dumps(fact["contradicted"], ensure_ascii=False)
                     if fact.get("contradicted") else None))

        _set_meta(connection, "repository_id", knowledge["repository_id"])
        _set_meta(connection, "repository_name", knowledge["repository_name"])
        _set_meta(connection, "source_commit", commit)
        _set_meta(connection, "dirty", int(dirty))
        _set_meta(connection, "generated_at", utc_now())
        _set_meta(connection, "mode", "full" if full else "incremental")
        _set_meta(connection, "entry_points",
                  connection.execute("SELECT COUNT(*) AS c FROM entry_points").fetchone()["c"])
        _set_meta(connection, "files_indexed", len(live_files))
        _set_meta(connection, "excluded_sensitive",
                  excluded.get("sensitive_name", 0) + excluded.get("symlink_sensitive", 0)
                  + len(sensitive_content))
        connection.commit()

        index_id = sha256_text(knowledge["repository_id"] + commit
                               + str(len(live_files)) + utc_now())[:12]
        _set_meta(connection, "index_id", index_id)
        connection.commit()

        symbols = sum(len(item.symbols) for item in live_files)
        routes = sum(len(item.routes) for item in live_files)
        tests = sum(1 for item in live_files if item.is_test)
        stale_after = staleness(root, connection=connection, entries=current)

        embedding = {"enabled": False, "reason": "include_vectors=false"}
        if include_vectors:
            from . import vectors as vectors_mod
            embedding = vectors_mod.ensure_index(connection, live_files,
                                                 backend=vector_backend)
            connection.commit()

        entity_total = connection.execute("SELECT COUNT(*) AS c FROM entities").fetchone()["c"]
        fact_total = connection.execute("SELECT COUNT(*) AS c FROM facts").fetchone()["c"]

    return {
        "status": "ok",
        "index_id": index_id,
        "index_version": INDEX_VERSION,
        "repository_name": knowledge["repository_name"],
        "repository_id": knowledge["repository_id"],
        "source_commit": commit,
        "dirty": dirty,
        "mode": "full" if full else "incremental",
        "files_indexed": len(live_files),
        "files_parsed": parse_ms["count"],
        "files_reused": len(reusable),
        "symbols_indexed": symbols,
        "routes_indexed": routes,
        "tests_indexed": tests,
        "entities": entity_total,
        "facts": fact_total,
        "stale_files": stale_after["stale_files"],
        "changed": sorted(changed),
        "added": sorted(added),
        "deleted": removed,
        "renamed": renamed,
        "warnings": warnings + budget.notes,
        "excluded": excluded,
        "sensitive_content": sorted(set(sensitive_content)),
        "embedding": embedding,
        "parse_ms": round(parse_ms["total"], 2),
        "duration_ms": round((time.time() - started) * 1000, 2),
    }


def _fold(text):
    return normalize_text(text or "")


def name_variants(name):
    """Index a name plus its camelCase/snake_case word split.

    `exportReport` must be findable by the query `export_report`, so the FTS
    row carries both the raw name and its separated words. This is an index
    concern only: the stored entity keeps the original spelling.
    """
    raw = str(name or "")
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", raw)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", spaced) if part]
    ordered = [raw] + parts
    seen, output = set(), []
    for item in ordered:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return " ".join(output)


# --------------------------------------------------------------------------
# status / staleness
# --------------------------------------------------------------------------

def status(root):
    path = db_path(root)
    git = facts_mod.git_state(root)
    if not path.exists():
        return {"status": "missing", "index_path": str(index_root(root)),
                "source_commit": "", "head_commit": git.get("commit") or "",
                "stale": True, "stale_files": 0, "reason": "index_missing",
                "warnings": ["Chưa có index; chạy project_code_index mode=full."]}
    with connect(root, create=False) as connection:
        _ensure_schema(connection)
        quick = quick_staleness(root, connection)
        return {
            "status": "ok",
            "index_path": str(path),
            "index_version": int(_meta(connection, "index_version", "0")),
            "index_id": _meta(connection, "index_id", ""),
            "source_commit": _meta(connection, "source_commit", ""),
            "head_commit": git.get("commit") or "",
            "dirty": git.get("dirty", False),
            "index_dirty": _meta(connection, "dirty", "0") == "1",
            "generated_at": _meta(connection, "generated_at", ""),
            "files_indexed": int(_meta(connection, "files_indexed", "0")),
            "stale": bool(_meta(connection, "source_commit", "") != (git.get("commit") or ""))
                     or _meta(connection, "index_version", "0") != str(INDEX_VERSION)
                     or quick["stale"],
            "stale_files": quick["stale_files"] or int(_meta(connection, "stale_files", "0")),
            "stale_reason": quick["reason"],
            "embedding_model": _meta(connection, "embedding_model", ""),
            "embedding_version": _meta(connection, "embedding_version", ""),
            "warnings": [],
        }


def quick_staleness(root, connection=None):
    """Cheap staleness: compare stored mtime_ns with the working tree.

    No file is read, only stat() is called, so this can run on every query.
    A real content diff is what `staleness()` does (and what refresh does).
    """
    own = connection is None
    if own:
        if not db_path(root).exists():
            return {"stale": True, "stale_files": 0, "reason": "index_missing", "files": []}
        connection = sqlite3.connect(str(db_path(root)))
        connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute("SELECT path, mtime_ns FROM files").fetchall()
    finally:
        if own:
            connection.close()
    changed = []
    for row in rows:
        path = Path(os.path.realpath(str(Path(root) / row["path"])))
        try:
            if path.stat().st_mtime_ns != row["mtime_ns"]:
                changed.append(row["path"])
        except OSError:
            changed.append(row["path"])
    return {"stale": bool(changed), "stale_files": len(changed),
            "reason": "mtime_changed" if changed else "", "files": sorted(changed)[:200]}


def staleness(root, connection=None, entries=None):
    """Compare stored hashes with the working tree; reports stale files."""
    own = connection is None
    if own:
        if not db_path(root).exists():
            return {"stale": True, "stale_files": 0, "reason": "index_missing", "files": []}
        connection = sqlite3.connect(str(db_path(root)))
        connection.row_factory = sqlite3.Row
    try:
        stored = {row["path"]: row["content_hash"] for row in
                  connection.execute("SELECT path, content_hash FROM files")}
    finally:
        if own:
            connection.close()
    if entries is None:
        walked, _excluded, _budget = facts_mod.walk_sources(root, include_tests=True)
        entries = {entry.rel: (entry, facts_mod.hash_file(entry.real)) for entry in walked}
    stale = []
    for rel, (_entry, digest) in entries.items():
        row = stored.get(rel)
        if row is None or row != digest:
            stale.append(rel)
    for rel in stored:
        if rel not in entries:
            stale.append(rel)
    return {
        "stale": bool(stale),
        "stale_files": len(stale),
        "reason": "content_changed" if stale else "",
        "files": sorted(stale)[:200],
    }


# --------------------------------------------------------------------------
# queries used by retrieval / impact
# --------------------------------------------------------------------------

def get_meta(root, key, default=None):
    if not db_path(root).exists():
        return default
    with connect(root, create=False) as connection:
        return _meta(connection, key, default)


def exact_search(root, query, top_k=10, filters=None):
    """FTS5 exact search. Returns ranked candidates with source refs, no source."""
    filters = filters or {}
    terms = [token for token in _fold(query).split() if token]
    if not terms:
        raise IndexError_("empty_query", "Query rỗng.", "Mô tả một tên hàm, route hoặc từ khoá.")
    if not db_path(root).exists():
        raise IndexError_("index_missing", "Repository chưa có index.",
                          "Chạy project_code_index mode=full trước.")
    # Prefix matching: "report" must reach "reports"/"reporting", otherwise a
    # Vietnamese question never meets the English plural in the code.
    match = " OR ".join('"' + term.replace('"', "") + '*"' for term in terms)
    with connect(root, create=False) as connection:
        _ensure_schema(connection)
        commit = _meta(connection, "source_commit", "")
        rows = connection.execute(
            "SELECT entity_id, kind, path, name, "
            "bm25(search, 0.0, 1.0, 1.5, 4.0, 1.2) AS score FROM search "
            "WHERE search MATCH ? ORDER BY score LIMIT ?",
            (match, max(top_k * 4, 20))).fetchall()
        raw = [(-float(row["score"]), row) for row in rows]
        best = max((value for value, _row in raw), default=0.0) or 1.0
        results = []
        for value, row in raw:
            if filters.get("kind") and row["kind"] != filters["kind"]:
                continue
            if filters.get("path_prefix") and not (row["path"] or "").startswith(filters["path_prefix"]):
                continue
            entity = connection.execute(
                "SELECT * FROM entities WHERE id = ?", (row["entity_id"],)).fetchone()
            if entity is None:
                continue
            if filters.get("language") and entity["language"]                     and entity["language"] != filters["language"]:
                continue
            related = connection.execute(
                "SELECT predicate, object FROM facts WHERE subject = ? "
                "OR object = ? LIMIT 8", (row["entity_id"], row["entity_id"])).fetchall()
            results.append({
                "entity": entity["id"],
                "kind": entity["kind"],
                "path": entity["path"] or "",
                "symbol": entity["symbol"] or entity["name"] or "",
                "start_line": entity["start_line"] or 1,
                "end_line": entity["end_line"] or entity["start_line"] or 1,
                "relation": sorted({item["predicate"] for item in related}),
                "confidence": "observed" if entity["path"] else "structural",
                "reason": "khớp chính xác từ khoá trong " + _field_of(row["kind"]),
                "source_commit": commit,
                "score": round(value, 4),
                "score_norm": round(min(1.0, value / best), 4),
            })
            if len(results) >= top_k:
                break
    return {"query": query, "terms": terms, "results": results,
            "index_commit": commit, "channel": "fts"}


def _field_of(kind):
    return {"file": "đường dẫn file", "symbol": "tên symbol", "function": "tên hàm",
            "class": "tên lớp", "route": "khai báo route", "test": "tên test",
            "flow": "tiêu đề flow", "data_model": "tên bảng",
            "error_case": "nhánh lỗi", "artifact": "tên artifact"}.get(kind, "nội dung index")


def entity(connection, entity_id):
    row = connection.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    return dict(row) if row else None


def facts_about(connection, entity_id, limit=40):
    rows = connection.execute(
        "SELECT subject, predicate, object, evidence, confidence, contradicted FROM facts "
        "WHERE subject = ? OR object = ? LIMIT ?", (entity_id, entity_id, limit)).fetchall()
    return [_fact_row(row) for row in rows]


def _fact_row(row):
    item = {"subject": row["subject"], "predicate": row["predicate"],
            "object": row["object"], "confidence": row["confidence"],
            "evidence": json.loads(row["evidence"] or "{}")}
    try:
        conflict = row["contradicted"]
    except (IndexError, KeyError):
        conflict = None
    if conflict:
        item["contradicted"] = json.loads(conflict)
    return item


def neighbours(connection, entity_id, predicates=None, limit=50):
    """One-hop graph expansion; each hop keeps its evidence."""
    if predicates:
        placeholders = ",".join("?" for _ in predicates)
        rows = connection.execute(
            "SELECT subject, predicate, object, evidence, confidence, contradicted FROM facts "
            "WHERE predicate IN (" + placeholders + ") AND (subject = ? OR object = ?) "
            "LIMIT ?", (*predicates, entity_id, entity_id, limit)).fetchall()
    else:
        rows = connection.execute(
            "SELECT subject, predicate, object, evidence, confidence, contradicted FROM facts "
            "WHERE subject = ? OR object = ? LIMIT ?", (entity_id, entity_id, limit)).fetchall()
    return [_fact_row(row) for row in rows]


def list_entities(connection, kind=None, path=None, limit=200):
    clause, params = [], []
    if kind:
        clause.append("kind = ?")
        params.append(kind)
    if path:
        clause.append("path = ?")
        params.append(path)
    where = (" WHERE " + " AND ".join(clause)) if clause else ""
    rows = connection.execute(
        "SELECT * FROM entities" + where + " ORDER BY path, start_line LIMIT ?",
        (*params, limit)).fetchall()
    return [dict(row) for row in rows]


def record_flow(root, flow, artifact_dir):
    """Persist a rendered flow projection so search/impact can use it.

    `artifact_dir` is stored repository-relative. An absolute path would leak
    the workstation layout into every later impact analysis, and the index is
    the one place that outlives the run that wrote it.
    """
    root_path = Path(os.path.realpath(str(root)))
    artifact_text = str(artifact_dir or "")
    if os.path.isabs(artifact_text):
        # Resolve symlinks before relativising so the stored value names the
        # directory the reader will actually find. A path outside the repository
        # keeps only its tail: an absolute host prefix must never be stored.
        try:
            artifact_text = Path(os.path.realpath(artifact_text)).relative_to(root_path).as_posix()
        except (ValueError, OSError):
            artifact_text = artifact_text.replace(str(root_path) + os.sep, "").strip("/")
    artifact_text = artifact_text.strip("/")
    counts = {}
    for node in flow.get("nodes", []):
        counts[node["confidence"]] = counts.get(node["confidence"], 0) + 1
    with connect(root) as connection:
        _ensure_schema(connection)
        connection.execute(
            "INSERT OR REPLACE INTO flows(flow_id, title, request, entry_node,"
            " artifact_dir, generated_at, confidence, counts) VALUES(?,?,?,?,?,?,?,?)",
            (flow["flow_id"], flow.get("title", ""), flow.get("meta", {}).get("request", ""),
             flow.get("entry_node", ""), artifact_text,
             flow.get("meta", {}).get("generated_at", ""),
             "partial" if counts.get("inferred") or counts.get("unknown") else "verified",
             json.dumps(counts, ensure_ascii=False)))
        entries = []
        facts = []
        commit = _meta(connection, "source_commit", "")
        flow_entity = ontology.entity_id("flow", flow["flow_id"])
        entries.append((flow_entity, "flow", flow["flow_id"], "artifacts/flows", 1,
                        None, flow["flow_id"], None, flow.get("title", ""), "[]", ""))
        for node in flow.get("nodes", []):
            for ref in node.get("source_refs") or []:
                fact = ontology.fact(
                    ontology.entity_id("file", ref["path"]), "belongs_to_flow", flow_entity,
                    ontology.evidence("inferred", path=ref["path"],
                                      start_line=ref.get("start_line") or 1,
                                      detail="thành viên luồng " + flow["flow_id"]),
                    "inferred", commit, "pfe.index.record_flow")
                facts.append(fact)
        for fact in facts:
            try:
                ontology.validate_fact(fact)
            except ontology.OntologyError:
                continue
            evidence = fact["evidence"]
            connection.execute(
                "INSERT OR REPLACE INTO facts(subject, predicate, object, path, evidence,"
                " confidence, source_commit, generated_by) VALUES(?,?,?,?,?,?,?,?)",
                (fact["subject"], fact["predicate"], fact["object"],
                 evidence.get("path") or "", json.dumps(evidence, ensure_ascii=False),
                 fact["confidence"], fact["source_commit"], fact["generated_by"]))
        for row in entries:
            connection.execute(
                "INSERT OR REPLACE INTO entities(id, kind, name, path, start_line,"
                " end_line, symbol, language, doc, flow_ids, content_hash)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)", row)
            connection.execute(
                "INSERT INTO search(entity_id, kind, path, name, doc) VALUES(?,?,?,?,?)",
                (row[0], row[1], row[3] or "", _fold(name_variants(row[2])),
                 _fold(row[8] or "")))
        connection.commit()
    return {"flow_id": flow["flow_id"], "recorded": True}


def list_flows(root, limit=20):
    if not db_path(root).exists():
        return []
    with connect(root, create=False) as connection:
        _ensure_schema(connection)
        rows = connection.execute(
            "SELECT flow_id, title, entry_node, artifact_dir, generated_at, counts "
            "FROM flows ORDER BY generated_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]
