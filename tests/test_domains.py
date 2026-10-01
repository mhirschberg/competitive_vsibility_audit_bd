"""Public URL normalization shared between hosted and notebook runners."""

import unittest

from audit_core.domains import (
    extract_visible_url, get_hostname, is_google_goto_url,
    normalize_public_url,
)


class DomainNormalizationTests(unittest.TestCase):
    def test_extracts_markdown_link_target_and_strips_trailing_punctuation(self):
        value = "Official site: [Rayner](https://www.rayner.com/products)."
        self.assertEqual(
            extract_visible_url(value), "https://www.rayner.com/products"
        )
        self.assertEqual(
            normalize_public_url(value), "https://www.rayner.com/products"
        )

    def test_normalizes_bare_host_and_drops_query_fragment(self):
        self.assertEqual(
            normalize_public_url("www.example.com/catalog?source=ad#top"),
            "https://www.example.com/catalog",
        )
        self.assertEqual(get_hostname("https://www.example.com/catalog"), "example.com")

    def test_empty_values_remain_empty(self):
        self.assertEqual(normalize_public_url("  "), "")
        self.assertEqual(get_hostname(None), "")

    def test_identifies_only_google_goto_redirect_urls(self):
        self.assertTrue(is_google_goto_url("https://www.google.com/goto?url=abc"))
        self.assertTrue(is_google_goto_url("https://google.com/goto/opaque"))
        self.assertFalse(is_google_goto_url("https://google.com/search?q=topic"))
        self.assertFalse(is_google_goto_url("https://google.co.uk/goto?url=abc"))
        self.assertFalse(is_google_goto_url("not a url"))


if __name__ == "__main__":
    unittest.main()
