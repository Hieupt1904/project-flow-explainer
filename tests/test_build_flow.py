"""Tests for the repository analyser (scripts/build_flow.py).

Run: python -m unittest discover -s tests -v
Every test works on a temp copy of the fixture repository; nothing is written
into tests/fixtures and nothing touches the network.
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
FLOW_NODE_PATHS = {"server.js", "services/report_service.js", "db/report_repo.js",
                   "db/connection.js"}


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
            stat = path.stat()
            result[str(path.relative_to(root))] = (stat.st_mtime_ns, stat.st_size)
    return result


def node_paths(graph):
    return {ref["path"] for node in graph["nodes"] for ref in node.get("source_refs", [])}


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

    def graph_of(self, result):
        return json.loads(Path(result["paths"]["flow_json"]).read_text(encoding="utf-8"))

    # --- happy path -----------------------------------------------------

    def test_three_files_are_consistent(self):
        result = self.build()
        paths, texts = self.read_outputs(result)
        for key in ("flow_json", "flow_html", "overview"):
            self.assertTrue(paths[key].is_file(), f"{key} missing")
        graph = json.loads(texts["flow_json"])
        render_flow.validate(graph)
        self.assertEqual(graph["flow_id"], result["flow_id"])
        self.assertIn(graph["flow_id"], texts["flow_html"])
        self.assertNotIn("__FLOW_JSON__", texts["flow_html"])
        for node in graph["nodes"]:
            self.assertIn(node["title"], texts["overview"])

    def test_all_artifacts_live_under_artifacts_flows(self):
        result = self.build()
        expected_prefix = (self.repo / "artifacts" / "flows").resolve()
        for value in result["paths"].values():
            resolved = Path(value).resolve()
            self.assertTrue(str(resolved).startswith(str(expected_prefix)),
                            f"{resolved} outside artifact root")
        self.assertEqual(Path(result["artifacts_dir"]).parent.resolve(), expected_prefix)

    def test_entry_is_the_export_route(self):
        graph = self.graph_of(self.build())
        entry = next(node for node in graph["nodes"] if node["id"] == "step-1")
        self.assertEqual(entry["source_refs"][0]["path"], "server.js")
        self.assertIn("/api/reports/export", entry["title"])

    def test_counts_are_reported_and_match_graph(self):
        result = self.build()
        graph = self.graph_of(result)
        counted = {}
        for node in graph["nodes"]:
            counted[node["confidence"]] = counted.get(node["confidence"], 0) + 1
        for label, value in result["counts"].items():
            self.assertEqual(value, counted.get(label, 0), label)

    def test_deterministic_graph_across_runs(self):
        other = copy_fixture(self.tmp / "shop-app-2")
        first = self.build()
        second = build_flow.run(other, REQUEST)
        a, b = self.graph_of(first), json.loads(
            Path(second["paths"]["flow_json"]).read_text(encoding="utf-8"))
        shape = lambda graph: [(n["id"], n["title"], n["confidence"], n.get("source_refs"))
                               for n in graph["nodes"]]
        self.assertEqual(shape(a), shape(b))
        self.assertEqual(a["edges"], b["edges"])

    def test_html_is_self_contained(self):
        html = self.read_outputs(self.build())[1]["flow_html"]
        self.assertNotIn("<script src=", html)
        self.assertNotIn('<link rel="stylesheet"', html)
        self.assertNotIn("cdn.", html)
        if 'data-project-flow-explainer-policy="export"' in html:
            self.assertIn("connect-src 'none'", html)
        else:
            self.assertNotIn("http://", html.replace("http://www.w3.org", ""))

    # --- evidence model (TASK 6) ---------------------------------------

    def test_keyword_only_file_is_not_chained_into_the_flow(self):
        result = self.build()
        graph = self.graph_of(result)
        related = {item["path"] for item in graph["meta"]["related"]}
        self.assertIn("routes/preview.js", related, "decoy phải nằm ở related")
        self.assertNotIn("routes/preview.js", node_paths(graph), "decoy không được thành node")
        self.assertNotIn("jobs/export_worker.py", node_paths(graph))
        self.assertIn("jobs/export_worker.py", related)

    def test_every_step_is_reached_by_a_structural_edge(self):
        graph = self.graph_of(self.build())
        inbound = {edge["to"]: edge for edge in graph["edges"]}
        for node in graph["nodes"]:
            if node["id"] in {"start", "end"}:
                continue
            self.assertIn(node["id"], inbound, f"{node['id']} không có cạnh vào")
            self.assertIn(inbound[node["id"]]["evidence"],
                          {"entry", "import", "call", "structure"})
        import_edges = [edge for edge in graph["edges"] if edge["evidence"] == "import"]
        self.assertGreaterEqual(len(import_edges), 2)

    def test_verified_nodes_have_location_and_membership(self):
        graph = self.graph_of(self.build())
        for node in graph["nodes"]:
            if node["confidence"] != "verified":
                continue
            refs = node.get("source_refs") or []
            self.assertTrue(refs and refs[0].get("start_line"), node["id"])
            self.assertIn("Bằng chứng thành viên", node.get("details", "") + node.get("summary", "")) \
                if node["id"] != "end" else None

    def test_no_entry_does_not_invent_a_chain(self):
        repo = self.tmp / "no-entry"
        repo.mkdir()
        (repo / "handler.js").write_text(
            "router.get('/ping', (req, res) => res.send('pong'))\n", encoding="utf-8")
        result = build_flow.run(repo, "luồng thanh toán thẻ tín dụng quốc tế")
        graph = json.loads(Path(result["paths"]["flow_json"]).read_text(encoding="utf-8"))
        ids = {node["id"] for node in graph["nodes"]}
        self.assertIn("no-entry", ids)
        self.assertNotIn("step-2", ids)
        self.assertTrue(any("điểm vào" in item for item in result["limits"]))

    def test_sys_path_flat_import_is_resolved_by_unique_basename(self):
        repo = self.tmp / "flat-import-app"
        (repo / "app").mkdir(parents=True)
        (repo / "src").mkdir()
        (repo / "app" / "main.py").write_text(
            'import sys\nsys.path.insert(0, "src")\nimport helper\n\n'
            'def main():\n    return helper.run()\n', encoding="utf-8")
        (repo / "src" / "helper.py").write_text(
            "def run():\n    return 1\n", encoding="utf-8")
        result = build_flow.run(repo, "luồng chạy chính của ứng dụng")
        graph = json.loads(Path(result["paths"]["flow_json"]).read_text(encoding="utf-8"))
        self.assertIn("src/helper.py", node_paths(graph))
        import_edges = [edge for edge in graph["edges"] if edge["evidence"] == "import"]
        self.assertTrue(any("qua sys.path" in edge.get("technical", "") for edge in import_edges))

    def test_ambiguous_flat_import_is_not_guessed(self):
        repo = self.tmp / "ambiguous-app"
        (repo / "a").mkdir(parents=True)
        (repo / "b").mkdir()
        (repo / "app.py").write_text(
            "import shared\n\ndef main():\n    return shared.run()\n", encoding="utf-8")
        (repo / "a" / "shared.py").write_text("def run():\n    return 1\n", encoding="utf-8")
        (repo / "b" / "shared.py").write_text("def run():\n    return 2\n", encoding="utf-8")
        result = build_flow.run(repo, "luồng chạy chính của ứng dụng")
        graph = json.loads(Path(result["paths"]["flow_json"]).read_text(encoding="utf-8"))
        self.assertNotIn("a/shared.py", node_paths(graph))
        self.assertNotIn("b/shared.py", node_paths(graph))

    # --- policy: read-only source, no leaks -----------------------------

    def test_source_files_are_untouched(self):
        before = hashes(self.repo)
        self.build()
        self.assertEqual(before, hashes(self.repo))

    def test_secrets_never_reach_output(self):
        paths, texts = self.read_outputs(self.build())
        for path, text in texts.items():
            for secret in SECRETS:
                self.assertNotIn(secret, text, f"secret leaked into {path}")
        run = json.loads(texts["run"])
        self.assertGreaterEqual(run["excluded"]["sensitive_name"], 1)
        self.assertGreaterEqual(run["excluded"]["secret_lines"], 2)

    def test_artifacts_contain_no_absolute_workstation_paths(self):
        paths, texts = self.read_outputs(self.build())
        for path, text in texts.items():
            self.assertNotIn(str(self.tmp), text, f"absolute path in {path}")
            self.assertNotIn("/home/", text, f"/home/ in {path}")
            self.assertNotIn("\\Users\\", text, f"Windows user path in {path}")
            self.assertNotIn("/artifacts/", text.replace("artifacts/flows", ""),
                             f"nested artifacts in {path}")

    def test_artifacts_are_not_reanalysed(self):
        first = self.build()
        second = self.build(request=REQUEST + " (lần hai)")
        for rel in node_paths(self.graph_of(second)):
            self.assertNotIn("artifacts/", rel)
        self.assertNotEqual(first["slug"], second["slug"])

    # --- artifact path policy (TASK 2) ----------------------------------

    def test_output_directory_outside_artifacts_flows_is_rejected(self):
        for bad in (".", "src", "docs", "tmp", "../outside", str(self.tmp / "elsewhere")):
            with self.assertRaises(build_flow.BuildError, msg=bad) as ctx:
                build_flow.run(self.repo, REQUEST, out_dir=bad)
            self.assertEqual(ctx.exception.code, "invalid_artifact_root", bad)
        self.assertFalse((self.tmp / "outside").exists())
        self.assertFalse((self.repo / "src").exists())
        self.assertFalse((self.repo / "docs").exists())

    def test_repository_root_as_output_directory_is_rejected(self):
        with self.assertRaises(build_flow.BuildError) as ctx:
            build_flow.run(self.repo, REQUEST, out_dir=str(self.repo))
        self.assertEqual(ctx.exception.code, "invalid_artifact_root")
        self.assertEqual(list(self.repo.glob("*.html")), [])

    def test_symlinked_artifact_directory_is_rejected(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        try:
            os.symlink(outside, self.repo / "artifacts")
        except OSError:
            self.skipTest("symlink không dùng được trên hệ thống này")
        with self.assertRaises(build_flow.BuildError) as ctx:
            build_flow.run(self.repo, REQUEST)
        self.assertEqual(ctx.exception.code, "artifact_symlink_escape")
        self.assertEqual(list(outside.iterdir()), [])

    def test_invalid_slug_is_rejected(self):
        for bad in ("..", "a/b", "../x", "  "):
            with self.assertRaises(build_flow.BuildError, msg=bad) as ctx:
                build_flow.run(self.repo, REQUEST, slug=bad)
            self.assertEqual(ctx.exception.code, "invalid_slug", bad)

    def test_existing_slug_is_not_overwritten(self):
        self.build(slug="fixed")
        with self.assertRaises(build_flow.BuildError) as ctx:
            self.build(slug="fixed")
        self.assertEqual(ctx.exception.code, "artifact_exists")

    def test_no_write_before_containment_check(self):
        with self.assertRaises(build_flow.BuildError):
            build_flow.run(self.repo, REQUEST, out_dir="../nope")
        self.assertFalse((self.repo / "artifacts").exists(), "artifacts tạo trước khi kiểm tra")

    # --- repository policy ---------------------------------------------

    def test_missing_request_rejected(self):
        with self.assertRaises(build_flow.BuildError) as ctx:
            build_flow.run(self.repo, "   ")
        self.assertEqual(ctx.exception.code, "missing_flow_request")

    def test_missing_repository_rejected(self):
        with self.assertRaises(build_flow.BuildError) as ctx:
            build_flow.run(self.tmp / "nope", REQUEST)
        self.assertEqual(ctx.exception.code, "repository_not_found")

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

    # --- CLI contract ---------------------------------------------------

    def test_cli_json_mode_is_machine_readable(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        buffer, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(buffer), redirect_stderr(errors):
            code = build_flow.main(["--repo", str(self.repo), "--request", REQUEST, "--json"])
        self.assertEqual(code, 0, errors.getvalue())
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertIn("flow_html", payload["paths"])

    def test_cli_error_mode_is_machine_readable(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        buffer, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(buffer), redirect_stderr(errors):
            code = build_flow.main(["--repo", str(self.repo), "--request", "", "--json"])
        self.assertEqual(code, 2)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["code"], "missing_flow_request")
        self.assertNotIn("Traceback", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
