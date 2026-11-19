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
