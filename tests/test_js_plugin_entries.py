"""JS/TS plugin entry recognition and request-scoped start selection.

Run: python -m unittest tests.test_js_plugin_entries -v
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from pfe import facts  # noqa: E402
import build_flow  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "js-plugin-app"
SLASH_REQUEST = (
    "Giải thích luồng đăng ký lệnh slash trong plugin: từ lúc apply() "
    "được host gọi đến khi lệnh được đăng ký."
)


def node_paths(graph):
    return {ref["path"] for node in graph["nodes"] for ref in node.get("source_refs", [])}


def step1(graph):
    return next(node for node in graph["nodes"] if node["id"] == "step-1")


class IterSourceLinesTests(unittest.TestCase):
    def test_skips_python_docstring_mention_of_main(self):
        lines = [
            "def find_entry_points(lines):",
            '    """Return entry points.',
            "",
            "    A bare `def main()` is *likely* an entry point.",
            '    """',
            "    return []",
        ]
        kept = [line.strip() for _, line in facts.iter_source_lines(lines, ".py")]
        self.assertIn("def find_entry_points(lines):", kept)
        self.assertTrue(any("return []" in line for line in kept))
        self.assertFalse(any("def main()" in line for line in kept))

    def test_skips_js_block_and_line_comments(self):
        lines = [
            "// export function apply(ctx) {}",
            "/* function main() {",
            "   export function apply(ctx) {}",
            " */",
            "export const name = 'x'",
        ]
        kept = [line.strip() for _, line in facts.iter_source_lines(lines, ".js")]
        self.assertEqual(kept, ["export const name = 'x'"])


class FindEntriesTests(unittest.TestCase):
    def test_docstring_def_main_is_not_an_entry(self):
        lines = Path(ROOT / "pfe" / "facts.py").read_text(encoding="utf-8").splitlines()
        entries = facts.find_entries(lines, ".py")
        self.assertFalse(any(item["label"] == "main" for item in entries), entries)

    def test_real_def_main_after_docstring_still_counts(self):
        entries = facts.find_entries([
            '"""A bare `def main()` is only documentation."""',
            "def main():",
            "    return 1",
        ], ".py")
        self.assertEqual(entries, [{"line": 2, "kind": "entry", "label": "main"}])

    def test_export_function_apply_is_an_entry(self):
        entries = facts.find_entries([
            "export function apply(ctx, config = {}) {",
            "  return ctx",
            "}",
        ], ".js")
        self.assertEqual(entries[0]["label"], "apply")
        self.assertEqual(entries[0]["line"], 1)

    def test_export_default_and_cjs_apply_forms(self):
        cases = [
            (["export default function plugin(ctx) {", "}"], "plugin"),
            (["export default apply;"], "apply"),
            (["exports.apply = function (ctx) {}"], "apply"),
            (["function apply(ctx) {}", "module.exports = apply"], "apply"),
            (["module.exports = function apply(ctx) {}"], "apply"),
            (["export const apply = (ctx) => ctx"], "apply"),
        ]
        for lines, label in cases:
            found = facts.find_entries(lines, ".js")
            self.assertTrue(any(item["label"] == label for item in found), (lines, found))

    def test_plain_module_exports_object_is_not_an_entry(self):
        entries = facts.find_entries([
            "module.exports = {",
            "  run() { return 1 }",
            "}",
        ], ".js")
        self.assertEqual(entries, [])

    def test_cordis_default_object_with_apply_is_an_entry(self):
        entries = facts.find_entries([
            "export default {",
            "  name: 'demo',",
            "  apply(ctx) {",
            "    return ctx",
            "  }",
            "}",
        ], ".js")
        self.assertEqual(entries, [{"line": 3, "kind": "entry", "label": "apply"}])

    def test_command_and_tool_registrations(self):
        entries = facts.find_entries([
            "export function apply(ctx) {",
            "  ctx.tools.register({ name: 'x' })",
            "  scoped.commands.register(flowCommand({}))",
            "  defineTool({ name: 'y' })",
            "}",
        ], ".js")
        kinds = {item["kind"] for item in entries}
        self.assertIn("entry", kinds)
        self.assertIn("command", kinds)
        self.assertIn("tool", kinds)

    def test_jsdoc_mention_of_register_is_not_an_entry(self):
        entries = facts.find_entries([
            "/**",
            " * A definition accepted by `ctx.commands.register()`.",
            " */",
            "export function flowCommand() { return {} }",
        ], ".js")
        self.assertEqual(entries, [])

    def test_entry_points_mark_apply_as_observed(self):
        points = facts.find_entry_points([
            "export function apply(ctx) {",
            "  ctx.commands.register(cmd)",
            "}",
        ], ".js")
        kinds = {(item["kind"], item["label"], item["evidence_kind"]) for item in points}
        self.assertIn(("export", "apply", "observed"), kinds)
        self.assertIn(("command", "", "observed"), kinds)



class BodyRangeTests(unittest.TestCase):
    def test_outer_function_body_includes_nested_functions(self):
        lines = [
            "export function apply(ctx) {",
            "  let refresh = () => {}",
            "  const coreOf = () => settings",
            "  ctx.commands.register(cmd)",
            "}",
            "export function other() {",
            "  return 1",
            "}",
        ]
        item = facts._facts_from("plugin/index.js", "plugin/index.js", lines, 0, False)
        start, end = item.body_range(1)
        self.assertEqual(start, 1)
        self.assertGreaterEqual(end, 4)
        self.assertLess(end, 6)


class JsPluginFlowTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "js-plugin-app"
        shutil.copytree(FIXTURE, self.repo)

    def tearDown(self):
        self._tmp.cleanup()

    def graph(self, request=SLASH_REQUEST):
        result = build_flow.run(self.repo, request)
        return json.loads(Path(result["paths"]["flow_json"]).read_text(encoding="utf-8"))

    def test_slash_registration_starts_at_apply_not_docstring_or_cli(self):
        graph = self.graph()
        entry = step1(graph)
        self.assertEqual(entry["source_refs"][0]["path"], "plugin/index.js")
        self.assertIn("apply", entry["title"])
        paths = node_paths(graph)
        self.assertIn("plugin/lib/command.js", paths)
        self.assertIn("plugin/lib/runner.js", paths)
        self.assertNotIn("core/facts.py", paths)
        self.assertNotIn("core/cli.py", paths)
        self.assertNotIn("no-entry", {node["id"] for node in graph["nodes"]})

    def test_typescript_apply_and_define_tool_are_recognized(self):
        ts_repo = Path(self._tmp.name) / "ts-plugin"
        src = ts_repo / "src"
        src.mkdir(parents=True)
        (src / "index.ts").write_text(
            "import { makeTool } from './tool.ts'\n\n"
            "export async function apply(ctx: unknown, config: unknown = {}) {\n"
            "  ctx.tools.register(makeTool())\n"
            "}\n",
            encoding="utf-8")
        (src / "tool.ts").write_text(
            "export function makeTool() {\n"
            "  return defineTool({ name: 'ping' })\n"
            "}\n",
            encoding="utf-8")
        (ts_repo / "notes.py").write_text(
            '"""Docs only. A bare `def main()` is not an entry here."""\n\n'
            "def collect():\n    return []\n",
            encoding="utf-8")
        result = build_flow.run(ts_repo, "luồng đăng ký tool trong plugin TypeScript")
        graph = json.loads(Path(result["paths"]["flow_json"]).read_text(encoding="utf-8"))
        entry = step1(graph)
        self.assertEqual(entry["source_refs"][0]["path"], "src/index.ts")
        self.assertIn("apply", entry["title"])
        self.assertIn("src/tool.ts", node_paths(graph))
        self.assertNotIn("notes.py", node_paths(graph))


if __name__ == "__main__":
    unittest.main()
