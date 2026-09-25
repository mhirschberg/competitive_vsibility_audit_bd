"""Focused regression checks for the notebook's live SERP transport."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.parse import quote_plus, urlparse

import requests


NOTEBOOK = Path(__file__).resolve().parents[1] / "competitive_visibility_audit_bd.ipynb"


class BrightDataAPIError(Exception):
    pass


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
        normalize_start = runtime.index("def find_parsed_organic_results(")
        normalize_end = runtime.index("def reliable_bing_serp(", normalize_start)
        exec(runtime[normalize_start:normalize_end], namespace)
        request_start = runtime.index("def resilient_serp_request(")
        request_end = runtime.index("def search_result_quality(", request_start)
        exec(runtime[request_start:request_end], namespace)
        cls.search = staticmethod(namespace["resilient_serp_request"])

    def test_retries_empty_http_200_and_preserves_direct_links_and_rank(self):
        client = FakeClient()
        records = {"organic": [
            {"link": "https://example.com/a", "title": "A", "global_rank": 3},
            {"link": "https://example.org/b", "title": "B", "global_rank": 4},
        ]}
        with mock.patch.object(
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
        with mock.patch.object(
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


if __name__ == "__main__":
    unittest.main()
