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


ENTRY_KIND_ORDER = {"http_route": 0, "main": 1, "cli_command": 2, "gui_event": 3,
                    "button_click": 4, "callback": 5, "worker": 6, "public_api": 7,
                    "export": 8, "command": 9}
ENTRY_KINDS_EMITTED = {"http_route", "main", "cli_command", "gui_event", "button_click",
                       "callback", "worker", "public_api"}
ENTRY_KINDS_DECLARED_ONLY = {
    "export": "module.exports là ranh giới module, mọi file JS đều có; cần consumer edge mới là entry",
    "command": "chưa có parser cho shell command; cần fixture riêng trước khi phát",
}
# Containment (`defines`) and module boundaries (`exports`) are not
# dependencies: including them filled the pack with every symbol of the file.
DEPENDENCY_PREDICATES = ["imports", "calls", "reads_from", "writes_to", "tested_by",
                         "raises", "catches"]


def _relevance(result, error_intent):
    """Task-aware relevance for the pack (search ranking is left untouched)."""
    score = float(result.get("score") or 0.0)
    kind = result.get("kind")
    why = []
    if kind == "route":
        score += 0.3
        why.append("entry point (route có khai báo)")
    if kind in {"function", "class"}:
        score += 0.1
        why.append("symbol thực thi được")
    if error_intent:
        if kind == "error_case" or any(item in {"raises", "catches"} for item in result["relation"]):
            score += 0.35
            why.append("khớp ý định tìm lỗi")
        if kind == "test":
            score += 0.2
            why.append("test liên quan tới lỗi")
    else:
        if kind == "error_case":
            score -= 0.3
            why.append("không hỏi lỗi nên hạ ưu tiên error_case")
        if kind == "test":
            score -= 0.15
            why.append("không hỏi lỗi nên hạ ưu tiên test")
    return score, why


def _entry_points(connection, results, paths):
    """Entry points that carry observed evidence, joined by file."""
    entries = []
    if not paths:
        return entries
    placeholders = ",".join("?" for _ in paths)
    rows = connection.execute(
        "SELECT path, kind, label, start_line, evidence_kind, confidence FROM entry_points "
        "WHERE path IN (" + placeholders + ") ORDER BY path, start_line",
        tuple(paths)).fetchall()
    for row in rows:
        if row["kind"] not in ENTRY_KINDS_EMITTED:
            continue
        entries.append({
            "path": row["path"],
            "kind": row["kind"],
            "label": row["label"] or "",
            "route": row["label"] or "",  # backward-compatible field
            "start_line": row["start_line"],
            "confidence": row["confidence"] or "observed",
            "evidence_kind": row["evidence_kind"] or "observed",
            "evidence_refs": [{"path": row["path"], "start_line": row["start_line"],
                               "relation": ["handles_route"] if row["kind"] == "http_route"
                               else ["registered_entry"],
                               "confidence": row["confidence"] or "observed"}],
        })
    entries.sort(key=lambda item: (ENTRY_KIND_ORDER.get(item["kind"], 99),
                                   item["path"], item["start_line"]))
    return entries


def _route_entities(connection, results):
    """Real route entities reachable from a result by handles_route.

    Never uses result['symbol'] as a route: a symbol is a function or file name
    unless a handles_route fact points at an actual route entity.
    """
    routes = []
    seen = set()
    for result in results:
        for hop in index_mod.neighbours(connection, result["entity"], ["handles_route"], limit=10):
            target = hop["object"] if hop["predicate"] == "handles_route" else None
            if not target or not target.startswith("route:"):
                continue
            if target in seen:
                continue
            seen.add(target)
            entity = index_mod.entity(connection, target)
            if entity is None:
                continue
            routes.append({
                "route": entity["name"],
                "path": entity["path"] or "",
                "start_line": entity["start_line"] or 1,
                "confidence": hop["confidence"],
                "via": result["entity"],
                "evidence_refs": [{"path": entity["path"] or "",
                                   "start_line": entity["start_line"] or 1,
                                   "relation": ["handles_route"],
                                   "confidence": hop["confidence"]}],
            })
    return routes


def _dependency(connection, entity_id, source, error_intent):
    entity = index_mod.entity(connection, entity_id)
    if entity is None:
        return None
    hops = index_mod.neighbours(connection, source["entity"], DEPENDENCY_PREDICATES, limit=40)
    relation, confidence, why = None, None, None
    for hop in hops:
        other = hop["object"] if hop["subject"] == source["entity"] else hop["subject"]
        if other == entity_id:
            relation, confidence = hop["predicate"], hop["confidence"]
            line = (hop["evidence"] or {}).get("start_line") or 1
            why = ("quan hệ " + relation + " với " + (source.get("symbol") or source["path"])
                   + " tại dòng " + str(line))
            break
    if relation is None:
        return None
    kind = entity["kind"]
    has_location = bool(entity["path"]) and bool(entity["start_line"])
    if error_intent and kind in {"error_case", "test"}:
        relevance = "observed"
    elif confidence == "observed":
        relevance = "observed"
    elif confidence == "structural":
        relevance = "structural"
    else:
        relevance = "inferred"
    return {
        "entity": entity["id"],
        "kind": kind,
        "path": entity["path"] or "",
        "symbol": entity["symbol"] or entity["name"] or "",
        "start_line": entity["start_line"] or 1,
        "end_line": entity["end_line"] or entity["start_line"] or 1,
        "relation": relation,
        "confidence": relevance,
        "location_confidence": "observed" if entity["path"] and entity["start_line"] else "unknown",
        "relevance_confidence": relevance,
        "why_included": why,
        "has_location": has_location,
        "evidence_refs": [{
            "path": entity["path"] or "",
            "start_line": entity["start_line"] or 1,
            "relation": [relation],
            "confidence": relevance,
        }] if has_location else [],
    }


def context_pack(root, task, max_files=12, include_snippets=False, backend=None):
    """Assemble a context pack for a coding task.

    Output answers three questions and says what it does not know:

      where does this code start?   entry_points (observed registration lines)
      what must I read?             likely_files + dependencies (path + line)
      why is this here?             why_matched / why_included + evidence_refs

    Entry points are never inferred from a function name, and a route label is
    only reported when a `handles_route` fact points at a real route entity.
    """
    parsed = parse_query(task)
    error_intent = parsed["has_error_term"]
    retrieval = retrieve(root, task, top_k=max(max_files * 2, 12), backend=backend,
                         include_snippets=False)
    stale = retrieval["stale"]
    warnings = list(retrieval["warnings"])
    limitations = [
        "Phân tích tĩnh: chưa chạy code, chưa thực thi test.",
        "Entry point chỉ lấy từ dòng đăng ký thật (route, add_parser, command=, bind, "
        "decorator task, __main__, __all__); không suy từ tên hàm.",
    ]
    if not parsed["routes"]:
        limitations.append("Không có route HTTP nào trong câu hỏi; dự án desktop/CLI "
                           "có thể có 0 http_route và điều đó là đúng.")

    with index_mod.connect(root, create=False) as connection:
        index_mod._ensure_schema(connection)
        ranked = []
        for result in retrieval["results"]:
            score, why = _relevance(result, error_intent)
            result = dict(result)
            result["relevance_score"] = round(score, 4)
            result["relevance_why"] = why
            ranked.append(result)
        ranked.sort(key=lambda item: (-item["relevance_score"], item["path"]))
        ranked = ranked[:max_files]

        seen_paths, seen_entities, seen_evidence = set(), set(), set()

        def add_evidence(refs):
            fresh = []
            for ref in refs or []:
                key = (ref.get("path"), ref.get("start_line"),
                       tuple(ref.get("relation") or []))
                if key in seen_evidence:
                    continue
                seen_evidence.add(key)
                fresh.append(ref)
            return fresh

        likely_files = []
        for result in ranked:
            if result["path"] and result["path"] not in seen_paths:
                seen_paths.add(result["path"])
                seen_entities.add(result["entity"])
                likely_files.append({
                    "path": result["path"],
                    "symbol": result["symbol"],
                    "kind": result["kind"],
                    "start_line": result["start_line"],
                    "end_line": result["end_line"],
                    "confidence": result["confidence"],
                    "location_confidence": ("observed" if result["path"] and result["start_line"]
                                            else "unknown"),
                    "relevance_confidence": result["confidence"],
                    "why_matched": result["why_matched"],
                    "relevance_why": result["relevance_why"],
                    "relation": result["relation"],
                    "evidence_refs": add_evidence(result["evidence_refs"]),
                })

        entry_points = _entry_points(connection, ranked, list(seen_paths))
        routes = _route_entities(connection, ranked)

        dependencies, external = [], []
        for result in ranked[:max_files]:
            for hop in index_mod.neighbours(connection, result["entity"],
                                            DEPENDENCY_PREDICATES, limit=30):
                other = hop["object"] if hop["subject"] == result["entity"] else hop["subject"]
                if other in seen_entities:
                    continue
                dep = _dependency(connection, other, result, error_intent)
                if dep is None:
                    continue
                seen_entities.add(other)
                if dep.pop("has_location", True):
                    dep["evidence_refs"] = add_evidence(dep["evidence_refs"])
                    dependencies.append(dep)
                else:
                    # A data model or an external package has no file: keep it,
                    # but never pretend it has a path/line.
                    external.append({
                        "entity": dep["entity"], "kind": dep["kind"],
                        "symbol": dep["symbol"], "relation": dep["relation"],
                        "confidence": dep["confidence"],
                        "why_included": dep["why_included"],
                        "location": "không có trong repository",
                    })
                if len(dependencies) >= max_files * 3:
                    break
            if len(dependencies) >= max_files * 3:
                break

        tests = [item for item in dependencies if item["kind"] == "test"]
        impacted = [item for item in likely_files
                    if item["kind"] in {"function", "class", "symbol"}]
        flows = index_mod.list_flows(root)

    pack = {
        "status": "ok",
        "analysis_kind": "context_pack",
        "task": task,
        "intent": parsed["intent"],
        "source_commit": retrieval["source_commit"],
        "head_commit": retrieval["head_commit"],
        "stale": stale,
        "relevant_flows": [{"flow_id": row["flow_id"], "title": row["title"]}
                           for row in flows[:5]],
        "entry_points": entry_points[:max_files],
        "routes": routes[:max_files],
        "impacted_symbols": [{"symbol": item["symbol"], "path": item["path"],
                              "start_line": item["start_line"],
                              "kind": item["kind"],
                              "confidence": item["relevance_confidence"]}
                             for item in impacted[:max_files]],
        "related_tests": [{"path": item["path"], "test": item["symbol"],
                           "start_line": item["start_line"],
                           "confidence": item["relevance_confidence"],
                           "why_included": item["why_included"]}
                          for item in tests[:max_files]],
        "likely_files": likely_files,
        "dependencies": dependencies,
        "external_dependencies": external[:max_files],
        "warnings": warnings,
        "limitations": limitations,
        "seen": {"paths": len(seen_paths), "entities": len(seen_entities),
                 "evidence": len(seen_evidence)},
        "evidence_refs": [ref for item in likely_files for ref in item["evidence_refs"]][:40],
        "max_files": max_files,
        "snippets_included": bool(include_snippets),
        "not_verified": ["runtime", "ui"] if not include_snippets else ["runtime", "ui"],
    }
    if include_snippets:
        pack["snippets"] = _snippets(root, ranked)
    return pack
