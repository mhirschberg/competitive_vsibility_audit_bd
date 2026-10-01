"""Search keeps partial evidence from one engine without hiding missing queries."""

import ast
import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from audit_core.search_discovery import run_search_discovery_core


NOTEBOOK = Path(__file__).resolve().parents[1] / "competitive_visibility_audit_bd.ipynb"


class FakeClient:
    debug = False
    active_search_engine = "google"

    def __init__(self):
        self.messages = []

    def choose_search_engine(self, test_query, requested_engine):
        return "google"

    def log(self, message, *_args):
        self.messages.append(message)


class SerpBatchFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        cell = next(
            "".join(item["source"])
            for item in notebook["cells"]
            if item["cell_type"] == "code"
            and "Google search coverage is low" in "".join(item["source"])
        )
        tree = ast.parse(cell)
        function = [
            item for item in tree.body
            if isinstance(item, ast.AsyncFunctionDef) and item.name == "run_serp_stage"
        ][-1]
        cls.stage_source = ast.get_source_segment(cell, function)

    def run_stage(self, *, google_fails=("query 2",), bing_fails=False,
                  bing_probe_fails=False,
                  requested_engine="auto", keywords=None,
                  google_ai_fails=False, include_google_ai_mode=True):
        client = FakeClient()
        client.ai_questions = []
        calls = []
        keywords = keywords or ["query 1", "query 2", "query 3"]

        async def keyword_task(keyword, semaphore, num_results, search_engine):
            calls.append((keyword, search_engine))
            succeeds = not (
                (search_engine == "google" and keyword in google_fails)
                or (search_engine == "bing" and bing_fails and keyword == "query 3")
                or (search_engine == "bing" and bing_probe_fails and keyword == "query 1")
            )
            return {
                "keyword": keyword,
                "engine": search_engine,
                "success": succeeds,
                "results": [{"domain": "example.com"}] if succeeds else [],
            }

        async def ai_question(question, question_index, **_kwargs):
            client.ai_questions.append(question_index)
            return {
                "question": question,
                "success": not google_ai_fails,
                "citations": [],
                "answer": "ok" if not google_ai_fails else "",
            }

        namespace = {
            "asyncio": asyncio,
            "bd_client": client,
            "SEARCH_ENGINE": requested_engine,
            "AUDIT_SETTINGS": {"include_google_ai_mode": include_google_ai_mode},
            "ACTIVE_SEARCH_STATUS": "available",
            "ACTIVE_SEARCH_ENGINE": "google",
            "run_keyword_serp_task": keyword_task,
            "run_ai_mode_question": ai_question,
            "CompetitorCandidate": lambda **kwargs: kwargs,
            "model_to_dict": lambda item: item,
            "run_search_discovery_core": run_search_discovery_core,
        }
        exec(self.stage_source, namespace)
        with patch(
            "audit_core.search_discovery.get_root_domain",
            side_effect=lambda domain: str(domain).removeprefix("www."),
        ):
            result = asyncio.run(namespace["run_serp_stage"](
                keywords, "example.com"
            ))
        return result, calls, client

    def test_one_google_failure_preserves_seven_of_eight_without_bing_spend(self):
        result, calls, client = self.run_stage(
            keywords=[f"query {index}" for index in range(1, 9)]
        )
        self.assertEqual(result["search_engine"], "google")
        self.assertEqual(result["search_status"], "partial")
        self.assertEqual(result["successful"], 7)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(len(result["keyword_results"]), 8)
        self.assertFalse(any(engine == "bing" for _, engine in calls))
        self.assertEqual(client.active_search_engine, "google")

    def test_low_google_coverage_replaces_batch_with_bing(self):
        result, calls, client = self.run_stage(google_fails=("query 2", "query 3"))
        self.assertEqual(result["search_engine"], "bing")
        self.assertEqual(result["search_status"], "available")
        self.assertEqual(result["successful"], 3)
        self.assertEqual(result["failed"], 0)
        self.assertEqual({item["engine"] for item in result["keyword_results"]}, {"bing"})
        self.assertEqual(sum(engine == "bing" for _, engine in calls), 3)
        self.assertEqual(client.active_search_engine, "bing")

    def test_failed_google_health_check_skips_remaining_paid_questions(self):
        result, _calls, client = self.run_stage(google_ai_fails=True)
        self.assertEqual(client.ai_questions, [1])
        self.assertEqual(result["ai_mode_successful"], 0)
        self.assertEqual(result["ai_mode_failed"], 3)
        self.assertEqual(len(result["ai_mode_discovery"]["results"]), 3)

    def test_disabled_google_ai_mode_starts_no_measured_snapshots(self):
        result, calls, client = self.run_stage(include_google_ai_mode=False)
        self.assertEqual(client.ai_questions, [])
        self.assertEqual(result["ai_mode_discovery"]["results"], [])
        self.assertEqual(result["ai_mode_failed"], 0)
        self.assertTrue(calls)  # Traditional search still runs.

    def test_entire_failed_first_wave_does_not_send_remaining_google_queries(self):
        result, calls, _ = self.run_stage(
            google_fails=("query 1", "query 2", "query 3", "query 4"),
            keywords=[f"query {index}" for index in range(1, 9)]
        )
        self.assertEqual(result["search_engine"], "bing")
        self.assertEqual(result["successful"], 8)
        self.assertEqual(sum(engine == "google" for _, engine in calls), 4)
        self.assertEqual(sum(engine == "bing" for _, engine in calls), 8)

    def test_failed_bing_fallback_keeps_partial_bing_evidence(self):
        result, _, client = self.run_stage(
            google_fails=("query 2", "query 3"), bing_fails=True
        )
        self.assertEqual(result["search_engine"], "bing")
        self.assertEqual(result["search_status"], "partial")
        self.assertEqual(result["successful"], 2)
        self.assertEqual(result["failed"], 1)
        self.assertEqual({item["engine"] for item in result["keyword_results"]}, {"bing"})
        self.assertEqual(client.active_search_engine, "bing")

    def test_explicit_google_keeps_partial_google_evidence(self):
        result, calls, _ = self.run_stage(requested_engine="google")
        self.assertEqual(result["search_engine"], "google")
        self.assertEqual(result["search_status"], "partial")
        self.assertEqual(result["successful"], 2)
        self.assertEqual(result["failed"], 1)
        self.assertFalse(any(engine == "bing" for _, engine in calls))

    def test_failed_bing_probe_keeps_google_partial_evidence(self):
        result, calls, _ = self.run_stage(
            google_fails=("query 2", "query 3"),
            bing_probe_fails=True,
            keywords=["query 1", "query 2", "query 3", "query 4"],
        )
        self.assertEqual(result["search_engine"], "google")
        self.assertEqual(result["search_status"], "partial")
        self.assertEqual(result["successful"], 2)
        self.assertEqual(result["failed"], 2)
        self.assertEqual({item["engine"] for item in result["keyword_results"]}, {"google"})
        self.assertEqual(sum(engine == "google" for _, engine in calls), 4)


if __name__ == "__main__":
    unittest.main()
