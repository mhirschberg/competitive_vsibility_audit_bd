"""The service and generated notebook share result-based usage accounting."""

import json
from pathlib import Path
import tempfile
import unittest

from audit_core.brightdata_usage import (
    DEFAULT_PRICE_PER_1000_RESULTS_USD, BrightDataUsageLedger,
)
from notebook_builder import (
    BRIGHTDATA_USAGE_END, BRIGHTDATA_USAGE_START, NOTEBOOK,
)


def bundled_ledger():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    cell = next(
        item for item in notebook["cells"]
        if item.get("metadata", {}).get("id") == "final-core"
    )
    source = "".join(cell["source"])
    embedded = source.split(BRIGHTDATA_USAGE_START, 1)[1].split(
        BRIGHTDATA_USAGE_END, 1
    )[0]
    namespace = {}
    exec(embedded, namespace)
    return namespace["BrightDataUsageLedger"]


def exercise_ledger(ledger_type):
    ledger = ledger_type()
    serp = ledger.start_usage_operation("Google SERP", expected_result_count=1)
    ledger.update_usage_operation(serp, status="success", result_count=1)
    race = ledger.start_usage_operation(
        "Google AI Mode", dataset_id="ai-dataset", expected_result_count=1
    )
    ledger.update_usage_operation(race, snapshot_id="race-1", status="triggered")
    reddit = ledger.start_usage_operation("Reddit posts")
    ledger.update_usage_operation(
        reddit, snapshot_id="reddit-1", status="triggered"
    )
    ledger.record_snapshot_results("reddit-1", 10)
    return ledger.usage_summary()


class BrightDataUsageTests(unittest.TestCase):
    def test_price_default_is_shared_with_the_standalone_notebook(self):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        cell = next(
            item for item in notebook["cells"]
            if item.get("metadata", {}).get("id") == "final-orchestration"
        )
        source = "".join(cell["source"])
        self.assertIn(
            "BRIGHT_DATA_PRICE_PER_1000_RESULTS_USD = "
            "DEFAULT_PRICE_PER_1000_RESULTS_USD",
            source,
        )
        self.assertEqual(DEFAULT_PRICE_PER_1000_RESULTS_USD, 1.5)

    def test_service_and_notebook_count_results_identically(self):
        service = exercise_ledger(BrightDataUsageLedger)
        notebook = exercise_ledger(bundled_ledger())
        self.assertEqual(service, notebook)
        self.assertEqual(service["data_operations_started"], 3)
        self.assertEqual(service["confirmed_result_records"], 11)
        self.assertEqual(service["expected_fixed_cardinality_results"], 1)
        self.assertEqual(service["estimated_billable_result_records"], 12)
        self.assertEqual(service["reddit_raw_result_records"], 10)
        self.assertEqual(service["estimated_cost_usd"], 0.018)

    def test_refresh_preserves_materializing_snapshots_and_marks_failures(self):
        class Ledger(BrightDataUsageLedger):
            def snapshot_status(self, snapshot_id):
                return {"status": {
                    "ready": "ready", "building": "ready", "failed": "failed"
                }[snapshot_id]}

            def download_snapshot(self, snapshot_id):
                if snapshot_id == "building":
                    return [{"status": "building"}]
                return [{"record": 1}, {"record": 2}]

        ledger = Ledger()
        for snapshot_id in ("ready", "building", "failed"):
            operation = ledger.start_usage_operation(
                "Google AI Mode", expected_result_count=1
            )
            ledger.update_usage_operation(
                operation, snapshot_id=snapshot_id, status="triggered"
            )
        ledger.refresh_usage_results()
        summary = ledger.usage_summary()
        self.assertEqual(summary["confirmed_result_records"], 2)
        self.assertEqual(summary["expected_fixed_cardinality_results"], 1)
        self.assertEqual(summary["failed_operations"], 1)
        self.assertEqual(summary["events"][1]["result_count"], None)

    def test_checkpoint_restore_does_not_duplicate_recovered_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usage.json"
            first = BrightDataUsageLedger()
            first.configure_usage_checkpoint(path)
            operation = first.start_usage_operation(
                "Google AI Mode", expected_result_count=1
            )
            first.update_usage_operation(
                operation, snapshot_id="saved-1", status="triggered"
            )
            restored = BrightDataUsageLedger()
            restored.configure_usage_checkpoint(path, restore=True)
            restored.record_recovered_snapshot("saved-1", 1)
            restored.record_recovered_snapshot("saved-1", 1)
            summary = restored.usage_summary()
            self.assertEqual(summary["data_operations_started"], 1)
            self.assertEqual(summary["confirmed_result_records"], 1)
            self.assertTrue(summary["checkpoint_history_complete"])


if __name__ == "__main__":
    unittest.main()
