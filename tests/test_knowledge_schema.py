"""Keep the JSON schema and the Python ontology from drifting apart.

Run: python -m unittest discover -s tests -v
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pfe import ontology  # noqa: E402

SCHEMA = ROOT / "references" / "code-knowledge-schema.json"


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    def test_entity_kinds_match(self):
        declared = set(self.schema["$defs"]["entityKind"]["enum"])
        self.assertEqual(declared, ontology.ENTITY_TYPES)

    def test_confidence_levels_match(self):
        declared = set(self.schema["$defs"]["confidence"]["enum"])
        self.assertEqual(declared, ontology.CONFIDENCE)

    def test_predicates_match(self):
        declared = set(self.schema["$defs"]["fact"]["properties"]["predicate"]["enum"])
        self.assertEqual(declared, set(ontology.RELATIONS))

    def test_relation_signatures_match(self):
        for predicate, signature in self.schema["x-relations"].items():
            subject, object_ = ontology.RELATIONS[predicate]
            self.assertEqual(set(signature["subject"]), subject, predicate)
            self.assertEqual(set(signature["object"]), object_, predicate)

    def test_declared_only_relations_match(self):
        for predicate, reason in ontology.NOT_EMITTED.items():
            self.assertFalse(self.schema["x-relations"][predicate]["emitted"], predicate)
            self.assertTrue(reason)

    def test_emitted_relations_are_a_subset_of_vocabulary(self):
        self.assertTrue(set(ontology.EMITTED_RELATIONS).issubset(set(ontology.RELATIONS)))
        self.assertNotIn("returns", ontology.EMITTED_RELATIONS)


class EvidenceConsistencyTests(unittest.TestCase):
    """Docs must agree with the machine-readable manifest, not with memory."""

    def manifest(self):
        path = ROOT / "artifacts" / "review" / "evidence-manifest.json"
        if not path.exists():
            self.skipTest("chưa có evidence-manifest.json (chạy scripts/regen_evidence.py)")
        return json.loads(path.read_text(encoding="utf-8"))

    def package(self):
        return json.loads((ROOT / "dsh-plugin" / "package.json").read_text(encoding="utf-8"))

    def test_release_evidence_is_attributed_to_its_own_version(self):
        manifest = self.manifest()
        recorded = manifest["package_version"]
        version = self.package()["version"]
        if version != recorded:
            # A newer version may keep a historical record, but the README
            # must attribute that record to the version that was actually tested.
            def release_key(value):
                base, separator, _ = value.partition("-")
                return (*map(int, base.split(".")), not separator)

            self.assertGreater(release_key(version), release_key(recorded))
            readme = (ROOT / "README.md").read_text(encoding="utf-8")
            self.assertIn(
                f"[Bản ghi phát hành {recorded}](artifacts/review/evidence-manifest.json)", readme)
        self.assertEqual(manifest["tarball"]["filename"],
                         "dsh-project-flow-explainer-" + recorded + ".tgz")

    def test_engines_dsh_matches_manifest(self):
        manifest = self.manifest()
        self.assertEqual(manifest["engines_dsh"], self.package()["engines"]["dsh"])

    def test_reports_quote_the_manifest_tarball_hash(self):
        manifest = self.manifest()
        digest = manifest["tarball"]["sha256"]
        for name in ("TEST_REPORT.md", "FINAL_REPORT.md", "REVIEW_PACKET.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn(digest[:8], text.replace("…", "").replace(" ", ""),
                          name + " không nhắc tới sha256 của tarball")

    def test_reports_quote_the_manifest_test_counts(self):
        manifest = self.manifest()
        total = (manifest["tests"]["python"] + manifest["tests"]["adapter"]
                 + manifest["tests"]["knowledge_tools"] + manifest["tests"]["pack"])
        self.assertGreater(total, 0)
        for name in ("README.md", "FINAL_REPORT.md", "REVIEW_PACKET.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn(str(manifest["tests"]["python"]), text,
                          name + " không khớp số test Python trong manifest")

    def test_smoke_claims_match_recorded_evidence(self):
        manifest = self.manifest()
        smoke = manifest["smoke"]
        # Model-driven selection is claimed only with a recorded session.
        self.assertIn(smoke["model_driven"], {"verified", "not_verified"})
        if smoke["model_driven"] == "verified":
            session = smoke.get("model_session") or {}
            self.assertTrue(session.get("record"), "verified without a session record")
            self.assertTrue(session.get("tools"), "verified without a tool sequence")
            # Attribution: a verified claim must name the build it observed.
            self.assertEqual(session.get("package_version"), manifest["package_version"],
                             "model session ran on a different package version")
            self.assertEqual(session.get("installed_version"), manifest["package_version"],
                             "the profile had a different build installed than the manifest")
            self.assertEqual(session.get("session_sha256") and True, True,
                             "verified without a session hash")
            # The claim is about behaviour, so it must be backed by the checks.
            order = session.get("order") or {}
            self.assertEqual(order.get("missing"), [], "verified with expected tools missing")
            self.assertTrue(order.get("ordered"), "verified with the workflow out of order")
            self.assertEqual((session.get("policy") or {}).get("tool_errors"), [],
                             "verified while a tool returned an error")
        self.assertIn(smoke["registry_runtime"], {"verified", "not_verified"})
        if smoke["registry_runtime"] == "verified":
            self.assertTrue(smoke.get("record"), "verified without a smoke record")
            # The named record must be for THIS release: a record carried over
            # from an earlier version is not evidence for this one.
            record = (ROOT / "artifacts" / "review" / smoke["record"])
            self.assertTrue(record.is_file(), "smoke record file is missing")
            payload = json.loads(record.read_text(encoding="utf-8"))
            self.assertEqual(payload.get("package_version"), manifest["package_version"],
                             "smoke record was recorded for a different package version")
            self.assertEqual(payload.get("tarball_sha256"), manifest["tarball"]["sha256"],
                             "smoke record was recorded against a different tarball")
            self.assertTrue(smoke.get("checks"), "verified without per-check evidence")
            self.assertTrue(all(smoke["checks"].values()),
                            "registry_runtime=verified nhưng có check false")
            self.assertGreaterEqual(smoke.get("tool_count", 0), 7)
        final = (ROOT / "FINAL_REPORT.md").read_text(encoding="utf-8")
        self.assertIn("CHƯA CHẠY", final)
        self.assertIn("BLOCKED_UI_API_UNVERIFIED", final)


if __name__ == "__main__":
    unittest.main()
