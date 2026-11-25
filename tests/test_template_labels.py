"""The offline viewer ships all controls and resources in one document."""

import base64
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import render_flow


class ViewerDocument(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.scripts = {}
        self.current_script = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if tag == "script":
            self.current_script = attrs.get("id", "viewer")
            self.scripts[self.current_script] = ""

    def handle_data(self, text):
        if self.current_script is not None:
            self.scripts[self.current_script] += text

    def handle_endtag(self, tag):
        if tag == "script":
            self.current_script = None


class ViewerDocumentTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / "assets" / "example_workflow.json"
        graph = json.loads(path.read_text(encoding="utf-8"))
        graph["description"] = "Giữ nguyên __VIEWER_CSS__ và </script>"
        render_flow.assign_positions(graph, render_flow.validate(graph))
        self.graph = graph
        self.document = ViewerDocument(render_flow.render_json(graph, viewer="classic"))

    def test_graph_data_survives_serialization(self):
        self.assertEqual(json.loads(self.document.scripts["workflow-json"]), self.graph)

    def test_views_and_controls_are_present_and_unique(self):
        ids = [attrs["id"] for _, attrs in self.document.tags if "id" in attrs]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue({"view-technical", "view-simple", "search", "guide-start", "minimap",
                         "tab-overview", "tab-details", "tab-evidence", "download-flow"} <= set(ids))
        self.assertLess(ids.index("edge-layer"), ids.index("nodes-layer"))

    def test_viewer_hash_covers_exact_embedded_script_and_network_is_disabled(self):
        script = self.document.scripts["viewer"].encode("utf-8")
        digest = base64.b64encode(hashlib.sha256(script).digest()).decode("ascii")
        policy = next(attrs["content"] for tag, attrs in self.document.tags
                      if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy")
        self.assertIn(f"script-src 'sha256-{digest}'", policy)
        self.assertIn("default-src 'none'", policy)
        self.assertFalse(any("src" in attrs or tag == "link" for tag, attrs in self.document.tags))
