"""A generated graph must round-trip through the standalone renderer."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import render_flow


class ViewerRenderCompatibilityTests(unittest.TestCase):
    def test_largest_accepted_graph_remains_valid_after_layout(self):
        nodes = [{'id': f'n-{i}', 'title': f'Bước {i}', 'type': 'action',
                  'summary': 'Một bước', 'confidence': 'inferred'} for i in range(250)]
        edges = [{'from': nodes[i]['id'], 'to': nodes[i + 1]['id'],
                  'label': 'Tiếp', 'kind': 'normal'} for i in range(len(nodes) - 1)]
        graph = {'flow_id': 'large', 'title': 'Sơ đồ lớn', 'description': 'Ví dụ',
                 'entry_node': nodes[0]['id'], 'nodes': nodes, 'edges': edges}
        render_flow.assign_positions(graph, render_flow.validate(graph))
        original = copy.deepcopy(graph)
        render_flow.assign_positions(graph, render_flow.validate(graph))
        self.assertEqual(graph, original)
        self.assertGreater(nodes[-1]['x'] - nodes[-2]['x'], 295)
