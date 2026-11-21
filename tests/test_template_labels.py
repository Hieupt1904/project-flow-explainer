"""Guard the edge-label placement that keeps step notes readable.

A label painted over a node card loses its text: the card layer is above the
edge layer. The template therefore samples the curve and picks a point that
clears every node rectangle, and truncates long labels to the box width.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "assets" / "workflow_template.html"


class EdgeLabelTemplateTests(unittest.TestCase):
    def setUp(self):
        self.text = TEMPLATE.read_text(encoding="utf-8")

    def test_node_layer_paints_above_edge_layer(self):
        world = self.text.index('id="world"')
        edge = self.text.index('id="edge-layer"', world)
        nodes = self.text.index('id="nodes-layer"', world)
        self.assertLess(edge, nodes,
                        "edge layer must come first so cards paint over labels")

    def test_label_placement_avoids_node_rectangles(self):
        self.assertIn("function pickLabelPoint", self.text)
        body = self.text[self.text.index("function pickLabelPoint"):]
        body = body[: body.index("function drawEdges")]
        self.assertIn("nodeRects()", body)
        self.assertIn("getTotalLength()", body)

    def test_long_labels_are_truncated_to_the_box(self):
        self.assertIn("function labelBox", self.text)
        label_box = self.text[self.text.index("function labelBox"):]
        label_box = label_box[: label_box.index("function placeLabel")]
        self.assertIn("ellipsis(text,", label_box)

    def test_labels_have_an_opaque_backing(self):
        self.assertRegex(self.text, r"\.edge-label-rect\s*\{[^}]*fill:\s*#fff")

    def test_simple_view_caps_the_number_of_stages(self):
        self.assertIn("MAX_SIMPLE_STAGES=7", self.text)
        body = self.text[self.text.index("function buildSimpleView"):]
        body = body[: body.index("function setView")]
        self.assertIn("budget=Math.max(1,MAX_SIMPLE_STAGES", body)
        self.assertIn("điểm rẽ nhánh", body,
                      "decisions that do not fit must collapse into one card")

    def test_simple_view_renders_step_notes(self):
        self.assertIn("stageCard(", self.text)
        self.assertRegex(self.text, r"\.stage-note\s*\{")


if __name__ == "__main__":
    unittest.main()