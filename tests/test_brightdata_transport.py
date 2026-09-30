"""The effective Bright Data snapshot transport is shared and network-free in tests."""

import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from audit_core import brightdata_transport as transport
from notebook_builder import (
    BRIGHTDATA_TRANSPORT_END, BRIGHTDATA_TRANSPORT_START, NOTEBOOK,
)


class Response:
    def __init__(self, data=None, *, text=None, status=200):
        self.data = data
        self.text = json.dumps(data) if text is None else text
        self.status_code = status
        self.ok = 200 <= status < 300

    def json(self):
        if self.data is None:
            raise ValueError("not JSON")
        return self.data


class BrightDataTransportTests(unittest.TestCase):
    def test_generated_notebook_embeds_exact_transport_source(self):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        cell = next(
            item for item in notebook["cells"]
            if item.get("metadata", {}).get("id") == "final-core"
        )
        source = "".join(cell["source"])
        embedded = source.split(BRIGHTDATA_TRANSPORT_START, 1)[1].split(
            BRIGHTDATA_TRANSPORT_END, 1
        )[0].strip()
        self.assertEqual(
            embedded,
            (Path(NOTEBOOK).parent / "audit_core" / "brightdata_transport.py")
            .read_text(encoding="utf-8").strip(),
        )
        self.assertIn(
            "BrightDataClient.wait_for_snapshot = wait_for_snapshot", source
        )

    def test_decoder_accepts_ndjson_and_rejects_empty_response(self):
        data = transport.decode_bright_data_response(
            Response(text='{"one": 1}\n{"two": 2}'), "fixture"
        )
        self.assertEqual(data, [{"one": 1}, {"two": 2}])
        with self.assertRaisesRegex(transport.BrightDataAPIError, "empty response"):
            transport.decode_bright_data_response(Response(text=""), "fixture")

    def test_status_and_download_handle_transient_provider_responses(self):
        logs = []
        client = SimpleNamespace(
            headers={"Authorization": "Bearer fixture"},
            log=lambda *args: logs.append(args),
            normalize_records=lambda data: data if isinstance(data, list) else [data],
        )
        with mock.patch.object(
            transport.requests, "get",
            side_effect=[Response({"status": "ready"}),
                         Response(text=""), Response([{"answer": "yes"}])],
        ), mock.patch.object(transport.time, "sleep") as sleep:
            status = transport.reliable_snapshot_status(client, "snap-1")
            records = transport.reliable_download_snapshot(client, "snap-1")
        self.assertEqual(status["status"], "ready")
        self.assertEqual(records, [{"answer": "yes"}])
        sleep.assert_called_once_with(3)
        self.assertEqual(len(logs), 1)

    def test_wait_ignores_materializing_record_then_counts_result(self):
        records = iter([[{"status": "building"}], [{"answer": "ready"}]])
        counted = []
        client = SimpleNamespace(
            debug=False,
            snapshot_status=lambda _snapshot: {"status": "ready"},
            download_snapshot=lambda _snapshot: next(records),
            record_snapshot_results=lambda *args: counted.append(args),
        )
        with mock.patch.object(transport.time, "sleep") as sleep:
            result = transport.wait_for_snapshot(
                client, "snap-2", timeout_seconds=60, poll_seconds=2
            )
        self.assertEqual(result, [{"answer": "ready"}])
        self.assertEqual(counted, [("snap-2", 1)])
        sleep.assert_called_once_with(2)

    def test_trigger_records_expected_results_not_just_request_count(self):
        operations = []

        class Client:
            headers = {}

            def start_usage_operation(self, *args, **kwargs):
                operations.append(("start", args, kwargs))
                return 1

            def update_usage_operation(self, *args, **kwargs):
                operations.append(("update", args, kwargs))

        payload = [{"prompt": "one"}, {"prompt": "two"}]
        with mock.patch.object(
            transport.requests, "post", return_value=Response({"snapshot_id": "s"})
        ):
            snapshot = transport.reliable_trigger_dataset(
                Client(), transport.GOOGLE_AI_MODE_DATASET_ID, payload
            )
        self.assertEqual(snapshot, "s")
        self.assertEqual(operations[0][2]["expected_result_count"], 2)
        self.assertEqual(operations[1][2]["status"], "triggered")


if __name__ == "__main__":
    unittest.main()
