"""Turn static facts into evidence-backed ontology records.

Every entity and relation produced here cites the file and line it came from.
Nothing is guessed: a symbol resolves only by unique name, a route only by an
explicit declaration, a call only by a call site, a test only by an explicit
reference to the tested name.
"""

import hashlib
import re
from pathlib import Path

from . import ontology

BACKTICK = chr(96)


def repository_id(root):
    """Stable id that never exposes the workstation path."""
    return hashlib.sha256(str(Path(root).resolve()).encode("utf-8")).hexdigest()[:16]


def module_id(rel):
    p = Path(rel)
    parts = list(p.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else p.stem


def symbol_id(rel, name):
    return "symbol:" + rel + "#" + name


def route_id(method, label):
    verb = (method or "").upper() or "ANY"
    return "route:" + verb + " " + label


def build_knowledge(root, files, git, flow=None, artifacts=(), commits=None):
    """Return {repository_id, source_commit, entities, facts, stats}."""
    repo_name = Path(root).name
    repo_id = repository_id(root)
    commit = (git or {}).get("commit") or ""
    repository = ontology.entity_id("repository", repo_name)
    commit_entity = ontology.entity_id("commit", commit) if commit else None
    entities = {}
    facts = []

    def add_entity(eid, kind, **extra):
        record = entities.get(eid)
        if record is None:
            record = {"id": eid, "kind": kind}
            entities[eid] = record
        record.update({k: v for k, v in extra.items() if v not in (None, "", [])})
        return eid

    def emit(subject, predicate, object_, evidence_kind, confidence, **evidence_kwargs):
        facts.append(ontology.fact(
            subject, predicate, object_,
            ontology.evidence(evidence_kind, **evidence_kwargs),
            confidence, commit, "pfe.knowledge"))

    add_entity(repository, "repository", name=repo_name)
    if commit_entity:
        add_entity(commit_entity, "commit", name=commit)

    symbol_index = {}
    for item in files:
        for symbol in item.symbols:
            symbol_index.setdefault(symbol["name"], []).append((item.rel, symbol["line"]))

    test_files = [item for item in files if item.is_test]
    stats = {"entities": 0, "facts": 0, "calls": 0, "routes": 0, "tests": 0}

    for item in files:
        rel = item.rel
        file_entity = add_entity(ontology.entity_id("file", rel), "file",
                                 name=rel, path=rel, language=item.language,
                                 content_hash=item.content_hash, size=item.size,
                                 module=module_id(rel),
                                 symbol=Path(rel).stem, doc=(item.doc or "")[:1200])
        emit(repository, "contains", file_entity, "structural", "structural",
             path=rel, start_line=1, detail="file nằm trong repository")
        if commit_entity and commits and rel in commits:
            emit(file_entity, "changed_in_commit",
                 ontology.entity_id("commit", commits[rel]), "observed", "observed",
                 path=rel, start_line=1, detail="git log read-only")

        if item.language in {"javascript", "typescript"}:
            add_entity(ontology.entity_id("module", module_id(rel)), "module",
                       name=module_id(rel), path=rel)

        for symbol in item.symbols:
            kind = "class" if symbol["kind"] == "class" else "function"
            sid = add_entity(ontology.entity_id(kind, rel + "#" + symbol["name"]), kind,
                             name=symbol["name"], path=rel, start_line=symbol["line"],
                             symbol=symbol["name"], file=rel)
            emit(file_entity, "defines", sid, "observed", "observed",
                 path=rel, start_line=symbol["line"], symbol=symbol["name"])
            add_entity(symbol_id(rel, symbol["name"]), "symbol",
                       name=symbol["name"], path=rel, start_line=symbol["line"],
                       symbol=symbol["name"])

        for route in item.routes:
            rid = add_entity(route_id(route.get("method"), route["label"]), "route",
                             name=route["label"], method=(route.get("method") or "").upper(),
                             path=rel, start_line=route["line"])
            emit(file_entity, "handles_route", rid, "observed", "observed",
                 path=rel, start_line=route["line"], detail="khai báo route")
            stats["routes"] += 1

        for edge in item.imports:
            target_module = add_entity(ontology.entity_id("module", module_id(edge["path"])),
                                       "module", name=module_id(edge["path"]), path=edge["path"])
            emit(file_entity, "imports", target_module, "structural", "structural",
                 path=rel, start_line=edge.get("line") or 1,
                 detail="spec " + str(edge.get("spec")) + " · " + str(edge.get("style")))

        for name in item.exports:
            target = symbol_index.get(name) or []
            same = [entry for entry in target if entry[0] == rel]
            if not same:
                continue
            sid = ontology.entity_id("symbol", rel + "#" + name)
            add_entity(sid, "symbol", name=name, path=rel, start_line=same[0][1],
                       symbol=name)
            emit(file_entity, "exports", sid, "observed", "observed",
                 path=rel, start_line=same[0][1], symbol=name)

        for site in item.call_sites:
            name = site["name"]
            targets = symbol_index.get(name) or []
            if len(targets) != 1:
                continue
            target_rel, target_line = targets[0]
            if target_rel == rel and site["caller"] == name:
                continue
            targets_id = add_entity(ontology.entity_id("symbol", target_rel + "#" + name),
                                    "symbol", name=name, path=target_rel,
                                    start_line=target_line, symbol=name)
            emit(file_entity, "calls", targets_id, "call_site", "observed",
                 path=rel, start_line=site["line"], symbol=site["caller"] or name,
                 detail="call site; declaration tại " + target_rel + ":" + str(target_line))
            stats["calls"] += 1

        for table in item.reads:
            did = add_entity(ontology.entity_id("data_model", table), "data_model", name=table)
            emit(file_entity, "reads_from", did, "observed", "observed",
                 path=rel, start_line=1, detail="SELECT … FROM " + table)

        for table in item.writes:
            did = add_entity(ontology.entity_id("data_model", table), "data_model", name=table)
            emit(file_entity, "writes_to", did, "observed", "observed",
                 path=rel, start_line=1, detail="ghi vào " + table)

        for pkg in item.external_imports:
            if pkg in {"node", "sys", "os", "re", "json", "path", "fs"}:
                continue
            xid = add_entity(ontology.entity_id("external_system", pkg),
                             "external_system", name=pkg)
            emit(file_entity, "reads_from", xid, "structural", "structural",
                 path=rel, start_line=1, detail="import gói ngoài")

        for site in item.raise_sites:
            case = ontology.entity_id(
                "error_case", rel + "#" + site["kind"] + "@" + str(site["line"]))
            add_entity(case, "error_case", name=site["kind"], path=rel,
                       start_line=site["line"])
            emit(file_entity, "raises", case, "observed", "observed",
                 path=rel, start_line=site["line"], detail=site["kind"])

        for site in item.error_sites:
            case = ontology.entity_id(
                "error_case", rel + "#caught@" + str(site["line"]))
            add_entity(case, "error_case", name="caught-" + site["kind"], path=rel,
                       start_line=site["line"])
            emit(file_entity, "catches", case, "observed", "observed",
                 path=rel, start_line=site["line"], detail="khối " + site["kind"])

        if item.is_test:
            add_entity(ontology.entity_id("test", rel), "test", name=rel, path=rel,
                       start_line=1)
            stats["tests"] += 1

    for test in test_files:
        referenced = set(test.identifiers)
        if not referenced:
            continue
        for item in files:
            if item.is_test or item.rel == test.rel:
                continue
            names = {symbol["name"] for symbol in item.symbols}
            names.add(Path(item.rel).stem)
            hit = sorted(name for name in names if len(name) > 3 and name in referenced)
            if not hit:
                continue
            test_entity = ontology.entity_id("test", test.rel)
            for name in hit[:3]:
                # "X tested_by Y" reads as: X is tested by Y. The subject is the
                # code under test, the object is the test that references it.
                emit(ontology.entity_id("file", item.rel), "tested_by",
                     test_entity, "structural", "structural",
                     path=test.rel, start_line=1,
                     detail="test nhắc tới " + name)

    if flow:
        flow_entity = add_entity(ontology.entity_id("flow", flow["flow_id"]), "flow",
                                 name=flow["flow_id"], path="artifacts/flows", start_line=1,
                                 title=flow.get("title", ""))
        for node in flow.get("nodes", []):
            for ref in node.get("source_refs") or []:
                emit(ontology.entity_id("file", ref["path"]), "belongs_to_flow",
                     flow_entity, "inferred", "inferred",
                     path=ref["path"], start_line=ref.get("start_line") or 1,
                     detail="thành viên luồng " + flow["flow_id"])
        for item in flow.get("meta", {}).get("related", []):
            emit(ontology.entity_id("file", item["path"]), "related_to", flow_entity,
                 "inferred", "inferred", path=item["path"], start_line=1,
                 detail="chỉ khớp từ khoá: " + item["reason"])
        for artifact in artifacts:
            aid = add_entity(ontology.entity_id("artifact", artifact), "artifact",
                             name=artifact, path=artifact, start_line=1)
            emit(aid, "generated_from", flow_entity, "observed", "observed",
                 path="artifacts/flows", start_line=1, detail="artifact sinh từ flow")

    merged = ontology.validate_facts(facts)
    stats["entities"] = len(entities)
    stats["facts"] = len(merged)
    return {
        "schema_version": ontology.SCHEMA_VERSION,
        "repository_id": repo_id,
        "repository_name": repo_name,
        "source_commit": commit,
        "generated_by": "pfe.knowledge",
        "entities": sorted(entities.values(), key=lambda item: item["id"]),
        "facts": merged,
        "stats": stats,
        "relations_emitted": sorted({record["predicate"] for record in merged}),
        "relations_declared_only": ontology.NOT_EMITTED,
    }
