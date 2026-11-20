"""Regression tests for the v0.4.0 audit (T0, T1, T3, T6, T7).

Each test names the failure it prevents; none of them needs the network or a
DSH profile.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import build_flow  # noqa: E402
from pfe import index, knowledge, vectors, verify  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "shop-app"
CLI = ROOT / "tools" / "pfe_cli.py"


def copy_repo(target):
    return shutil.copytree(FIXTURE, target,
                           ignore=shutil.ignore_patterns("artifacts", ".pfe", "__pycache__"))


class CliFlowTests(unittest.TestCase):
    """T0: `pfe_cli.py flow` must run from any working directory."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = copy_repo(self.tmp / "repo")

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, args, cwd):
        return subprocess.run([sys.executable, str(CLI), *args], cwd=str(cwd),
                              capture_output=True, text=True, check=False)

    def parse_single_json(self, result):
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, "CLI phải in đúng một object JSON: " + result.stdout)
        return json.loads(lines[0])

    def test_flow_from_repository_root(self):
        result = self.run_cli(["flow", "--repo", str(self.repo),
                               "--request", "Giải thích luồng xuất báo cáo"], ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.parse_single_json(result)
        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("ModuleNotFoundError", result.stdout + result.stderr)

    def test_flow_from_another_working_directory(self):
        result = self.run_cli(["flow", "--repo", str(self.repo),
                               "--request", "Giải thích luồng xuất báo cáo"], self.tmp)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.parse_single_json(result)
        self.assertEqual(payload["status"], "ok")
        self.assertIn("flow_html", payload["paths"])

    def test_invalid_repository_keeps_stable_code(self):
        result = self.run_cli(["flow", "--repo", str(self.tmp / "missing"),
                               "--request", "x"], ROOT)
        self.assertEqual(result.returncode, 2)
        payload = self.parse_single_json(result)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["code"], "repository_not_found")

    def test_missing_request_keeps_stable_code(self):
        result = self.run_cli(["flow", "--repo", str(self.repo), "--request", "  "], ROOT)
        self.assertEqual(result.returncode, 2)
        payload = self.parse_single_json(result)
        self.assertEqual(payload["code"], "missing_flow_request")


class IncrementalCacheRepairTests(unittest.TestCase):
    """T1: a missing/malformed cache row must not remove a file from the graph."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = copy_repo(Path(self._tmp.name) / "repo")
        index.build_index(self.repo, mode="full")

    def tearDown(self):
        self._tmp.cleanup()

    def entities_of(self, rel):
        with index.connect(self.repo, create=False) as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS c FROM entities WHERE path = ?", (rel,)).fetchone()
            facts = connection.execute(
                "SELECT COUNT(*) AS c FROM facts WHERE path = ?", (rel,)).fetchone()
        return row["c"], facts["c"]

    def test_missing_cache_row_is_repaired(self):
        before = self.entities_of("server.js")
        self.assertGreater(before[0], 0)
        with index.connect(self.repo) as connection:
            connection.execute("DELETE FROM file_cache WHERE path = 'server.js'")
            connection.commit()
        summary = index.build_index(self.repo, mode="incremental")
        self.assertGreaterEqual(summary["files_parsed"], 1)
        self.assertEqual(self.entities_of("server.js"), before)
        self.assertTrue(any("Cache thiếu" in item for item in summary["warnings"]))

    def test_malformed_cache_payload_is_repaired(self):
        before = self.entities_of("db/report_repo.js")
        with index.connect(self.repo) as connection:
            connection.execute(
                "UPDATE file_cache SET payload = '{not json' WHERE path = 'db/report_repo.js'")
            connection.commit()
        summary = index.build_index(self.repo, mode="incremental")
        self.assertGreaterEqual(summary["files_parsed"], 1)
        self.assertEqual(self.entities_of("db/report_repo.js"), before)
        self.assertTrue(any("Cache hỏng" in item for item in summary["warnings"]))

    def test_graph_is_equivalent_after_repair(self):
        def snapshot():
            with index.connect(self.repo, create=False) as connection:
                entities = connection.execute(
                    "SELECT id FROM entities ORDER BY id").fetchall()
                facts = connection.execute(
                    "SELECT subject, predicate, object FROM facts ORDER BY 1,2,3").fetchall()
            return ([row["id"] for row in entities],
                    [(row["subject"], row["predicate"], row["object"]) for row in facts])

        before = snapshot()
        with index.connect(self.repo) as connection:
            connection.execute("DELETE FROM file_cache")
            connection.commit()
        index.build_index(self.repo, mode="incremental")
        self.assertEqual(snapshot(), before)

    def test_deleted_and_renamed_still_work(self):
        (self.repo / "db" / "connection.js").unlink()
        summary = index.build_index(self.repo, mode="incremental")
        self.assertIn("db/connection.js", summary["deleted"])
        self.assertEqual(self.entities_of("db/connection.js"), (0, 0))


class ConflictPersistenceTests(unittest.TestCase):
    """T3: a known contradiction must survive in SQLite."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = copy_repo(Path(self._tmp.name) / "repo")

    def tearDown(self):
        self._tmp.cleanup()

    def test_conflict_metadata_is_written_and_read_back(self):
        original = knowledge.build_knowledge

        def with_conflict(*args, **kwargs):
            result = original(*args, **kwargs)
            if result["facts"]:
                first = dict(result["facts"][0])
                first["contradicted"] = {
                    "confidence": "inferred",
                    "evidence": {"kind": "inferred", "path": "server.js", "start_line": 1},
                }
                result["facts"] = [first] + result["facts"][1:]
            return result

        with mock.patch.object(index.knowledge_mod, "build_knowledge", with_conflict):
            index.build_index(self.repo, mode="full")

        with index.connect(self.repo, create=False) as connection:
            row = connection.execute(
                "SELECT contradicted FROM facts WHERE contradicted IS NOT NULL LIMIT 1"
            ).fetchone()
            self.assertIsNotNone(row, "conflict metadata bị mất khi ghi index")
            stored = json.loads(row["contradicted"])
            self.assertEqual(stored["confidence"], "inferred")
            payload = index.facts_about(connection, "file:server.js", limit=50)
        self.assertTrue(any("contradicted" in item for item in payload),
                        "đọc lại index không thấy conflict")


class VerifyVerdictTests(unittest.TestCase):
    """T6: static pass must not read as a full pass."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = copy_repo(Path(self._tmp.name) / "repo")
        build_flow.run(self.repo, "Giải thích từ lúc người dùng nhấn xuất báo cáo")

    def tearDown(self):
        self._tmp.cleanup()

    def flow_dir(self):
        return next((self.repo / "artifacts" / "flows").iterdir())

    def test_static_pass_ui_runtime_blocked_is_partial(self):
        index.build_index(self.repo, mode="full")
        payload = verify.verify_repository(self.repo)
        self.assertEqual(payload["static_verdict"], "pass")
        self.assertEqual(payload["overall_verdict"], "partial")
        self.assertEqual(payload["gates"], {"static": "pass", "ui": "blocked", "runtime": "blocked"})
        self.assertEqual(payload["not_verified"], ["ui", "runtime"])
        self.assertEqual(payload["verdict"], payload["overall_verdict"])

    def test_full_pass_requires_real_gate_evidence(self):
        index.build_index(self.repo, mode="full")
        payload = verify.verify_repository(self.repo, ui_verified=True, runtime_verified=True)
        self.assertEqual(payload["static_verdict"], "pass")
        self.assertEqual(payload["overall_verdict"], "pass")
        self.assertEqual(payload["not_verified"], [])

    def test_static_failure_is_overall_failure(self):
        path = self.flow_dir() / "flow.json"
        graph = json.loads(path.read_text(encoding="utf-8"))
        graph["edges"][0]["evidence"] = "call"
        graph["edges"][0]["technical"] = "không có call site"
        path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
        payload = verify.verify_repository(self.repo)
        self.assertEqual(payload["static_verdict"], "fail")
        self.assertEqual(payload["overall_verdict"], "fail")

    def test_no_artifact_is_blocked_not_pass(self):
        empty = Path(self._tmp.name) / "empty"
        empty.mkdir()
        payload = verify.verify_repository(empty)
        self.assertEqual(payload["static_verdict"], "partial")
        self.assertEqual(payload["overall_verdict"], "partial")
        statuses = {item["check"]: item["status"] for item in payload["checks"]}
        self.assertEqual(statuses["flow_artifacts"], "blocked")


class VectorContractTests(unittest.TestCase):
    """T7: the hashing backend is lexical, never semantic."""

    def test_hashing_backend_is_declared_lexical(self):
        backend = vectors.HashingEmbedding()
        self.assertFalse(backend.semantic)
        self.assertTrue(backend.local)
        self.assertIn("hash", backend.name)

    def test_vectors_are_off_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp) / "repo")
            summary = index.build_index(repo, mode="full")
            self.assertFalse(summary["embedding"]["enabled"])
            self.assertEqual(summary["embedding"]["reason"], "include_vectors=false")

    def test_missing_vector_index_falls_back_with_warning(self):
        from pfe import retrieval
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp) / "repo")
            index.build_index(repo, mode="full")
            payload = retrieval.retrieve(repo, "export_report")
            self.assertTrue(any("vector" in item for item in payload["warnings"]))
            self.assertIn("fts", payload["channels"])


    def test_source_change_without_rebuild_marks_vectors_stale(self):
        """T0: full+vectors -> edit -> incremental without vectors.

        Before the fix the old rows survived, `embedding_model` stayed active and
        retrieval silently returned candidates from the previous entity set.
        """
        from pfe import retrieval
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp) / "repo")
            index.build_index(repo, mode="full", include_vectors=True)
            target = repo / "services" / "report_service.js"
            text = target.read_text(encoding="utf-8")
            target.write_text(text.replace("exportReport", "exportReportV2"), encoding="utf-8")

            summary = index.build_index(repo, mode="incremental", include_vectors=False)
            self.assertEqual(summary["embedding"]["state"], "stale")
            self.assertEqual(summary["embedding"]["reason"], "vector_stale")
            self.assertFalse(summary["embedding"]["enabled"])

            payload = retrieval.retrieve(repo, "export report")
            self.assertNotIn("vector", payload["channels"],
                             "a stale vector index must not be used as a channel")
            self.assertTrue(any("vector_stale" in item for item in payload["warnings"]),
                            "the caller must be told the index is stale, not left guessing")
            self.assertIn("fts", payload["channels"], "FTS must still work while vectors are stale")

    def test_touched_paths_lose_their_vector_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp) / "repo")
            index.build_index(repo, mode="full", include_vectors=True)
            target = repo / "services" / "report_service.js"
            target.write_text(target.read_text(encoding="utf-8")
                              .replace("exportReport", "exportReportV2"), encoding="utf-8")
            index.build_index(repo, mode="incremental", include_vectors=False)
            import sqlite3
            connection = sqlite3.connect(str(index.db_path(repo)))
            try:
                stale_rows = connection.execute(
                    "SELECT COUNT(*) FROM vectors v JOIN entities e ON e.id = v.entity_id"
                    " WHERE e.path = ?", ("services/report_service.js",)).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(stale_rows, 0,
                             "rows for a re-parsed file must not survive as candidates")

    def test_rebuild_clears_the_stale_flag(self):
        from pfe import retrieval
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp) / "repo")
            index.build_index(repo, mode="full", include_vectors=True)
            target = repo / "services" / "report_service.js"
            target.write_text(target.read_text(encoding="utf-8")
                              .replace("exportReport", "exportReportV2"), encoding="utf-8")
            index.build_index(repo, mode="incremental", include_vectors=False)
            rebuilt = index.build_index(repo, mode="incremental", include_vectors=True)
            self.assertEqual(rebuilt["embedding"]["state"], "enabled")
            payload = retrieval.retrieve(repo, "export report")
            self.assertIn("vector", payload["channels"])

    def test_vector_hits_are_labelled_lexical_not_semantic(self):
        from pfe import retrieval
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp) / "repo")
            index.build_index(repo, mode="full", include_vectors=True)
            payload = retrieval.retrieve(repo, "export report")
            for item in payload["results"]:
                self.assertNotIn("semantic_candidate", item.get("relation") or [],
                                 "a hashing backend must not produce semantic labels")


class ImpactEvidenceTests(unittest.TestCase):
    """T4: the blast radius must name where it lands, not where it started."""

    @staticmethod
    def _repo(tmp):
        from pfe import facts, flow as flow_mod
        repo = copy_repo(Path(tmp) / "repo")
        index.build_index(repo, mode="full")
        files, _e, _b = facts.scan_repository(repo, include_tests=False)
        known = {item.rel for item in files}
        basenames = facts.index_basenames(files)
        for item in files:
            item.imports = facts.find_imports(item.text(), item.rel, known, basenames)
        graph, _l, _w, _r = flow_mod.build_graph("xuất báo cáo", files, facts.git_state(repo))
        graph["flow_id"] = "t4-flow"
        index.record_flow(repo, graph, "artifacts/flows/t4-flow")
        return repo

    def test_downstream_path_is_the_downstream_file(self):
        from pfe import impact
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp)
            payload = impact.impact_analysis(repo, changed_files=["services/report_service.js"])
            self.assertTrue(payload["downstream_modules"])
            for item in payload["downstream_modules"]:
                self.assertNotEqual(
                    item["path"], "services/report_service.js",
                    "downstream.path must be the caller's path, not the changed file's")
                self.assertTrue(item["path"], "every downstream row needs a path")

    def test_every_downstream_row_carries_line_and_evidence(self):
        from pfe import impact
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp)
            payload = impact.impact_analysis(repo, changed_files=["services/report_service.js"])
            for item in payload["downstream_modules"]:
                self.assertGreaterEqual(item["start_line"], 1,
                                        "line 0 is not a location")
                self.assertIn(item["relation"], {"imports", "calls"})
                self.assertTrue(item["confidence"])
                self.assertTrue(item["evidence_refs"])

    def test_related_tests_carry_path_and_evidence_kind(self):
        from pfe import impact
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp)
            payload = impact.impact_analysis(repo, changed_files=["services/report_service.js"])
            self.assertTrue(payload["related_tests"])
            for item in payload["related_tests"]:
                self.assertTrue(item["path"])
                self.assertIn(item["evidence_kind"], {"file_level", "line_level"})

    def test_affected_flows_only_lists_real_members(self):
        from pfe import impact
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp)
            payload = impact.impact_analysis(repo, changed_files=["services/report_service.js"])
            for flow in payload["affected_flows"]:
                self.assertEqual(flow["flow_id"], "t4-flow",
                                 "only flows the changed file belongs to are affected")
                self.assertTrue(flow["evidence_refs"])

    def test_stale_artifacts_say_whether_they_are_affected(self):
        from pfe import impact
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp)
            payload = impact.impact_analysis(repo, changed_files=["./nope.js"])
            for item in payload["stale_artifacts"]:
                self.assertIn(item["relation"], {"affected_flow", "informational"})
                self.assertIn("source_commit", item)


class EntryPointEvidenceTests(unittest.TestCase):
    """T3: `def main()` alone is not proof that control enters there."""

    def test_a_bare_def_main_is_structural(self):
        from pfe import facts
        lines = ["def main():", "    return 0"]
        entries = facts.find_entry_points(lines)
        mains = [item for item in entries if item["kind"] == "main"]
        self.assertTrue(mains, "a def main() is still worth reporting")
        for item in mains:
            self.assertEqual(item["evidence_kind"], "structural")

    def test_a_main_guard_is_observed(self):
        from pfe import facts
        lines = ["def main():", "    return 0", "", "if __name__ == '__main__':", "    main()"]
        entries = facts.find_entry_points(lines)
        mains = [item for item in entries if item["kind"] == "main"]
        self.assertTrue(mains)
        self.assertTrue(all(item["evidence_kind"] == "observed" for item in mains))

    def test_the_index_persists_the_evidence_quality(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            # The desktop fixture is the one with both shapes: a guarded
            # __main__.py and a bare def main() in cli.py.
            repo = Path(tmp) / "desktop"
            shutil.copytree(ROOT / "tests" / "fixtures" / "desktop-app", repo,
                            ignore=shutil.ignore_patterns("artifacts", ".pfe", "__pycache__"))
            index.build_index(repo, mode="full")
            connection = sqlite3.connect(str(index.db_path(repo)))
            connection.row_factory = sqlite3.Row
            try:
                rows = {row["path"]: row["evidence_kind"] for row in connection.execute(
                    "SELECT path, evidence_kind FROM entry_points WHERE kind = 'main'")}
            finally:
                connection.close()
        # cli.py has a bare def main(); __main__.py has the guard.
        self.assertEqual(rows.get("app/cli.py"), "structural")
        self.assertEqual(rows.get("app/__main__.py"), "observed")


class FlowIdFilterTests(unittest.TestCase):
    """T1: `filters.flow_id` was advertised in the tool schema and silently ignored.

    The filter now applies to the merged candidate set, not only to the FTS
    channel: expansion and flow summaries added rows after the filter had run.
    """

    @staticmethod
    def _repo_with_flow(tmp):
        from pfe import facts, flow as flow_mod
        repo = copy_repo(Path(tmp) / "repo")
        index.build_index(repo, mode="full")
        files, _excluded, _budget = facts.scan_repository(repo, include_tests=False)
        known = {item.rel for item in files}
        basenames = facts.index_basenames(files)
        for item in files:
            item.imports = facts.find_imports(item.text(), item.rel, known, basenames)
        graph, _limits, _warnings, _related = flow_mod.build_graph(
            "xuất báo cáo", files, facts.git_state(repo))
        graph["flow_id"] = "t1-flow"
        index.record_flow(repo, graph, "artifacts/flows/t1-flow")
        return repo, graph

    def test_a_known_flow_filter_keeps_only_members(self):
        from pfe import retrieval
        with tempfile.TemporaryDirectory() as tmp:
            repo, graph = self._repo_with_flow(tmp)
            member_paths = {(ref["path"]) for node in graph["nodes"]
                            for ref in node.get("source_refs") or []}
            payload = retrieval.retrieve(repo, "export report excel",
                                         filters={"flow_id": "t1-flow"}, top_k=20)
            self.assertTrue(payload["results"], "a known flow must still return its members")
            outside = [item for item in payload["results"]
                       if item["path"] and item["path"] not in member_paths
                       and not item["entity"].startswith("flow:")]
            self.assertEqual(outside, [],
                             "flow_id must scope the whole result set, not just FTS")

    def test_an_unknown_flow_filter_returns_nothing_and_says_why(self):
        from pfe import retrieval
        with tempfile.TemporaryDirectory() as tmp:
            repo, _graph = self._repo_with_flow(tmp)
            payload = retrieval.retrieve(repo, "export", filters={"flow_id": "does-not-exist"})
            self.assertEqual(payload["results"], [],
                             "an unknown flow must not degrade into 'no filter'")
            self.assertTrue(any("flow_id" in item for item in payload["warnings"]))

    def test_without_a_filter_results_are_not_restricted(self):
        from pfe import retrieval
        with tempfile.TemporaryDirectory() as tmp:
            repo, _graph = self._repo_with_flow(tmp)
            payload = retrieval.retrieve(repo, "export report excel", top_k=20)
            self.assertGreater(len(payload["results"]), 0)


class PrivacyPatternTests(unittest.TestCase):
    """T7: a workspace root leaks the runner's layout the same way /home does."""

    def test_workspace_style_roots_are_detected(self):
        from pfe import verify
        for sample in ("/workspace/proj/a.js", "/mnt/data/a", "/root/secret"):
            hits = [label for pattern, label in verify.ABSOLUTE_PATHS if pattern.search(sample)]
            self.assertTrue(hits, sample + " must be treated as an absolute path")

    def test_placeholders_are_not_flagged(self):
        from pfe import verify
        for sample in ("<repo>/a.js", "artifacts/flows/x", "/home/<user>/x"):
            hits = [label for pattern, label in verify.ABSOLUTE_PATHS if pattern.search(sample)]
            self.assertEqual(hits, [], sample + " is a documented placeholder")


class ArtifactPathPrivacyTests(unittest.TestCase):
    """T7 privacy: the model-facing impact result must not carry host paths.

    `record_flow` used to store the absolute artifact directory in the index, so
    one earlier flow run made every later `impact` reply leak the workstation
    layout (`/home/<user>/...`) through `stale_artifacts`.
    """

    def test_artifact_dir_is_stored_repository_relative(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp) / "repo")
            index.build_index(repo, mode="full")
            flow = {
                "flow_id": "privacy-check",
                "entry_node": "start",
                "nodes": [{"id": "start", "confidence": "verified"}],
                "meta": {"generated_at": "2026-01-01T00:00:00+00:00", "request": "privacy"},
            }
            index.record_flow(repo, flow, str(repo / "artifacts" / "flows" / "privacy-check"))
            payload = index.list_flows(repo, limit=5)
            stored = [row["artifact_dir"] for row in payload
                      if row["flow_id"] == "privacy-check"]
            self.assertEqual(stored, ["artifacts/flows/privacy-check"])

    def test_impact_never_returns_an_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp) / "repo")
            index.build_index(repo, mode="full")
            flow = {
                "flow_id": "privacy-check",
                "entry_node": "start",
                "nodes": [{"id": "start", "confidence": "verified"}],
                "meta": {"generated_at": "2026-01-01T00:00:00+00:00", "request": "privacy"},
            }
            index.record_flow(repo, flow, str(repo / "artifacts" / "flows" / "privacy-check"))
            from pfe import impact
            payload = impact.impact_analysis(repo, changed_files=["services/report_service.js"])
            blob = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn(str(repo), blob, "impact leaked the repository's absolute path")
            for item in payload["stale_artifacts"]:
                self.assertFalse(Path(item["artifact_dir"]).is_absolute(),
                                 "stale_artifacts.artifact_dir must be repository-relative")


if __name__ == "__main__":
    unittest.main()
