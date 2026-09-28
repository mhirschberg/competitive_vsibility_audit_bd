import re
import unittest
from pathlib import Path

from app import _build_runner_script


ROOT = Path(__file__).resolve().parents[1]


class WebLongWaitTests(unittest.TestCase):
    def test_checkbox_is_sent_with_audit_request(self):
        html = (ROOT / "web/index.html").read_text(encoding="utf-8")
        js = (ROOT / "web/src/main.js").read_text(encoding="utf-8")
        self.assertIn('name="wait_longer_for_google_ai_mode" type="checkbox"', html)
        self.assertIn('wait_longer_for_google_ai_mode: data.get("wait_longer_for_google_ai_mode") === "on"', js)

    def test_only_extended_runner_changes_google_ai_timeout(self):
        args = ("Acme", "example.com", "widgets", "US", "auto", False, False)
        standard = _build_runner_script(*args)
        extended = _build_runner_script(*args, True)
        self.assertIn("timeout_seconds=720", standard)
        self.assertIn("timeout_seconds=1800", extended)
        self.assertNotIn("timeout_seconds=720", extended)
        self.assertTrue(re.search(r"bd_client\.google_ai_mode,\s*\n\s*prompt,\s*\n\s*720,", standard))
        self.assertFalse(re.search(r"bd_client\.google_ai_mode,\s*\n\s*prompt,\s*\n\s*720,", extended))
        self.assertIn("'up to 30 minutes'", extended)
        compile(extended, "<extended-runner>", "exec")


if __name__ == "__main__":
    unittest.main()
