"""Opt-in integration test against `supabase start`; never uses hosted credentials."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from uuid import UUID, uuid4
from concurrent.futures import ThreadPoolExecutor

import requests
from fastapi.testclient import TestClient

from hosted.api import create_app
from hosted.supabase_gateway import SupabaseGateway, TrialQuotaError


ROOT = Path(__file__).resolve().parents[1]


class DummyDispatcher:
    def __init__(self):
        self.dispatched = []

    def dispatch(self, audit_id):
        self.dispatched.append(audit_id)


@unittest.skipUnless(
    os.environ.get("RUN_SUPABASE_INTEGRATION") == "1",
    "Run explicitly against the disposable local Supabase stack",
)
class SupabaseLocalIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            ["npx", "--yes", "supabase", "status", "--output", "json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        status = json.loads(result.stdout)
        cls.url = status["API_URL"]
        if cls.url != "http://127.0.0.1:54321":
            raise AssertionError("Integration test requires the default local stack")
        cls.publishable_key = status["PUBLISHABLE_KEY"]
        cls.secret_key = status["SECRET_KEY"]

    def anonymous_session(self):
        response = requests.post(
            f"{self.url}/auth/v1/signup",
            headers={"apikey": self.publishable_key},
            json={},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        return payload["user"]["id"], payload["access_token"]

    def test_trial_limits_are_atomic_and_idempotent(self):
        # The API checks Google identity; this exercises the service-only SQL
        # admission function against a disposable local Auth user.
        user_id, _ = self.anonymous_session()
        gateway = SupabaseGateway(
            self.url, self.publishable_key, self.secret_key, allow_local_http=True
        )

        def request(request_id):
            return gateway.submit_trial_audit(
                p_user_id=user_id,
                p_client_request_id=str(request_id),
                p_company_name="Trial Company",
                p_company_domain="example.com",
                p_audit_focus="",
                p_country_code="DE",
                p_input_options={},
                p_engine_commit="integration-test",
                p_methodology_version="integration-test",
            )

        first_id = uuid4()
        second_id = uuid4()
        def attempt(request_id):
            try:
                return request(request_id)
            except TrialQuotaError as exc:
                return exc
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, [first_id, second_id]))
        # A concurrent second submission must fail the daily limit.
        self.assertEqual(sum(isinstance(r, TrialQuotaError) for r in results), 1)
        first_audit = next(r for r in results if not isinstance(r, TrialQuotaError))
        self.assertEqual(gateway.trial_status(UUID(user_id))["used"], 1)

        # Retry with the original request ID, then age the accepted row so the
        # following day's audit can run without waiting 24 real hours.
        # If the first of the two requests won, first_id is its idempotency key.
        winning_key = first_id if results[0] == first_audit else second_id
        self.assertEqual(request(winning_key), first_audit)
        for index in range(2):
            patch = requests.patch(
                f"{self.url}/rest/v1/audits",
                headers={"apikey": self.secret_key, "Content-Type": "application/json"},
                params={"id": f"eq.{first_audit}" if index == 0 else f"eq.{audit_id}"},
                json={"created_at": "2026-01-01T00:00:00Z"},
                timeout=10,
            )
            self.assertEqual(patch.status_code, 204, patch.text)
            last_request_id = uuid4()
            audit_id = request(last_request_id)
        self.assertEqual(gateway.trial_status(UUID(user_id))["used"], 3)
        with self.assertRaises(TrialQuotaError) as context:
            request(uuid4())
        self.assertEqual(context.exception.reason, "trial_total_limit")
        self.assertEqual(request(last_request_id), audit_id)

    def test_submit_rls_worker_and_private_artifact(self):
        user_a, token_a = self.anonymous_session()
        _, token_b = self.anonymous_session()
        gateway = SupabaseGateway(
            self.url,
            self.publishable_key,
            self.secret_key,
            allow_local_http=True,
        )
        self.assertEqual(str(gateway.authenticate(token_a)), user_a)
        workshop_id = str(uuid4())
        response = requests.post(
            f"{self.url}/rest/v1/workshops",
            headers={"apikey": self.secret_key},
            json={
                "id": workshop_id,
                "slug": f"integration-{uuid4().hex[:12]}",
                "name": "Integration test",
                "max_total_audits": 3,
                "max_concurrent_audits": 2,
                "max_audits_per_user": 2,
            },
            timeout=10,
        )
        self.assertEqual(response.status_code, 201)

        dispatcher = DummyDispatcher()
        client = TestClient(
            create_app(
                gateway=gateway,
                dispatcher=dispatcher,
                settings={
                    "ENGINE_COMMIT": "integration-test",
                    "METHODOLOGY_VERSION": "integration-test",
                },
            )
        )
        request_body = {
            "client_request_id": str(uuid4()),
            "company_name": "Example Company",
            "company_domain": "example.com",
            "audit_focus": "Sample product",
            "country_code": "DE",
            "workshop_id": workshop_id,
        }
        auth_a = {"Authorization": f"Bearer {token_a}"}
        auth_b = {"Authorization": f"Bearer {token_b}"}
        submitted = client.post("/audits", json=request_body, headers=auth_a)
        self.assertEqual(submitted.status_code, 202, submitted.text)
        audit_id = submitted.json()["audit_id"]
        self.assertEqual(submitted.json()["dispatch_state"], "started")
        self.assertEqual(len(dispatcher.dispatched), 1)
        duplicate = client.post("/audits", json=request_body, headers=auth_a)
        self.assertEqual(duplicate.status_code, 202, duplicate.text)
        self.assertEqual(duplicate.json()["audit_id"], audit_id)
        self.assertEqual(len(dispatcher.dispatched), 1)

        own = client.get(f"/audits/{audit_id}", headers=auth_a)
        other = client.get(f"/audits/{audit_id}", headers=auth_b)
        self.assertEqual(own.status_code, 200, own.text)
        self.assertEqual(other.status_code, 404, other.text)
        direct_write = requests.post(
            f"{self.url}/rest/v1/audit_events",
            headers={
                "apikey": self.publishable_key,
                "Authorization": f"Bearer {token_a}",
            },
            json={"audit_id": audit_id, "event_kind": "forged", "message": "x"},
            timeout=10,
        )
        self.assertIn(direct_write.status_code, (401, 403))

        claim = gateway.claim_audit(audit_id, f"local-integration-{uuid4()}")
        self.assertIsNotNone(claim)
        execution_id, claim_token = claim
        self.assertIsNone(gateway.claim_audit(audit_id, "duplicate"))
        self.assertTrue(gateway.heartbeat_audit(execution_id, claim_token))
        gateway.record_step(audit_id, "company_analysis", "Company analysis", "completed")
        gateway.record_event(audit_id, execution_id, "step_completed", "Ready")

        artifact_id = str(uuid4())
        object_path = f"audits/{audit_id}/{artifact_id}/report.txt"
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "report.txt"
            file_path.write_text("integration artifact", encoding="utf-8")
            gateway.upload_artifact(object_path, file_path, "text/plain")
        gateway.record_artifact(
            {
                "id": artifact_id,
                "audit_id": audit_id,
                "kind": "report_text",
                "bucket_id": "audit-artifacts",
                "object_path": object_path,
                "content_type": "text/plain",
                "size_bytes": len(b"integration artifact"),
            }
        )
        forbidden = client.get(
            f"/audits/{audit_id}/artifacts/{artifact_id}/download", headers=auth_b
        )
        self.assertEqual(forbidden.status_code, 404, forbidden.text)
        signed = client.get(
            f"/audits/{audit_id}/artifacts/{artifact_id}/download", headers=auth_a
        )
        self.assertEqual(signed.status_code, 200, signed.text)
        download = requests.get(signed.json()["url"], timeout=10)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, b"integration artifact")

        self.assertTrue(
            gateway.finish_audit(
                execution_id,
                claim_token,
                "completed",
                summary={"result": "ok"},
                usage_summary={"requests": 0},
                report_schema_version=1,
            )
        )
        finished = client.get(f"/audits/{audit_id}", headers=auth_a)
        self.assertEqual(finished.status_code, 200, finished.text)
        self.assertEqual(finished.json()["status"], "completed")
        self.assertEqual(len(finished.json()["artifacts"]), 1)


if __name__ == "__main__":
    unittest.main()
