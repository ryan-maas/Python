"""Smoke tests for /api/version, /api/config, and static cache headers in app.py.
Uses Flask's test client against a temporary static folder. Run with:
  python3 -m unittest discover tests
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as kiosk


class VersionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.static = Path(self.tmp.name)
        (self.static / "app.js").write_text("console.log(1);")
        (self.static / "index.html").write_text("<!doctype html>")
        self.orig_static = kiosk.app.static_folder
        kiosk.app.static_folder = str(self.static)
        kiosk._version_cache.update(t=0.0, value=None)
        self.client = kiosk.app.test_client()

    def tearDown(self):
        kiosk.app.static_folder = self.orig_static
        self.tmp.cleanup()

    def version(self):
        return self.client.get("/api/version").get_json()["version"]

    def test_stable_across_calls(self):
        self.assertEqual(self.version(), self.version())

    def test_changes_when_static_file_changes(self):
        before = self.version()
        (self.static / "app.js").write_text("console.log(2);")
        kiosk._version_cache["t"] = 0.0  # skip the 5 second cache
        self.assertNotEqual(before, self.version())

    def test_cached_for_five_seconds(self):
        before = self.version()
        (self.static / "app.js").write_text("console.log(3);")
        self.assertEqual(before, self.version())

    def test_ignores_dotfiles(self):
        before = self.version()
        (self.static / ".DS_Store").write_bytes(b"\x00")
        kiosk._version_cache["t"] = 0.0
        self.assertEqual(before, self.version())

    def test_changes_with_process_start(self):
        before = self.version()
        kiosk._version_cache["t"] = 0.0
        with patch.object(kiosk, "_STARTED", "another process"):
            self.assertNotEqual(before, self.version())

    def test_no_cache_headers(self):
        self.assertEqual(self.client.get("/").headers.get("Cache-Control"), "no-cache")
        self.assertEqual(self.client.get("/app.js").headers.get("Cache-Control"), "no-cache")
        self.assertIsNone(self.client.get("/api/version").headers.get("Cache-Control"))

    def test_config_has_reload_and_airports(self):
        cfg = self.client.get("/api/config").get_json()
        self.assertIn("auto_reload", cfg)
        self.assertEqual(cfg["version_poll_seconds"], 30)
        self.assertEqual(cfg["airports"][0]["iata"], "AUS")


if __name__ == "__main__":
    unittest.main()
