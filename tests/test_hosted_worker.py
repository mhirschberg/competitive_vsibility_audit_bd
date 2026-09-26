import unittest
from unittest.mock import patch
from uuid import UUID
import subprocess

from hosted.worker import run_worker


AUDIT_ID = UUID("20000000-0000-0000-0000-000000000001")
EXECUTION_ID = UUID("50000000-0000-0000-0000-000000000001")
CLAIM_TOKEN = UUID("60000000-0000-0000-0000-000000000001")


class FakeWorkerGateway:
    def __init__(self):
        self.claim = (EXECUTION_ID, CLAIM_TOKEN)
        self.uploads = []
        self.artifacts = []
        self.steps = []
        self.events = []
        self.usage_rows = []
        self.finishes = []

    def claim_audit(self, audit_id, platform_execution_id):
        assert audit_id == AUDIT_ID
        return self.claim

    def get_audit(self, audit_id):
        return {
            "workspace_id": "10000000-0000-0000-0000-000000000001",
            "company_name": "Rayner",
            "company_domain": "rayner.com",
            "audit_focus": "RayOne Galaxy",
            "country_code": "GB",
            "input_options": {"search_engine": "auto", "social_sources": ["reddit"]},
        }

    def heartbeat_audit(self, execution_id, claim_token):
        return True

    def record_step(self, audit_id, step_key, label, status):
        self.steps.append((step_key, status))

    def record_event(self, audit_id, execution_id, kind, message, **kwargs):
        self.events.append((kind, message))

    def upload_artifact(self, object_path, file_path, content_type):
        self.uploads.append((object_path, file_path.read_bytes()))

    def record_artifact(self, metadata):
        self.artifacts.append(metadata)

    def record_usage_operations(self, rows):
        self.usage_rows = rows

    def finish_audit(self, execution_id, claim_token, outcome, **kwargs):
        self.finishes.append((outcome, kwargs))
        return True


SUCCESS_RUNNER = """
import json
from pathlib import Path
print('[1/2] Company analysis and buyer keywords', flush=True)
print('[2/2] Final report and export', flush=True)
output = Path('competitive-visibility-test')
output.mkdir()
report = {
    'target': {'brand_name': 'Rayner'},
    'competitor_selection': {'selected': [{'brand_name': 'Brand B', 'domain': 'b.example'}]},
    'warnings': [],
    'bright_data_usage': {
        'price_per_1000_results_usd': 1.5,
        'confirmed_result_records': 3,
        'events': [
            {'operation_id': 1, 'operation': 'SERP', 'status': 'success',
             'input_count': 1, 'result_count': 1},
            {'operation_id': 2, 'operation': 'Reddit snapshot', 'status': 'triggered',
             'input_count': 1, 'expected_result_count': 2},
            {'operation_id': 3, 'operation': 'Failed snapshot', 'status': 'failed',
             'input_count': 1, 'expected_result_count': 10},
        ],
    },
}
(output / '06_competitive_visibility_audit.json').write_text(json.dumps(report))
"""


class HostedWorkerTests(unittest.TestCase):
    def setUp(self):
        self.gateway = FakeWorkerGateway()

    def test_success_uploads_report_and_counts_all_operations(self):
        arguments = []

        def runner_source(*args):
            arguments.append(args)
            return SUCCESS_RUNNER

        result = run_worker(
            self.gateway,
            AUDIT_ID,
            runner_source_factory=runner_source,
            heartbeat_interval=3600,
        )
        self.assertEqual(result, 0)
        self.assertEqual(arguments[0][0:4], ("Rayner", "rayner.com", "RayOne Galaxy", "GB"))
        self.assertTrue(arguments[0][5])  # Reddit selected.
        self.assertEqual(len(self.gateway.uploads), 2)  # Log and JSON.
        self.assertEqual(len(self.gateway.usage_rows), 3)
        self.assertEqual(self.gateway.usage_rows[0]["confirmed_result_count"], 1)
        self.assertIsNone(self.gateway.usage_rows[1]["confirmed_result_count"])
        self.assertTrue(self.gateway.usage_rows[1]["accepted"])
        self.assertFalse(self.gateway.usage_rows[2]["accepted"])
        self.assertIsNone(self.gateway.usage_rows[2]["estimated_cost_usd"])
        self.assertEqual(self.gateway.finishes[0][0], "completed")
        self.assertEqual(self.gateway.finishes[0][1]["summary"]["target_name"], "Rayner")

    def test_duplicate_cloud_run_invocation_does_no_paid_work(self):
        self.gateway.claim = None

        def should_not_run(*args):
            self.fail("duplicate invocation built a runner")

        result = run_worker(
            self.gateway, AUDIT_ID, runner_source_factory=should_not_run
        )
        self.assertEqual(result, 0)
        self.assertEqual(self.gateway.uploads, [])

    def test_failed_runner_keeps_log_and_marks_audit_failed(self):
        result = run_worker(
            self.gateway,
            AUDIT_ID,
            runner_source_factory=lambda *args: "import sys\nprint('failed', flush=True)\nsys.exit(4)\n",
            heartbeat_interval=3600,
        )
        self.assertEqual(result, 1)
        self.assertEqual(len(self.gateway.uploads), 1)
        self.assertEqual(self.gateway.finishes[0][0], "failed")

    def test_worker_exception_terminates_paid_runner(self):
        original_popen = subprocess.Popen
        children = []

        def capture_popen(*args, **kwargs):
            child = original_popen(*args, **kwargs)
            children.append(child)
            return child

        def fail_to_record_step(*args):
            raise RuntimeError("simulated unexpected database error")

        self.gateway.record_step = fail_to_record_step
        source = (
            "import time\n"
            "print('[1/2] Working', flush=True)\n"
            "time.sleep(60)\n"
        )
        with patch("hosted.worker.subprocess.Popen", side_effect=capture_popen):
            with self.assertRaises(RuntimeError):
                run_worker(
                    self.gateway,
                    AUDIT_ID,
                    runner_source_factory=lambda *args: source,
                    heartbeat_interval=3600,
                )
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())
        self.assertEqual(self.gateway.finishes[0][0], "failed")


if __name__ == "__main__":
    unittest.main()
