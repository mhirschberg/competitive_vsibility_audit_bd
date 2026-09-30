"""Search-engine selection is stateful but no longer notebook-global core logic."""

import unittest
from unittest import mock

from audit_core import serp_selection
from tests.test_google_ai_timeout_safety import definition


def search_result(engine, count):
    return {
        "engine": engine,
        "results": [
            {"domain": f"example-{index}.com", "rank": index + 1}
            for index in range(count)
        ],
    }


class Client:
    def __init__(self, google_count, bing_count):
        self.google_count = google_count
        self.bing_count = bing_count
        self.calls = []
        self.active_search_engine = None

    def markdown_serp(self, *, query, engine, num_results=20, language="en"):
        self.calls.append((query, engine, num_results))
        count = self.google_count if engine == "google" else self.bing_count
        return search_result(engine, count)

    def log(self, *_args):
        pass


class SerpSelectionTests(unittest.TestCase):
    def test_auto_falls_back_to_bing_and_reuses_health_check_result(self):
        client = Client(google_count=2, bing_count=1)
        state = {"engine": None, "status": "unavailable"}
        cache = {}
        with mock.patch.object(serp_selection.time, "sleep") as sleep:
            selected = serp_selection.choose_search_engine_core(
                client, "premium phone", cache=cache, state=state
            )
        self.assertEqual(selected, "bing")
        self.assertEqual(state, {"engine": "bing", "status": "available"})
        self.assertEqual(len(client.calls), 3)
        sleep.assert_called_once_with(5)
        first = serp_selection.search_serp_core(
            client, "premium phone", cache=cache
        )
        self.assertEqual(first["engine"], "bing")
        self.assertEqual(len(client.calls), 3)
        serp_selection.search_serp_core(client, "premium phone", cache=cache)
        self.assertEqual(len(client.calls), 4)

    def test_explicit_google_failure_does_not_silently_use_bing(self):
        client = Client(google_count=0, bing_count=1)
        state = {"engine": "bing", "status": "available"}
        with mock.patch.object(serp_selection.time, "sleep"):
            selected = serp_selection.choose_search_engine_core(
                client, "question", "google", cache={}, state=state
            )
        self.assertIsNone(selected)
        self.assertEqual(state, {"engine": None, "status": "unavailable"})
        self.assertEqual([engine for _, engine, _ in client.calls], ["google", "google"])

    def test_notebook_wrapper_synchronizes_legacy_globals(self):
        client = Client(google_count=5, bing_count=1)
        namespace = {
            "ACTIVE_SEARCH_ENGINE": None,
            "ACTIVE_SEARCH_STATUS": "unavailable",
            "MARKDOWN_SERP_CACHE": {},
            "choose_search_engine_core": serp_selection.choose_search_engine_core,
        }
        exec(definition("choose_markdown_search_engine", last=True), namespace)
        selected = namespace["choose_markdown_search_engine"](
            client, "premium phone", "auto"
        )
        self.assertEqual(selected, "google")
        self.assertEqual(namespace["ACTIVE_SEARCH_ENGINE"], "google")
        self.assertEqual(namespace["ACTIVE_SEARCH_STATUS"], "available")
        self.assertIn(("google", "premium phone"), namespace["MARKDOWN_SERP_CACHE"])


if __name__ == "__main__":
    unittest.main()
