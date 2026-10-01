"""Slow Google AI Mode snapshots must not be re-triggered or scored as complete."""

import ast
import asyncio
from concurrent.futures import Future, as_completed
import json
import inspect
from pathlib import Path
import threading
import unittest

from audit_core.visibility_stage import run_visibility_stage_core
from audit_core.brightdata_transport import SnapshotTimeoutError
from audit_core.search_discovery import run_google_ai_mode_question_core
from audit_core.ai_localization import (
    answer_acknowledges_target_market,
    country_details,
    market_language,
)


NOTEBOOK = Path(__file__).resolve().parents[1] / "competitive_visibility_audit_bd.ipynb"


def notebook_source():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    parsed = []
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue
        source = "".join(cell["source"])
        try:
            parsed.append((source, ast.parse(source)))
        except SyntaxError:
            # The Colab setup cell contains notebook-only shell commands.
            continue
    return parsed


def definition(name, *, last=False):
    matches = []
    for source, tree in notebook_source():
        for item in tree.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and item.name == name:
                matches.append(ast.get_source_segment(source, item))
    return matches[-1 if last else 0]


class FakeClock:
    def __init__(self):
        self.now = 0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class ImmediateExecutor:
    def __init__(self, max_workers):
        self.max_workers = max_workers

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def submit(self, function, *args):
        future = Future()
        try:
            future.set_result(function(*args))
        except Exception as exc:
            future.set_exception(exc)
        return future


class GoogleAITimeoutSafetyTests(unittest.TestCase):
    def make_namespace(self):
        namespace = {}
        exec(definition("SnapshotTimeoutError"), namespace)
        exec(definition("GoogleAIRaceTimeoutError"), namespace)
        return namespace

    def test_race_timeout_preserves_existing_snapshot_ids(self):
        namespace = self.make_namespace()
        clock = FakeClock()
        triggers = []

        def trigger(_prompt, request_index):
            triggers.append(request_index)
            return {"request_index": request_index, "snapshot_id": f"snap-{request_index}"}

        class Client:
            def log(self, *_args):
                pass

            def snapshot_status(self, _snapshot_id):
                return {"status": "building"}

        namespace.update({
            "time": clock,
            "identify_google_ai_research_task": lambda _prompt: "research",
            "_GOOGLE_AI_RACE_SEMAPHORE": threading.Semaphore(1),
            "GOOGLE_AI_RESEARCH_REDUNDANCY": 3,
            "GOOGLE_AI_RACE_POLL_SECONDS": 5,
            "FAILED_STATUSES": {"failed", "error"},
            "GoogleAIRaceExecutor": ImmediateExecutor,
            "google_ai_as_completed": as_completed,
            "trigger_google_ai_race_snapshot": trigger,
            "cached_google_ai_snapshot_ids": lambda _prompt: [],
            "remember_google_ai_snapshot": lambda _prompt, _snapshot_id: None,
            "_GOOGLE_AI_ONLY_REUSE": False,
        })
        exec(definition("race_google_ai_mode"), namespace)
        with self.assertRaises(namespace["GoogleAIRaceTimeoutError"]) as caught:
            namespace["race_google_ai_mode"](Client(), "buyer question", 10)
        self.assertEqual(triggers, [1, 2, 3])
        self.assertEqual(caught.exception.snapshot_ids, ["snap-1", "snap-2", "snap-3"])

    def test_market_retry_stops_after_pending_race(self):
        class GoogleAIRaceTimeoutError(SnapshotTimeoutError):
            def __init__(self, snapshot_ids, timeout_seconds):
                self.snapshot_ids = list(snapshot_ids)
                super().__init__(self.snapshot_ids[0], timeout_seconds)
                self.args = (
                    "Google AI Mode snapshots did not finish; IDs: "
                    + ", ".join(self.snapshot_ids),
                )

        class Client:
            def __init__(self):
                self.calls = 0

            def google_ai_mode_measured(self, *_args):
                self.calls += 1
                raise GoogleAIRaceTimeoutError(["snap-1", "snap-2"], 720)

            def log(self, *_args):
                pass

        client = Client()
        result = asyncio.run(run_google_ai_mode_question_core(
            "test query", 1,
            client=client,
            country_code="DE",
            timeout_seconds=720,
            max_attempts=3,
            is_google_goto_url=lambda _url: False,
            resolve_google_goto_url=lambda url: url,
            get_root_domain=lambda url: url,
            country_details_fn=country_details,
            market_language_fn=market_language,
            acknowledge_market_fn=answer_acknowledges_target_market,
            timeout_error_type=SnapshotTimeoutError,
        ))
        self.assertFalse(result["success"])
        self.assertEqual(client.calls, 1)
        self.assertIn("snap-1", result["error"])

    def test_notebook_market_runner_is_only_a_shared_core_adapter(self):
        source = definition("run_ai_mode_question", last=True)
        self.assertIn("run_google_ai_mode_question_core", source)
        self.assertNotIn("google_ai_mode_measured", source)

    def test_market_runner_retries_localization_and_normalizes_citations(self):
        class Client:
            def __init__(self):
                self.calls = []
                self.records = [
                    {"answer_text": "Leading premium smartphone options."},
                    {
                        "answer_text": "For the Germany market, buyers compare these options.",
                        "citations": [
                            {
                                "url": "https://google.com/url?opaque=1",
                                "title": "Publisher",
                            },
                            {
                                "url": "https://google.com/url?opaque=2",
                                "title": "Unresolved",
                            },
                            {
                                "url": "https://publisher.de/guide",
                                "title": "Direct source",
                            },
                        ],
                    },
                ]

            def google_ai_mode_measured(self, prompt, timeout_seconds):
                self.calls.append((prompt, timeout_seconds))
                return self.records.pop(0)

            @staticmethod
            def answer_text(record):
                return record.get("answer_text", "")

            def log(self, *_args):
                pass

        client = Client()
        result = asyncio.run(run_google_ai_mode_question_core(
            "premium smartphone", 2,
            client=client,
            country_code="DE",
            timeout_seconds=1800,
            is_google_goto_url=lambda url: url.startswith("https://google.com/url"),
            resolve_google_goto_url=lambda url: (
                "https://publisher.de/article" if "opaque=1" in url
                else url if "opaque=2" in url else url
            ),
            get_root_domain=lambda url: "publisher.de" if "publisher.de" in url else "google.com",
            country_details_fn=country_details,
            market_language_fn=market_language,
            acknowledge_market_fn=answer_acknowledges_target_market,
            timeout_error_type=SnapshotTimeoutError,
        ))

        self.assertEqual(len(client.calls), 2)
        self.assertTrue(all(timeout == 1800 for _, timeout in client.calls))
        self.assertIn("Germany", client.calls[0][0])
        self.assertIn("German", client.calls[0][0])
        self.assertTrue(result["success"])
        self.assertEqual(result["market_attempt"], 2)
        self.assertEqual(result["requested_country"], "DE")
        self.assertEqual([item["url"] for item in result["citations"]], [
            "https://publisher.de/article", "https://publisher.de/guide",
        ])
        self.assertEqual(result["citations"][0]["position"], 1)
        self.assertEqual(client.records, [])

    def test_partial_google_sample_is_not_labeled_success(self):
        source = inspect.getsource(run_visibility_stage_core)
        self.assertIn('len(successful_ai_answers) == 3', source)
        self.assertIn('else "partial" if ai_mode_answers', source)
        self.assertIn('else "unavailable"', source)
        self.assertIn('if google_ai_result["status"] == "success"', source)
        self.assertIn('mentions["google_ai_mode"] = []', source)

    def test_partial_engine_is_excluded_from_report_source_counts(self):
        captured = []

        def collect(visibility, max_per_engine):
            captured.append(visibility)
            return [{"source_type": "Editorial"}]

        from audit_core.report_content import deterministic_source_counts

        _, counts = deterministic_source_counts({
            "engines": {
                "google_ai_mode": {"status": "partial", "citations": [{"url": "https://partial.test"}]},
                "chatgpt": {"status": "success", "citations": [{"url": "https://complete.test"}]},
            }
        }, collect)
        self.assertEqual(set(captured[0]["engines"]), {"chatgpt"})
        self.assertEqual(counts["Editorial"], 1)


if __name__ == "__main__":
    unittest.main()
