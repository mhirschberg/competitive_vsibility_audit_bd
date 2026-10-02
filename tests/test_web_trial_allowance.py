import unittest
from pathlib import Path


class WebTrialAllowanceTests(unittest.TestCase):
    def test_signed_in_copy_uses_server_quota_and_cooldown(self):
        source = (
            Path(__file__).resolve().parents[1] / "web" / "src" / "main.js"
        ).read_text(encoding="utf-8")
        self.assertIn("of ${trialStatus.limit} audits left.", source)
        self.assertIn("Your ${trialStatus.limit} personal trial audits are used.", source)
        self.assertIn('cooldown === 0 ? "No daily cooldown."', source)
        self.assertNotIn("of 3 audits left.", source)


if __name__ == "__main__":
    unittest.main()
