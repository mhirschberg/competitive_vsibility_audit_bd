import json
import re
import unittest

from app import _build_config_cell


class WebRedditToggleTests(unittest.TestCase):
    def _web_config(self, include_reddit_analysis):
        source = _build_config_cell(
            "Acme",
            "example.com",
            "widgets",
            "US",
            "auto",
            include_reddit_analysis,
            False,
        )
        match = re.search(r"_WEB_CONFIG = json.loads\((.+)\)", source)
        self.assertIsNotNone(match)
        payload = json.loads(json.loads(match.group(1)))
        return source, payload

    def test_reddit_analysis_defaults_can_be_passed_as_disabled(self):
        source, payload = self._web_config(False)

        self.assertFalse(payload["include_reddit_analysis"])
        self.assertIn(
            '"include_reddit_analysis": INCLUDE_REDDIT_ANALYSIS',
            source,
        )

    def test_reddit_analysis_can_be_enabled(self):
        _, payload = self._web_config(True)

        self.assertTrue(payload["include_reddit_analysis"])

    def test_comment_collection_defaults_off_and_can_be_selected(self):
        _, payload = self._web_config(True)
        self.assertEqual(payload["reddit_comment_posts_per_cohort"], 0)
        source = _build_config_cell(
            "Acme", "example.com", "widgets", "US", "auto", True, False,
            reddit_comment_posts_per_cohort=2,
        )
        self.assertIn('os.environ["REDDIT_COMMENT_POSTS_PER_COHORT"] = str(', source)
        match = re.search(r"_WEB_CONFIG = json.loads\((.+)\)", source)
        selected = json.loads(json.loads(match.group(1)))
        self.assertEqual(selected["reddit_comment_posts_per_cohort"], 2)

    def test_comment_collection_rejects_out_of_range_value(self):
        with self.assertRaises(ValueError):
            _build_config_cell(
                "Acme", "example.com", "widgets", "US", "auto", True, False,
                reddit_comment_posts_per_cohort=11,
            )


if __name__ == "__main__":
    unittest.main()
