"""Focused regression checks for the notebook's live SERP transport."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.parse import quote_plus, urlparse

import requests

from audit_core import serp_parsing, serp_transport
from audit_core.serp_markdown import SerpMarkdownParser, SerpParserPorts
from audit_core.brightdata_transport import BrightDataAPIError

NOTEBOOK = Path(__file__).resolve().parents[1] / "competitive_visibility_audit_bd.ipynb"


class FakeClient:
    country = "US"
    serp_zone = "test-zone"
    headers = {"Authorization": "Bearer test"}
    debug = False

    def __init__(self):
        self.events = []

    def start_usage_operation(self, name, input_count):
        self.events.append({"name": name, "status": "started"})
        return len(self.events) - 1

    def update_usage_operation(self, operation_id, status, result_count=None):
        self.events[operation_id].update(status=status, result_count=result_count)

    def log(self, *_args):
        pass


def fake_response(value, headers=None):
    text = "" if value is None else json.dumps(value)
    return SimpleNamespace(
        ok=True, status_code=200, text=text, headers=headers or {}
    )


class SerpTransportTests(unittest.TestCase):
    @staticmethod
    def strict_bing_parser(decode):
        parser = SerpMarkdownParser(SerpParserPorts(
            get_hostname=lambda value: urlparse(value).hostname or "",
            get_root_domain=lambda value: (
                urlparse(value).hostname or ""
            ).removeprefix("www."),
            canonical_source_url=lambda value: value,
            is_google_goto_url=lambda _value: False,
            resolve_google_goto_url=lambda _value: "",
            diagnostics={},
        ))
        parser.decode_bing_redirect = decode
        return parser

    @classmethod
    def setUpClass(cls):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        runtime = "".join(notebook["cells"][3]["source"])

        def decode(response, context):
            if not response.text.strip():
                raise BrightDataAPIError(f"{context} returned an empty response")
            return json.loads(response.text)

        namespace = {
            "BD_REQUEST_URL": "https://example.test/request",
            "BrightDataAPIError": BrightDataAPIError,
            "decode_bright_data_response": decode,
            "get_root_domain": lambda value: (
                urlparse(value).hostname or ""
            ).removeprefix("www."),
            "quote_plus": quote_plus,
            "requests": requests,
            "core_find_parsed_organic_results": (
                serp_parsing.core_find_parsed_organic_results
            ),
            "normalize_parsed_serp_records": (
                serp_parsing.normalize_parsed_serp_records
            ),
            "time": SimpleNamespace(sleep=mock.Mock()),
            "parse_bing_markdown": lambda markdown, query, num_results, requested_country: {
                "engine": "bing",
                "query": query,
                "results": [{
                    "rank": 1,
                    "url": "https://example.com/bing-result",
                    "domain": "example.com",
                    "title": "Bing result",
                }],
                "raw_result_count": 1,
            },
        }
        normalize_end = runtime.index("def reliable_bing_serp(")
        normalize_start = runtime.rindex(
            "def find_parsed_organic_results(", 0, normalize_end
        )
        exec(runtime[normalize_start:normalize_end], namespace)
        cls.search = staticmethod(
            lambda client, query, engine: serp_transport.run_resilient_serp_request(
                client, query, engine,
                normalize_serp_records=namespace["normalize_serp_records"],
                parse_bing_markdown=namespace["parse_bing_markdown"],
            )
        )

    def test_retries_empty_http_200_and_preserves_direct_links_and_rank(self):
        client = FakeClient()
        records = {"organic": [
            {"link": "https://example.com/a", "title": "A", "global_rank": 3},
            {"link": "https://example.org/b", "title": "B", "global_rank": 4},
        ]}
        with mock.patch.object(serp_transport.time, "sleep"), mock.patch.object(
            requests, "post", side_effect=[fake_response(None), fake_response(records)]
        ) as post:
            result = self.search(client, "website builders", "google")

        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args.kwargs["json"]["data_format"], "parsed_light")
        self.assertEqual(result["parser"], "parsed_light")
        self.assertEqual([item["url"] for item in result["results"]], [
            "https://example.com/a", "https://example.org/b"
        ])
        self.assertEqual(result["results"][0]["rank"], 3)
        self.assertEqual([event["status"] for event in client.events], [
            "failed", "success"
        ])

    def test_three_empty_http_200_responses_raise_instead_of_returning_zero(self):
        client = FakeClient()
        with mock.patch.object(serp_transport.time, "sleep"), mock.patch.object(
            requests,
            "post",
            return_value=fake_response(
                None,
                {"x-brd-error-code": "captcha", "x-brd-error": "redirect location was rejected"},
            ),
        ) as post:
            with self.assertRaisesRegex(BrightDataAPIError, "captcha"):
                self.search(client, "website builders", "google")

        self.assertEqual(post.call_count, 3)
        self.assertEqual([event["status"] for event in client.events], [
            "failed", "failed", "failed"
        ])

    def test_google_selector_timeout_is_not_repeated_three_times(self):
        client = FakeClient()
        selector_error = fake_response(
            None,
            {
                "x-brd-error-code": "expect_element",
                "x-brd-error": 'waiting for selector "#main" failed: timeout 30000ms exceeded',
            },
        )
        with mock.patch.object(requests, "post", return_value=selector_error) as post:
            with self.assertRaises(BrightDataAPIError) as raised:
                self.search(client, "website builders", "google")

        self.assertEqual(post.call_count, 1)
        self.assertTrue(raised.exception.selector_timeout)
        self.assertEqual([event["status"] for event in client.events], ["failed"])

    def test_bing_uses_raw_markdown_when_parsed_light_is_unsupported(self):
        client = FakeClient()
        response = SimpleNamespace(
            ok=True,
            status_code=200,
            text="Bing organic Markdown",
            headers={},
        )
        with mock.patch.object(requests, "post", return_value=response) as post:
            result = self.search(client, "website builders", "bing")

        self.assertNotIn("data_format", post.call_args.kwargs["json"])
        self.assertEqual(result["results"][0]["url"], "https://example.com/bing-result")
        self.assertEqual(result["parser"], "bing_markdown")

    def test_indented_bing_organic_headings_ignore_navigation_links(self):
        parser = self.strict_bing_parser(
            lambda _url: "https://phone.example/review"
        )
        markdown = (
            "1. navigation\n"
            "    ## [More results from this site]"
            "(https://www.bing.com/ck/a?u=a1ignore)\n"
            "2. organic\n"
            "    ## [Best flagship phones]"
            "(https://www.bing.com/ck/a?u=a1valid)\n"
        )

        result = parser.strict_parse_bing_markdown(markdown, "flagship phones")

        self.assertEqual([item["title"] for item in result["results"]], [
            "Best flagship phones"
        ])
        self.assertEqual(result["results"][0]["rank"], 1)

    def test_bing_headings_survive_broken_numbering_and_skip_ads(self):
        parser = self.strict_bing_parser(
            lambda url: (
                "https://ad.example/sale" if "/aclk?" in url else
                "https://review.example/phone" if "review" in url else
                "https://guide.example/phone"
            )
        )
        markdown = (
            "1.  [\n" + "\n" * 12 +
            "    ## [Phone review](https://www.bing.com/ck/a?u=review)\n"
            "    Useful comparison.\n"
            "2.  [\n" + "\n" * 12 +
            "    ## [Phone guide](https://www.bing.com/ck/a?u=guide)\n"
            "3.  [\n"
            "    ## [Sponsored phone](https://www.bing.com/aclk?u=ad)\n"
            "4.  [\n"
            "    ## [More results from this site](https://www.bing.com/ck/a?u=nav)\n"
        )

        result = parser.strict_parse_bing_markdown(markdown, "premium phone")

        self.assertEqual([item["title"] for item in result["results"]], [
            "Phone review", "Phone guide"
        ])


if __name__ == "__main__":
    unittest.main()
