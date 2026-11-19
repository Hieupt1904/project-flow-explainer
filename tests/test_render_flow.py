"""Smoke tests for the dependency-free HTML renderer.
Run: python -m unittest discover -s tests -v
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import render_flow


class RenderFlowTests(unittest.TestCase):
    def setUp(self):
        self.flow = json.loads((ROOT / "assets" / "example_workflow.json").read_text(encoding="utf-8"))

    def test_sample_graph_valid(self):
        info = render_flow.validate(self.flow)
        self.assertIn("welcome", info["topo_order"])
        html = render_flow.render_json(self.flow)
        self.assertIn("<!doctype html>", html.lower())
        self.assertIn("Chào mừng khách hàng", html)
        self.assertNotIn("__FLOW_JSON__", html)

    def test_invalid_dangling_edge(self):
        f = copy.deepcopy(self.flow)
        f["edges"][0]["to"] = "not-here"
        with self.assertRaises(render_flow.FlowError):
            render_flow.validate(f)

    def test_invalid_verified_without_source(self):
        f = copy.deepcopy(self.flow)
        f["nodes"][0]["confidence"] = "verified"
        with self.assertRaises(render_flow.FlowError):
            render_flow.validate(f)

    def test_invalid_unmarked_cycle(self):
        f = copy.deepcopy(self.flow)
        f["edges"][-1]["kind"] = "normal"
        with self.assertRaises(render_flow.FlowError):
            render_flow.validate(f)

    def test_html_escapes_script_boundary(self):
        f = copy.deepcopy(self.flow)
        f["nodes"][0]["details"] = "</script><img src=x onerror=alert('xss')>"
        html = render_flow.render_json(f)
        self.assertNotIn("</script><img", html)
        self.assertIn("\\u003c/script\\u003e", html)

    def test_edge_labels_avoid_node_cards(self):
        """Guard the UI-003 fix: labels are placed through pickLabelPoint."""
        template = (ROOT / "assets" / "workflow_template.html").read_text(encoding="utf-8")
        self.assertIn("function pickLabelPoint", template)
        self.assertIn("pickLabelPoint(pathEl", template)
        self.assertNotIn("placeLabel(group,labelX,labelY", template)

    def test_auto_layout_for_missing_coordinates(self):
        f = copy.deepcopy(self.flow)
        for node in f["nodes"]:
            node.pop("x", None)
            node.pop("y", None)
        info = render_flow.validate(f)
        render_flow.assign_positions(f, info)
        self.assertTrue(all(isinstance(n.get("x"), int) and isinstance(n.get("y"), int) for n in f["nodes"]))
        self.assertLess(f["nodes"][0]["x"], f["nodes"][4]["x"])


if __name__ == "__main__":
    unittest.main()
