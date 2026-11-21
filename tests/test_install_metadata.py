"""The bundle must stay installable from its own manifest."""

import json
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "dsh-plugin" / "package.json"


class InstallMetadataTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(PACKAGE.read_text(encoding="utf-8"))

    def test_install_block_points_at_a_stable_tarball(self):
        install = (self.manifest.get("dsh") or {}).get("install") or {}
        self.assertEqual(install.get("preferred"), "tarball")
        self.assertTrue(install.get("tarball", "").endswith(".tgz"),
                        "tarball URL must end in .tgz")
        self.assertIn("/releases/latest/download/", install.get("tarball", ""),
                      "a versioned asset URL breaks after the next release")
        self.assertTrue(install.get("git", "").startswith("https://github.com/"))

    def test_bundle_and_client_declarations_survive(self):
        dsh = self.manifest["dsh"]
        self.assertEqual(dsh["bundle"]["patch"], "./cordis.patch.yml")
        self.assertEqual(dsh["client"]["platform"], "web")
        self.assertIn("client.js", self.manifest["files"])
        self.assertIn("cordis.patch.yml", self.manifest["files"])


if __name__ == "__main__":
    unittest.main()
