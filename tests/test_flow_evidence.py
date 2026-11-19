"""Regression tests for the evidence model and the artifact write path.

Every test here guards a defect that was real:

  * an edge claimed `evidence: "call"` without a call-site parser (TASK A2);
  * a success edge bypassing the decision node (TASK A3);
  * a try/catch from a different route becoming a decision of the selected flow
    (TASK A4);
  * a half-written artifact left behind after a failure (TASK A9);
  * a raw TypeError escaping instead of a stable code (TASK A10);
  * run.json being presented as a public output (TASK A12).
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import build_flow  # noqa: E402
import render_flow  # noqa: E402
from pfe import emit, facts  # noqa: E402

SHOP = ROOT / "tests" / "fixtures" / "shop-app"
TWO_ROUTES = ROOT / "tests" / "fixtures" / "two-routes-app"
SCOPE = ROOT / "tests" / "fixtures" / "scope-app"
SHOP_REQUEST = ("Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file")
TWO_ROUTE_REQUEST = "Xem chi tiết hóa đơn và xử lý lỗi khi đọc hóa đơn"
SCOPE_REQUEST = "Xuất báo cáo ra file excel cho người dùng"


def copy(src, target):
    shutil.copytree(src, target, ignore=shutil.ignore_patterns("artifacts", ".pfe"))
    return target


def graph_of(result):
    return json.loads(Path(result["paths"]["flow_json"]).read_text(encoding="utf-8"))


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def build(self, src, request, name):
        repo = copy(src, self.tmp / name)
        return repo, build_flow.run(repo, request)

    def test_no_edge_claims_call_without_call_site(self):
        _repo, result = self.build(SHOP, SHOP_REQUEST, "shop")
        graph = graph_of(result)
        for edge in graph["edges"]:
            self.assertNotEqual(edge["evidence"], "call",
                                "cạnh call không được tồn tại khi chưa có call-site parser")
        self.assertEqual(graph["meta"]["evidence_model"]["call_edges"], False)
        self.assertEqual(graph["meta"]["evidence_model"]["runtime_verified"], False)

    def test_verified_never_means_runtime(self):
        _repo, result = self.build(SHOP, SHOP_REQUEST, "shop")
        graph = graph_of(result)
        meaning = graph["meta"]["evidence_model"]["confidence"]["verified"]
        self.assertIn("KHÔNG phải chạy runtime", meaning)

    def test_decision_has_no_direct_success_bypass(self):
        _repo, result = self.build(TWO_ROUTES, TWO_ROUTE_REQUEST, "two")
        graph = graph_of(result)
        decisions = [node["id"] for node in graph["nodes"] if node["type"] == "decision"]
        self.assertTrue(decisions, "fixture phải sinh ít nhất một decision")
        outgoing = {}
        for edge in graph["edges"]:
            outgoing.setdefault(edge["from"], []).append(edge)
        for decision in decisions:
            inbound = [edge for edge in graph["edges"] if edge["to"] == decision]
            self.assertTrue(inbound, decision + " phải có cạnh vào")
            for edge in inbound:
                direct = [other for other in outgoing[edge["from"]]
                          if other["to"] != decision and other["kind"] == "success"]
                self.assertEqual(direct, [],
                                 edge["from"] + " vẫn có cạnh success trực tiếp: bypass " + decision)

    def test_error_node_is_reachable_from_the_decision(self):
        _repo, result = self.build(TWO_ROUTES, TWO_ROUTE_REQUEST, "two")
        graph = graph_of(result)
        errors = [node["id"] for node in graph["nodes"] if node["type"] == "error"]
        self.assertTrue(errors)
        for error in errors:
            inbound = [edge for edge in graph["edges"]
                       if edge["to"] == error and edge["kind"] == "error"]
            self.assertTrue(inbound, error + " phải được nối bằng cạnh error")

    def test_decision_points_inside_the_selected_route(self):
        repo, result = self.build(TWO_ROUTES, TWO_ROUTE_REQUEST, "two")
        graph = graph_of(result)
        decision = next(node for node in graph["nodes"] if node["type"] == "decision")
        ref = decision["source_refs"][0]
        self.assertEqual(ref["path"], "server.js")
        lines = (repo / "server.js").read_text(encoding="utf-8").splitlines()
        route_start = next(index for index, line in enumerate(lines, start=1)
                           if "/api/invoices/:id" in line)
        route_end = next(index for index, line in enumerate(lines, start=1)
                         if "/api/invoices/void" in line) - 1
        self.assertGreaterEqual(ref["start_line"], route_start)
        self.assertLessEqual(ref["start_line"], route_end)
        self.assertIn("try", lines[ref["start_line"] - 1])

    def test_other_route_exception_does_not_create_a_decision(self):
        """The selected route has no try/catch; the other route does."""
        repo, result = self.build(SCOPE, SCOPE_REQUEST, "scope")
        graph = graph_of(result)
        entry = graph["nodes"][1]
        self.assertIn("/api/reports/export", entry["title"])
        decisions = [node for node in graph["nodes"] if node["type"] == "decision"]
        self.assertEqual(decisions, [],
                         "try/catch của route khác không được tạo decision cho luồng đã chọn")
        self.assertTrue(all(edge["kind"] != "error" for edge in graph["edges"]))

    def test_related_file_is_never_a_node(self):
        _repo, result = self.build(SHOP, SHOP_REQUEST, "shop")
        graph = graph_of(result)
        node_paths = {ref["path"] for node in graph["nodes"] for ref in node.get("source_refs") or []}
        for item in graph["meta"]["related"]:
            self.assertNotIn(item["path"], node_paths)


class ArtifactWriteTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = copy(SHOP, self.tmp / "shop")

    def tearDown(self):
        self._tmp.cleanup()

    def flows_root(self):
        return self.repo / "artifacts" / "flows"

    def test_failure_leaves_no_partial_artifact(self):
        with mock.patch.object(emit, "write_flow_artifacts",
                               side_effect=OSError("đĩa đầy")):
            with self.assertRaises(build_flow.BuildError) as ctx:
                build_flow.run(self.repo, SHOP_REQUEST, slug="fixed")
        self.assertEqual(ctx.exception.code, "artifact_write_failed")
        self.assertFalse((self.flows_root() / "fixed").exists())
        leftover = [item.name for item in self.flows_root().iterdir()
                    if item.name.startswith(".staging-")]
        self.assertEqual(leftover, [], "staging phải được dọn sau lỗi")

    def test_retry_with_same_slug_succeeds_after_failure(self):
        with mock.patch.object(emit, "write_flow_artifacts",
                               side_effect=OSError("đĩa đầy")):
            with self.assertRaises(build_flow.BuildError):
                build_flow.run(self.repo, SHOP_REQUEST, slug="fixed")
        result = build_flow.run(self.repo, SHOP_REQUEST, slug="fixed")
        self.assertEqual(result["slug"], "fixed")
        self.assertTrue((self.flows_root() / "fixed" / "flow.html").is_file())

    def test_concurrent_same_slug_has_one_winner(self):
        results, errors = [], []

        def worker():
            try:
                results.append(build_flow.run(self.repo, SHOP_REQUEST, slug="race"))
            except build_flow.BuildError as error:
                errors.append(error.code)
            except Exception as error:  # noqa: BLE001 - must not happen
                errors.append(type(error).__name__)

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(results), 1, "chỉ một lần ghi được thắng")
        self.assertEqual(sorted(errors), ["artifact_exists", "artifact_exists"])
        leftover = [item.name for item in self.flows_root().iterdir()
                    if item.name.startswith(".staging-")]
        self.assertEqual(leftover, [])

    def test_run_json_is_internal_provenance(self):
        result = build_flow.run(self.repo, SHOP_REQUEST)
        payload = json.loads(Path(result["paths"]["run"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["contract"], "internal-provenance")
        self.assertEqual(payload["public_outputs"], ["flow.json", "flow.html", "overview.md"])
        self.assertEqual(payload["internal_outputs"], ["run.json"])
        self.assertEqual(result["contract"]["run_json"], "internal-provenance")
        self.assertNotIn("run.json", result["contract"]["public"])
        overview = Path(result["paths"]["overview"]).read_text(encoding="utf-8")
        self.assertIn("internal provenance", overview)

    def test_files_scanned_is_reported_and_never_null(self):
        result = build_flow.run(self.repo, SHOP_REQUEST)
        self.assertIsInstance(result["files_scanned"], int)
        self.assertGreater(result["files_scanned"], 0)
        payload = json.loads(Path(result["paths"]["run"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["files_scanned"], result["files_scanned"])

    def test_budget_note_reaches_limits(self):
        original = facts.scan_repository

        def tight_scan(root, **kwargs):
            kwargs["max_total_bytes"] = 120
            return original(root, **kwargs)

        with mock.patch.object(facts, "scan_repository", tight_scan):
            result = build_flow.run(self.repo, SHOP_REQUEST)
        self.assertTrue(any("ngân sách bộ nhớ" in item for item in result["limits"]))
        graph = graph_of(result)
        self.assertTrue(any("ngân sách" in item for item in graph["assumptions"]))


class InputValidationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = copy(SHOP, self.tmp / "shop")

    def tearDown(self):
        self._tmp.cleanup()

    def assert_code(self, code, fn, *args, **kwargs):
        with self.assertRaises(build_flow.BuildError) as ctx:
            fn(*args, **kwargs)
        self.assertEqual(ctx.exception.code, code, ctx.exception.message)
        self.assertTrue(ctx.exception.hint or code == "missing_flow_request")

    def test_bad_request_values(self):
        self.assert_code("invalid_argument_type", build_flow.run, self.repo, None)
        self.assert_code("invalid_argument_type", build_flow.run, self.repo, 42)
        self.assert_code("invalid_argument_type", build_flow.run, self.repo, {"x": 1})
        self.assert_code("missing_flow_request", build_flow.run, self.repo, "   ")

    def test_bad_repository_values(self):
        self.assert_code("invalid_argument_type", build_flow.run, None, SHOP_REQUEST)
        self.assert_code("invalid_argument_type", build_flow.run, 42, SHOP_REQUEST)
        self.assert_code("repository_not_found", build_flow.run,
                         self.tmp / "nope", SHOP_REQUEST)

    def test_bad_optional_values(self):
        self.assert_code("invalid_argument_type", build_flow.run,
                         self.repo, SHOP_REQUEST, 42)
        self.assert_code("invalid_argument_type", build_flow.run,
                         self.repo, SHOP_REQUEST, None, 42)
        self.assert_code("invalid_slug", build_flow.run,
                         self.repo, SHOP_REQUEST, None, "a/b")

    def test_cli_returns_json_error_without_traceback(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = build_flow.main(["--repo", str(self.repo), "--request", "  ", "--json"])
        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["code"], "missing_flow_request")
        self.assertNotIn("Traceback", err.getvalue())


class DeterminismTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_two_runs_agree_on_nodes_edges_and_counts(self):
        first_repo = copy(SHOP, self.tmp / "a")
        second_repo = copy(SHOP, self.tmp / "b")
        first = build_flow.run(first_repo, SHOP_REQUEST, slug="same")
        second = build_flow.run(second_repo, SHOP_REQUEST, slug="same")
        a, b = graph_of(first), graph_of(second)
        self.assertEqual([(n["id"], n["type"], n["title"], n["confidence"]) for n in a["nodes"]],
                         [(n["id"], n["type"], n["title"], n["confidence"]) for n in b["nodes"]])
        self.assertEqual(a["edges"], b["edges"])
        self.assertEqual(first["counts"], second["counts"])


class FlowIndexIntegrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = copy(SHOP, self.tmp / "shop")

    def tearDown(self):
        self._tmp.cleanup()

    def test_flow_is_recorded_into_an_existing_index(self):
        from pfe import index
        index.build_index(self.repo, mode="full")
        result = build_flow.run(self.repo, SHOP_REQUEST)
        self.assertTrue(result["indexed"])
        with index.connect(self.repo, create=False) as connection:
            rows = connection.execute(
                "SELECT COUNT(*) AS c FROM facts WHERE predicate = 'belongs_to_flow'").fetchone()
        self.assertGreater(rows["c"], 0)

    def test_flow_still_runs_without_an_index(self):
        result = build_flow.run(self.repo, SHOP_REQUEST)
        self.assertFalse(result["indexed"])
        self.assertEqual(result["status"], "ok")
        render_flow.validate(graph_of(result))


if __name__ == "__main__":
    unittest.main()
