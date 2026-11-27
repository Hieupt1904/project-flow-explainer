"""Flow projection: select one user journey out of the static facts.

This is a projection, not a scanner: every fact it uses comes from
pfe.facts (file, line, symbol, route, import, call site, error site). The
projection decides only which facts belong to the requested journey and how
they are titled.

Evidence rules kept by design:

  * membership comes from an explicit route declaration or an import edge -
    a keyword match never adds a node (it lands in meta.related);
  * evidence never says "call" unless a call site (path + line) is attached;
  * a decision branch replaces the direct edge, so a success path can never
    bypass the decision node;
  * an error marker counts only inside the selected route body or the selected
    symbol body, never for the whole file;
  * "verified" means location + membership verified statically. It never means
    the code ran.
"""

import re
from pathlib import Path

from .facts import error_site_in_window
from .text import normalize_text

SCHEMA_VERSION = 2
MAX_STEPS = 12
BQ = chr(96)

EVIDENCE_MEMBERSHIP = {
    "entry": "điểm vào do yêu cầu + khai báo route xác định",
    "import": "file trước import trực tiếp file này",
    "route_body": "cùng file với khai báo route",
    "structure": "nhánh điều kiện do cấu trúc khối xử lý lỗi trong file",
}

CONFIDENCE_MEANING = {
    "verified": "vị trí có thật (file + dòng) và có bằng chứng thành viên (route/import); "
                "xác minh tĩnh, KHÔNG phải chạy runtime",
    "partial": "vị trí có thật nhưng vai trò trong luồng chỉ suy ra từ cấu trúc",
    "inferred": "suy luận từ ngữ cảnh, chưa có bằng chứng trực tiếp",
    "unknown": "chưa xác minh được",
}

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

PREFERRED_SYMBOL = re.compile(
    r"(?i)^(main|run|apply|execute|handler|handle|export|process|start|generate|build_flow|build)$")


REQUEST_STOPWORDS = {
    "the", "and", "for", "from", "with", "this", "that", "are", "was", "were",
    "into", "when", "then", "than", "how", "what", "which", "where", "who",
    "not", "but", "can", "you", "your", "our", "its", "has", "have", "had",
    "giai", "thich", "trong", "khi", "den", "luc", "nhu", "hay", "nay", "kia",
    "duoc", "mot", "cac", "nhung", "cho", "voi", "cua", "la", "se", "da",
    "co", "khong", "tai", "toi", "ban", "nguoi", "dung", "nhan", "cung",
    "len", "xuong", "qua", "lai", "sau", "truoc", "giua", "hoac", "neu",
    "vi", "de", "ma", "thi", "ra", "vao", "lam", "nao", "xem", "biet",
    "can", "muon", "code", "file",
}
HOOK_LABELS = {"apply", "main", "default"}
INDEX_FILENAMES = {
    "index.js", "index.mjs", "index.cjs", "index.ts", "index.tsx",
    "plugin.js", "plugin.mjs", "plugin.ts", "main.js", "main.ts", "main.py",
    "__main__.py", "__init__.py",
}


def request_terms(request_norm):
    """Distinctive tokens from the request, used to score a candidate start."""
    terms = []
    seen = set()
    for token in re.findall(r"[a-z0-9_]{3,}", request_norm):
        if token in REQUEST_STOPWORDS or token in seen:
            continue
        seen.add(token)
        terms.append(token)
    return terms


def _term_bonus(item, start, terms, window):
    score = 0
    rel_norm = normalize_text(re.sub(r"[^A-Za-z0-9]+", " ", item.rel))
    rel_tokens = set(rel_norm.split())
    label = normalize_text(start.get("label") or "")
    blob = normalize_text(window or "")
    for term in terms:
        if term in rel_tokens:
            score += 8
        if term == label or (label and term in label.split()):
            score += 6
        elif term in blob:
            score += 2
    if label in HOOK_LABELS:
        score += 12
    if Path(item.rel).name.lower() in INDEX_FILENAMES:
        score += 6
    return score


def _entry_window(item, start):
    line = start.get("line") or 1
    span = item.body_range(line)
    if not span:
        return (line, min(line + 24, item.line_count))
    return span





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


def pick_symbol(symbols, after_line=0):
    if not symbols:
        return None
    later = [item for item in symbols if item["line"] >= after_line] or symbols
    callables = [item for item in later if item.get("kind") != "class"] or later
    public = [item for item in callables if not item["name"].startswith("_")]
    named = public or [item for item in callables if not item["name"].startswith("__")] or callables
    preferred = [item for item in named if PREFERRED_SYMBOL.match(item["name"])]
    return (preferred or named)[0]


def _ref(rel, line, symbol=None):
    item = {"path": rel, "start_line": int(line)}
    name = (symbol or "").strip()
    if name:
        item["symbol"] = name
    return item


def build_graph(request, files, git):
    """Return (graph, limits, warnings, related) for one request."""
    request_norm = normalize_text(request)
    active = match_facets(request_norm)
    limits = []
    warnings = []
    related = []

    terms = request_terms(request_norm)

    def rank(item):
        best, best_kind, best_index = 0, None, None
        for index, route in enumerate(item.routes):
            start, end = item.route_range(index)
            window = item.window(start, end)
            score = score_window(window, active)
            for facet, _hits in active:
                for pattern in facet["path"]:
                    if re.search(pattern, route.get("label") or ""):
                        score += 6
            score += _term_bonus(item, route, terms, window)
            if score > best:
                best, best_kind, best_index = score, "route", index
        # A command/tool registration inside apply()/main() is a step, not a
        # rival start: the hook is where the host actually enters the file.
        hook_entries = [entry for entry in item.entries
                        if (entry.get("label") or "").lower() in HOOK_LABELS]
        for index, entry in enumerate(item.entries):
            if hook_entries and entry.get("kind") in {"command", "tool"}:
                continue
            start, end = _entry_window(item, entry)
            window = item.window(start, end)
            score = score_window(window, active)
            for facet, _hits in active:
                for pattern in facet["path"]:
                    if re.search(pattern, item.rel) or re.search(pattern, entry.get("label") or ""):
                        score += 6
            score += _term_bonus(item, entry, terms, window)
            if score > best:
                best, best_kind, best_index = score, "entry", index
        return (best, len(item.symbols), item.rel), best_kind, best_index

    ranked = []
    for item in files:
        score, kind, index = rank(item)
        if score[0] > 0 or item.routes or item.entries:
            ranked.append((score, kind, index, item))
    ranked.sort(key=lambda row: (-row[0][0], -row[0][1], row[0][2]))

    facet_labels = ", ".join(facet["label"] for facet, _ in active)
    nodes = []
    edges = []

    def add_node(node_id, title, node_type, summary, confidence, refs, **extra):
        node = {"id": node_id, "title": title, "type": node_type, "summary": summary,
                "confidence": confidence, "source_refs": refs}
        node.update(extra)
        nodes.append(node)

    def add_edge(source, target, label, kind, evidence, technical):
        if evidence == "call":
            raise AssertionError("call evidence requires a call site; this projection never claims one")
        edges.append({"from": source, "to": target, "label": label, "kind": kind,
                      "technical": technical, "evidence": evidence})

    add_node("start", "Bắt đầu từ yêu cầu", "start",
             "Yêu cầu: “" + request.strip() + "”. Nhóm chủ đề: " + facet_labels + ".",
             "partial", [],
             details="Điểm vào của sơ đồ do yêu cầu quyết định, không phải một dòng code cụ thể.",
             technical="entry=request")

    if not ranked:
        add_node("no-evidence", "Không tìm thấy mã nguồn liên quan", "error",
                 "Không file nào trong phạm vi đọc khớp với yêu cầu. Sơ đồ dừng ở đây "
                 "thay vì mô tả một luồng không có bằng chứng.",
                 "unknown", [],
                 details="Cần mô tả flow cụ thể hơn, hoặc repository chưa chứa phần xử lý tương ứng.")
        add_edge("start", "no-evidence", "không khớp mã nguồn", "error", "structure", "no-match")
        limits.append("Không tìm được bằng chứng nào cho yêu cầu này.")
        graph = _finish(nodes, edges, limits, warnings, related, active, request, git)
        return graph, limits, warnings, related

    entry = None
    for score, kind, index, item in ranked:
        if kind is not None and score[0] > 0:
            chosen = item.routes[index] if kind == "route" else item.entries[index]
            entry = (item, chosen, index, kind)
            break
    if entry is None:
        for score, kind, index, item in ranked:
            if item.entries:
                pick = 0
                for offset, candidate in enumerate(item.entries):
                    if (candidate.get("label") or "").lower() in HOOK_LABELS:
                        pick = offset
                        break
                entry = (item, item.entries[pick], pick, "entry")
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
        add_edge("start", "no-entry", "không có điểm vào", "error", "structure", "no-entry")
        related = [{"path": item.rel, "reason": "khớp từ khoá, không có liên kết tới điểm vào"}
                   for _score, _kind, _index, item in ranked[:5]]
        graph = _finish(nodes, edges, limits, warnings, related, active, request, git)
        return graph, limits, warnings, related

    entry_item, entry_route, entry_route_index, entry_kind = entry
    entry_line = entry_route["line"]
    entry_symbol = pick_symbol(entry_item.symbols,
                               after_line=entry_line if entry_kind == "route" else 0)
    entry_label = entry_route.get("label") or (entry_symbol or {}).get("name") or ""

    steps = [{
        "item": entry_item, "line": entry_line, "label": entry_label,
        "evidence": "entry",
        "technical": (("route" if entry_kind == "route" else "điểm vào")
                      + " khai báo tại " + entry_item.rel + ":" + str(entry_line)),
        "window": (entry_item.route_range(entry_route_index) if entry_kind == "route"
                   else entry_item.body_range(entry_line)),
        "symbol": entry_label,
    }]

    by_rel = {item.rel: item for item in files}
    visited = {entry_item.rel}
    queue = [entry_item]
    while queue and len(steps) < MAX_STEPS:
        current = queue.pop(0)
        for edge in current.imports:
            target_rel = edge["path"]
            if target_rel in visited or target_rel not in by_rel:
                continue
            target = by_rel[target_rel]
            visited.add(target_rel)
            symbol = pick_symbol(target.symbols)
            line = (symbol or {}).get("line") or 1
            steps.append({
                "item": target, "line": line,
                "label": (symbol or {}).get("name") or "",
                "evidence": "import",
                "technical": current.rel + " import " + target.rel
                             + (" (qua sys.path)" if edge["style"] == "flat-basename" else "")
                             + " · dòng import " + str(edge["line"]),
                "window": target.body_range(line) if symbol else None,
                "symbol": (symbol or {}).get("name") or "",
            })
            queue.append(target)
            if len(steps) >= MAX_STEPS:
                break

    if len(visited) >= MAX_STEPS:
        warnings.append("Luồng có từ " + str(MAX_STEPS) + " bước trở lên; sơ đồ đã cắt bớt.")
    if len(visited) == 1:
        limits.append(
            "Không có cạnh import/gọi hàm nào từ điểm vào: chưa có call graph thật, "
            "nên sơ đồ chỉ có bước mở đầu thay vì nối các file khớp từ khoá.")

    for index, step in enumerate(steps, start=1):
        step["id"] = "step-" + str(index)
        if index == 1:
            add_node("step-1", ("Nhận yêu cầu " + entry_label) if entry_kind == "route"
                     else ("Bắt đầu tại " + entry_label), "action",
                     ("Điểm vào HTTP" if entry_kind == "route" else "Điểm vào") + " — "
                     + BQ + entry_item.rel + BQ + " (dòng " + str(entry_line) + ").",
                     "verified", [_ref(entry_item.rel, entry_line, entry_label)],
                     details="Bằng chứng thành viên: " + EVIDENCE_MEMBERSHIP["entry"] + ".",
                     technical=entry_item.rel, actor="Hệ thống")
        else:
            item = step["item"]
            module = Path(item.rel).stem
            title = ("Xử lý tại " + step["label"]) if step["label"] else ("Module " + module)
            add_node(step["id"], title, "action",
                     "Bước xử lý — " + BQ + item.rel + BQ + " (dòng " + str(step["line"]) + ").",
                     "verified", [_ref(item.rel, step["line"], step["label"])],
                     details="Bằng chứng thành viên: import từ "
                             + BQ + steps[index - 2]["item"].rel + BQ + ".",
                     technical=item.rel, actor="Hệ thống")

    branch_count = {"value": 0}

    def connect(source_id, source_step, target_id, target_label,
                target_evidence=None, target_technical=None):
        """Emit one edge, through a decision node when the source handles an
        exception inside its own selected window (route body / symbol body).

        The edge carries the evidence of how the *target* is reached, never the
        evidence of the source; an import edge keeps saying "import".
        """
        source = source_step["item"]
        window = source_step["window"]
        site = error_site_in_window(source, window[0], window[1]) if window else None
        if site is None:
            add_edge(source_id, target_id, target_label, "success",
                     target_evidence or source_step["evidence"],
                     target_technical or source_step["technical"])
            return
        suffix = re.sub(r"[^A-Za-z0-9_-]+", "-", source.rel)[:60]
        decision_id = "decision-" + suffix
        error_id = "error-" + suffix
        if not any(node["id"] == decision_id for node in nodes):
            add_node(decision_id, "Có lỗi trong bước này?", "decision",
                     "Bước xử lý có nhánh bắt lỗi trong chính route/hàm được chọn; "
                     "sơ đồ tách nhánh thành công và thất bại.",
                     "partial", [_ref(source.rel, site["line"])],
                     details="Nhánh lỗi suy ra từ khối " + site["kind"]
                             + " nằm trong vùng code của bước này; mã lỗi chưa xác minh.")
            add_node(error_id, "Trả lỗi cho người gọi", "error",
                     "Lỗi được bắt và trả về lớp gọi thay vì kết thúc im lặng.",
                     "partial", [_ref(source.rel, site["line"])],
                     details="Chưa xác minh nội dung thông báo và mã lỗi.")
            add_edge(source_id, decision_id, "vào bước xử lý", "normal", "structure",
                     "cùng bước " + BQ + source.rel + BQ + ", khối " + site["kind"]
                     + " tại dòng " + str(site["line"]))
            add_edge(decision_id, error_id, "có lỗi", "error", "structure",
                     "khối xử lý ngoại lệ trong file")
            branch_count["value"] += 1
        add_edge(decision_id, target_id, target_label, "success",
                 target_evidence or "structure",
                 (target_technical or "đường đi tiếp khi không lỗi") + " · qua nhánh không lỗi")

    add_edge("start", steps[0]["id"], "bắt đầu xử lý", "success", "entry", steps[0]["technical"])
    for index in range(len(steps) - 1):
        following = steps[index + 1]
        connect(steps[index]["id"], steps[index], following["id"], "dùng module",
                following["evidence"], following["technical"])

    last = steps[-1]
    response_pick = None
    for index, step in enumerate(steps):
        candidates = [candidate for candidate in step["item"].response_lines
                      if candidate >= (step["line"] if index == 0 else 1)]
        if candidates:
            response_pick = (step["item"], candidates[0])
            break
    if response_pick:
        add_node("end", "Trả kết quả", "end",
                 "Kết quả được trả về từ " + BQ + response_pick[0].rel + BQ + ".",
                 "verified", [_ref(response_pick[0].rel, response_pick[1])],
                 details="Điểm kết thúc xác định theo lời gọi trả kết quả trong code.")
    else:
        add_node("end", "Kết thúc xử lý", "end",
                 "Không tìm thấy lời gọi trả kết quả rõ ràng; điểm kết thúc suy ra từ bước cuối.",
                 "inferred", [], details="Chưa xác minh nơi trả kết quả cho người dùng.")
        limits.append("Không tìm thấy điểm trả kết quả rõ ràng; node kết thúc là suy luận.")
    connect(last["id"], last, "end", "hoàn tất",
            last["evidence"] if len(steps) > 1 else "entry",
            "bước cuối của luồng" if len(steps) > 1 else "điểm vào trả kết quả")

    for item in files:
        if item.rel in visited:
            continue
        keyword = 0
        for facet, _hits in active:
            for pattern in facet["code"]:
                keyword += len(re.findall(pattern, item.text()))
            for pattern in facet["path"]:
                if re.search(pattern, item.rel):
                    keyword += 3
        if keyword > 0:
            related.append({
                "path": item.rel,
                "reason": "khớp từ khoá nhưng không nối được tới điểm vào bằng import/gọi hàm",
            })
    related.sort(key=lambda entry: entry["path"])

    limits.append("Chưa có call graph runtime: cạnh chỉ mang bằng chứng entry/import/structure; "
                  "không có cạnh nào tự nhận là call.")
    graph = _finish(nodes, edges, limits, warnings, related, active, request, git,
                    branch_count["value"])
    return graph, limits, warnings, related


def _finish(nodes, edges, limits, warnings, related, active, request, git, branch_count=0):
    title_topic = re.sub(r"(?i)^\s*(?:luồng|luong|quy trình|quy trinh|flow)\s*[:\-–]?\s*",
                         "", request.strip())
    title_topic = (title_topic or request.strip())[:120]
    graph = {
        "flow_id": "",
        "title": "Luồng: " + title_topic,
        "description": (
            "Sơ đồ dựng từ phân tích tĩnh theo yêu cầu: " + request.strip() + ". "
            "Mỗi bước trỏ tới file và dòng thật; bước chỉ khớp từ khoá được tách riêng "
            "thay vì nối vào luồng."),
        "audience": "Người không đọc code, BA, kiểm thử",
        "scope": "Đọc source trong repository · " + ", ".join(f["label"] for f, _ in active),
        "entry_node": "start",
        "nodes": nodes,
        "edges": edges,
        "assumptions": limits + warnings,
        "notes": ("Phân tích tĩnh, không chạy code của repository, không dùng network. "
                  "verified = vị trí có thật + có bằng chứng thành viên (route/import). "
                  "partial/inferred = suy luận từ cấu trúc. Không chép nội dung source."),
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "generated_at": "",
            "source": git,
            "request": request.strip(),
            "facets": [facet["id"] for facet, _ in active],
            "related": related,
            "projection": {
                "kind": "flow",
                "source": "static_facts",
                "scanner": "pfe.facts",
                "branch_count": branch_count,
            },
            "evidence_model": {
                "membership": EVIDENCE_MEMBERSHIP,
                "confidence": CONFIDENCE_MEANING,
                "call_edges": False,
                "runtime_verified": False,
                "note": ("Không có cạnh nào mang evidence=call: projection này không có "
                         "call-site parser cho flow. verified mô tả xác minh tĩnh vị trí và "
                         "quan hệ, không phải đã chạy code."),
            },
        },
    }
    return graph
