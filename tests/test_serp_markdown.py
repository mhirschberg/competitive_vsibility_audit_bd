"""Strict and fallback Markdown parsing is shared by service and notebook."""

import base64
import json
from pathlib import Path
import unittest
from urllib.parse import urlparse, urlunparse

from audit_core.serp_markdown import SerpMarkdownParser, SerpParserPorts
from audit_core.brightdata_transport import BrightDataAPIError
from notebook_builder import (
    SERP_MARKDOWN_END, SERP_MARKDOWN_SOURCE, SERP_MARKDOWN_START,
    _without_service_imports,
)
from tests.test_google_ai_timeout_safety import definition


NOTEBOOK = Path(__file__).resolve().parents[1] / "competitive_visibility_audit_bd.ipynb"


def domain(value):
    return (urlparse(value).hostname or "").removeprefix("www.")


def canonical(value):
    parsed = urlparse(value)
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", "", ""))


def parser(diagnostics=None, resolver=None):
    return SerpMarkdownParser(SerpParserPorts(
        get_hostname=domain,
        get_root_domain=domain,
        canonical_source_url=canonical,
        is_google_goto_url=lambda value: "/goto?" in value,
        resolve_google_goto_url=resolver or (lambda _value: ""),
        diagnostics=diagnostics if diagnostics is not None else {},
    ))


class SerpMarkdownTests(unittest.TestCase):
    def test_google_strict_organic_results_skip_rich_module(self):
        markdown = (
            "# Search Results\n"
            "## Web results\n"
            "### Example guide\n"
            "https://example.com/guide\n"
            "A substantial explanation of the product category and its uses.\n"
            "## Videos\n"
            "### Video result\n"
            "https://video.example/watch\n"
        )
        result = parser().parse_google_markdown(markdown, "buyer question")
        self.assertEqual(result["parser"], "strict_google")
        self.assertEqual([item["domain"] for item in result["results"]], [
            "example.com"
        ])
        self.assertEqual(result["results"][0]["rank"], 1)

    def test_google_fallback_decodes_direct_destination_and_records_diagnostics(self):
        for redirect in (
            "/url?q=https%3A%2F%2Fexample.org%2Fguide",
            "https://www.google.com/url?q=https%3A%2F%2Fexample.org%2Fguide",
        ):
            with self.subTest(redirect=redirect):
                diagnostics = {}
                markdown = (
                    f"## [Useful buying guide]({redirect})\n"
                    "A long, useful description of the different available options.\n"
                )
                result = parser(diagnostics).parse_google_markdown(
                    markdown, "buyer question"
                )
                self.assertEqual(result["parser"], "generic_markdown")
                self.assertEqual(
                    result["results"][0]["url"], "https://example.org/guide"
                )
                self.assertEqual(diagnostics["google"]["usable_results"], 1)
                self.assertIn("Search Results marker", result["strict_parser_error"])

    def test_google_nearby_url_avoids_goto_resolution(self):
        def forbidden(_value):
            raise AssertionError("No redirect request should be needed")
        markdown = (
            "## [Useful guide](https://www.google.com/goto?url=expired)\n"
            "https://example.com/guide\n"
        )
        result = parser(resolver=forbidden).parse_google_markdown(markdown, "guide")
        self.assertEqual(result["results"][0]["url"], "https://example.com/guide")

    def test_bing_strict_decodes_tracking_url_and_ignores_navigation(self):
        destination = "https://review.example/phone"
        encoded = base64.urlsafe_b64encode(destination.encode()).decode().rstrip("=")
        markdown = (
            "1. Organic\n"
            f"    ## [Phone review](https://www.bing.com/ck/a?u=a1{encoded})\n"
            "A useful comparison of premium phones for buyers.\n"
            "2. Navigation\n"
            "    ## [More results from this site]"
            "(https://www.bing.com/ck/a?u=a1ignore)\n"
        )
        result = parser().parse_bing_markdown(markdown, "premium phone")
        self.assertEqual(result["parser"], "strict_bing")
        self.assertEqual([item["url"] for item in result["results"]], [destination])

    def test_bing_does_not_promote_unverified_generic_links(self):
        result = parser().parse_bing_markdown(
            "## [Random page](https://example.com/page)\n", "buyer question"
        )
        self.assertEqual(result["parser"], "strict_bing")
        self.assertEqual(result["results"], [])

    def test_notebook_adapter_uses_exact_embedded_parser(self):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        cell = next(
            cell for cell in notebook["cells"]
            if cell.get("metadata", {}).get("id") == "final-core"
        )
        source = "".join(cell["source"])
        embedded = source.split(SERP_MARKDOWN_START, 1)[1].split(
            SERP_MARKDOWN_END, 1
        )[0].strip()
        self.assertEqual(
            embedded,
            _without_service_imports(SERP_MARKDOWN_SOURCE.read_text()).strip(),
        )
        diagnostics = {}
        namespace = {
            "BrightDataAPIError": BrightDataAPIError,
            "get_hostname": domain,
            "get_root_domain": domain,
            "canonical_source_url": canonical,
            "is_google_goto_url": lambda _value: False,
            "resolve_google_goto_url": lambda _value: "",
            "LAST_SERP_PARSER_DIAGNOSTICS": diagnostics,
        }
        exec(embedded, namespace)
        exec(definition("_markdown_parser"), namespace)
        exec(definition("parse_google_markdown", last=True), namespace)
        markdown = "## [Buying guide](https://example.com/review)\n"
        bundled = namespace["parse_google_markdown"](markdown, "buyer question")
        service = parser().parse_google_markdown(markdown, "buyer question")
        self.assertEqual(bundled, service)
        self.assertIsNotNone(diagnostics.get("google"))


if __name__ == "__main__":
    unittest.main()
