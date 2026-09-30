"""Parity and unavailable-source semantics for the shared AI visibility stage."""

import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import tldextract

from audit_core.brand_mentions import find_brand_mentions
from audit_core.visibility_stage import run_visibility_stage_core


ROOT = Path(__file__).resolve().parents[1]


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def race_ai_engine(self, engine, prompt, redundancy, timeout_seconds):
        self.calls.append((engine, redundancy, timeout_seconds, prompt))
        response = self.responses[engine]
        if isinstance(response, Exception):
            raise response
        return copy.deepcopy(response)


def bundled_stage(client, discovery):
    notebook = json.loads((ROOT / "competitive_visibility_audit_bd.ipynb").read_text())
    cell = next(cell for cell in notebook["cells"]
                if cell.get("metadata", {}).get("id") == "final-orchestration")
    source = "".join(cell["source"])
    code = source.split("# AUDIT-VISIBILITY-STAGE: start\n", 1)[1].split(
        "# ============================================================\n# SERP visibility metrics", 1
    )[0]
    namespace = {
        "find_brand_mentions": find_brand_mentions,
        "bd_client": client,
        "build_visibility_prompt": lambda **_: "Spain buyer prompt",
        "LAST_AI_MODE_DISCOVERY": discovery,
    }
    exec(compile(code, "bundled-visibility-stage", "exec"), namespace)
    return namespace["run_visibility_stage"]


def without_timings(result):
    result = copy.deepcopy(result)
    for engine in result["engines"].values():
        engine.pop("duration_seconds", None)
    return result


class VisibilityStageTests(unittest.TestCase):
    def setUp(self):
        extractor = tldextract.TLDExtract(cache_dir=None, suffix_list_urls=())
        mock = patch("tldextract.extract", extractor)
        mock.start()
        self.addCleanup(mock.stop)
        self.profiles = [
            SimpleNamespace(brand_name="Idealista", domain="idealista.com",
                            direct_competitor=False),
            SimpleNamespace(brand_name="Fotocasa", domain="fotocasa.es",
                            direct_competitor=True),
        ]
        self.responses = {
            "chatgpt": {"engine": "chatgpt", "engine_name": "ChatGPT",
                        "status": "success", "answer": "Idealista and Fotocasa serve Spain.",
                        "citations": []},
            "gemini": {"engine": "gemini", "engine_name": "Gemini",
                       "status": "success", "answer": "Fotocasa is an option.",
                       "citations": []},
            "copilot": RuntimeError("Sign in page shown"),
        }

    def run_service(self, client, discovery, **options):
        return asyncio.run(run_visibility_stage_core(
            self.profiles[0], self.profiles, ["buy a home in Spain"],
            bd_client=client,
            prompt_builder=lambda **_: "Spain buyer prompt",
            ai_mode_discovery=discovery,
            **options,
        ))

    def test_service_matches_generated_notebook_adapter(self):
        discovery = {"results": [
            {"success": True, "answer": "Idealista helps buyers.", "citations": []},
            {"success": True, "answer": "Fotocasa helps buyers.", "citations": []},
            {"success": True, "answer": "Idealista and Fotocasa.", "citations": []},
        ]}
        options = {"include_copilot": True, "wait_longer_for_copilot": True}
        service_client = FakeClient(self.responses)
        bundled_client = FakeClient(self.responses)
        service = self.run_service(service_client, discovery, **options)
        bundled = asyncio.run(bundled_stage(bundled_client, discovery)(
            self.profiles[0], self.profiles, ["buy a home in Spain"], **options,
        ))
        self.assertEqual(without_timings(service), without_timings(bundled))
        self.assertEqual(service["engines"]["copilot"]["status"], "failed")
        self.assertEqual(service["mentions"]["copilot"], [])
        idealista = next(item for item in service["mentions"]["google_ai_mode"]
                         if item["domain"] == "idealista.com")
        self.assertEqual(idealista["answer_appearances"], 2)
        self.assertEqual(idealista["answer_total"], 3)
        self.assertIn(("copilot", 1, 900, "Spain buyer prompt"), service_client.calls)

    def test_partial_google_sample_is_unknown_not_absent(self):
        discovery = {"results": [
            {"success": True, "answer": "Idealista", "citations": []},
            {"success": False, "error": "Timeout"},
        ]}
        result = self.run_service(
            FakeClient(self.responses), discovery,
            include_chatgpt=False, include_gemini=False,
        )
        self.assertEqual(result["engines"]["google_ai_mode"]["status"], "partial")
        self.assertEqual(result["mentions"]["google_ai_mode"], [])
        self.assertNotIn("chatgpt", result["engines"])

    def test_disabled_google_not_measured(self):
        result = self.run_service(
            FakeClient(self.responses), None,
            include_google_ai_mode=False, include_chatgpt=False,
            include_gemini=False,
        )
        self.assertEqual(result["engines"], {})
        self.assertEqual(result["mentions"]["google_ai_mode"], [])


if __name__ == "__main__":
    unittest.main()
