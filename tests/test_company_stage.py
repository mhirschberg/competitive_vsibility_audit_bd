"""Company/keyword stage remains resumable outside the notebook."""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import time
import unittest

from audit_core.artifact_writes import write_json_with_scope
from audit_core.company_stage import CompanyStagePorts, run_company_stage_core
from notebook_builder import COMPANY_STAGE_CALL_SOURCE


class Model:
    def __init__(self, **values):
        self.__dict__.update(values)


class CompanyStageTests(unittest.TestCase):
    def setUp(self):
        self.settings = {
            "company_domain": "idealista.com",
            "company_url": "https://idealista.com/",
        }
        self.timestamp = datetime(2026, 9, 30, tzinfo=timezone.utc)

    def ports(self, scope_holder, calls, messages):
        def analyze(_settings):
            calls.append("analyze")
            scope_holder["value"] = {"market": "Spanish property portals"}
            return {
                "intake": Model(
                    brand=Model(
                        brand_name="Idealista", domain="old.example",
                        official_url="https://old.example/",
                    ),
                    buyer_intent_keywords=[
                        Model(keyword="comprar piso"),
                        Model(keyword="alquilar casa"),
                    ],
                ),
                "record": {"answer": "saved"},
                "structuring_record": {"structured": True},
                "keyword_completion": {"record": {"keywords": 2}},
            }

        def write(path, data):
            return write_json_with_scope(
                path, data, locked_target_scope=scope_holder["value"],
            )

        return CompanyStagePorts(
            analyze=analyze,
            intake_factory=Model,
            brand_factory=Model,
            keyword_factory=Model,
            get_locked_scope=lambda: scope_holder["value"],
            set_locked_scope=lambda scope: scope_holder.__setitem__("value", scope),
            restore_locked_scope=lambda checkpoint, _brand, _settings: dict(
                checkpoint["locked_target_scope"]
            ),
            model_to_dict=lambda item: vars(item).copy(),
            write_json=write,
            clean_record=lambda record: dict(record),
            stage_success=messages.append,
        )

    def test_new_run_persists_company_keywords_and_raw_records(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "competitive-visibility-idealista"
            raw = output / "raw"
            output.mkdir()
            raw.mkdir()
            scope = {"value": None}
            calls, messages = [], []
            result = asyncio.run(run_company_stage_core(
                self.settings, continuing=False, output_directory=output,
                raw_directory=raw, run_timestamp=self.timestamp,
                started_at=0.0, ports=self.ports(scope, calls, messages),
            ))
            self.assertEqual(calls, ["analyze"])
            self.assertEqual(result["keywords"], ["comprar piso", "alquilar casa"])
            self.assertEqual(result["target_brand"].domain, "idealista.com")
            self.assertEqual(scope["value"]["official_url"], "https://idealista.com/")
            saved = json.loads((output / "01_company_analysis.json").read_text())
            self.assertEqual(saved["locked_target_scope"]["market"], "Spanish property portals")
            self.assertEqual(len(saved["buyer_intent_keywords"]), 2)
            self.assertEqual(json.loads(
                (raw / "01_keyword_completion_record.json").read_text()
            ), {"keywords": 2})
            self.assertTrue((raw / "01_company_structuring_record.json").is_file())
            self.assertIn("2 buyer keywords generated", messages[0])

    def test_resume_reuses_checkpoint_without_provider_call(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "competitive-visibility-idealista"
            raw = output / "raw"
            output.mkdir()
            raw.mkdir()
            saved = {
                "created_at": self.timestamp.isoformat(),
                "brand": {
                    "brand_name": "Idealista", "domain": "idealista.com",
                    "official_url": "https://idealista.com/",
                },
                "buyer_intent_keywords": [{"keyword": "comprar piso"}],
                "duration_seconds": 42.5,
                "locked_target_scope": {
                    "market": "Spanish property portals",
                    "domain": "idealista.com",
                    "official_url": "https://idealista.com/",
                },
            }
            (output / "01_company_analysis.json").write_text(json.dumps(saved))
            (raw / "01_company_ai_record.json").write_text('{"answer":"saved"}')
            scope = {"value": None}
            calls, messages = [], []
            result = asyncio.run(run_company_stage_core(
                self.settings, continuing=True, output_directory=output,
                raw_directory=raw, run_timestamp=self.timestamp,
                started_at=0.0, ports=self.ports(scope, calls, messages),
            ))
            self.assertEqual(calls, [])
            self.assertEqual(result["duration_seconds"], 42.5)
            self.assertEqual(result["keywords"], ["comprar piso"])
            self.assertEqual(scope["value"]["domain"], "idealista.com")
            rewritten = json.loads((output / "01_company_analysis.json").read_text())
            self.assertEqual(rewritten["locked_target_scope"]["market"], "Spanish property portals")
            self.assertEqual(json.loads((raw / "01_company_ai_record.json").read_text()), {
                "answer": "saved",
            })

    def test_generated_notebook_adapter_passes_scope_and_outputs(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "competitive-visibility-idealista"
            raw = output / "raw"
            output.mkdir()
            raw.mkdir()
            messages = []
            namespace = {
                "LOCKED_TARGET_SCOPE": None,
                "run_company_stage_core": run_company_stage_core,
                "CompanyStagePorts": CompanyStagePorts,
                "CompanyIntake": Model,
                "BrandAnalysis": Model,
                "BuyerIntentKeyword": Model,
                "restore_locked_target_scope": lambda checkpoint, _brand, _settings:
                    dict(checkpoint["locked_target_scope"]),
                "model_to_dict": lambda item: vars(item).copy(),
                "clean_record_for_storage": lambda record: dict(record),
                "print_stage_success": messages.append,
            }

            def analyze(_settings):
                namespace["LOCKED_TARGET_SCOPE"] = {"market": "Spanish property portals"}
                return {
                    "intake": Model(
                        brand=Model(brand_name="Idealista", domain="old.example",
                                    official_url="https://old.example/"),
                        buyer_intent_keywords=[Model(keyword="comprar piso")],
                    ),
                    "record": {"answer": "saved"},
                }

            namespace["analyze_company_stage"] = analyze
            namespace["write_json"] = lambda path, data: write_json_with_scope(
                path, data, locked_target_scope=namespace["LOCKED_TARGET_SCOPE"]
            )
            script = (
                "async def adapter(settings, continuing, output_directory, "
                "raw_directory, run_timestamp, stage_started_at, stage_durations):\n"
                "    global LOCKED_TARGET_SCOPE\n"
                + COMPANY_STAGE_CALL_SOURCE
                + "\n    return target_brand, keyword_records, keywords\n"
            )
            exec(compile(script, "notebook-company-adapter", "exec"), namespace)
            durations = {}
            brand, records, keywords = asyncio.run(namespace["adapter"](
                self.settings, False, output, raw, self.timestamp,
                time.monotonic(), durations,
            ))
            self.assertEqual(brand.domain, "idealista.com")
            self.assertEqual([item.keyword for item in records], keywords)
            self.assertEqual(namespace["LOCKED_TARGET_SCOPE"]["domain"], "idealista.com")
            self.assertIn("company_analysis", durations)
            self.assertEqual(json.loads(
                (output / "01_company_analysis.json").read_text()
            )["locked_target_scope"]["domain"], "idealista.com")


if __name__ == "__main__":
    unittest.main()
