"""Optional local-only vector index.

Hard rules enforced here:

  * no network: a backend must declare local=True and the code never opens a
    socket; the default backend is dependency-free and deterministic;
  * an embedding never leaves the machine, and a chunk never contains a
    secret-shaped line (the index only embeds names, paths and comments,
    and comment text was already scrubbed by the scanner);
  * a vector result is a *candidate*, never "verified": the graph/evidence
    layer confirms it;
  * two embedding models are never mixed: rows carry model+version, and a
    model change drops the old rows instead of blending them;
  * no local backend -> the caller falls back to FTS + graph.
"""

import hashlib
import json
import math
import re
import sqlite3

from .text import normalize_text

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}|[0-9]{2,}")


class EmbeddingBackend:
    """Interface every local backend implements."""

    name = "abstract"
    version = "0"
    dim = 0
    local = True
    semantic = False

    def embed(self, texts):
        raise NotImplementedError

    def describe(self):
        return {"name": self.name, "version": self.version, "dim": self.dim,
                "local": self.local, "semantic": self.semantic}


class HashingEmbedding(EmbeddingBackend):
    """Deterministic hashed bag-of-words; dependency-free and lexical.

    This is not a semantic model. It widens recall for morphological variants
    (report/reports/reporting) and is used only to propose candidates; every
    candidate still has to be confirmed by exact match or graph evidence. A
    real local sentence-embedding model can be plugged in through the same
    interface without changing callers.
    """

    name = "hashing-bow"
    version = "1"
    local = True
    semantic = False

    def __init__(self, dim=256):
        self.dim = int(dim)

    @staticmethod
    def _tokens(text):
        folded = normalize_text(text)
        return [token for token in TOKEN_RE.findall(folded) if len(token) > 2]

    def embed(self, texts):
        vectors = []
        for text in texts:
            vector = [0.0] * self.dim
            counts = {}
            for token in self._tokens(text):
                stem = token[:6]
                counts[stem] = counts.get(stem, 0) + 1
            for stem, count in counts.items():
                digest = hashlib.sha256(stem.encode("utf-8")).digest()
                bucket = int.from_bytes(digest[:4], "big") % self.dim
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vector[bucket] += sign * (1.0 + math.log(count))
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors


class NoBackend(EmbeddingBackend):
    """Explicit "no local embedding runtime" backend: forces the FTS fallback."""

    name = "none"
    version = "0"
    dim = 0
    local = True
    semantic = False

    def embed(self, texts):
        raise RuntimeError("no local embedding backend configured")


DEFAULT_BACKEND = HashingEmbedding

CHUNK_KINDS = ("function", "class", "symbol", "route", "module", "file", "test",
               "flow", "error_case")


def _chunk_text(entity):
    parts = [entity.get("name") or "", entity.get("symbol") or "",
             entity.get("path") or "", entity.get("doc") or ""]
    return " ".join(part for part in parts if part)[:2000]


def ensure_index(connection, files, backend=None):
    """(Re)build vectors for the indexed entities. Returns a summary dict."""
    backend = backend or DEFAULT_BACKEND()
    if not isinstance(backend, EmbeddingBackend) or not backend.local:
        return {"enabled": False, "reason": "no_local_embedding_backend",
                "hint": "Vector index chỉ chấp nhận backend local; nếu không có thì dùng FTS + graph."}
    stored_model = _meta(connection, "embedding_model")
    stored_version = _meta(connection, "embedding_version")
    stale = stored_model != backend.name or stored_version != backend.version
    if stale:
        connection.execute("DELETE FROM vectors")
        _set_meta(connection, "embedding_model", backend.name)
        _set_meta(connection, "embedding_version", backend.version)
        _set_meta(connection, "embedding_dim", backend.dim)
    rows = connection.execute(
        "SELECT id, kind, name, symbol, path, doc, content_hash FROM entities").fetchall()
    chunks = [dict(row) for row in rows if row["kind"] in CHUNK_KINDS]
    if not chunks:
        return {"enabled": True, "model": backend.name, "version": backend.version,
                "chunks": 0, "rebuilt": stale}
    texts = [_chunk_text(chunk) for chunk in chunks]
    vectors = backend.embed(texts)
    for chunk, vector in zip(chunks, vectors):
        connection.execute(
            "INSERT OR REPLACE INTO vectors(entity_id, model, version, dim, vector)"
            " VALUES(?,?,?,?,?)",
            (chunk["id"], backend.name, backend.version, backend.dim,
             json.dumps([round(value, 5) for value in vector])))
    return {"enabled": True, "model": backend.name, "version": backend.version,
            "dim": backend.dim, "semantic": backend.semantic,
            "chunks": len(chunks), "rebuilt": stale}


def search(connection, query, backend=None, top_k=20):
    """Cosine search restricted to the current model/version."""
    backend = backend or DEFAULT_BACKEND()
    stored_model = _meta(connection, "embedding_model")
    stored_version = _meta(connection, "embedding_version")
    if not stored_model:
        return {"enabled": False, "reason": "vector_index_absent", "results": []}
    if stored_model != backend.name or stored_version != backend.version:
        return {"enabled": False, "reason": "embedding_model_mismatch",
                "stored": {"model": stored_model, "version": stored_version},
                "current": backend.describe(), "results": []}
    query_vector = backend.embed([query])[0]
    scored = []
    for row in connection.execute(
            "SELECT entity_id, dim, vector FROM vectors WHERE model = ? AND version = ?",
            (backend.name, backend.version)):
        try:
            vector = json.loads(row["vector"])
        except json.JSONDecodeError:
            continue
        if len(vector) != len(query_vector):
            continue
        score = sum(a * b for a, b in zip(query_vector, vector))
        if score > 0:
            scored.append((score, row["entity_id"]))
    scored.sort(reverse=True)
    results = []
    for score, entity_id in scored[:top_k]:
        entity = connection.execute(
            "SELECT id, kind, name, symbol, path, start_line, end_line FROM entities"
            " WHERE id = ?", (entity_id,)).fetchone()
        if entity is None:
            continue
        results.append({
            "entity": entity["id"], "kind": entity["kind"], "path": entity["path"] or "",
            "symbol": entity["symbol"] or entity["name"] or "",
            "start_line": entity["start_line"] or 1,
            "end_line": entity["end_line"] or entity["start_line"] or 1,
            "similarity": round(float(score), 4),
            "confidence": "inferred",
            "relation": ["semantic_candidate"],
            "reason": "vector candidate (" + backend.name + " " + backend.version
                      + "); cần graph/exact xác nhận",
            "verified": False,
        })
    return {"enabled": True, "model": backend.name, "version": backend.version,
            "results": results, "channel": "vector"}


def _meta(connection, key, default=None):
    row = connection.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return default if row is None else row["value"]


def _set_meta(connection, key, value):
    connection.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))


def status(connection):
    row = connection.execute("SELECT COUNT(*) AS c FROM vectors").fetchone()
    return {
        "vectors": row["c"],
        "model": _meta(connection, "embedding_model", ""),
        "version": _meta(connection, "embedding_version", ""),
        "dim": int(_meta(connection, "embedding_dim", "0") or 0),
    }
