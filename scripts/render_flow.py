#!/usr/bin/env python3
"""Validate flow JSON and generate a self-contained, offline interactive HTML diagram.

Usage:
  python render_flow.py flow.json --out flow.html
  python render_flow.py flow.json --check-only
No third-party packages required.
"""

import argparse
import json
import re
import sys
from collections import defaultdict, deque
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
TEMPLATE = HERE / "assets" / "workflow_template.html"
ALLOWED_TYPES = {"start", "message", "action", "decision", "data", "end", "error", "external"}
ALLOWED_CONFIDENCE = {"verified", "partial", "inferred", "unknown", "illustrative"}
ALLOWED_KINDS = {"normal", "condition", "success", "error", "fallback", "loop"}
REQUIRED_GRAPH = ("flow_id", "title", "description", "entry_node", "nodes", "edges")
REQUIRED_NODE = ("id", "title", "type", "summary", "confidence")
REQUIRED_EDGE = ("from", "to", "label", "kind")
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


class FlowError(ValueError):
    """Schema and graph validation error."""


def fail(message):
    raise FlowError(message)


def text_field(record, field, context, empty=False):
    value = record.get(field)
    if not isinstance(value, str) or (not empty and not value.strip()):
        fail(f"{context}.{field} phải là chuỗi không rỗng")
    if len(value) > 2500:
        fail(f"{context}.{field} vượt giới hạn 2500 ký tự")
    return value


def validate(data):
    if not isinstance(data, dict):
        fail("Dữ liệu gốc phải là JSON object")
    for field in REQUIRED_GRAPH:
        if field not in data:
            fail(f"Thiếu trường bắt buộc của flow: {field}")
    for field in ("flow_id", "title", "description", "entry_node"):
        text_field(data, field, "flow")
    if not ID_PATTERN.fullmatch(data["flow_id"]):
        fail("flow.flow_id chỉ nhận chữ Latin, số, gạch dưới và gạch ngang")
    if not isinstance(data["nodes"], list) or not data["nodes"]:
        fail("nodes phải là mảng và có ít nhất 1 node")
    if not isinstance(data["edges"], list):
        fail("edges phải là mảng")
    if len(data["nodes"]) > 250 or len(data["edges"]) > 600:
        fail("Flow quá lớn (>250 node hoặc >600 cạnh): hãy tách thành nhiều subflow")
    node_ids = set()
    for index, node in enumerate(data["nodes"]):
        context = f"nodes[{index}]"
        if not isinstance(node, dict):
            fail(f"{context} phải là object")
        for field in REQUIRED_NODE:
            text_field(node, field, context)
        if not ID_PATTERN.fullmatch(node["id"]):
            fail(f"{context}.id không hợp lệ: {node['id']}")
        if node["id"] in node_ids:
            fail(f"Node id trùng: {node['id']}")
        node_ids.add(node["id"])
        if node["type"] not in ALLOWED_TYPES:
            fail(f"{context}.type không hỗ trợ: {node['type']}")
        if node["confidence"] not in ALLOWED_CONFIDENCE:
            fail(f"{context}.confidence không hỗ trợ: {node['confidence']}")
        for field in ("details", "technical", "actor"):
            if field in node:
                text_field(node, field, context, empty=True)
        if ("x" in node) != ("y" in node):
            fail(f"{context}: cần có cả x và y, hoặc bỏ cả hai")
        if "x" in node and (not all(isinstance(node[k], (int, float)) and not isinstance(node[k], bool) and -100 <= node[k] <= 25000 for k in ("x", "y"))):
            fail(f"{context}: tọa độ x/y không hợp lệ")
        refs = node.get("source_refs", [])
        if not isinstance(refs, list):
            fail(f"{context}.source_refs phải là mảng")
        if node["confidence"] == "verified" and not refs:
            fail(f"{context}: verified phải có source_refs từ code")
        for j, ref in enumerate(refs):
            label = f"{context}.source_refs[{j}]"
            if not isinstance(ref, dict):
                fail(f"{label} phải là object")
            path = text_field(ref, "path", label)
            if path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", path):
                fail(f"{label}.path cần là đường dẫn tương đối repository, không phải absolute path")
            if ".." in Path(path.replace("\\", "/")).parts:
                fail(f"{label}.path không được đi ra ngoài repository")
            if "start_line" in ref and (type(ref["start_line"]) is not int or ref["start_line"] < 1):
                fail(f"{label}.start_line phải là số nguyên > 0")
            if "end_line" in ref and (type(ref["end_line"]) is not int or ref["end_line"] < ref.get("start_line", 1)):
                fail(f"{label}.end_line không hợp lệ")
            if "symbol" in ref:
                text_field(ref, "symbol", label, empty=True)
        if node["confidence"] == "verified" and not any("start_line" in r for r in refs):
            fail(f"{context}: verified phải có ít nhất một nguồn chứa start_line")
    if data["entry_node"] not in node_ids:
        fail("entry_node không tồn tại trong nodes")
    if data.get("assumptions") is not None and (not isinstance(data["assumptions"], list) or not all(isinstance(s, str) for s in data["assumptions"])):
        fail("assumptions phải là mảng các chuỗi")
    adjacency = defaultdict(list)
    non_loop = defaultdict(list)
    out_edges = defaultdict(list)
    indegrees = {node_id: 0 for node_id in node_ids}
    edge_ids = set()
    for i, edge in enumerate(data["edges"]):
        context = f"edges[{i}]"
        if not isinstance(edge, dict):
            fail(f"{context} phải là object")
        for field in REQUIRED_EDGE:
            text_field(edge, field, context, empty=(field == "label"))
        if edge["from"] not in node_ids or edge["to"] not in node_ids:
            fail(f"{context}: from/to trỏ tới node không tồn tại")
        if edge["kind"] not in ALLOWED_KINDS:
            fail(f"{context}: loại kind không hỗ trợ")
        if "id" in edge:
            text_field(edge, "id", context)
            if edge["id"] in edge_ids:
                fail(f"{context}: trùng edge id")
            edge_ids.add(edge["id"])
        if "technical" in edge:
            text_field(edge, "technical", context, empty=True)
        adjacency[edge["from"]].append(edge["to"])
        out_edges[edge["from"]].append(edge)
        if edge["kind"] != "loop":
            non_loop[edge["from"]].append(edge["to"])
            indegrees[edge["to"]] += 1
    lookup = {n["id"]: n for n in data["nodes"]}
    for node_id, edges in out_edges.items():
        if len(edges) >= 2 or lookup[node_id]["type"] == "decision":
            for edge in edges:
                if not edge["label"].strip():
                    fail(f"Node rẽ nhánh {node_id}: mọi cạnh cần nhãn điều kiện")
    # Reachability must include back edges. Reject islands which hide missing steps.
    seen = {data["entry_node"]}
    queue = deque(seen)
    while queue:
        for child in adjacency[queue.popleft()]:
            if child not in seen:
                seen.add(child)
                queue.append(child)
    if len(seen) != len(node_ids):
        fail("Có node không đi tới được từ entry_node: " + ", ".join(sorted(node_ids - seen)))
    # Excluding explicitly marked loop edges, graph should be a DAG for auto-layout.
    remaining = indegrees.copy()
    topo_queue = deque(n["id"] for n in data["nodes"] if not remaining[n["id"]])
    topo_order = []
    while topo_queue:
        current = topo_queue.popleft()
        topo_order.append(current)
        for child in non_loop[current]:
            remaining[child] -= 1
            if remaining[child] == 0:
                topo_queue.append(child)
    if len(topo_order) != len(node_ids):
        fail("Phát hiện chu trình chưa gắn kind=loop. Hãy đánh dấu back-edge loop")
    return {"lookup": lookup, "topo_order": topo_order, "non_loop": non_loop}


def assign_positions(graph, info):
    """Dependency-free layered layout; preserve any explicit node coordinates."""
    level = {n["id"]: 0 for n in graph["nodes"]}
    for current in info["topo_order"]:
        for target in info["non_loop"][current]:
            level[target] = max(level[target], level[current] + 1)
    columns = defaultdict(list)
    for node in graph["nodes"]:
        if "x" not in node:
            columns[level[node["id"]]].append(node)
    if not columns:
        return
    # y lanes aligned per column; explicit coords kept unchanged when mixed.
    max_count = max(len(items) for items in columns.values())
    for depth, items in columns.items():
        padding_top = 85 + (max_count - len(items)) * 141
        for row, item in enumerate(items):
            item["x"] = 70 + depth * 395
            item["y"] = padding_top + row * 282


def render_json(graph):
    serialized = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
    # Leave JSON valid; prevent data from breaking out of the application/json script element.
    for old, new in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"), ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        serialized = serialized.replace(old, new)
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count("__FLOW_JSON__") != 1:
        fail("Template HTML sai: cần chính xác một placeholder __FLOW_JSON__")
    return template.replace("__FLOW_JSON__", serialized)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate graph JSON and render offline flow HTML")
    parser.add_argument("input", type=Path, help="Path to workflow graph JSON")
    parser.add_argument("--out", type=Path, help="HTML output path")
    parser.add_argument("--check-only", action="store_true", help="Only validate graph")
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        info = validate(data)
        print(f"OK: {len(data['nodes'])} nodes, {len(data['edges'])} edges, entry={data['entry_node']}")
        if args.check_only:
            return 0
        if not args.out:
            fail("Thiếu --out để ghi HTML. Hoặc truyền --check-only")
        assign_positions(data, info)
        html = render_json(data)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(html, encoding="utf-8")
        print(f"HTML created: {args.out.resolve()} ({args.out.stat().st_size:,} bytes)")
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, FlowError) as ex:
        print("ERROR:", ex, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
