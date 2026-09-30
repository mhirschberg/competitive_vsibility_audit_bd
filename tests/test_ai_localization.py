"""Country targeting is shared while measured answers remain truthful."""

import json
from pathlib import Path
import unittest

from audit_core import ai_localization as localization
from audit_core.brightdata_transport import BrightDataAPIError
from notebook_builder import (
    AI_LOCALIZATION_END, AI_LOCALIZATION_SOURCE, AI_LOCALIZATION_START,
    _without_service_imports,
)
from tests.test_google_ai_timeout_safety import definition


NOTEBOOK = Path(__file__).resolve().parents[1] / "competitive_visibility_audit_bd.ipynb"


class FakeClient:
    def __init__(self):
        self.events = []

    def log(self, *args):
        self.events.append(args)


class AILocalizationTests(unittest.TestCase):
    def test_us_de_gb_market_evidence(self):
        cases = (
            ("US", "For the U.S. market, these brands matter.", True),
            ("DE", "For the German market, these brands matter.", True),
            ("GB", "For the British market, these brands matter.", True),
            ("DE", "For the US market, these brands matter.", False),
        )
        for code, answer, expected in cases:
            with self.subTest(code=code, answer=answer):
                self.assertEqual(
                    localization.answer_acknowledges_target_market(
                        answer, localization.country_details(code)
                    )["acknowledged"],
                    expected,
                )

    def test_explicit_wrong_scraper_country_requires_retry(self):
        details = localization.country_details("DE")
        result = {
            "status": "success",
            "answer": "For the German market, Example is visible.",
            "record": {"country": "US"},
        }
        metadata, reasons = localization.assess_localized_answer(
            result, details, attempt=1
        )
        self.assertFalse(metadata["country_verified"])
        self.assertTrue(metadata["market_acknowledged"])
        self.assertIn("US", reasons[0])

    def test_failed_localization_retries_then_accepts_measured_result(self):
        client = FakeClient()
        snapshots = iter((
            {
                "status": "success", "answer": "This is for the US market.",
                "record": {"country": "US"}, "winner_snapshot_id": "first",
            },
            {
                "status": "success", "answer": "This is for the German market.",
                "record": {"country": "DE"}, "winner_snapshot_id": "second",
            },
        ))
        calls = []

        def race_once(_client, engine, prompt, redundancy, timeout_seconds):
            calls.append((engine, prompt, redundancy, timeout_seconds))
            return next(snapshots)

        result = localization.race_localized_ai_visibility(
            client, "gemini", "neutral question", 3, 600,
            race_once=race_once, details=localization.country_details("DE"),
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["winner_snapshot_id"], "second")
        self.assertEqual(result["localization_attempt"], 2)
        self.assertEqual(result["record"]["_localization"]["requested_country"], "DE")
        self.assertEqual(len(client.events), 1)

    def test_two_wrong_answers_raise_instead_of_counting_as_visible(self):
        client = FakeClient()
        calls = []

        def race_once(*_args):
            calls.append(1)
            return {
                "status": "success", "answer": "Only the US market is discussed.",
                "record": {"country": "US"}, "winner_snapshot_id": f"s{len(calls)}",
            }

        with self.assertRaisesRegex(BrightDataAPIError, "strictly localized"):
            localization.race_localized_ai_visibility(
                client, "chatgpt", "neutral question", 3, 600,
                race_once=race_once, details=localization.country_details("DE"),
            )
        self.assertEqual(len(calls), 2)

    def test_country_payload_modes_keep_gemini_de_prompt_only(self):
        for engine, country, expected_field, expected_mode in (
            ("gemini", "DE", None, "prompt_only"),
            ("gemini", "US", "US", "country_field_and_prompt"),
            ("chatgpt", "DE", "DE", "country_field_and_prompt"),
            ("copilot", "GB", "GB", "country_field_and_prompt"),
        ):
            with self.subTest(engine=engine, country=country):
                payload = {"input": [{"prompt": "buyer question", "country": "old"}]}
                localization.apply_compatible_country_payload(
                    payload, engine, country
                )
                self.assertEqual(payload["input"][0].get("country"), expected_field)
                result = {"record": {}}
                localization.annotate_country_transport(result, engine, country)
                self.assertEqual(result["country_transport_mode"], expected_mode)
                self.assertEqual(
                    result["record"]["_localization"]["requested_country"], country
                )

    def test_utility_payload_has_no_country(self):
        result = {
            "payload": [{"country": "DE", "prompt": "Rewrite this text"}],
        }
        localization.clear_utility_country(result)
        self.assertNotIn("country", result["payload"][0])
        self.assertEqual(result["country_transport"], "not_required")

    def test_prompts_keep_country_instruction_and_limit(self):
        details = localization.country_details("DE")
        visibility = localization.localized_visibility_prompt(
            "Compare category alternatives.", details
        )
        self.assertIn("Germany (DE)", visibility)
        self.assertIn("Keep the answer in English", visibility)
        self.assertIn(
            "Buyer search queries must be written in German",
            localization.compact_market_instruction_core(details),
        )
        research = localization.localize_google_ai_prompt_core(
            "Research the current market for premium phones.", details
        )
        self.assertIn("STRICT TARGET MARKET:", research)
        self.assertLessEqual(len(research), 4096)
        self.assertEqual(
            localization.localize_google_ai_prompt_core(research, details), research
        )
        with self.assertRaisesRegex(ValueError, "too long"):
            localization.localized_visibility_prompt("x" * 4096, details)

    def test_notebook_embeds_source_and_country_adapter_calls_core(self):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        cell = next(
            cell for cell in notebook["cells"]
            if cell.get("metadata", {}).get("id") == "runtime-utilities-merged"
        )
        source = "".join(cell["source"])
        embedded = source.split(AI_LOCALIZATION_START, 1)[1].split(
            AI_LOCALIZATION_END, 1
        )[0].strip()
        self.assertEqual(
            embedded,
            _without_service_imports(
                AI_LOCALIZATION_SOURCE.read_text(encoding="utf-8")
            ).strip(),
        )
        namespace = {
            "country_details": localization.country_details,
            "AUDIT_SETTINGS": {"country": "GB"},
            "bd_client": type("Client", (), {"country": "US"})(),
        }
        exec(definition("get_ai_country_details"), namespace)
        self.assertEqual(namespace["get_ai_country_details"]()["code"], "US")
        self.assertEqual(namespace["get_ai_country_details"]("DE")["code"], "DE")

    def test_notebook_race_adapters_preserve_country_evidence_and_transport(self):
        class Client(FakeClient):
            country = "DE"

        namespace = {
            "race_localized_ai_visibility": localization.race_localized_ai_visibility,
            "annotate_country_transport": localization.annotate_country_transport,
            "get_ai_country_details": localization.country_details,
            "AI_LOCALIZATION_RACE_ATTEMPTS": 2,
            "STRICT_AI_COUNTRY_VALIDATION": True,
            "_race_ai_engine_before_localization": (
                lambda _client, engine, _prompt, _redundancy, _timeout: {
                    "engine": engine,
                    "status": "success",
                    "answer": "For the German market, this brand appears.",
                    "record": {"country": "DE"},
                    "winner_snapshot_id": "measured-de",
                }
            ),
        }
        exec(definition("race_ai_engine_with_localization"), namespace)
        namespace["_race_ai_engine_before_country_compatibility"] = (
            namespace["race_ai_engine_with_localization"]
        )
        exec(definition("race_ai_engine_country_compatible"), namespace)
        result = namespace["race_ai_engine_country_compatible"](
            Client(), "gemini", "neutral question", 1, 10
        )
        self.assertTrue(result["country_verified"])
        self.assertEqual(result["country_transport_mode"], "prompt_only")
        self.assertEqual(result["record"]["_localization"]["requested_country"], "DE")
        self.assertEqual(result["winner_snapshot_id"], "measured-de")


if __name__ == "__main__":
    unittest.main()
