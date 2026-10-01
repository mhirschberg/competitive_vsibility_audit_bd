"""Research can fail over between assistants without forging Google metrics."""

import json
from pathlib import Path
import unittest

from audit_core.research_race import ResearchProviderAdapter
from audit_core.ai_localization import country_details, localize_google_ai_prompt_core
from notebook_builder import (
    RESEARCH_RACE_END, RESEARCH_RACE_SOURCE, RESEARCH_RACE_START,
    RESEARCH_VALIDATION_END, RESEARCH_VALIDATION_SOURCE,
    RESEARCH_VALIDATION_START,
    _without_service_imports,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research_fallback.py"
NOTEBOOK = ROOT / "competitive_visibility_audit_bd.ipynb"


class SnapshotTimeoutError(TimeoutError):
    def __init__(self, snapshot_id, timeout_seconds):
        self.snapshot_id = snapshot_id
        self.timeout_seconds = timeout_seconds
        super().__init__(snapshot_id)


class FakeClient:
    country = "DE"

    def __init__(self):
        self.triggers = []
        self.counted = []

    def log(self, *_args):
        pass

    def _engine_payload(self, engine, prompt, request_index, web_search):
        assert web_search
        return engine, {"prompt": prompt, "index": request_index}

    def trigger_dataset(self, dataset_id, _payload):
        self.triggers.append(dataset_id)
        return f"snapshot-{dataset_id}"

    def snapshot_status(self, _snapshot_id):
        return {"status": "ready"}

    def download_snapshot(self, snapshot_id):
        if snapshot_id.endswith("chatgpt"):
            return [{"answer_text": "invalid"}]
        return [{
            "answer_text": "A substantive market research answer with useful details. " * 4
        }]

    def record_snapshot_results(self, snapshot_id, count):
        self.counted.append((snapshot_id, count))

    @staticmethod
    def answer_text(record):
        return record.get("answer_text", "")


def load_runtime(*, cache=None, only_reuse=False):
    cache = cache or {}
    namespace = {
        "ResearchProviderAdapter": ResearchProviderAdapter,
        "SnapshotTimeoutError": SnapshotTimeoutError,
        "BrightDataAPIError": RuntimeError,
        "BrightDataClient": FakeClient,
        "bd_client": FakeClient(),
        "race_google_ai_mode": lambda *_args: {"answer_text": "Google measured"},
        "google_ai_mode_market_consistent": lambda *_args: {"answer_text": "Google measured"},
        "cached_google_ai_snapshot_ids": lambda prompt: cache.get(prompt, []),
        "remember_google_ai_snapshot": lambda prompt, sid: cache.setdefault(prompt, []).append(sid),
        "_GOOGLE_AI_ONLY_REUSE": only_reuse,
        "FAILED_STATUSES": {"failed", "canceled"},
        "country_details": country_details,
        "localize_google_ai_prompt_core": localize_google_ai_prompt_core,
        "parse_ai_json": json.loads,
        "remove_ai_boilerplate": lambda value: value,
    }
    exec(SOURCE.read_text(encoding="utf-8"), namespace)
    return namespace


class ResearchFallbackTests(unittest.TestCase):
    def test_gemini_wins_after_invalid_chatgpt_result(self):
        namespace = load_runtime()
        client = FakeClient()
        result = client.google_ai_mode("research", timeout_seconds=3)
        self.assertEqual(set(client.triggers), {"chatgpt", "gemini"})
        self.assertEqual(result["_research_race"]["provider"], "gemini")
        self.assertIn("substantive market research", result["answer_text"].lower())

    def test_continuation_reuses_saved_provider_snapshot(self):
        localized = localize_google_ai_prompt_core("research", country_details("DE"))
        cache = {f"research-provider-v1:gemini:{localized}": ["snapshot-gemini"]}
        namespace = load_runtime(cache=cache, only_reuse=True)
        client = FakeClient()
        result = client.google_ai_mode("research", timeout_seconds=3)
        self.assertEqual(client.triggers, [])
        self.assertEqual(result["_research_race"]["provider"], "gemini")
        self.assertEqual(
            namespace["cached_research_snapshot_ids"]("research"),
            {"gemini": ["snapshot-gemini"]},
        )

    def test_legacy_google_research_checkpoint_remains_resumable(self):
        localized = localize_google_ai_prompt_core("research", country_details("DE"))
        cache = {localized: ["snapshot-legacy-google"]}
        namespace = load_runtime(cache=cache, only_reuse=True)
        client = FakeClient()
        result = client.google_ai_mode("research", timeout_seconds=3)
        self.assertEqual(client.triggers, [])
        self.assertEqual(result["_research_race"]["provider"], "google_ai_mode")
        self.assertEqual(
            namespace["cached_research_snapshot_ids"]("research"),
            {"google_ai_mode": ["snapshot-legacy-google"]},
        )

    def test_google_measurement_stays_separate(self):
        load_runtime()
        self.assertEqual(
            FakeClient().google_ai_mode_measured("buyer prompt")["answer_text"],
            "Google measured",
        )
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        source = "\n".join(
            "".join(cell["source"])
            for cell in notebook["cells"] if cell["cell_type"] == "code"
        )
        self.assertIn("bd_client.google_ai_mode_measured,", source)

    def test_notebook_embeds_current_source(self):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        cell = next(
            cell for cell in notebook["cells"]
            if cell.get("metadata", {}).get("id") == "research-provider-race"
        )
        source = "".join(cell["source"])
        embedded = source.split(RESEARCH_RACE_START, 1)[1].split(
            RESEARCH_RACE_END, 1
        )[0].strip()
        self.assertEqual(embedded, RESEARCH_RACE_SOURCE.read_text().strip())
        self.assertTrue(source.endswith(_without_service_imports(SOURCE.read_text())))
        validation = source.split(RESEARCH_VALIDATION_START, 1)[1].split(
            RESEARCH_VALIDATION_END, 1
        )[0].strip()
        self.assertEqual(
            validation,
            _without_service_imports(RESEARCH_VALIDATION_SOURCE.read_text()).strip(),
        )


if __name__ == "__main__":
    unittest.main()
