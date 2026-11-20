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
