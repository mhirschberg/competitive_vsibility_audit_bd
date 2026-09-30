"""Measured answer races preserve provider labels and citation accounting."""

import ast
import json
from pathlib import Path
import textwrap
import unittest

from audit_core.ai_visibility_race import race_ai_visibility_core
from audit_core.brightdata_transport import BrightDataAPIError
from notebook_builder import (
    AI_VISIBILITY_RACE_END, AI_VISIBILITY_RACE_SOURCE,
    AI_VISIBILITY_RACE_START, _without_service_imports,
)


NOTEBOOK = Path(__file__).resolve().parents[1] / "competitive_visibility_audit_bd.ipynb"


class FakeClient:
    def __init__(self, record, status="ready"):
        self.record = record
        self.status = status
        self.triggers = []
        self.counted = []

    def _engine_payload(self, engine, prompt, request_index, web_search):
        assert web_search
        return engine, [{"prompt": prompt, "index": request_index}]

    def trigger_dataset(self, dataset_id, payload):
        self.triggers.append((dataset_id, payload))
        return f"snapshot-{dataset_id}"

    def snapshot_status(self, _snapshot_id):
        return {"status": self.status}

    def download_snapshot(self, _snapshot_id):
        return [self.record]

    def record_snapshot_results(self, snapshot_id, count):
        self.counted.append((snapshot_id, count))

    def answer_text(self, record):
        return record.get("answer_text", "")

    def log(self, *_args):
        pass


def race(client, engine):
    return race_ai_visibility_core(
        client, engine, "neutral buyer question", redundancy=1,
        timeout_seconds=10, failed_statuses={"failed"},
        canonical_source_url=lambda url: url.split("#", 1)[0],
    )


class VisibilityRaceTests(unittest.TestCase):
    def test_chatgpt_keeps_real_provider_and_citations(self):
        record = {
            "answer_text": "Brand A appears in the answer.",
            "citations": [{"url": "https://source.example/a"}],
            "web_search_triggered": True,
        }
        client = FakeClient(record)
        result = race(client, "chatgpt")
        self.assertEqual(result["engine"], "chatgpt")
        self.assertEqual(result["winner_snapshot_id"], "snapshot-chatgpt")
        self.assertEqual(result["citations"], record["citations"])
        self.assertEqual(result["record"], record)
        self.assertEqual(client.counted, [("snapshot-chatgpt", 1)])

    def test_copilot_uses_only_cited_sources_and_compact_record(self):
        record = {
            "answer_text": "  Useful answer.  ",
            "sources": [
                {"url": "https://source.example/a#section", "cited": True},
                {"url": "https://source.example/b", "cited": False},
            ],
            "private_extra": "not persisted",
        }
        result = race(FakeClient(record), "copilot")
        self.assertEqual(result["engine"], "copilot")
        self.assertEqual(result["answer"], "Useful answer.")
        self.assertEqual(result["citations"], [
            {"url": "https://source.example/a", "cited": True}
        ])
        self.assertNotIn("private_extra", result["record"])

    def test_failed_snapshot_does_not_create_a_fabricated_answer(self):
        with self.assertRaisesRegex(BrightDataAPIError, "returned no answer"):
            race(FakeClient({"answer_text": "unused"}, status="failed"), "gemini")

    def test_notebook_embeds_core_and_calls_it_from_client(self):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        cell = next(
            cell for cell in notebook["cells"]
            if cell.get("metadata", {}).get("id") == "final-core"
        )
        source = "".join(cell["source"])
        embedded = source.split(AI_VISIBILITY_RACE_START, 1)[1].split(
            AI_VISIBILITY_RACE_END, 1
        )[0].strip()
        self.assertEqual(
            embedded, _without_service_imports(
                AI_VISIBILITY_RACE_SOURCE.read_text(encoding="utf-8")
            ).strip()
        )
        namespace = {
            "race_ai_visibility_core": race_ai_visibility_core,
            "FAILED_STATUSES": {"failed"},
            "canonical_source_url": lambda url: url,
        }
        client_class = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.ClassDef) and node.name == "BrightDataClient"
        )
        wrapper = next(
            node for node in client_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "race_ai_engine"
        )
        exec(textwrap.dedent(ast.get_source_segment(source, wrapper)), namespace)
        result = namespace["race_ai_engine"](
            FakeClient({"answer_text": "Measured answer"}),
            "gemini", "question", redundancy=1, timeout_seconds=10,
        )
        self.assertEqual(result["engine"], "gemini")


if __name__ == "__main__":
    unittest.main()
