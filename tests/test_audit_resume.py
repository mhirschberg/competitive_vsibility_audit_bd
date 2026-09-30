"""Interrupted Colab audits reuse checkpoints and already-triggered snapshots."""

import hashlib
import json
from pathlib import Path
import re
import tempfile
import threading
import unittest
import zipfile
from concurrent.futures import as_completed

from audit_core.brightdata_usage import BrightDataUsageLedger
from tests.test_google_ai_timeout_safety import (
    FakeClock,
    ImmediateExecutor,
    definition,
)


class AuditResumeTests(unittest.TestCase):
    def test_usage_events_survive_runtime_restart(self):
        namespace = {
            "Path": Path, "json": json, "Lock": threading.Lock,
            "BrightDataUsageLedger": BrightDataUsageLedger,
        }
        exec(definition("BrightDataClient"), namespace)
        client_class = namespace["BrightDataClient"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usage.json"
            first = client_class("token", "zone")
            first.configure_usage_checkpoint(path)
            operation_id = first.start_usage_operation(
                "Google AI Mode", expected_result_count=1
            )
            first.update_usage_operation(
                operation_id, snapshot_id="snap-1", status="triggered"
            )
            second = client_class("token", "zone")
            second.configure_usage_checkpoint(path, restore=True)
            second.record_snapshot_results("snap-1", 1)
            self.assertEqual(second.usage_summary()["confirmed_result_records"], 1)
            self.assertTrue(second.usage_summary()["checkpoint_history_complete"])

            legacy = client_class("token", "zone")
            legacy.configure_usage_checkpoint(
                Path(directory) / "legacy.json", restore=True
            )
            self.assertFalse(legacy.usage_summary()["checkpoint_history_complete"])

    def test_legacy_resume_cost_is_labeled_lower_bound(self):
        namespace = {}
        exec(definition("build_bright_data_usage_section"), namespace)
        report = namespace["build_bright_data_usage_section"]({
            "checkpoint_history_complete": False,
            "estimated_billable_result_records": 27,
            "estimated_cost_usd": 0.0405,
            "price_per_1000_results_usd": 1.5,
        })
        self.assertIn("At least 27", report)
        self.assertIn("legacy checkpoint", report)

    def test_snapshot_cache_persists_and_deduplicates_ids(self):
        namespace = {
            "Path": Path,
            "hashlib": hashlib,
            "json": json,
            "threading": threading,
        }
        namespace.update({
            "_GOOGLE_AI_RACE_CACHE_PATH": None,
            "_GOOGLE_AI_RACE_CACHE_LOCK": threading.RLock(),
            "_GOOGLE_AI_ONLY_REUSE": False,
        })
        for name in (
            "configure_google_ai_race_cache",
            "google_ai_race_cache_key",
            "read_google_ai_race_cache",
            "cached_google_ai_snapshot_ids",
            "remember_google_ai_snapshot",
        ):
            exec(definition(name), namespace)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw" / "google_ai_snapshot_cache.json"
            namespace["configure_google_ai_race_cache"](path, only_reuse=True)
            remember = namespace["remember_google_ai_snapshot"]
            remember("candidate A", "snap-1")
            remember("candidate A", "snap-1")
            remember("candidate A", "snap-2")
            remember("candidate B", "snap-3")
            self.assertEqual(
                namespace["cached_google_ai_snapshot_ids"]("candidate A"),
                ["snap-1", "snap-2"],
            )
            self.assertEqual(len(json.loads(path.read_text())), 2)
            self.assertNotIn("candidate A", path.read_text())

    def test_saved_race_does_not_trigger_new_snapshots(self):
        clock = FakeClock()
        triggers = []

        class Client:
            def log(self, *_args):
                pass

            def snapshot_status(self, _snapshot_id):
                return {"status": "ready"}

            def download_snapshot(self, _snapshot_id):
                return [{"answer_text": '{"candidate_name":"Samsung"}'}]

            def record_snapshot_results(self, *_args):
                pass

            def answer_text(self, record):
                return record["answer_text"]

        namespace = {
            "time": clock,
            "identify_google_ai_research_task": lambda _prompt: "candidate_validation_json",
            "_GOOGLE_AI_RACE_SEMAPHORE": threading.Semaphore(1),
            "_GOOGLE_AI_ONLY_REUSE": True,
            "cached_google_ai_snapshot_ids": lambda _prompt: ["saved-1"],
            "GOOGLE_AI_RESEARCH_REDUNDANCY": 3,
            "GOOGLE_AI_RACE_POLL_SECONDS": 3,
            "GOOGLE_AI_RESEARCH_RACE_HISTORY": [],
            "FAILED_STATUSES": {"failed", "error"},
            "GoogleAIRaceExecutor": ImmediateExecutor,
            "google_ai_as_completed": as_completed,
            "trigger_google_ai_race_snapshot": lambda *_args: triggers.append(1),
            "remember_google_ai_snapshot": lambda *_args: None,
            "google_ai_snapshot_is_materializing": lambda _records: False,
            "validate_google_ai_research_answer": lambda **_kwargs: {
                "valid": True,
                "task_type": "candidate_validation_json",
            },
        }
        exec(definition("race_google_ai_mode"), namespace)
        result = namespace["race_google_ai_mode"](Client(), "same prompt", 10)
        self.assertEqual(result["_google_ai_race"]["winner_snapshot_id"], "saved-1")
        self.assertEqual(triggers, [])

    def test_old_error_snapshot_is_matched_by_input_prompt(self):
        remembered = []

        class Client:
            def download_snapshot(self, snapshot_id):
                self_id = snapshot_id
                return [{
                    "error_code": "cdp_disconnect",
                    "input": {"prompt": "original candidate prompt"},
                    "snapshot_id": self_id,
                }]

            def record_recovered_snapshot(self, *_args):
                pass

        namespace = {
            "re": re,
            "bd_client": Client(),
            "read_google_ai_race_cache": lambda: {},
            "remember_google_ai_snapshot": lambda prompt, sid: remembered.append((prompt, sid)),
            "GOOGLE_AI_MODE_DATASET_ID": "dataset",
        }
        exec(definition("import_google_ai_snapshot_ids"), namespace)
        imported = namespace["import_google_ai_snapshot_ids"](
            "sd_one sd_one, sd_two"
        )
        self.assertEqual(imported, 2)
        self.assertEqual(remembered[0], ("original candidate prompt", "sd_one"))

    def test_resume_without_saved_ids_refuses_new_requests(self):
        triggers = []

        class Client:
            def log(self, *_args):
                pass

        namespace = {
            "time": FakeClock(),
            "identify_google_ai_research_task": lambda _prompt: "candidate_validation_json",
            "_GOOGLE_AI_RACE_SEMAPHORE": threading.Semaphore(1),
            "_GOOGLE_AI_ONLY_REUSE": True,
            "cached_google_ai_snapshot_ids": lambda _prompt: [],
            "GOOGLE_AI_RESEARCH_REDUNDANCY": 3,
            "GoogleAIRaceExecutor": ImmediateExecutor,
            "google_ai_as_completed": as_completed,
            "trigger_google_ai_race_snapshot": lambda *_args: triggers.append(1),
            "BrightDataAPIError": RuntimeError,
        }
        exec(definition("race_google_ai_mode"), namespace)
        with self.assertRaisesRegex(RuntimeError, "will not launch replacement"):
            namespace["race_google_ai_mode"](Client(), "candidate prompt", 10)
        self.assertEqual(triggers, [])

    def test_resume_chooses_matching_incomplete_run(self):
        namespace = {"Path": Path, "json": json, "zipfile": zipfile}
        exec(definition("find_latest_audit_to_continue"), namespace)
        settings = {
            "company_domain": "apple.com",
            "audit_focus": "iPhone",
            "country": "US",
            "search_engine": "auto",
            "serp_zone": "serp_api2",
            "include_reddit_analysis": False,
        }
        with tempfile.TemporaryDirectory() as root:
            candidate = Path(root) / "competitive-visibility-apple-20260928"
            candidate.mkdir()
            (candidate / "01_company_analysis.json").write_text(
                json.dumps({"brand": {"domain": "apple.com"}})
            )
            (candidate / "02_serp_results.json").write_text("{}")
            (candidate / "00_run_settings.json").write_text(json.dumps(settings))
            other = Path(root) / "competitive-visibility-other"
            other.mkdir()
            (other / "01_company_analysis.json").write_text(
                json.dumps({"brand": {"domain": "other.com"}})
            )
            (other / "02_serp_results.json").write_text("{}")
            selected = namespace["find_latest_audit_to_continue"](settings, root)
            self.assertEqual(selected, candidate)
            (candidate / "06_competitive_visibility_audit.json").write_text("{}")
            with self.assertRaises(FileNotFoundError):
                namespace["find_latest_audit_to_continue"](settings, root)

            archive_path = Path(root) / "competitive-visibility-restored.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    "01_company_analysis.json",
                    json.dumps({"brand": {"domain": "apple.com"}}),
                )
                archive.writestr("02_serp_results.json", "{}")
                archive.writestr("00_run_settings.json", json.dumps(settings))
            restored = namespace["find_latest_audit_to_continue"](settings, root)
            self.assertEqual(restored.name, "competitive-visibility-restored")
            self.assertTrue((restored / "02_serp_results.json").is_file())

    def test_resume_selector_skips_candidates_without_snapshots(self):
        source = definition("select_competitors_stage", last=True)
        self.assertIn("only_reuse=_GOOGLE_AI_ONLY_REUSE", source)
        self.assertIn("cached_research_snapshot_ids", source)
        self.assertIn("select_competitors_core", source)


if __name__ == "__main__":
    unittest.main()
