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

    def test_package_version_matches_manifest(self):
        manifest = self.manifest()
        self.assertEqual(manifest["package_version"], self.package()["version"])
        self.assertIn(manifest["tarball"]["filename"],
                      "dsh-project-flow-explainer-" + manifest["package_version"] + ".tgz")

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
            self.assertGreaterEqual(session.get("entry_points") or 0, 1)
        self.assertIn(smoke["registry_runtime"], {"verified", "not_verified"})
        if smoke["registry_runtime"] == "verified":
            self.assertTrue(smoke.get("record"), "verified without a smoke record")
            self.assertTrue(smoke.get("checks"), "verified without per-check evidence")
            self.assertTrue(all(smoke["checks"].values()),
                            "registry_runtime=verified nhưng có check false")
            self.assertGreaterEqual(smoke.get("tool_count", 0), 7)
        final = (ROOT / "FINAL_REPORT.md").read_text(encoding="utf-8")
        self.assertIn("CHƯA CHẠY", final)
        self.assertIn("BLOCKED_UI_API_UNVERIFIED", final)


if __name__ == "__main__":
    unittest.main()
