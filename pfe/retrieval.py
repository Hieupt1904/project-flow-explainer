"""Hybrid retrieval: parse -> exact -> vector candidates -> graph -> rerank -> pack.

Ranking policy (explicit, so a semantic hit can never outrank an exact hit):

    exact name/path/route match   1.00
    FTS keyword match             0.75
    vector similarity             0.45 * similarity (never verified)
    graph proximity               0.60 / (1 + hops)
    evidence quality              observed +0.25 / structural +0.15 / inferred +0.05
    freshness (commit == HEAD)    +0.05
    keyword-only, no graph edge   -0.35

The context pack returns paths, symbols, line ranges, relations and reasons. It
does not return raw source unless include_snippets is requested, and then only
up to the line window that was already cited.
"""

import os
import re
from pathlib import Path

from . import facts as facts_mod
from . import index as index_mod
from . import vectors as vectors_mod
from .text import normalize_text

ROUTE_RE = re.compile(r"(?<![\w])/[A-Za-z0-9_\-/:{}.]{2,}")
FILE_RE = re.compile(r"[\w.-]+(?:/[\w.-]+)*\.(?:py|js|mjs|cjs|ts|tsx|jsx|vue|svelte|php|rb|go|rs|java|cs|sql|sh)")
SYMBOL_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
ERROR_WORDS = {"loi", "error", "exception", "fail", "failed", "throw", "catch", "loi"}
FLOW_WORDS = {"luong", "flow", "quy", "trinh", "journey", "user"}
# Function words of a Vietnamese/English request. They carry no retrieval
# signal; keeping them makes a long sentence match every file in the repo.
STOPWORDS = {
    "the", "and", "for", "when", "from", "with", "this", "that", "which", "what",
    "how", "does", "did", "are", "was", "were", "you", "can", "please",
    "tu", "luc", "khi", "den", "cua", "va", "la", "co", "nhu", "the", "nao",
    "cac", "nhung", "mot", "trong", "ra", "vao", "di", "qua",
    "giai", "thich", "huong", "dan", "nguoi", "dung", "bam",
    "truoc", "thi", "se", "da", "dang", "bi", "duoc", "cho", "voi", "de",
    "hay", "hoac", "roi",
}

# Bilingual bridge: a Vietnamese business request must reach English identifiers.
# Keys are folded (accents removed); values are the code words worth searching.
LEXICON = {
    "xuat": ["export", "download", "write"],
    "bao cao": ["report", "summary"],
    "tai xuong": ["download", "file", "attachment"],
    "tai ve": ["download"],
    "hoa don": ["invoice", "bill"],
    "don hang": ["order", "checkout"],
    "thanh toan": ["payment", "checkout"],
    "dang nhap": ["login", "signin", "authenticate", "session"],
    "dang ky": ["register", "signup", "create"],
    "xac thuc": ["auth", "authenticate", "session", "token"],
    "mat khau": ["password", "hash"],
    "tim kiem": ["search", "query", "find", "filter"],
    "tra cuu": ["search", "lookup", "query"],
    "loc": ["filter", "where"],
    "luu": ["save", "insert", "update", "persist", "store"],
    "ghi": ["write", "insert", "save"],
    "doc": ["read", "load", "get", "fetch"],
    "gui": ["send", "notify", "mail"],
    "thong bao": ["notification", "email", "sms"],
    "loi": ["error", "exception", "fail", "throw"],
    "xu ly": ["handle", "process"],
    "kich hoat": ["activate", "enable"],
    "bao mat": ["security", "auth", "token"],
    "tep": ["file", "upload", "attachment"],
    "tai len": ["upload", "multipart"],
    "nguoi dung": ["user", "customer"],
    "quan tri": ["admin", "manage"],
    "kiem tra": ["verify", "validate", "check"],
    "xoa": ["delete", "remove"],
    "sua": ["update", "edit"],
    "them": ["create", "add", "insert"],
}


def expand_terms(folded_query, terms):
    """Add English code words for Vietnamese business phrases (recall only)."""
    extra = []
    for phrase, words in LEXICON.items():
        if " " in phrase:
            present = phrase in folded_query
        else:
            present = re.search(r"\b" + re.escape(phrase) + r"\b", folded_query) is not None
        if present:
            extra.extend(words)
    ordered = list(dict.fromkeys([term for term in terms if term] + extra))
    return ordered[:16]

EVIDENCE_WEIGHT = {"observed": 0.25, "structural": 0.15, "inferred": 0.05,
                   "runtime_verified": 0.3, "stale": 0.0, "contradicted": 0.0}
EXPAND_PREDICATES = ["imports", "calls", "handles_route", "tested_by", "reads_from",
                     "writes_to", "raises", "catches", "belongs_to_flow", "exports"]
MAX_EXPANSION = 60


def parse_query(query):
    text = str(query or "").strip()
    folded = normalize_text(text)
    routes = ROUTE_RE.findall(text)
    files = FILE_RE.findall(text)
    error = any(word in folded.split() for word in ERROR_WORDS)
    flow = any(word in folded.split() for word in FLOW_WORDS)
    candidates = []
    for token in SYMBOL_RE.findall(text):
        if len(token) < 3 or token.lower() in STOPWORDS:
            continue
        if token in routes or token in files:
            continue
        candidates.append(token)
    # Underscored or camelCase identifiers are stronger than plain words.
    identifiers = [token for token in candidates
                   if "_" in token or re.search(r"[a-z][A-Z]", token)]
    symbol = identifiers[0] if identifiers else (candidates[0] if candidates else "")
    terms = [token for token in candidates if token != symbol][:8]
    if symbol:
        terms = [symbol] + terms
    if not terms and not routes and not files:
        terms = [token for token in folded.split() if token not in STOPWORDS][:8]
    return {
        "text": text,
        "folded": folded,
        "intent": "error" if error else ("flow" if flow else "locate"),
        "routes": routes,
        "files": files,
        "symbol": symbol,
        "terms": terms[:10],
        "has_error_term": error,
        "has_flow_term": flow,
    }


HUB_KINDS = {"repository", "commit", "directory"}
_KIND_PRIORITY = {"function": 4, "class": 4, "route": 3, "test": 3, "flow": 2,
                  "file": 1, "module": 1, "symbol": 2}


def _merge(bucket, entity, score, channel, reason, relation, evidence_quality):
    """Record a candidate and keep the strongest base score per channel.

    Channels are combined as max(base) + small bonuses, never summed: otherwise
    a hub entity reached by four different graph hops would outrank an exact
    match, which is exactly the failure this ranking must prevent.
    """
    if entity.get("kind") in HUB_KINDS:
        return
    current = bucket.get(entity["id"])
    payload = {
        "entity": entity["id"], "kind": entity["kind"],
        "path": entity.get("path") or "", "symbol": entity.get("symbol") or entity.get("name") or "",
        "start_line": entity.get("start_line") or 1,
        "end_line": entity.get("end_line") or entity.get("start_line") or 1,
        "base": score, "channels": [channel], "reasons": [reason],
        "relation": list(relation), "confidence": evidence_quality,
        "verified": False,
    }
    if current is None:
        bucket[entity["id"]] = payload
        return
    current["base"] = max(current["base"], score)
    if channel not in current["channels"]:
        current["channels"].append(channel)
    if reason not in current["reasons"]:
        current["reasons"].append(reason)
    for item in relation:
        if item not in current["relation"]:
            current["relation"].append(item)


def retrieve(root, query, top_k=10, filters=None, backend=None, use_vectors=True,
             expand=True, include_snippets=False):
    """Run the hybrid pipeline and return ranked results + diagnostics."""
    filters = filters or {}
    parsed = parse_query(query)
    if not parsed["terms"] and not parsed["routes"] and not parsed["files"]:
        from .index import IndexError_
        raise IndexError_("empty_query", "Query rỗng.",
                          "Mô tả một tên hàm, route, file hoặc nghiệp vụ cần tìm.")
    if not index_mod.db_path(root).exists():
        from .index import IndexError_
        raise IndexError_("index_missing", "Repository chưa có index.",
                          "Chạy project_code_index mode=full trước.")
    diagnostics = {"channels": [], "warnings": [], "parsed": parsed}
    if len(parsed["terms"]) > 8 or len(parsed["text"].split()) > 10:
        # Exact search is an OR over terms: a long sentence pulls in every file
        # that shares a common word. Say so instead of returning a confident lie.
        diagnostics["warnings"].append(
            "Query dài: exact search cộng dồn theo từ khoá. Với câu mô tả nghiệp vụ, "
            "dùng project_flow_explain, hoặc rút query về symbol / route / 2-3 từ khoá.")

    with index_mod.connect(root, create=False) as connection:
        index_mod._ensure_schema(connection)
        commit = index_mod._meta(connection, "source_commit", "")
        git = facts_mod.git_state(root)
        head = git.get("commit") or ""
        quick = index_mod.quick_staleness(root, connection)
        stale = bool(commit and head and commit != head) or quick["stale"]

        candidates = {}

        # 1. exact identifiers the query literally names
        for route in parsed["routes"]:
            rows = connection.execute(
                "SELECT * FROM entities WHERE kind = 'route' AND name = ?",
                (route,)).fetchall()
            for row in rows:
                _merge(candidates, dict(row), 1.0, "exact_route",
                       "route được nêu đúng tên trong câu hỏi",
                       ["handles_route"], "observed")
            if rows:
                diagnostics["channels"].append("exact_route")
        for file_name in parsed["files"]:
            rows = connection.execute(
                "SELECT * FROM entities WHERE kind = 'file' AND (path = ? OR path LIKE ?)",
                (file_name, "%/" + file_name)).fetchall()
            for row in rows:
                _merge(candidates, dict(row), 1.0, "exact_file",
                       "đường dẫn file được nêu đúng", ["contains"], "observed")
            if rows:
                diagnostics["channels"].append("exact_file")
        if parsed["symbol"]:
            flattened = re.sub(r"[_\-]", "", parsed["symbol"]).lower()
            rows = connection.execute(
                "SELECT * FROM entities WHERE symbol = ? OR name = ? "
                "OR lower(replace(replace(symbol, '_', ''), '-', '')) = ?"
                "OR lower(replace(replace(name, '_', ''), '-', '')) = ?",
                (parsed["symbol"], parsed["symbol"], flattened, flattened)).fetchall()
            for row in rows:
                _merge(candidates, dict(row), 1.0, "exact_symbol",
                       "tên symbol xuất hiện nguyên văn trong câu hỏi",
                       ["defines"], "observed")
            if rows:
                diagnostics["channels"].append("exact_symbol")

        search_terms = expand_terms(parsed["folded"], parsed["terms"])

        # 2. exact text search (FTS5)
        try:
            fts = index_mod.exact_search(root, " ".join(search_terms) or query,
                                         top_k=top_k * 3, filters=filters)
            for hit in fts["results"]:
                row = connection.execute(
                    "SELECT * FROM entities WHERE id = ?", (hit["entity"],)).fetchone()
                if row is None:
                    continue
                # bm25 decides *how well* a keyword matched: a match in the
                # name column must beat a match buried in a comment.
                quality = hit.get("score_norm", 0.0)
                _merge(candidates, dict(row), round(0.35 + 0.5 * quality, 4), "fts",
                       hit["reason"], hit["relation"], hit["confidence"])
            if fts["results"]:
                diagnostics["channels"].append("fts")
        except index_mod.IndexError_ as error:
            diagnostics["warnings"].append(error.code + ": " + error.message)

        # 3. vector candidates (optional, never verified)
        if use_vectors:
            vector_hits = vectors_mod.search(connection, query, backend=backend,
                                             top_k=max(top_k * 2, 10))
            if vector_hits.get("enabled"):
                diagnostics["channels"].append("vector")
                for hit in vector_hits["results"]:
                    row = connection.execute(
                        "SELECT * FROM entities WHERE id = ?", (hit["entity"],)).fetchone()
                    if row is None:
                        continue
                    _merge(candidates, dict(row), 0.45 * float(hit["similarity"]),
                           "vector", hit["reason"], ["semantic_candidate"], "inferred")
            else:
                diagnostics["warnings"].append(
                    "vector: " + str(vector_hits.get("reason")) + " — dùng FTS + graph")
                diagnostics["vector"] = vector_hits

        # 3b. flow summaries: a Vietnamese request must reach a rendered flow
        for row in connection.execute(
                "SELECT flow_id, title, request, artifact_dir FROM flows"):
            haystack = normalize_text((row["title"] or "") + " " + (row["request"] or ""))
            hits = sum(1 for term in search_terms if term and term in haystack)
            if hits == 0:
                continue
            entity_row = connection.execute(
                "SELECT * FROM entities WHERE id = ?",
                ("flow:" + row["flow_id"],)).fetchone()
            entity = dict(entity_row) if entity_row else {
                "id": "flow:" + row["flow_id"], "kind": "flow", "name": row["flow_id"],
                "symbol": row["title"], "path": (row["artifact_dir"] or "").split("/flows/")[-1],
                "start_line": 1, "end_line": 1, "language": None, "doc": row["title"],
            }
            _merge(candidates, entity, 0.8, "flow_summary",
                   "flow đã render khớp mô tả nghiệp vụ", ["belongs_to_flow"], "inferred")
        if any("flow_summary" in item["channels"] for item in candidates.values()):
            diagnostics["channels"].append("flow_summary")

        # 4. graph expansion around the strongest exact hits
        if expand and candidates:
            anchors = sorted(candidates.values(), key=lambda item: -item["base"])[:4]
            for anchor in anchors:
                for hop in index_mod.neighbours(connection, anchor["entity"],
                                               EXPAND_PREDICATES, limit=MAX_EXPANSION):
                    other = hop["object"] if hop["subject"] == anchor["entity"] else hop["subject"]
                    row = connection.execute(
                        "SELECT * FROM entities WHERE id = ?", (other,)).fetchone()
                    if row is None:
                        continue
                    quality = hop["confidence"]
                    _merge(candidates, dict(row), 0.45, "graph",
                           "quan hệ " + hop["predicate"] + " với "
                           + anchor["entity"].split(":", 1)[-1],
                           [hop["predicate"]], quality)
            diagnostics["channels"].append("graph")

        flow_members = {row["subject"] for row in connection.execute(
            "SELECT subject FROM facts WHERE predicate = 'belongs_to_flow'")}

        # 5. rerank
        for item in candidates.values():
            quality = item["confidence"]
            score = item["base"]
            if "graph" in item["channels"]:
                score += 0.25
            score += EVIDENCE_WEIGHT.get(quality, 0.0)
            if item["kind"] == "route":
                # A route is the user-facing entry point: when it matches at all
                # it should outrank an internal helper with the same evidence.
                score += 0.15
            if item["entity"] in flow_members:
                # Already part of a rendered journey: strong evidence of relevance,
                # still weaker than an exact identifier match.
                score += 0.2
                item["reasons"].append("thành viên flow đã render")
            if commit and head and commit == head:
                score += 0.05
            if "graph" not in item["channels"] and "exact_symbol" not in item["channels"] \
                    and "exact_route" not in item["channels"] \
                    and "exact_file" not in item["channels"] \
                    and "flow_summary" not in item["channels"]:
                score -= 0.35
                item["reasons"].append("chỉ khớp từ khoá, không có quan hệ graph")
            item["score"] = score
            if stale:
                item["reasons"].append("index cũ hơn HEAD: " + commit + " → " + head)
            item["score"] = round(score, 4)
            item["source_commit"] = commit
            item["confidence"] = _confidence_of(item, quality)
            item["why_matched"] = "; ".join(item["reasons"])
            item["evidence_refs"] = [{
                "path": item["path"], "start_line": item["start_line"],
                "relation": item["relation"][:4] or ["keyword_match"],
                "confidence": item["confidence"],
            }]

        # One symbol can exist as both `function:X` and `symbol:X`. The caller
        # wants a place to read, not two rows for the same place.
        best = {}
        for item in candidates.values():
            # The same symbol may be indexed as `function:X` (declaration) and
            # `symbol:X` (target of an export/call). Same file and same name means
            # one place to read; keep the strongest, preferring the declaration.
            key = ((item["path"], item["symbol"]) if item["symbol"]
                   else (item["path"], item["kind"], item["start_line"]))
            current = best.get(key)
            if current is None or item["score"] > current["score"] \
                    or (item["score"] == current["score"]
                        and _KIND_PRIORITY.get(item["kind"], 0) > _KIND_PRIORITY.get(current["kind"], 0)):
                best[key] = item
        ranked = sorted(best.values(), key=lambda item: (-item["score"], item["path"]))[:top_k]
        flows = index_mod.list_flows(root)

    results = []
    for item in ranked:
        entry = dict(item)
        entry.pop("reasons", None)
        entry.pop("channels", None)
        results.append(entry)

    payload = {
        "status": "ok",
        "query": parsed["text"],
        "intent": parsed["intent"],
        "source_commit": commit,
        "head_commit": head,
        "stale": stale,
        "stale_warning": ("Index được xây ở " + commit + ", HEAD là " + head
                          + "; chạy project_knowledge_refresh.") if stale else "",
        "results": results,
        "channels": sorted(set(diagnostics["channels"])),
        "warnings": diagnostics["warnings"],
        "flows": [{"flow_id": row["flow_id"], "title": row["title"]} for row in flows[:5]],
        "filters": filters,
    }
    if include_snippets:
        payload["snippets"] = _snippets(root, results)
    return payload


def _confidence_of(item, quality):
    channels = item["channels"]
    if "exact_symbol" in channels or "exact_route" in channels or "exact_file" in channels:
        return "observed"
    if quality in EVIDENCE_WEIGHT:
        return quality
    return "structural" if "graph" in channels else "inferred"


def _snippets(root, results, max_lines=40):
    """Opt-in local snippets: only the cited window, only inside the repo."""
    root = Path(os.path.realpath(str(root)))
    output = []
    for item in results[:5]:
        rel = item.get("path")
        if not rel:
            continue
        path = Path(os.path.realpath(str(root / rel)))
        if not facts_mod.is_inside(root, path) or not path.exists():
            continue
        lines = facts_mod.read_lines(path) or []
        start = max(1, int(item.get("start_line") or 1))
        end = min(len(lines), int(item.get("end_line") or start))
        window = lines[start - 1: min(end, start - 1 + max_lines)]
        output.append({"path": rel, "start_line": start,
                       "lines": [facts_mod.SECRET_LINE.sub("", line) for line in window]})
    return output


def context_pack(root, task, max_files=12, include_snippets=False, backend=None):
    """Assemble a context pack for a coding task. No raw source by default."""
    parsed = parse_query(task)
    retrieval = retrieve(root, task, top_k=max(max_files, 6), backend=backend,
                         include_snippets=False)
    stale = retrieval["stale"]
    warnings = list(retrieval["warnings"])
    files, entry_points, impacted, tests, deps = [], [], [], [], []
    seen = set()
    for result in retrieval["results"]:
        if result["path"] and result["path"] not in seen:
            seen.add(result["path"])
            files.append({
                "path": result["path"], "symbol": result["symbol"],
                "start_line": result["start_line"], "end_line": result["end_line"],
                "confidence": result["confidence"], "why_matched": result["why_matched"],
                "relation": result["relation"],
            })
        if "handles_route" in result["relation"]:
            entry_points.append({"path": result["path"], "route": result["symbol"],
                                 "start_line": result["start_line"],
                                 "confidence": result["confidence"]})
        if result["kind"] in {"function", "class", "symbol"}:
            impacted.append({"symbol": result["symbol"], "path": result["path"],
                             "start_line": result["start_line"]})
        if result["kind"] == "test":
            tests.append({"path": result["path"], "start_line": result["start_line"]})
    with index_mod.connect(root, create=False) as connection:
        index_mod._ensure_schema(connection)
        flows = index_mod.list_flows(root)
        for result in retrieval["results"]:
            for hop in index_mod.neighbours(connection, result["entity"],
                                            ["imports", "reads_from", "writes_to"], limit=8):
                other = hop["object"] if hop["subject"] == result["entity"] else hop["subject"]
                if other not in seen:
                    deps.append({"entity": other, "relation": hop["predicate"],
                                 "confidence": hop["confidence"]})
                    seen.add(other)
        for row in connection.execute(
                "SELECT id, path, start_line FROM entities WHERE kind = 'test' LIMIT 40"):
            if parsed["symbol"] and parsed["symbol"].lower() in (row["path"] or "").lower():
                tests.append({"path": row["path"], "start_line": row["start_line"]})
    if stale:
        warnings.append("Knowledge index cũ hơn HEAD; kết quả có thể lệch.")
    pack = {
        "status": "ok",
        "task": task,
        "source_commit": retrieval["source_commit"],
        "head_commit": retrieval["head_commit"],
        "stale": stale,
        "relevant_flows": [{"flow_id": row["flow_id"], "title": row["title"]} for row in flows[:5]],
        "entry_points": entry_points[:max_files],
        "impacted_symbols": impacted[:max_files],
        "related_tests": tests[:max_files],
        "likely_files": files[:max_files],
        "dependencies": deps[:max_files],
        "warnings": warnings,
        "evidence_refs": [ref for result in retrieval["results"]
                          for ref in result["evidence_refs"]][:40],
        "max_files": max_files,
        "snippets_included": bool(include_snippets),
    }
    if include_snippets:
        pack["snippets"] = _snippets(root, retrieval["results"])
    return pack
