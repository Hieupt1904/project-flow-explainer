"""Lightweight code-knowledge ontology: entities, relations, evidence, confidence.

The ontology is deliberately small and local. It is not a triple store and not
a graph database: facts are plain records validated against this file, so any
projection (flow diagram, search result, impact report) can agree on what a
fact means and what evidence it must carry.

Vocabulary decisions that matter for honesty:

  * confidence separates *how* a fact was obtained. observed = read at
    path:line; structural = derived from structure (imports, declarations);
    inferred = heuristic; runtime_verified = only with runtime evidence, which
    this static layer never produces; stale/contradicted are health states.
  * an inferred fact never replaces an observed fact for the same
    subject/predicate/object: the observed one wins, and the conflict is
    recorded as contradicted instead of silently merging.
  * a relation is emitted only when its evidence kind fits it. `calls` needs a
    call site (path + line). `handles_route` needs a route declaration.
  * `returns` is declared but not emitted: static text cannot prove a return
    value without type information. Declared-but-unemitted relations are listed
    in EMITTED_RELATIONS so documentation and tests cannot drift.
"""

import re

SCHEMA_VERSION = 1
BACKTICK = chr(96)

ENTITY_TYPES = {
    "repository", "commit", "directory", "file", "module", "symbol", "function",
    "class", "route", "service", "data_model", "external_system", "test", "flow",
    "error_case", "artifact",
}

CONFIDENCE = {
    "observed", "structural", "inferred", "runtime_verified", "stale", "contradicted",
}

# subject entity types -> predicate -> object entity types
RELATIONS = {
    "contains": ({"repository", "directory", "file", "module"}, {"file", "symbol", "directory"}),
    "defines": ({"file", "module"}, {"symbol", "function", "class"}),
    "imports": ({"file", "module"}, {"module", "file"}),
    "exports": ({"file", "module"}, {"symbol", "function", "class"}),
    "calls": ({"file", "module", "symbol", "function"}, {"symbol", "function"}),
    "handles_route": ({"file", "module", "service"}, {"route"}),
    "reads_from": ({"file", "module", "function", "symbol"}, {"data_model", "external_system"}),
    "writes_to": ({"file", "module", "function", "symbol"}, {"data_model", "external_system"}),
    "returns": ({"function", "symbol", "route", "class"}, {"data_model", "external_system", "symbol"}),
    "raises": ({"file", "function", "symbol"}, {"error_case"}),
    "catches": ({"file", "function", "symbol"}, {"error_case"}),
    "tested_by": ({"file", "module", "symbol", "function"}, {"test", "file"}),
    "belongs_to_flow": ({"file", "symbol", "function", "route", "service"}, {"flow"}),
    "related_to": ({"file", "module", "symbol", "service", "flow"}, {"file", "module", "symbol", "service", "flow"}),
    "generated_from": ({"artifact"}, {"repository", "flow", "commit"}),
    "changed_in_commit": ({"file", "directory"}, {"commit"}),
}

# Relations the static layer really emits, with the evidence kind that justifies
# each one. A relation present in RELATIONS but absent here is vocabulary only.
EMITTED_RELATIONS = {
    "contains": {"structural"},
    "defines": {"observed"},
    "imports": {"structural"},
    "exports": {"observed"},
    # A call is proven by its call site (path + line), not by a declaration.
    "calls": {"call_site"},
    "handles_route": {"observed"},
    "reads_from": {"observed", "structural"},
    "writes_to": {"observed", "structural"},
    "raises": {"observed"},
    "catches": {"observed"},
    "tested_by": {"structural"},
    "belongs_to_flow": {"inferred"},
    "related_to": {"inferred"},
    "generated_from": {"observed"},
    "changed_in_commit": {"observed"},
}

NOT_EMITTED = {
    "returns": "cần thông tin kiểu/giá trị trả về; đọc text tĩnh không chứng minh được",
}

# <kind>:<name>; the name may contain single spaces (for example "route:GET /api/x")
# but never a newline, and never a leading/trailing space.
ID_PATTERN = re.compile(r"^[a-z_]+:[^\n]{1,300}$")


def normalize_id(value):
    """Collapse whitespace inside an id so 'route:GET  /x' and 'route:GET /x' match."""
    if not isinstance(value, str):
        return value
    kind, _, name = value.partition(":")
    return kind + ":" + re.sub(r"\s+", " ", name).strip()


class OntologyError(ValueError):
    """A fact that does not fit the ontology."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def entity_id(kind, name):
    if kind not in ENTITY_TYPES:
        raise OntologyError("unknown_entity_type", "Loại entity không hỗ trợ: " + str(kind))
    cleaned = re.sub(r"\s+", " ", str(name)).strip()
    if not cleaned:
        raise OntologyError("empty_entity_name", "Tên entity rỗng")
    return kind + ":" + cleaned[:300]


def fact(subject, predicate, object_, evidence, confidence, source_commit, generated_by):
    """Build one fact record. Validation happens in validate_fact."""
    return {
        "subject": subject,
        "predicate": predicate,
        "object": object_,
        "evidence": evidence,
        "confidence": confidence,
        "source_commit": source_commit or "",
        "generated_by": generated_by,
    }


def validate_fact(record):
    if not isinstance(record, dict):
        raise OntologyError("invalid_fact", "Fact phải là object")
    for key in ("subject", "predicate", "object", "confidence", "generated_by"):
        if key not in record:
            raise OntologyError("missing_field", "Fact thiếu trường " + key)
    subject = normalize_id(record["subject"])
    object_ = normalize_id(record["object"])
    record["subject"] = subject
    record["object"] = object_
    for label, value in (("subject", subject), ("object", object_)):
        if not isinstance(value, str) or not ID_PATTERN.match(value):
            raise OntologyError("invalid_entity_id",
                                label + " phải có dạng <kind>:<name>, nhận được " + repr(value))
        kind = value.split(":", 1)[0]
        if kind not in ENTITY_TYPES:
            raise OntologyError("unknown_entity_type", "Loại entity không hỗ trợ: " + kind)
    predicate = record["predicate"]
    if predicate not in RELATIONS:
        raise OntologyError("unknown_relation", "Quan hệ không hỗ trợ: " + str(predicate))
    if predicate in NOT_EMITTED:
        raise OntologyError("relation_not_emittable",
                            "Quan hệ " + predicate + " chưa được lớp tĩnh sinh ra: "
                            + NOT_EMITTED[predicate])
    subject_kind = subject.split(":", 1)[0]
    object_kind = object_.split(":", 1)[0]
    allowed_subject, allowed_object = RELATIONS[predicate]
    if subject_kind not in allowed_subject:
        raise OntologyError("invalid_subject_type",
                            predicate + " không nhận subject " + subject_kind)
    if object_kind not in allowed_object:
        raise OntologyError("invalid_object_type", predicate + " không nhận object " + object_kind)
    confidence = record["confidence"]
    if confidence not in CONFIDENCE:
        raise OntologyError("invalid_confidence", "Mức tin cậy không hỗ trợ: " + str(confidence))
    evidence = record.get("evidence")
    if not isinstance(evidence, dict) or not evidence.get("kind"):
        raise OntologyError("missing_evidence", "Fact phải có evidence.kind")
    kind = evidence["kind"]
    if predicate in EMITTED_RELATIONS and kind not in EMITTED_RELATIONS[predicate]:
        raise OntologyError(
            "evidence_kind_mismatch",
            predicate + " cần evidence " + "/".join(sorted(EMITTED_RELATIONS[predicate]))
            + ", nhận được " + kind)
    if confidence == "runtime_verified" and not evidence.get("runtime"):
        raise OntologyError("runtime_evidence_required",
                            "confidence=runtime_verified chỉ hợp lệ khi có evidence.runtime")
    if confidence == "observed":
        path = evidence.get("path")
        line = evidence.get("start_line")
        if not isinstance(path, str) or not path:
            raise OntologyError("observed_without_location",
                                "confidence=observed cần evidence.path")
        if not isinstance(line, int) or line < 1:
            raise OntologyError("observed_without_location",
                                "confidence=observed cần evidence.start_line >= 1")
    if predicate == "calls":
        if evidence.get("kind") != "call_site" or not evidence.get("start_line"):
            raise OntologyError("call_without_call_site",
                                "calls phải trỏ đúng dòng gọi hàm (call site)")
    if not isinstance(record.get("source_commit"), str):
        raise OntologyError("invalid_source_commit", "source_commit phải là chuỗi")
    return record


def fact_key(record):
    return (record["subject"], record["predicate"], record["object"])


def validate_facts(records):
    """Validate a list and resolve duplicate keys without silent merging."""
    seen = {}
    merged = []
    for record in records:
        validate_fact(record)
        key = fact_key(record)
        previous = seen.get(key)
        if previous is None:
            seen[key] = record
            merged.append(record)
            continue
        winner = _prefer(previous, record)
        loser = record if winner is previous else previous
        winner = dict(winner)
        winner["contradicted"] = {
            "confidence": loser["confidence"],
            "evidence": loser.get("evidence"),
        }
        seen[key] = winner
        for index, item in enumerate(merged):
            if fact_key(item) == key:
                merged[index] = winner
                break
    return merged


CONFIDENCE_RANK = {"observed": 4, "runtime_verified": 3, "structural": 2,
                   "inferred": 1, "stale": 0, "contradicted": 0}


def _prefer(left, right):
    """Observed beats inferred; equal ranks keep the first fact (stable)."""
    left_rank = CONFIDENCE_RANK.get(left["confidence"], 0)
    right_rank = CONFIDENCE_RANK.get(right["confidence"], 0)
    if right_rank > left_rank:
        return right
    return left


def evidence(kind, path=None, start_line=None, end_line=None, symbol=None, detail=""):
    item = {"kind": kind}
    if path:
        item["path"] = path
    if start_line:
        item["start_line"] = int(start_line)
    if end_line:
        item["end_line"] = int(end_line)
    if symbol:
        item["symbol"] = symbol
    if detail:
        item["detail"] = detail
    return item


def describe(record):
    """One human-readable line, no source text."""
    location = ""
    path = (record.get("evidence") or {}).get("path")
    line = (record.get("evidence") or {}).get("start_line")
    if path:
        location = " @ " + path + (":" + str(line) if line else "")
    return (record["subject"] + " " + record["predicate"] + " " + record["object"]
            + " [" + record["confidence"] + location + "]")
