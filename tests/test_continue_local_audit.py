"""Continuation restores the saved engine and audit options."""

import unittest

from scripts.continue_local_audit import restore_continuation_settings


class ContinueLocalAuditTests(unittest.TestCase):
    def test_saved_checkpoint_options_override_notebook_defaults(self):
        settings = restore_continuation_settings(
            {
                "include_copilot_visibility": True,
                "include_google_ai_mode": True,
                "include_chatgpt_visibility": False,
                "include_gemini_visibility": False,
            },
            {
                "include_copilot_visibility": False,
                "include_google_ai_mode": False,
                "include_chatgpt_visibility": True,
                "include_gemini_visibility": True,
                "country": "US",
            },
        )
        self.assertFalse(settings["include_copilot_visibility"])
        self.assertFalse(settings["include_google_ai_mode"])
        self.assertTrue(settings["include_chatgpt_visibility"])
        self.assertTrue(settings["include_gemini_visibility"])
        self.assertEqual(settings["country"], "US")

    def test_explicit_no_copilot_flag_can_only_disable(self):
        settings = restore_continuation_settings(
            {"include_copilot_visibility": True},
            {"include_copilot_visibility": True},
            no_copilot=True,
        )
        self.assertFalse(settings["include_copilot_visibility"])


if __name__ == "__main__":
    unittest.main()
