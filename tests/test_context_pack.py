"""T2 regression tests: context pack must answer with evidence, not guesses."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pfe import index, retrieval  # noqa: E402

WEB = ROOT / "tests" / "fixtures" / "shop-app"
DESKTOP = ROOT / "tests" / "fixtures" / "desktop-app"


def prepare(src, target):
    repo = shutil.copytree(src, target,
                           ignore=shutil.ignore_patterns("artifacts", ".pfe", "__pycache__"))
    index.build_index(repo, mode="full")
    return repo


class WebContextPackTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = prepare(WEB, Path(self._tmp.name) / "web")

    def tearDown(self):
        self._tmp.cleanup()

    def test_route_is_a_real_route_entity_not_a_file_name(self):
        pack = retrieval.context_pack(self.repo, "export report")
        labels = {item["route"] for item in pack["routes"]}
        self.assertIn("/api/reports/export", labels)
        for item in pack["routes"]:
            self.assertTrue(item["route"].startswith("/"), item)
            self.assertTrue(item["path"].endswith(".js"), item)
            self.assertGreaterEqual(item["start_line"], 1)
            self.assertEqual(item["confidence"], "observed")

    def test_entry_points_carry_evidence_and_kind(self):
        pack = retrieval.context_pack(self.repo, "export report")
        kinds = {item["kind"] for item in pack["entry_points"]}
        self.assertIn("http_route", kinds)
        for item in pack["entry_points"]:
            self.assertIn(item["kind"], retrieval.ENTRY_KINDS_EMITTED)
            self.assertTrue(item["evidence_refs"])
            self.assertEqual(item["evidence_kind"], "observed")

    def test_likely_files_and_dependencies_have_paths_and_lines(self):
        pack = retrieval.context_pack(self.repo, "export report")
        self.assertTrue(pack["likely_files"])
        for item in pack["likely_files"]:
            self.assertTrue(item["path"])
            self.assertGreaterEqual(item["start_line"], 1)
            self.assertTrue(item["evidence_refs"])
        for dep in pack["dependencies"]:
            self.assertTrue(dep["path"], dep)
            self.assertGreaterEqual(dep["start_line"], 1)
            self.assertTrue(dep["why_included"])
            self.assertTrue(dep["evidence_refs"])
            self.assertIn(dep["kind"], {"test", "function", "class", "symbol", "file",
                                        "module", "data_model", "external_system",
                                        "error_case", "route"})

    def test_seen_sets_are_separate(self):
        pack = retrieval.context_pack(self.repo, "export report")
        self.assertEqual(set(pack["seen"]), {"paths", "entities", "evidence"})
        self.assertGreaterEqual(pack["seen"]["paths"], 1)
        self.assertGreaterEqual(pack["seen"]["entities"], 1)

    def test_analysis_metadata_present(self):
        pack = retrieval.context_pack(self.repo, "export report")
        self.assertEqual(pack["analysis_kind"], "context_pack")
        self.assertTrue(pack["limitations"])
        self.assertIn("source_commit", pack)
        self.assertIn("stale", pack)

    def test_error_intent_raises_error_case_priority(self):
        normal = retrieval.context_pack(self.repo, "export report")
        error = retrieval.context_pack(self.repo, "export report lỗi xử lý ở đâu")
        normal_kinds = [item["kind"] for item in normal["likely_files"]]
        error_kinds = ([item["kind"] for item in error["likely_files"]]
                       + [item["kind"] for item in error["dependencies"]])
        self.assertNotIn("error_case", normal_kinds)
        self.assertIn("error_case", error_kinds)

    def test_confidence_fields_are_split(self):
        pack = retrieval.context_pack(self.repo, "export report")
        for item in pack["likely_files"]:
            self.assertIn(item["location_confidence"], {"observed", "unknown"})
            self.assertIn(item["relevance_confidence"],
                          {"observed", "structural", "inferred"})


class FlaskBlueprintTests(unittest.TestCase):
    """A blueprint decorator is a route declaration and must be found."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = prepare(ROOT / "tests" / "fixtures" / "flask-app",
                            Path(self._tmp.name) / "flask")

    def tearDown(self):
        self._tmp.cleanup()

    def test_blueprint_route_is_an_entry_point(self):
        pack = retrieval.context_pack(self.repo, "xuất báo cáo")
        routes = {item["route"] for item in pack["entry_points"]}
        self.assertIn("/reports/export", routes)
        for item in pack["entry_points"]:
            self.assertEqual(item["kind"], "http_route")
            self.assertGreaterEqual(item["start_line"], 1)

    def test_a_route_that_does_not_name_the_task_is_only_related(self):
        """Both routes live in app.py; only one is what "xuất báo cáo" is about.

        Sharing a file is not evidence of relevance, so `/reports/status` must be
        reported as related context rather than presented as the entry point.
        """
        pack = retrieval.context_pack(self.repo, "xuất báo cáo")
        entry = {item["route"] for item in pack["entry_points"]}
        related = {item["label"] for item in pack.get("related_routes", [])}
        self.assertNotIn("/reports/status", entry)
        self.assertIn("/reports/status", related)

class DecoyRouteTests(unittest.TestCase):
    """0.7.3: a route that only shares vocabulary is not context."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = prepare(ROOT / "tests" / "fixtures" / "shop-app",
                            Path(self._tmp.name) / "shop")

    def tearDown(self):
        self._tmp.cleanup()

    def test_exact_file_task_excludes_decoy_route(self):
        """0.7.3: a keyword-only decoy must not be a file to read before editing.

        `routes/preview.js` declares /api/legacy/preview. It shares vocabulary with
        the task and has relations to its own route, which used to be enough to
        put it in likely_files next to the file the task actually named.
        """
        from pfe import retrieval
        pack = retrieval.context_pack(self.repo, "Sửa services/report_service.js: gom context")
        paths = {item["path"] for item in pack["likely_files"]}
        self.assertIn("services/report_service.js", paths)
        self.assertNotIn("routes/preview.js", paths)
        excluded = {item["path"] for item in pack["lexical_only"]}
        self.assertIn("routes/preview.js", excluded)

    def test_exact_file_task_reaches_its_callers(self):
        from pfe import retrieval
        pack = retrieval.context_pack(self.repo, "Sửa services/report_service.js: gom context")
        paths = {item["path"] for item in pack["likely_files"]}
        self.assertIn("server.js", paths, "the caller of the named file is real context")
        self.assertIn("tests/report_service.test.js", paths)

    def test_decoy_is_never_an_entry_point(self):
        from pfe import retrieval
        for task in ("export report", "xuất báo cáo", "lỗi khi xuất báo cáo"):
            pack = retrieval.context_pack(self.repo, task)
            entry = {item["label"] for item in pack["entry_points"]}
            self.assertNotIn("/api/legacy/preview", entry, task)
            related = {item["label"] for item in pack.get("related_routes", [])}
            self.assertNotIn("/api/legacy/preview", entry & related, task)

    def test_routes_field_holds_only_task_relevant_routes(self):
        from pfe import retrieval
        pack = retrieval.context_pack(self.repo, "export report")
        self.assertEqual({item["route"] for item in pack["routes"]}, {"/api/reports/export"})

    def test_lexical_only_candidate_carries_inferred_relevance(self):
        from pfe import retrieval
        pack = retrieval.context_pack(self.repo, "Sửa services/report_service.js: gom context")
        for item in pack["lexical_only"]:
            self.assertEqual(item["confidence"], "inferred")

    def test_three_confidence_axes_are_distinct(self):
        from pfe import retrieval
        pack = retrieval.context_pack(self.repo, "export report")
        for item in pack["likely_files"]:
            for key in ("location_confidence", "relation_confidence",
                        "relevance_confidence"):
                self.assertIn(key, item)
            self.assertEqual(item["location_confidence"], "observed")


class RelatedTestsResolutionTests(unittest.TestCase):
    """T2: `tested_by` is a file -> test fact, but the pack ranks symbols.

    Looking only at a symbol's direct neighbours therefore missed every test in
    a repository that has one — `related_tests` came back empty while the fact
    was sitting in the index.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = prepare(ROOT / "tests" / "fixtures" / "shop-app",
                            Path(self._tmp.name) / "shop")

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_file_level_test_still_reaches_the_pack(self):
        pack = retrieval.context_pack(self.repo, "export report")
        paths = {item["path"] for item in pack["related_tests"]}
        self.assertIn("tests/report_service.test.js", paths)

    def test_test_evidence_is_labelled_file_level_not_line_level(self):
        pack = retrieval.context_pack(self.repo, "export report")
        for item in pack["related_tests"]:
            self.assertEqual(item["evidence_kind"], "file_level")
            self.assertEqual(item["via"], "file")
            self.assertTrue(item["evidence_refs"])

    def test_every_related_test_carries_a_path(self):
        pack = retrieval.context_pack(self.repo, "export report")
        self.assertTrue(pack["related_tests"])
        for item in pack["related_tests"]:
            self.assertTrue(item["path"])
            self.assertGreaterEqual(item["start_line"], 1)


class EntryPointRelevanceTests(unittest.TestCase):
    """T2: a route must name the task to be the entry point."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = prepare(ROOT / "tests" / "fixtures" / "shop-app",
                            Path(self._tmp.name) / "shop")

    def tearDown(self):
        self._tmp.cleanup()

    def test_the_matching_route_wins_and_the_sibling_moves_to_related(self):
        pack = retrieval.context_pack(self.repo, "export report")
        entry = {item["route"] for item in pack["entry_points"]}
        related = {item["label"] for item in pack.get("related_routes", [])}
        self.assertEqual(entry, {"/api/reports/export"})
        self.assertIn("/api/reports/:id", related)

    def test_related_routes_say_why_they_were_excluded(self):
        pack = retrieval.context_pack(self.repo, "export report")
        for item in pack.get("related_routes", []):
            self.assertIn("không khớp task", item["why_excluded"])

    def test_an_error_task_still_reaches_its_entry_point(self):
        pack = retrieval.context_pack(self.repo, "lỗi khi xuất báo cáo")
        self.assertTrue(pack["entry_points"])
        self.assertTrue(any(item["path"].endswith("test.js")
                            for item in pack["related_tests"]))


class DesktopContextPackTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = prepare(DESKTOP, Path(self._tmp.name) / "desktop")

    def tearDown(self):
        self._tmp.cleanup()

    def test_gui_cli_worker_entry_points(self):
        pack = retrieval.context_pack(self.repo, "cập nhật dữ liệu xuất excel")
        kinds = {item["kind"] for item in pack["entry_points"]}
        self.assertIn("gui_event", kinds)
        self.assertIn("cli_command", kinds)
        self.assertIn("worker", kinds)
        self.assertIn("main", kinds)
        for item in pack["entry_points"]:
            self.assertGreaterEqual(item["start_line"], 1)
            self.assertTrue(item["path"].endswith(".py"))

    def test_desktop_has_no_invented_http_route(self):
        pack = retrieval.context_pack(self.repo, "cập nhật dữ liệu xuất excel")
        self.assertEqual(pack["routes"], [])
        self.assertTrue(any("desktop" in item.lower() or "route" in item.lower()
                            for item in pack["limitations"]), pack["limitations"])

    def test_dependency_is_a_real_relation(self):
        pack = retrieval.context_pack(self.repo, "xuất excel từ dữ liệu")
        allowed = set(retrieval.DEPENDENCY_PREDICATES)
        for dep in pack["dependencies"]:
            self.assertIn(dep["relation"], allowed, dep)


if __name__ == "__main__":
    unittest.main()
