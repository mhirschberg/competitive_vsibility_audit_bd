import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WebEmailOptInTests(unittest.TestCase):
    def test_email_switch_is_hidden_until_server_capability_and_google_login(self):
        html = (ROOT / "web/index.html").read_text(encoding="utf-8")
        js = (ROOT / "web/src/main.js").read_text(encoding="utf-8")
        self.assertIn('id="email-option" class="social-option" hidden', html)
        self.assertIn('name="email_when_ready" type="checkbox"', html)
        self.assertIn('fetch(`${config.api_url}/notification-capabilities`', js)
        self.assertIn('emailNotificationsEnabled && trialSession?.user?.email', js)
        self.assertIn('email_when_ready: !emailOption.hidden && data.get("email_when_ready") === "on"', js)


if __name__ == "__main__":
    unittest.main()
