import unittest

from audit_core.text_cleaning import remove_ai_boilerplate


class RemoveAiBoilerplateTests(unittest.TestCase):
    def test_removes_interface_prompts_and_preserves_report(self):
        text = (
            "Here is the requested audit\n"
            "# Competitive Visibility Audit\n"
            "## Executive Summary\n"
            "Useful findings\n"
            "Sign up for free"
        )
        self.assertEqual(
            remove_ai_boilerplate(text),
            "# Competitive Visibility Audit\n"
            "## Executive Summary\n"
            "Useful findings",
        )

    def test_unwraps_single_markdown_bullet_and_setext_title(self):
        text = (
            "* Competitive Visibility Audit\n"
            "    ============================\n"
            "    Executive Summary\n"
            "    Findings"
        )
        self.assertEqual(
            remove_ai_boilerplate(text),
            "# Competitive Visibility Audit\nExecutive Summary\nFindings",
        )

    def test_empty_or_non_text_input_returns_empty_string(self):
        self.assertEqual(remove_ai_boilerplate(None), "")
        self.assertEqual(remove_ai_boilerplate("  \n "), "")


if __name__ == "__main__":
    unittest.main()
