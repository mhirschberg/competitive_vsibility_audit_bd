"""Slow Google AI Mode snapshots must not be re-triggered or scored as complete."""

import ast
import asyncio
from concurrent.futures import Future, as_completed
import json
from pathlib import Path
import threading
import unittest


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
        namespace = self.make_namespace()

        class Client:
            def __init__(self):
                self.calls = 0

            def google_ai_mode_measured(self, *_args):
                self.calls += 1
                raise namespace["GoogleAIRaceTimeoutError"](["snap-1", "snap-2"], 720)

        client = Client()
        namespace.update({
            "asyncio": asyncio,
            "time": __import__("time"),
            "json": json,
            "bd_client": client,
            "AUDIT_SETTINGS": {"country": "DE"},
            "get_ai_country_details": lambda _country: {"name": "Germany", "code": "DE"},
            "get_market_language": lambda _country: "German",
            "GOOGLE_AI_MARKET_ATTEMPTS": 3,
        })
        exec(definition("run_ai_mode_question", last=True), namespace)
        result = asyncio.run(namespace["run_ai_mode_question"]("test query", 1))
        self.assertFalse(result["success"])
        self.assertEqual(client.calls, 1)
        self.assertIn("snap-1", result["error"])

    def test_partial_google_sample_is_not_labeled_success(self):
        source = definition("run_visibility_stage")
        self.assertIn('if len(successful_ai_answers) == 3', source)
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
