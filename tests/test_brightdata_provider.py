"""The standalone service provider client reuses shared result accounting."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from audit_core.brightdata_transport import CHATGPT_DATASET_ID
from hosted.brightdata_provider import BrightDataProviderClient


class FakeResponse:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.text = json.dumps(data)

    def json(self):
        return self.data


class BrightDataProviderTests(unittest.TestCase):
    def test_trigger_wait_and_download_share_result_ledger(self):
        client = BrightDataProviderClient("test-token", "test-zone", "US")
        self.assertEqual(
            client.headers["Authorization"], "Bearer test-token"
        )
        with tempfile.TemporaryDirectory() as directory:
            client.configure_usage_checkpoint(
                Path(directory) / "usage.json"
            )
            with patch(
                "audit_core.brightdata_transport.requests.post",
                return_value=FakeResponse({"snapshot_id": "snapshot-1"}),
            ) as post:
                snapshot_id = client.trigger_dataset(
                    CHATGPT_DATASET_ID,
                    [{"prompt": "neutral question"}],
                )
            self.assertEqual(snapshot_id, "snapshot-1")
            self.assertEqual(
                post.call_args.kwargs["headers"]["Authorization"],
                "Bearer test-token",
            )

            with patch(
                "audit_core.brightdata_transport.requests.get",
                side_effect=[
                    FakeResponse({"status": "ready"}),
                    FakeResponse([{"answer_text": "A measured answer."}]),
                ],
            ):
                records = client.wait_for_snapshot(
                    snapshot_id, timeout_seconds=2, poll_seconds=0
                )

            self.assertEqual(
                client.answer_text(records[0]), "A measured answer."
            )
            summary = client.usage_summary()
            self.assertEqual(summary["accepted_operations"], 1)
            self.assertEqual(summary["confirmed_result_records"], 1)
            self.assertAlmostEqual(summary["estimated_cost_usd"], 0.0015)

    def test_service_provider_module_has_no_notebook_runtime_dependency(self):
        from hosted import brightdata_provider

        self.assertNotIn("notebook", brightdata_provider.__dict__)
        self.assertNotIn("app", brightdata_provider.__dict__)

    def test_measured_engine_race_uses_provider_label_and_accounting(self):
        client = BrightDataProviderClient("test-token", "test-zone", "US")
        client.trigger_dataset = lambda dataset, payload: "snapshot-ai"
        client.snapshot_status = lambda _snapshot: {"status": "ready"}
        client.download_snapshot = lambda _snapshot: [{
            "answer_text": "For the United States market, Brand A is a good option.",
            "citations": [{"url": "https://source.example/page?ref=1"}],
            "web_search_triggered": True,
        }]
        counted = []
        client.record_snapshot_results = lambda snapshot, count: counted.append(
            (snapshot, count)
        )

        result = client.race_ai_engine(
            "chatgpt", "best product in the category", redundancy=1,
            timeout_seconds=2,
        )

        self.assertEqual(result["engine_name"], "ChatGPT")
        self.assertEqual(result["winner_snapshot_id"], "snapshot-ai")
        self.assertEqual(counted, [("snapshot-ai", 1)])
        self.assertTrue(result["market_acknowledged"])
        self.assertEqual(result["country_transport_mode"], "country_field_and_prompt")

    def test_gemini_payload_omits_country_for_prompt_only_markets(self):
        client = BrightDataProviderClient("test-token", "test-zone", "DE")
        dataset, payload = client._engine_payload(
            "gemini", "question", request_index=1
        )
        self.assertEqual(dataset, "gd_mbz66arm2mf9cu856y")
        self.assertNotIn("country", payload["input"][0])

    def test_google_search_engine_selection_caches_health_check_result(self):
        client = BrightDataProviderClient("test-token", "test-zone", "US")
        calls = []

        def fake_serp(**kwargs):
            calls.append(kwargs)
            return {
                "query": kwargs["query"],
                "engine": "google",
                "results": [
                    {"rank": index, "domain": f"site{index}.example",
                     "url": f"https://site{index}.example/"}
                    for index in range(1, 6)
                ],
            }

        client.markdown_serp = fake_serp
        selected = client.choose_search_engine(
            "test query", requested_engine="google"
        )
        cached = client.search_serp("test query")

        self.assertEqual(selected, "google")
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(cached["results"]), 5)


if __name__ == "__main__":
    unittest.main()
