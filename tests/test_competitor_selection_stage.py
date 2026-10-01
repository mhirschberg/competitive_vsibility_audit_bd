"""Stage 3 selection and social prefetch remain usable outside the notebook."""

import asyncio
import json
from pathlib import Path
import tempfile
import time
import unittest

from audit_core.competitor_selection_stage import (
    CompetitorSelectionStagePorts, run_competitor_selection_stage_core,
)
from notebook_builder import COMPETITOR_SELECTION_STAGE_CALL_SOURCE


class Model:
    def __init__(self, **values):
        self.__dict__.update(values)


class CompetitorSelectionStageTests(unittest.TestCase):
    def make_ports(self, calls, warnings, *, fallback=False, skipped=0):
        def select(target, candidates, keywords, locked_scope):
            calls.append(("select", target.brand_name, candidates, keywords, locked_scope))
            return {
                "selected": [Model(brand_name="Samsung", domain="samsung.com")],
                "rejected": [{"brand_name": "Not a competitor"}],
                "validation_results": [{"status": "success"}],
                "record": {"provider": "saved"},
                "used_fallback": fallback,
                "unvalidated_on_resume": skipped,
            }

        def write(path, data):
            calls.append(("write", path.name))
            path.write_text(json.dumps(data), encoding="utf-8")

        async def social(**kwargs):
            calls.append(("social", kwargs))

        return CompetitorSelectionStagePorts(
            select_competitors=select,
            configure_race_cache=lambda path, only_reuse: calls.append(
                ("cache", path.name, only_reuse)
            ),
            write_json=write,
            model_to_dict=lambda item: vars(item).copy(),
            clean_record=lambda record: dict(record),
            stage_warning=warnings.append,
            print_selected=lambda competitor: calls.append(
                ("selected", competitor.brand_name)
            ),
            social_notice=lambda: calls.append(("notice",)),
            start_reddit_prefetch=social,
        )

    def test_fresh_run_saves_selection_before_starting_social_prefetch(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            raw = output / "raw"
            raw.mkdir()
            calls, warnings = [], []
            target = Model(brand_name="Apple")

            async def run():
                result = await run_competitor_selection_stage_core(
                    target, ["candidate"], ["premium smartphone"],
                    locked_scope={"market_role": "manufacturer"},
                    continuing=False, output_directory=output,
                    raw_directory=raw, started_at=time.monotonic(),
                    include_reddit_analysis=True, audit_focus="iPhone",
                    ports=self.make_ports(calls, warnings),
                )
                await result["reddit_prefetch_task"]
                return result

            result = asyncio.run(run())
            self.assertEqual(warnings, [])
            self.assertEqual(result["selected_competitors"][0].brand_name, "Samsung")
            self.assertEqual(result["selection_result"]["validation_results"],
                             [{"status": "success"}])
            self.assertEqual(calls[0][0], "select")
            self.assertEqual(calls[0][4], {"market_role": "manufacturer"})
            self.assertLess(
                calls.index(("write", "03_competitor_selection.json")),
                calls.index(("notice",)),
            )
            self.assertLess(
                calls.index(("write", "03_selection_ai_record.json")),
                calls.index(("social", calls[-1][1])),
            )
            self.assertEqual(calls[-1][1]["audit_focus"], "iPhone")
            saved = json.loads((output / "03_competitor_selection.json").read_text())
            self.assertEqual(saved["selected_competitors"][0]["domain"], "samsung.com")
            self.assertEqual(saved["rejected_candidates"][0]["brand_name"],
                             "Not a competitor")
            self.assertEqual(saved["validation_results"][0]["status"], "success")
            self.assertEqual(json.loads(
                (raw / "03_selection_ai_record.json").read_text()
            ), {"provider": "saved"})

    def test_continuation_restores_cache_and_reports_missing_validation(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            raw = output / "raw"
            raw.mkdir()
            calls, warnings = [], []
            result = asyncio.run(run_competitor_selection_stage_core(
                Model(brand_name="Apple"), [], ["premium smartphone"],
                locked_scope={"market_role": "manufacturer"},
                continuing=True, output_directory=output, raw_directory=raw,
                started_at=time.monotonic(), include_reddit_analysis=False,
                audit_focus="", ports=self.make_ports(
                    calls, warnings, fallback=True, skipped=2,
                ),
            ))
            self.assertEqual(calls[1], ("cache", "google_ai_snapshot_cache.json", False))
            self.assertEqual(len(warnings), 2)
            self.assertIn("2 candidate(s)", warnings[0])
            self.assertIn("fallback", warnings[1])
            self.assertIsNone(result["reddit_prefetch_task"])
            self.assertFalse(any(call[0] == "social" for call in calls))

    def test_generated_notebook_adapter_passes_duration_warnings_and_task(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            raw = output / "raw"
            raw.mkdir()
            calls, displayed = [], []
            namespace = {
                "run_competitor_selection_stage_core": run_competitor_selection_stage_core,
                "CompetitorSelectionStagePorts": CompetitorSelectionStagePorts,
                "select_competitors_stage": lambda *_: {
                    "selected": [Model(brand_name="Samsung")],
                    "used_fallback": False,
                },
                "configure_google_ai_race_cache": lambda *args, **kwargs: None,
                "write_json": lambda path, data: path.write_text(json.dumps(data)),
                "model_to_dict": lambda item: vars(item).copy(),
                "clean_record_for_storage": lambda record: dict(record),
                "print_stage_warning": displayed.append,
                "console": Model(print=displayed.append),
                "start_reddit_discovery_prefetch": lambda **kwargs: None,
            }
            script = (
                "async def adapter(settings, target_brand, competitor_candidates, "
                "keywords, continuing, output_directory, raw_directory, "
                "stage_started_at, include_reddit_analysis, stage_durations, "
                "warnings):\n"
                "    company_stage = {'locked_scope': {'market_role': 'manufacturer'}}\n"
                + COMPETITOR_SELECTION_STAGE_CALL_SOURCE
                + "\n    return selected_competitors, selection_result, reddit_prefetch_task\n"
            )
            exec(compile(script, "notebook-competitor-adapter", "exec"), namespace)
            durations, warnings = {}, []
            selected, selection, task = asyncio.run(namespace["adapter"](
                {"audit_focus": "premium smartphone"}, Model(brand_name="Apple"),
                [], ["premium smartphone"], False, output, raw,
                time.monotonic(), False, durations, warnings,
            ))
            self.assertEqual(selected[0].brand_name, "Samsung")
            self.assertEqual(selection["selected"][0].brand_name, "Samsung")
            self.assertIsNone(task)
            self.assertIn("competitor_selection", durations)
            self.assertEqual(warnings, [])
            self.assertTrue((output / "03_competitor_selection.json").is_file())
            self.assertTrue(any("Samsung" in item for item in displayed))


if __name__ == "__main__":
    unittest.main()
