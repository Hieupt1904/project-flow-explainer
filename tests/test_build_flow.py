"""Tests for the repository analyser (scripts/build_flow.py).

Run: python -m unittest discover -s tests -v
The tests copy the fixture repository into a temp dir; they never write into
tests/fixtures and never touch the network.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_flow  # noqa: E402
import render_flow  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "shop-app"
REQUEST = ("Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file: "
           "dữ liệu đi qua những bước nào, thành phần nào xử lý và lỗi được xử lý ở đâu?")
SECRETS = ("fixture-secret-value-abc123", "fixture-db-password-xyz789")


def copy_fixture(target):
    shutil.copytree(FIXTURE, target, ignore=shutil.ignore_patterns("artifacts"))
    (target / ".env").write_text(
        f"API_KEY={SECRETS[0]}\nDB_PASSWORD={SECRETS[1]}\n", encoding="utf-8")
    (target / "config.py").write_text(
        f'API_KEY = "{SECRETS[0]}"\nDB_PASSWORD = "{SECRETS[1]}"\n', encoding="utf-8")
    return target


def hashes(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and "artifacts" not in path.parts:
            result[str(path.relative_to(root))] = path.stat().st_mtime_ns, path.stat().st_size
    return result


class BuildFlowTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = copy_fixture(self.tmp / "shop-app")

    def tearDown(self):
        self._tmp.cleanup()

    def build(self, request=REQUEST, **kwargs):
        return build_flow.run(self.repo, request, **kwargs)

    def read_outputs(self, result):
        paths = {key: Path(value) for key, value in result["paths"].items()}
        return paths, {key: path.read_text(encoding="utf-8") for key, path in paths.items()}

    # --- happy path -----------------------------------------------------

    def test_three_files_are_consistent(self):
        result = self.build()
        paths, texts = self.read_outputs(result)
        for key in ("flow_json", "flow_html", "overview"):
            self.assertTrue(paths[key].is_file(), f"{key} missing")

        graph = json.loads(texts["flow_json"])
        render_flow.validate(graph)  # raises FlowError on a broken graph
        self.assertEqual(graph["flow_id"], result["flow_id"])
        self.assertIn(graph["flow_id"], texts["flow_html"])
        self.assertNotIn("__FLOW_JSON__", texts["flow_html"])
        for node in graph["nodes"]:
            self.assertIn(node["title"], texts["overview"])
        self.assertIn(result["slug"], str(paths["flow_html"]))

    def test_entry_is_the_export_route(self):
        result = self.build()
        graph = json.loads(Path(result["paths"]["flow_json"]).read_text(encoding="utf-8"))
        entry = next(node for node in graph["nodes"] if node["id"] == "step-1")
        self.assertEqual(entry["source_refs"][0]["path"], "server.js")
        self.assertIn("/api/reports/export", entry["title"])

    def test_counts_are_reported_and_match_graph(self):
        result = self.build()
        graph = json.loads(Path(result["paths"]["flow_json"]).read_text(encoding="utf-8"))
        counted = {}
        for node in graph["nodes"]:
            counted[node["confidence"]] = counted.get(node["confidence"], 0) + 1
        for label, value in result["counts"].items():
            self.assertEqual(value, counted.get(label, 0), label)

    def test_deterministic_graph_across_runs(self):
        other = copy_fixture(self.tmp / "shop-app-2")
        first = self.build()
        second = build_flow.run(other, REQUEST)
        a = json.loads(Path(first["paths"]["flow_json"]).read_text(encoding="utf-8"))
        b = json.loads(Path(second["paths"]["flow_json"]).read_text(encoding="utf-8"))
        strip = lambda graph: [(n["id"], n["title"], n["confidence"], n.get("source_refs")) for n in graph["nodes"]]
        self.assertEqual(strip(a), strip(b))
        self.assertEqual(a["edges"], b["edges"])

    def test_html_is_self_contained(self):
        result = self.build()
        html = Path(result["paths"]["flow_html"]).read_text(encoding="utf-8")
        self.assertNotIn("<script src=", html)
        self.assertNotIn("<link rel=\"stylesheet\"", html)
        self.assertNotIn("cdn.", html)
        self.assertNotIn("http://", html.replace("http://www.w3.org", ""))

    # --- policy: read-only source --------------------------------------

    def test_source_files_are_untouched(self):
        before = hashes(self.repo)
        self.build()
        self.assertEqual(before, hashes(self.repo))

    def test_secrets_never_reach_output(self):
        result = self.build()
        _, texts = self.read_outputs(result)
        for path, text in texts.items():
            for secret in SECRETS:
                self.assertNotIn(secret, text, f"secret leaked into {path}")
        run = json.loads(texts["run"])
        self.assertGreaterEqual(run["excluded"]["sensitive_name"], 1)  # .env
        self.assertGreaterEqual(run["excluded"]["secret_lines"], 2)    # .env + config.py

    def test_artifacts_are_not_reanalysed(self):
        first = self.build()
        second = self.build(request=REQUEST + " (lần hai)")
        graph = json.loads(Path(second["paths"]["flow_json"]).read_text(encoding="utf-8"))
        for node in graph["nodes"]:
            for ref in node.get("source_refs", []):
                self.assertNotIn("artifacts/", ref["path"])
        self.assertNotEqual(first["slug"], second["slug"])

    # --- validation and containment ------------------------------------

    def test_missing_request_rejected(self):
        with self.assertRaises(build_flow.BuildError) as ctx:
            build_flow.run(self.repo, "   ")
        self.assertEqual(ctx.exception.code, "missing_flow_request")

    def test_missing_repository_rejected(self):
        with self.assertRaises(build_flow.BuildError) as ctx:
            build_flow.run(self.tmp / "nope", REQUEST)
        self.assertEqual(ctx.exception.code, "repository_not_found")

    def test_out_dir_outside_root_rejected(self):
        with self.assertRaises(build_flow.BuildError) as ctx:
            build_flow.run(self.repo, REQUEST, out_dir=self.tmp / "elsewhere")
        self.assertEqual(ctx.exception.code, "path_outside_root")

    def test_existing_slug_is_not_overwritten(self):
        self.build(out_dir=self.repo / "artifacts" / "flows", slug="fixed")
        with self.assertRaises(build_flow.BuildError) as ctx:
            self.build(out_dir=self.repo / "artifacts" / "flows", slug="fixed")
        self.assertEqual(ctx.exception.code, "artifact_exists")

    def test_symlink_escape_is_skipped(self):
        link = self.repo / "escape.js"
        try:
            os.symlink("/etc/hostname", link)
        except OSError:
            self.skipTest("symlink không dùng được trên hệ thống này")
        result = self.build()
        self.assertGreaterEqual(result["excluded"]["symlink_escape"], 1)

    def test_no_evidence_reports_limits_instead_of_inventing_a_flow(self):
        empty = self.tmp / "empty-repo"
        empty.mkdir()
        (empty / "notes.txt").write_text("không có code ở đây\n", encoding="utf-8")
        (empty / "app.js").write_text("console.log('hello world')\n", encoding="utf-8")
        result = build_flow.run(empty, "luồng thanh toán thẻ tín dụng quốc tế")
        graph = json.loads(Path(result["paths"]["flow_json"]).read_text(encoding="utf-8"))
        ids = {node["id"] for node in graph["nodes"]}
        self.assertIn("no-evidence", ids)
        self.assertTrue(result["limits"])
        self.assertNotIn("step-2", ids)

    def test_cli_json_mode_is_machine_readable(self):
        import io
        from contextlib import redirect_stdout, redirect_stderr

        buffer, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(buffer), redirect_stderr(errors):
            code = build_flow.main(["--repo", str(self.repo), "--request", REQUEST, "--json"])
        self.assertEqual(code, 0, errors.getvalue())
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertIn("flow_html", payload["paths"])

    def test_cli_error_mode_is_machine_readable(self):
        import io
        from contextlib import redirect_stdout, redirect_stderr

        buffer, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(buffer), redirect_stderr(errors):
            code = build_flow.main(["--repo", str(self.repo), "--request", "", "--json"])
        self.assertEqual(code, 2)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["code"], "missing_flow_request")


if __name__ == "__main__":
    unittest.main()
