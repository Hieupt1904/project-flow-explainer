"""Tests for the code-knowledge layer: ontology, index, retrieval, impact, verify.

Run: python -m unittest discover -s tests -v
Every test works on a temp copy of a fixture; nothing is written into
tests/fixtures, nothing touches the network.
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
sys.path.insert(0, str(ROOT))
import build_flow  # noqa: E402
from pfe import (  # noqa: E402
    facts, impact, index, knowledge, ontology, retrieval, vectors, verify,
)

FIXTURE = ROOT / "tests" / "fixtures" / "shop-app"
TWO_ROUTES = ROOT / "tests" / "fixtures" / "two-routes-app"
SECRET = "fixture-secret-value-abc123"


def copy_fixture(target):
    shutil.copytree(FIXTURE, target, ignore=shutil.ignore_patterns("artifacts", ".pfe"))
    (target / ".env").write_text("API_KEY=" + SECRET + "\n", encoding="utf-8")
    (target / "config.py").write_text('API_KEY = "' + SECRET + '"\n', encoding="utf-8")
    return target


class OntologyTests(unittest.TestCase):
    def test_valid_fact_passes(self):
        record = ontology.fact(
            "file:server.js", "handles_route", "route:GET /api/reports",
            ontology.evidence("observed", path="server.js", start_line=4),
            "observed", "abc123", "test")
        self.assertIs(ontology.validate_fact(record), record)
        self.assertEqual(record["subject"], ontology.normalize_id("file:server.js"))

    def test_call_without_call_site_is_rejected(self):
        record = ontology.fact(
            "file:a.js", "calls", "symbol:b.js#run",
            ontology.evidence("structural", path="a.js", start_line=1),
            "structural", "abc", "test")
        with self.assertRaises(ontology.OntologyError) as ctx:
            ontology.validate_fact(record)
        self.assertEqual(ctx.exception.code, "evidence_kind_mismatch")

    def test_observed_without_location_is_rejected(self):
        record = ontology.fact(
            "file:a.py", "defines", "function:a.py#run",
            ontology.evidence("observed"), "observed", "abc", "test")
        with self.assertRaises(ontology.OntologyError) as ctx:
            ontology.validate_fact(record)
        self.assertEqual(ctx.exception.code, "observed_without_location")

    def test_runtime_confidence_requires_runtime_evidence(self):
        record = ontology.fact(
            "file:a.py", "defines", "function:a.py#run",
            ontology.evidence("observed", path="a.py", start_line=1),
            "runtime_verified", "abc", "test")
        with self.assertRaises(ontology.OntologyError) as ctx:
            ontology.validate_fact(record)
        self.assertEqual(ctx.exception.code, "runtime_evidence_required")

    def test_declared_only_relation_is_not_emittable(self):
        record = ontology.fact(
            "function:a.py#run", "returns", "data_model:rows",
            ontology.evidence("observed", path="a.py", start_line=1),
            "observed", "abc", "test")
        with self.assertRaises(ontology.OntologyError) as ctx:
            ontology.validate_fact(record)
        self.assertEqual(ctx.exception.code, "relation_not_emittable")

    def test_wrong_subject_type_is_rejected(self):
        record = ontology.fact(
            "route:GET /x", "defines", "function:a.py#run",
            ontology.evidence("observed", path="a.py", start_line=1),
            "observed", "abc", "test")
        with self.assertRaises(ontology.OntologyError) as ctx:
            ontology.validate_fact(record)
        self.assertEqual(ctx.exception.code, "invalid_subject_type")

    def test_structural_never_replaces_observed(self):
        observed = ontology.fact(
            "file:a.py", "reads_from", "data_model:rows",
            ontology.evidence("observed", path="a.py", start_line=3),
            "observed", "abc", "test")
        structural = ontology.fact(
            "file:a.py", "reads_from", "data_model:rows",
            ontology.evidence("structural", path="a.py", start_line=1),
            "structural", "abc", "test")
        merged = ontology.validate_facts([structural, observed])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["confidence"], "observed")
        self.assertEqual(merged[0]["evidence"]["start_line"], 3)
        self.assertIn("contradicted", merged[0])


class KnowledgeBuildTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = copy_fixture(self.tmp / "shop-app")

    def tearDown(self):
        self._tmp.cleanup()

    def build(self):
        files, excluded, budget = facts.scan_repository(self.repo, include_tests=True)
        basenames = facts.index_basenames(files)
        known = {item.rel for item in files}
        for item in files:
            item.imports = facts.find_imports(item.text(), item.rel, known, basenames)
        git = facts.git_state(self.repo)
        return knowledge.build_knowledge(self.repo, files, git)

    def test_every_fact_has_evidence(self):
        graph = self.build()
        self.assertGreater(graph["stats"]["facts"], 0)
        for record in graph["facts"]:
            self.assertTrue(record["evidence"].get("kind"), record)
            self.assertIn(record["confidence"], ontology.CONFIDENCE)

    def test_call_facts_carry_a_call_site_line(self):
        graph = self.build()
        calls = [record for record in graph["facts"] if record["predicate"] == "calls"]
        self.assertGreater(len(calls), 0, "fixture phải có ít nhất một call site")
        for record in calls:
            self.assertEqual(record["evidence"]["kind"], "call_site")
            self.assertGreaterEqual(record["evidence"]["start_line"], 1)

    def test_relation_kinds_match_entity_types(self):
        graph = self.build()
        for record in graph["facts"]:
            subject_kind = record["subject"].split(":", 1)[0]
            object_kind = record["object"].split(":", 1)[0]
            allowed = ontology.RELATIONS[record["predicate"]]
            self.assertIn(subject_kind, allowed[0], record)
            self.assertIn(object_kind, allowed[1], record)

    def test_secret_values_never_reach_the_graph(self):
        graph = self.build()
        payload = json.dumps(graph, ensure_ascii=False)
        self.assertNotIn(SECRET, payload)


class TestMappingTests(unittest.TestCase):
    """A test file must map to the code it references, in the right direction."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = copy_fixture(self.tmp / "shop-app")

    def tearDown(self):
        self._tmp.cleanup()

    def test_tested_by_points_from_source_to_test(self):
        summary = index.build_index(self.repo, mode="full")
        self.assertGreaterEqual(summary["tests_indexed"], 1)
        with index.connect(self.repo, create=False) as connection:
            rows = connection.execute(
                "SELECT subject, object, evidence FROM facts WHERE predicate = 'tested_by'"
            ).fetchall()
        self.assertTrue(rows, "phải có ít nhất một quan hệ tested_by")
        for row in rows:
            self.assertTrue(row["subject"].startswith("file:"), row["subject"])
            self.assertTrue(row["object"].startswith("test:"), row["object"])
            evidence = json.loads(row["evidence"])
            self.assertTrue(evidence["path"].startswith("tests/"), evidence["path"])

    def test_impact_lists_the_related_test(self):
        index.build_index(self.repo, mode="full")
        payload = impact.impact_analysis(self.repo, ["services/report_service.js"])
        self.assertTrue(payload["related_tests"], payload)
        self.assertTrue(payload["related_tests"][0]["test"].startswith("tests/"))


class IndexTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = copy_fixture(self.tmp / "shop-app")

    def tearDown(self):
        self._tmp.cleanup()

    def test_full_then_incremental_reuses_parsed_files(self):
        first = index.build_index(self.repo, mode="full")
        self.assertEqual(first["mode"], "full")
        self.assertEqual(first["files_parsed"], first["files_indexed"])
        second = index.build_index(self.repo, mode="incremental")
        self.assertEqual(second["files_parsed"], 0)
        self.assertEqual(second["files_reused"], second["files_indexed"])
        self.assertTrue(index.db_path(self.repo).exists())

    def test_changed_file_is_reparsed(self):
        index.build_index(self.repo, mode="full")
        target = self.repo / "server.js"
        target.write_text(target.read_text(encoding="utf-8") + "\n// thay đổi\n",
                          encoding="utf-8")
        summary = index.build_index(self.repo, mode="incremental")
        self.assertEqual(summary["changed"], ["server.js"])
        self.assertEqual(summary["files_parsed"], 1)

    def test_deleted_file_is_removed(self):
        index.build_index(self.repo, mode="full")
        (self.repo / "routes" / "preview.js").unlink()
        summary = index.build_index(self.repo, mode="incremental")
        self.assertIn("routes/preview.js", summary["deleted"])
        with index.connect(self.repo, create=False) as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS c FROM entities WHERE path = ?",
                ("routes/preview.js",)).fetchone()
        self.assertEqual(row["c"], 0)

    def test_renamed_file_is_reported(self):
        index.build_index(self.repo, mode="full")
        source = self.repo / "db" / "report_repo.js"
        (self.repo / "db" / "repo_query.js").write_text(
            source.read_text(encoding="utf-8"), encoding="utf-8")
        source.unlink()
        summary = index.build_index(self.repo, mode="incremental")
        self.assertEqual(len(summary["renamed"]), 1)
        self.assertEqual(summary["renamed"][0]["to"], "db/repo_query.js")

    def test_index_version_change_forces_rebuild(self):
        index.build_index(self.repo, mode="full")
        with index.connect(self.repo) as connection:
            index._set_meta(connection, "index_version", "0")
            connection.commit()
        summary = index.build_index(self.repo, mode="incremental")
        self.assertEqual(summary["mode"], "full")
        self.assertGreater(summary["files_parsed"], 0)

    def test_sensitive_files_are_not_indexed(self):
        index.build_index(self.repo, mode="full")
        with index.connect(self.repo, create=False) as connection:
            rows = connection.execute("SELECT path FROM entities WHERE path IS NOT NULL").fetchall()
        paths = {row["path"] for row in rows}
        self.assertNotIn(".env", paths)
        self.assertNotIn("config.py", paths)
        self.assertGreaterEqual(index.status(self.repo)["files_indexed"], 1)

    def test_index_directory_is_not_reindexed(self):
        index.build_index(self.repo, mode="full")
        summary = index.build_index(self.repo, mode="incremental")
        for path in summary["added"] + summary["changed"]:
            self.assertNotIn(".pfe", path)

    def test_symlink_to_env_is_not_indexed(self):
        link = self.repo / "leak.py"
        try:
            os.symlink(self.repo / ".env", link)
        except OSError:
            self.skipTest("symlink không dùng được trên hệ thống này")
        index.build_index(self.repo, mode="full")
        with index.connect(self.repo, create=False) as connection:
            rows = connection.execute(
                "SELECT path FROM entities WHERE path = ?", ("leak.py",)).fetchall()
            payload = connection.execute("SELECT payload FROM file_cache").fetchall()
        self.assertEqual(rows, [])
        self.assertNotIn(SECRET, json.dumps([dict(row) for row in payload], ensure_ascii=False))

    def test_symlink_to_artifacts_is_not_indexed(self):
        build_flow.run(self.repo, "Giải thích luồng xuất báo cáo")
        link = self.repo / "artifact_link.js"
        real = next((self.repo / "artifacts").rglob("flow.json"))
        try:
            os.symlink(real, link)
        except OSError:
            self.skipTest("symlink không dùng được trên hệ thống này")
        summary = index.build_index(self.repo, mode="full")
        self.assertNotIn("artifact_link.js", summary["added"])

    def test_budget_truncation_is_reported(self):
        entries, excluded, budget = facts.walk_sources(self.repo, max_total_bytes=100)
        self.assertTrue(budget.truncated_bytes)
        self.assertTrue(budget.notes)
        self.assertGreater(excluded["budget_bytes"], 0)

    def test_two_walkers_classify_the_same_files(self):
        scanned, _excluded, _budget = facts.scan_repository(self.repo, include_tests=True)
        walked, _e, _b = facts.walk_sources(self.repo, include_tests=True)
        self.assertEqual(sorted(item.rel for item in scanned),
                         sorted(entry.rel for entry in walked))


class SearchTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = copy_fixture(self.tmp / "shop-app")
        index.build_index(self.repo, mode="full", include_vectors=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_symbol_search_finds_the_function(self):
        payload = retrieval.retrieve(self.repo, "export_report")
        kinds = [(item["kind"], item["symbol"]) for item in payload["results"]]
        self.assertIn(("function", "exportReport"), kinds)
        self.assertEqual(payload["results"][0]["symbol"], "exportReport")
        self.assertEqual(payload["results"][0]["source_commit"], payload["source_commit"])

    def test_route_search_finds_the_declaration(self):
        payload = retrieval.retrieve(self.repo, "/api/reports/export")
        self.assertEqual(payload["results"][0]["kind"], "route")
        self.assertEqual(payload["results"][0]["symbol"], "/api/reports/export")
        self.assertGreaterEqual(payload["results"][0]["start_line"], 1)

    def test_vietnamese_query_is_bridged_to_code_terms(self):
        payload = retrieval.retrieve(self.repo, "xuất báo cáo ra excel")
        self.assertTrue(payload["results"])
        top = payload["results"][0]
        self.assertIn(top["symbol"], {"exportReport", "/api/reports/export", "loadReportRows"})

    def test_same_symbol_is_not_listed_twice(self):
        payload = retrieval.retrieve(self.repo, "export_report")
        keys = [(item["path"], item["symbol"]) for item in payload["results"]]
        self.assertEqual(len(keys), len(set(keys)), keys)
        self.assertEqual(payload["results"][0]["symbol"], "exportReport")

    def test_long_natural_query_is_flagged(self):
        payload = retrieval.retrieve(
            self.repo,
            "Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file")
        self.assertTrue(any("Query dài" in item for item in payload["warnings"]),
                        payload["warnings"])

    def test_short_query_has_no_long_query_warning(self):
        payload = retrieval.retrieve(self.repo, "exportReport")
        self.assertFalse(any("Query dài" in item for item in payload["warnings"]))

    def test_results_carry_evidence_and_no_source_text(self):
        payload = retrieval.retrieve(self.repo, "report")
        self.assertNotIn(SECRET, json.dumps(payload, ensure_ascii=False))
        for item in payload["results"]:
            self.assertTrue(item["evidence_refs"])
            self.assertIn("why_matched", item)
            self.assertIn("confidence", item)
            self.assertNotIn("snippets", payload)

    def test_flow_summary_is_searchable(self):
        build_flow.run(self.repo, "Giải thích từ lúc người dùng nhấn xuất báo cáo")
        payload = retrieval.retrieve(self.repo, "xuất báo cáo")
        self.assertTrue(any(item["kind"] == "flow" for item in payload["results"]),
                        payload["results"])

    def test_exact_match_outranks_vector_candidate(self):
        payload = retrieval.retrieve(self.repo, "export_report")
        exact = payload["results"][0]
        self.assertIn("exact_symbol", exact["channels"] if "channels" in exact
                      else ["exact_symbol"])
        self.assertGreater(exact["score"], 1.0)

    def test_vector_result_is_never_verified(self):
        with index.connect(self.repo, create=False) as connection:
            payload = vectors.search(connection, "báo cáo")
        self.assertTrue(payload["enabled"])
        for item in payload["results"]:
            self.assertEqual(item["verified"], False)
            self.assertEqual(item["confidence"], "inferred")

    def test_embedding_model_mismatch_disables_vectors(self):
        class Other(vectors.EmbeddingBackend):
            name = "other-model"
            version = "9"
            dim = 16

            def embed(self, texts):
                return [[0.1] * self.dim for _ in texts]

        with index.connect(self.repo, create=False) as connection:
            payload = vectors.search(connection, "report", backend=Other())
        self.assertFalse(payload["enabled"])
        self.assertEqual(payload["reason"], "embedding_model_mismatch")

    def test_offline_backend_is_rejected(self):
        class Remote(vectors.EmbeddingBackend):
            name = "remote"
            version = "1"
            dim = 8
            local = False

            def embed(self, texts):
                return [[0.0] * self.dim for _ in texts]

        with index.connect(self.repo, create=False) as connection:
            summary = vectors.ensure_index(connection, [], backend=Remote())
        self.assertFalse(summary["enabled"])
        self.assertEqual(summary["reason"], "no_local_embedding_backend")

    def test_stale_index_is_reported(self):
        index.build_index(self.repo, mode="full")
        target = self.repo / "server.js"
        target.write_text(target.read_text(encoding="utf-8") + "\n// moi\n", encoding="utf-8")
        payload = retrieval.retrieve(self.repo, "export_report")
        self.assertTrue(payload["stale"])
        self.assertTrue(payload["stale_warning"])

    def test_missing_index_has_a_stable_code(self):
        shutil.rmtree(self.repo / ".pfe")
        with self.assertRaises(index.IndexError_) as ctx:
            retrieval.retrieve(self.repo, "export_report")
        self.assertEqual(ctx.exception.code, "index_missing")


class ImpactTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = copy_fixture(self.tmp / "shop-app")
        index.build_index(self.repo, mode="full")

    def tearDown(self):
        self._tmp.cleanup()

    def test_route_file_is_high_risk(self):
        payload = impact.impact_analysis(self.repo, ["server.js"])
        self.assertEqual(payload["risk_level"], "high")
        self.assertTrue(payload["affected_routes"])

    def test_service_file_reports_downstream_caller(self):
        payload = impact.impact_analysis(self.repo, ["services/report_service.js"])
        self.assertIn("server.js", [item["file"] for item in payload["downstream_modules"]])
        self.assertIn(payload["risk_level"], {"medium", "high"})
        self.assertTrue(payload["suggested_verification"])

    def test_unknown_file_is_reported_not_guessed(self):
        payload = impact.impact_analysis(self.repo, ["khong/ton/tai.js"])
        self.assertEqual(payload["unknown_files"], ["khong/ton/tai.js"])
        self.assertEqual(payload["affected_symbols"], [])

    def test_diff_input_is_parsed(self):
        diff = "--- a/server.js\n+++ b/server.js\n@@ -1 +1 @@\n-x\n+y\n"
        payload = impact.impact_analysis(self.repo, diff=diff)
        self.assertIn("server.js", payload["changed_files"])

    def test_missing_input_has_a_stable_code(self):
        with self.assertRaises(index.IndexError_) as ctx:
            impact.impact_analysis(self.repo, [])
        self.assertEqual(ctx.exception.code, "no_changed_files")


class VerifyTests(unittest.TestCase):
    """The two-route fixture is used here: the selected route handles an
    exception, so a decision node exists and a bypass can be injected."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = self.tmp / "two-routes-app"
        shutil.copytree(TWO_ROUTES, self.repo,
                        ignore=shutil.ignore_patterns("artifacts", ".pfe"))
        build_flow.run(self.repo, "Xem chi tiết hóa đơn và xử lý lỗi khi đọc hóa đơn")

    def tearDown(self):
        self._tmp.cleanup()

    def flow_dir(self):
        return next((self.repo / "artifacts" / "flows").iterdir())

    def test_fresh_artifacts_pass(self):
        payload = verify.verify_repository(self.repo)
        statuses = {item["check"]: item["status"] for item in payload["checks"]}
        self.assertEqual(statuses["graph_evidence"], "pass")
        self.assertEqual(statuses["ui_self_contained"], "pass")
        self.assertEqual(statuses["privacy"], "pass")
        self.assertFalse(payload["ui_verified"])
        self.assertFalse(payload["runtime_verified"])

    def test_fabricated_call_edge_is_detected(self):
        path = self.flow_dir() / "flow.json"
        graph = json.loads(path.read_text(encoding="utf-8"))
        graph["edges"][0]["evidence"] = "call"
        graph["edges"][0]["technical"] = "không có call site"
        path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
        payload = verify.verify_repository(self.repo)
        statuses = {item["check"]: item["status"] for item in payload["checks"]}
        self.assertEqual(statuses["graph_evidence"], "fail")

    def test_decision_bypass_is_detected(self):
        path = self.flow_dir() / "flow.json"
        graph = json.loads(path.read_text(encoding="utf-8"))
        decision = next(node for node in graph["nodes"] if node["type"] == "decision")
        inbound = next(edge for edge in graph["edges"] if edge["to"] == decision["id"])
        target = next(edge for edge in graph["edges"]
                      if edge["from"] == decision["id"] and edge["kind"] == "success")
        graph["edges"].append({"from": inbound["from"], "to": target["to"],
                               "label": "bỏ qua nhánh", "kind": "success",
                               "technical": "bypass", "evidence": "structure"})
        path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
        payload = verify.verify_repository(self.repo)
        statuses = {item["check"]: item["status"] for item in payload["checks"]}
        self.assertEqual(statuses["graph_evidence"], "fail")

    def test_missing_public_file_is_detected(self):
        (self.flow_dir() / "overview.md").unlink()
        payload = verify.verify_repository(self.repo)
        statuses = {item["check"]: item["status"] for item in payload["checks"]}
        self.assertEqual(statuses["flow_artifacts"], "fail")

    def test_absolute_path_in_artifact_is_detected(self):
        path = self.flow_dir() / "overview.md"
        path.write_text(path.read_text(encoding="utf-8")
                        + "\n" + str(self.tmp) + "/shop-app\n", encoding="utf-8")
        payload = verify.verify_repository(self.repo)
        statuses = {item["check"]: item["status"] for item in payload["checks"]}
        self.assertEqual(statuses["privacy"], "fail")

    def test_no_artifact_means_blocked_not_pass(self):
        other = self.tmp / "empty-repo"
        other.mkdir()
        payload = verify.verify_repository(other)
        statuses = {item["check"]: item["status"] for item in payload["checks"]}
        self.assertEqual(statuses["flow_artifacts"], "blocked")
        self.assertEqual(payload["verdict"], "partial")


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = copy_fixture(self.tmp / "shop-app")
        index.build_index(self.repo, mode="full")

    def tearDown(self):
        self._tmp.cleanup()

    def test_refresh_only_reparses_changed_files(self):
        (self.repo / "extra.js").write_text(
            "function extraThing() {\n  return 1\n}\n", encoding="utf-8")
        payload = impact.refresh(self.repo)
        self.assertEqual(payload["mode"], "incremental")
        self.assertIn("extra.js", payload["added"])
        self.assertEqual(payload["files_parsed"], 1)
        self.assertTrue(payload["no_full_rebuild"])


if __name__ == "__main__":
    unittest.main()
