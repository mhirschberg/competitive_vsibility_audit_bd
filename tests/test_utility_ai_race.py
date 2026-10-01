"""Offline coverage for the shared Reddit utility AI race."""

import json
from pathlib import Path
import unittest

from audit_core.utility_ai_race import race_utility_ai_core
from notebook_builder import (
    UTILITY_AI_RACE_ADAPTER_SOURCE, UTILITY_AI_RACE_END,
    UTILITY_AI_RACE_SOURCE, UTILITY_AI_RACE_START,
)


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "competitive_visibility_audit_bd.ipynb"


class FakeClient:
    def __init__(self, answers=None, trigger_failures=None):
        self.answers = answers or {}
        self.trigger_failures = trigger_failures or {}
        self.triggers = []
        self.counted = []
        self.requests = []

    def log(self, *_args):
        pass

    def trigger_dataset(self, dataset_id, payload):
        self.triggers.append(dataset_id)
        self.requests.append((dataset_id, payload))
        if dataset_id in self.trigger_failures:
            raise RuntimeError(self.trigger_failures[dataset_id])
        return f"snapshot-{dataset_id}"

    def snapshot_status(self, _snapshot_id):
        return {"status": "ready"}

    def download_snapshot(self, snapshot_id):
        dataset_id = snapshot_id.removeprefix("snapshot-")
        return [{"answer_text": self.answers.get(dataset_id, "")}]

    def record_snapshot_results(self, snapshot_id, count):
        self.counted.append((snapshot_id, count))

    @staticmethod
    def answer_text(record):
        return record.get("answer_text", "")


def race(client, *, validator=None):
    return race_utility_ai_core(
        client,
        "Return a JSON object.",
        validator=validator or (lambda answer: {
            "valid": answer == '{"ok": true}',
            "reason": "Expected a valid JSON object.",
        }),
        timeout_seconds=2,
        task_name="Reddit keyword generation",
        dataset_ids={"gemini": "gemini-dataset", "chatgpt": "chatgpt-dataset"},
        failed_statuses={"failed", "canceled"},
        error_type=RuntimeError,
        poll_seconds=0.001,
    )


class UtilityAIRaceTests(unittest.TestCase):
    def test_only_valid_answer_wins_and_country_is_not_sent(self):
        client = FakeClient({
            "gemini-dataset": "not JSON",
            "chatgpt-dataset": '{"ok": true}',
        })
        result = race(client)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["engine"], "chatgpt")
        self.assertEqual(result["task_name"], "Reddit keyword generation")
        self.assertEqual(
            result["all_snapshot_ids"],
            {"gemini": "snapshot-gemini-dataset", "chatgpt": "snapshot-chatgpt-dataset"},
        )
        self.assertCountEqual(client.triggers, ["gemini-dataset", "chatgpt-dataset"])
        self.assertTrue(all(
            "country" not in str(payload).lower()
            for _, payload in client.requests
        ))
        self.assertCountEqual(client.counted, [
            ("snapshot-gemini-dataset", 1),
            ("snapshot-chatgpt-dataset", 1),
        ])

    def test_trigger_failure_does_not_prevent_other_provider_from_winning(self):
        client = FakeClient(
            {"gemini-dataset": '{"ok": true}'},
            {"chatgpt-dataset": "temporary provider failure"},
        )
        result = race(client)
        self.assertEqual(result["engine"], "gemini")
        self.assertIn("chatgpt", result["trigger_errors"])

    def test_both_invalid_answers_raise_provider_error(self):
        client = FakeClient({
            "gemini-dataset": "not JSON",
            "chatgpt-dataset": "also not JSON",
        })
        with self.assertRaisesRegex(RuntimeError, "Neither Gemini nor ChatGPT"):
            race(client)

    def test_payload_shapes_remain_provider_specific(self):
        client = FakeClient({
            "gemini-dataset": '{"ok": true}',
            "chatgpt-dataset": '{"ok": true}',
        })
        race(client)
        by_dataset = dict(client.requests)
        self.assertFalse(by_dataset["chatgpt-dataset"][0]["web_search"])
        self.assertEqual(
            by_dataset["chatgpt-dataset"][0]["url"], "https://chatgpt.com/"
        )
        self.assertEqual(
            by_dataset["gemini-dataset"]["input"][0]["url"],
            "https://gemini.google.com/",
        )

    def test_notebook_embeds_the_same_module_and_uses_compatibility_wrapper(self):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        utility_cell = next(
            cell for cell in notebook["cells"]
            if cell.get("metadata", {}).get("id") == "runtime-utilities-merged"
        )
        source = "".join(utility_cell["source"])
        self.assertEqual(source.count(UTILITY_AI_RACE_START), 1)
        self.assertEqual(source.count(UTILITY_AI_RACE_END), 1)
        embedded = source.split(UTILITY_AI_RACE_START, 1)[1].split(
            UTILITY_AI_RACE_END, 1
        )[0]
        module_source = UTILITY_AI_RACE_SOURCE.read_text(encoding="utf-8").strip()
        self.assertIn(module_source, embedded)
        self.assertIn(UTILITY_AI_RACE_ADAPTER_SOURCE.strip(), source)
        self.assertEqual(source.count("def race_utility_ai("), 1)

        namespace = {
            "UTILITY_RACE_TIMEOUT_SECONDS": 2,
            "UTILITY_RACE_POLL_SECONDS": 0.001,
            "CHATGPT_DATASET_ID": "chatgpt-dataset",
            "GEMINI_DATASET_ID": "gemini-dataset",
            "FAILED_STATUSES": {"failed", "canceled"},
            "BrightDataAPIError": RuntimeError,
            "validate_utility_json_answer": lambda answer: {
                "valid": answer == '{"ok": true}',
            },
            "LAST_UTILITY_AI_RESULT": None,
            "bd_client": FakeClient({
                "chatgpt-dataset": '{"ok": true}',
                "gemini-dataset": "invalid",
            }),
        }
        exec(embedded, namespace)
        exec(UTILITY_AI_RACE_ADAPTER_SOURCE, namespace)
        result = namespace["race_utility_ai"]("Return JSON")
        self.assertEqual(result["status"], "success")
        self.assertIs(namespace["LAST_UTILITY_AI_RESULT"], result)


if __name__ == "__main__":
    unittest.main()
