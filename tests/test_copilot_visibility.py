"""Copilot is an optional measured answer, never a zero on scraper failure."""

import ast
import asyncio
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import time
import unittest
from unittest import mock
from urllib.parse import urlparse, urlunparse

from audit_core.brightdata_usage import BrightDataUsageLedger
from audit_core import ai_localization, ai_visibility_race

NOTEBOOK = Path(__file__).resolve().parents[1] / "competitive_visibility_audit_bd.ipynb"


def definition(name, *, last=True):
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    matches = []
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue
        source = "".join(cell["source"])
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                matches.append(ast.get_source_segment(source, node))
    return matches[-1 if last else 0]


def canonical_source_url(value):
    parsed = urlparse(value)
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", "", ""))


class CopilotVisibilityTests(unittest.TestCase):
    def _race_client(self, sleep):
        namespace = {
            "ThreadPoolExecutor": ThreadPoolExecutor,
            "as_completed": as_completed,
            "time": type("Clock", (), {"monotonic": staticmethod(time.monotonic), "sleep": sleep}),
            "BrightDataAPIError": RuntimeError,
            "FAILED_STATUSES": {"failed", "canceled"},
            "COPILOT_DATASET_ID": "gd_m7di5jy6s9geokz8w",
            "canonical_source_url": canonical_source_url,
            "BrightDataUsageLedger": BrightDataUsageLedger,
            "race_ai_visibility_core": ai_visibility_race.race_ai_visibility_core,
        }
        exec(definition("BrightDataClient"), namespace)
        client = object.__new__(namespace["BrightDataClient"])
        client.country = "US"
        client.log = lambda *_args: None
        client.snapshot_status = lambda _snapshot_id: {"status": "ready"}
        client.download_snapshot = lambda _snapshot_id: [{
            "answer_text": "Samsung appears in this answer.",
            "sources": [],
        }]
        client.record_snapshot_results = lambda *_args: None
        return client

    def test_ai_trigger_recovers_after_transient_burst_failure(self):
        sleep = mock.Mock()
        client = self._race_client(sleep)
        attempts = []

        def trigger(_dataset_id, _payload):
            attempts.append(1)
            if len(attempts) <= 3:
                raise RuntimeError("Snapshot trigger failed. HTTP 429: rate limited")
            return "recovered-snapshot"

        client.trigger_dataset = trigger
        with mock.patch.object(ai_visibility_race.time, "sleep", sleep):
            result = client.race_ai_engine("copilot", "buyer question", 3, 60)

        self.assertEqual(len(attempts), 4)
        sleep.assert_called_once_with(2)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["winner_snapshot_id"], "recovered-snapshot")

    def test_ai_trigger_does_not_retry_permanent_request_error(self):
        sleep = mock.Mock()
        client = self._race_client(sleep)
        attempts = []

        def trigger(_dataset_id, _payload):
            attempts.append(1)
            raise RuntimeError("Snapshot trigger failed. HTTP 400: invalid payload")

        client.trigger_dataset = trigger
        with mock.patch.object(ai_visibility_race.time, "sleep", sleep):
            with self.assertRaisesRegex(RuntimeError, "HTTP 400"):
                client.race_ai_engine("copilot", "buyer question", 3, 60)

        self.assertEqual(len(attempts), 3)
        sleep.assert_not_called()

    def test_source_appendix_includes_copilot_citations(self):
        namespace = {"defaultdict": defaultdict}
        exec(definition("build_source_appendix"), namespace)
        appendix = namespace["build_source_appendix"]([{
            "engine": "Copilot", "title": "Review", "canonical_url": "https://example.com/review",
            "source_type": "Publisher or other source",
        }])
        self.assertIn("### Copilot", appendix)
        self.assertIn("https://example.com/review", appendix)

    def test_copilot_country_survives_localization_wrapper(self):
        class Client:
            country = "US"

        namespace = {
            "_engine_payload_before_country_compatibility":
                lambda _client, _engine, prompt, index, _web_search: (
                    "copilot-dataset", [{"prompt": prompt, "index": index, "country": "us"}]
                ),
            "apply_compatible_country_payload": (
                ai_localization.apply_compatible_country_payload
            ),
        }
        exec(definition("country_compatible_engine_payload"), namespace)
        dataset_id, payload = namespace["country_compatible_engine_payload"](
            Client(), "copilot", "question", 1
        )
        self.assertEqual(dataset_id, "copilot-dataset")
        self.assertEqual(payload[0]["country"], "US")

    def test_copilot_payload_and_plain_answer_with_sources(self):
        namespace = {
            "ThreadPoolExecutor": ThreadPoolExecutor,
            "as_completed": as_completed,
            "time": time,
            "FAILED_STATUSES": {"failed", "canceled"},
            "COPILOT_DATASET_ID": "gd_m7di5jy6s9geokz8w",
            "canonical_source_url": canonical_source_url,
            "BrightDataUsageLedger": BrightDataUsageLedger,
            "race_ai_visibility_core": ai_visibility_race.race_ai_visibility_core,
        }
        exec(definition("BrightDataClient"), namespace)
        client_type = namespace["BrightDataClient"]
        client = object.__new__(client_type)
        client.country = "US"
        submitted = []

        def trigger(dataset_id, payload):
            submitted.append((dataset_id, payload))
            return "copilot-snapshot"

        client.trigger_dataset = trigger
        client.log = lambda *_args: None
        client.snapshot_status = lambda _snapshot_id: {"status": "ready"}
        client.download_snapshot = lambda _snapshot_id: [{
            "answer_text": "Apple and Samsung are compared here.",
            "answer_text_markdown": "<table>shopping card noise</table>" * 100,
            "sources": [
                {"url": "https://example.com/review?utm_source=copilot", "title": "Review", "cited": True},
                {"url": "https://example.com/uncited", "title": "Unused", "cited": False},
            ],
        }]
        client.record_snapshot_results = lambda *_args: None

        result = client.race_ai_engine("copilot", "neutral buyer question", 1, 180)

        self.assertEqual(submitted[0][0], "gd_m7di5jy6s9geokz8w")
        self.assertEqual(submitted[0][1][0]["country"], "US")
        self.assertEqual(submitted[0][1][0]["url"], "https://copilot.microsoft.com/chats")
        self.assertEqual(result["answer"], "Apple and Samsung are compared here.")
        self.assertEqual([source["url"] for source in result["citations"]], ["https://example.com/review"])
        self.assertNotIn("answer_text_markdown", result["record"])
        self.assertEqual(result["engine_name"], "Copilot")

    def test_copilot_failure_is_not_scored_as_zero(self):
        class Profile:
            brand_name = "Apple"
            domain = "apple.com"
            direct_competitor = False

        class Client:
            def __init__(self):
                self.calls = []

            def race_ai_engine(self, engine, _prompt, redundancy, timeout):
                self.calls.append((engine, redundancy, timeout))
                if engine == "copilot":
                    raise TimeoutError("Copilot unavailable")
                return {"engine": engine, "status": "success", "answer": "Apple", "citations": []}

        client = Client()
        namespace = {
            "asyncio": asyncio,
            "time": time,
            "bd_client": client,
            "LAST_AI_MODE_DISCOVERY": {"results": []},
            "build_visibility_prompt": lambda **_kwargs: "neutral buyer question",
            "find_brand_mentions": lambda _answer, _profiles: [{
                "brand_name": "Apple", "domain": "apple.com", "role": "target",
                "mentioned": True, "mention_count": 1, "first_position": 0,
                "matched_aliases": ["Apple"],
            }],
        }
        exec(definition("run_visibility_stage"), namespace)
        result = asyncio.run(namespace["run_visibility_stage"](Profile(), [Profile()], [], True))

        self.assertEqual(result["engines"]["copilot"]["status"], "failed")
        self.assertEqual(result["mentions"]["copilot"], [])
        self.assertIn(("copilot", 1, 360), client.calls)

    def test_copilot_is_absent_when_disabled(self):
        source = definition("run_visibility_stage")
        self.assertIn('if include_copilot:', source)
        self.assertIn('scheduled.append(("copilot", run_engine(', source)
        self.assertIn('if item in engine_results', source)
        self.assertIn('mentions[engine] = []', source)
        report_source = definition("build_deterministic_report", last=False)
        self.assertIn('if engine in visibility.get("engines", {})', report_source)

    def test_only_selected_engines_are_measured_with_per_engine_waits(self):
        class Profile:
            brand_name = "Apple"
            domain = "apple.com"
            direct_competitor = False

        class Client:
            def __init__(self):
                self.calls = []

            def race_ai_engine(self, engine, _prompt, redundancy, timeout):
                self.calls.append((engine, redundancy, timeout))
                return {"engine": engine, "status": "success", "answer": "Apple", "citations": []}

        client = Client()
        namespace = {
            "asyncio": asyncio,
            "time": time,
            "bd_client": client,
            "LAST_AI_MODE_DISCOVERY": {"results": []},
            "build_visibility_prompt": lambda **_kwargs: "buyer question",
            "find_brand_mentions": lambda _answer, _profiles: [{
                "brand_name": "Apple", "domain": "apple.com", "role": "target",
                "mentioned": True, "mention_count": 1, "first_position": 0,
                "matched_aliases": ["Apple"],
            }],
        }
        exec(definition("run_visibility_stage"), namespace)
        result = asyncio.run(namespace["run_visibility_stage"](
            Profile(), [Profile()], [], include_google_ai_mode=False,
            include_chatgpt=False, include_gemini=True,
            wait_longer_for_gemini=True, include_copilot=True,
            wait_longer_for_copilot=True,
        ))
        self.assertEqual(client.calls, [("gemini", 3, 1800), ("copilot", 1, 900)])
        self.assertEqual(set(result["engines"]), {"gemini", "copilot"})


if __name__ == "__main__":
    unittest.main()
