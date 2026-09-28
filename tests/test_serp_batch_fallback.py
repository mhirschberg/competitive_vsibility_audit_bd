"""The search stage must never score a mixed or incomplete SERP sample."""

import ast
import asyncio
import json
import unittest
from pathlib import Path


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
            and "Google search batch was incomplete" in "".join(item["source"])
        )
        tree = ast.parse(cell)
        function = [
            item for item in tree.body
            if isinstance(item, ast.AsyncFunctionDef) and item.name == "run_serp_stage"
        ][-1]
        cls.stage_source = ast.get_source_segment(cell, function)

    def run_stage(self, *, bing_fails=False, requested_engine="auto", keywords=None):
        client = FakeClient()
        calls = []
        keywords = keywords or ["query 1", "query 2", "query 3"]

        async def keyword_task(keyword, semaphore, num_results, search_engine):
            calls.append((keyword, search_engine))
            succeeds = not (
                (search_engine == "google" and keyword == "query 2")
                or (search_engine == "bing" and bing_fails and keyword == "query 3")
            )
            return {
                "keyword": keyword,
                "engine": search_engine,
                "success": succeeds,
                "results": [{"domain": "example.com"}] if succeeds else [],
            }

        async def ai_question(question, question_index):
            return {"success": True, "citations": [], "answer": "ok"}

        namespace = {
            "asyncio": asyncio,
            "bd_client": client,
            "SEARCH_ENGINE": requested_engine,
            "ACTIVE_SEARCH_STATUS": "available",
            "ACTIVE_SEARCH_ENGINE": "google",
            "run_keyword_serp_task": keyword_task,
            "run_ai_mode_question": ai_question,
            "aggregate_competitor_domains": lambda **kwargs: [],
            "build_ai_mode_source_candidates": lambda **kwargs: [],
            "merge_discovery_candidates": lambda **kwargs: [],
            "model_to_dict": lambda item: item,
        }
        exec(self.stage_source, namespace)
        result = asyncio.run(namespace["run_serp_stage"](
            keywords, "example.com"
        ))
        return result, calls, client

    def test_auto_replaces_entire_failed_google_batch_with_bing(self):
        result, calls, client = self.run_stage()
        self.assertEqual(result["search_engine"], "bing")
        self.assertEqual(result["search_status"], "available")
        self.assertEqual(result["successful"], 3)
        self.assertEqual(result["failed"], 0)
        self.assertEqual({item["engine"] for item in result["keyword_results"]}, {"bing"})
        self.assertEqual(sum(engine == "bing" for _, engine in calls), 3)
        self.assertEqual(client.active_search_engine, "bing")

    def test_failed_first_wave_does_not_send_remaining_google_queries(self):
        result, calls, _ = self.run_stage(
            keywords=[f"query {index}" for index in range(1, 9)]
        )
        self.assertEqual(result["search_engine"], "bing")
        self.assertEqual(result["successful"], 8)
        self.assertEqual(sum(engine == "google" for _, engine in calls), 4)
        self.assertEqual(sum(engine == "bing" for _, engine in calls), 8)

    def test_failed_bing_fallback_discards_partial_search_evidence(self):
        result, _, client = self.run_stage(bing_fails=True)
        self.assertIsNone(result["search_engine"])
        self.assertEqual(result["search_status"], "unavailable")
        self.assertEqual(result["keyword_results"], [])
        self.assertEqual(result["successful"], 0)
        self.assertIsNone(client.active_search_engine)

    def test_explicit_google_does_not_switch_engines_or_score_partial_batch(self):
        result, calls, _ = self.run_stage(requested_engine="google")
        self.assertIsNone(result["search_engine"])
        self.assertEqual(result["search_status"], "unavailable")
        self.assertEqual(result["keyword_results"], [])
        self.assertFalse(any(engine == "bing" for _, engine in calls))


if __name__ == "__main__":
    unittest.main()
