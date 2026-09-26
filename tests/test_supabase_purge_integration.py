"""Opt-in end-to-end purge test against only the disposable local Supabase stack."""

import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import requests

from hosted.purge import purge_once
from hosted.supabase_gateway import SubmissionError, SupabaseGateway


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(
    os.environ.get("RUN_SUPABASE_PURGE_INTEGRATION") == "1",
    "Run explicitly against the disposable local Supabase stack",
)
class SupabasePurgeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            ["npx", "--yes", "supabase", "status", "--output", "json"],
            cwd=ROOT, capture_output=True, text=True, check=True, timeout=30,
        )
        status = json.loads(result.stdout)
        cls.url = status["API_URL"]
        if cls.url != "http://127.0.0.1:54321":
            raise AssertionError("Purge integration test requires the local stack")
        cls.publishable_key = status["PUBLISHABLE_KEY"]
        cls.secret_key = status["SECRET_KEY"]

    def service_request(self, method, path, **kwargs):
        headers = {"apikey": self.secret_key, "Prefer": "return=representation"}
        headers.update(kwargs.pop("headers", {}))
        response = requests.request(
            method, f"{self.url}{path}", headers=headers, timeout=20, **kwargs
        )
        self.assertTrue(response.ok, response.text)
        return response

    def gateway(self):
        return SupabaseGateway(
            self.url, self.publishable_key, self.secret_key,
            allow_local_http=True,
        )

    def test_organizer_can_set_retention_only_before_closing(self):
        organizer = self.service_request(
            "POST", "/auth/v1/admin/users", json={
                "email": f"purge-organizer-{uuid4().hex}@example.invalid",
                "password": uuid4().hex,
                "email_confirm": True,
            },
        ).json()
        organizer_id = organizer["id"]
        team_id = str(uuid4())
        workshop_id = str(uuid4())
        future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        self.service_request("POST", "/rest/v1/workspaces", json={
            "id": team_id, "kind": "team", "name": "Retention fixture",
            "created_by": organizer_id,
        })
        self.service_request("POST", "/rest/v1/workspace_members", json={
            "workspace_id": team_id, "user_id": organizer_id, "role": "owner",
        })
        self.service_request("POST", "/rest/v1/workshops", json={
            "id": workshop_id, "organizer_workspace_id": team_id,
            "slug": f"retention-fixture-{uuid4().hex[:12]}",
            "name": "Retention fixture", "closes_at": future,
            "max_total_audits": 2, "max_concurrent_audits": 1,
            "max_audits_per_user": 1,
        })
        gateway = self.gateway()
        self.assertEqual(str(gateway.admin_set_workshop_retention(
            p_user_id=organizer_id, p_workshop_id=workshop_id, p_hours=24,
        )), workshop_id)
        workshop = self.service_request(
            "GET", "/rest/v1/workshops",
            params={"id": f"eq.{workshop_id}"},
        ).json()[0]
        self.assertEqual(workshop["anonymous_retention_hours"], 24)
        listing = gateway.admin_list_workshops(UUID(organizer_id))
        self.assertEqual(next(
            row["anonymous_retention_hours"]
            for row in listing["workshops"] if row["id"] == workshop_id
        ), 24)
        self.service_request(
            "PATCH", "/rest/v1/workshops",
            params={"id": f"eq.{workshop_id}"},
            json={"closes_at": past},
        )
        with self.assertRaises(SubmissionError):
            gateway.admin_set_workshop_retention(
                p_user_id=organizer_id, p_workshop_id=workshop_id,
                p_hours=12,
            )

    def test_expired_anonymous_report_is_removed_but_totals_remain(self):
        existing_audit_ids = {
            row["id"] for row in self.service_request(
                "GET", "/rest/v1/audits", params={"select": "id"},
            ).json()
        }
        sign_in = requests.post(
            f"{self.url}/auth/v1/signup",
            headers={"apikey": self.publishable_key},
            json={}, timeout=10,
        )
        sign_in.raise_for_status()
        user_id = sign_in.json()["user"]["id"]
        registered = self.service_request(
            "POST", "/auth/v1/admin/users", json={
                "email": f"purge-registered-{uuid4().hex}@example.invalid",
                "password": uuid4().hex,
                "email_confirm": True,
            },
        ).json()
        registered_user_id = registered["id"]
        workspace_id = str(uuid4())
        registered_workspace_id = str(uuid4())
        workshop_id = str(uuid4())
        audit_id = str(uuid4())
        registered_audit_id = str(uuid4())
        execution_id = str(uuid4())
        old = (datetime.now(timezone.utc) - timedelta(hours=80)).isoformat()
        finished = (datetime.now(timezone.utc) - timedelta(hours=75)).isoformat()
        self.service_request("POST", "/rest/v1/workspaces", json={
            "id": workspace_id, "kind": "personal", "name": "Purge fixture",
            "created_by": user_id,
        })
        self.service_request("POST", "/rest/v1/workspace_members", json={
            "workspace_id": workspace_id, "user_id": user_id, "role": "owner",
        })
        self.service_request("POST", "/rest/v1/workspaces", json={
            "id": registered_workspace_id, "kind": "personal",
            "name": "Registered fixture", "created_by": registered_user_id,
        })
        self.service_request("POST", "/rest/v1/workspace_members", json={
            "workspace_id": registered_workspace_id,
            "user_id": registered_user_id, "role": "owner",
        })
        self.service_request("POST", "/rest/v1/workshops", json={
            "id": workshop_id, "slug": f"purge-fixture-{uuid4().hex[:12]}",
            "name": "Disposable purge fixture", "closes_at": old,
            "anonymous_retention_hours": 48, "max_total_audits": 2,
            "max_concurrent_audits": 1, "max_audits_per_user": 1,
        })
        self.service_request("POST", "/rest/v1/audits", json={
            "id": audit_id, "workspace_id": workspace_id,
            "workshop_id": workshop_id, "created_by": user_id,
            "client_request_id": str(uuid4()), "company_name": "Fixture",
            "company_domain": "example.com", "country_code": "DE",
            "engine_commit": "fixture", "methodology_version": "fixture",
            "status": "completed", "created_at": old, "started_at": old,
            "finished_at": finished, "updated_at": finished,
        })
        self.service_request("POST", "/rest/v1/audits", json={
            "id": registered_audit_id,
            "workspace_id": registered_workspace_id,
            "workshop_id": workshop_id, "created_by": registered_user_id,
            "client_request_id": str(uuid4()), "company_name": "Preserved",
            "company_domain": "example.org", "country_code": "DE",
            "engine_commit": "fixture", "methodology_version": "fixture",
            "status": "completed", "created_at": old, "started_at": old,
            "finished_at": finished, "updated_at": finished,
        })
        self.service_request("POST", "/rest/v1/audit_executions", json={
            "id": execution_id, "audit_id": audit_id, "attempt_number": 1,
            "status": "succeeded", "started_at": old, "finished_at": finished,
        })
        self.service_request("POST", "/rest/v1/brightdata_operations", json={
            "audit_id": audit_id, "execution_id": execution_id,
            "source_operation_id": 1, "operation_name": "fixture search",
            "operation_status": "completed", "accepted": True,
            "input_count": 1, "confirmed_result_count": 5,
            "estimated_cost_usd": 0.0075,
        })
        gateway = self.gateway()
        object_path = f"workspaces/{workspace_id}/audits/{audit_id}/report.txt"
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.txt"
            report.write_text("disposable purge fixture", encoding="utf-8")
            gateway.upload_artifact(object_path, report, "text/plain")
        gateway.record_artifact({
            "audit_id": audit_id, "kind": "report_text",
            "object_path": object_path, "content_type": "text/plain",
            "size_bytes": len(b"disposable purge fixture"),
        })

        preview = purge_once(gateway, dry_run=True, workshop_ids=[workshop_id])
        self.assertEqual(preview["audits_planned"], 1)
        self.assertEqual(preview["objects_planned"], 1)
        self.assertEqual(preview["audits_deleted"], 0)
        self.assertEqual(len(self.service_request(
            "GET", "/rest/v1/audits", params={"id": f"eq.{audit_id}"}
        ).json()), 1)

        completed = purge_once(gateway, workshop_ids=[workshop_id])
        self.assertEqual(completed["audits_deleted"], 1)
        self.assertEqual(completed["workshops_completed"], 1)
        self.assertEqual(self.service_request(
            "GET", "/rest/v1/audits", params={"id": f"eq.{audit_id}"}
        ).json(), [])
        self.assertEqual(len(self.service_request(
            "GET", "/rest/v1/audits",
            params={"id": f"eq.{registered_audit_id}"},
        ).json()), 1)
        remaining_audit_ids = {
            row["id"] for row in self.service_request(
                "GET", "/rest/v1/audits", params={"select": "id"},
            ).json()
        }
        self.assertTrue(existing_audit_ids.issubset(remaining_audit_ids))
        self.assertEqual(self.service_request(
            "GET", "/rest/v1/workspaces", params={"id": f"eq.{workspace_id}"}
        ).json(), [])
        totals = self.service_request(
            "GET", "/rest/v1/workshop_purge_totals",
            params={"workshop_id": f"eq.{workshop_id}"},
        ).json()[0]
        self.assertEqual(totals["submitted_audits"], 1)
        self.assertEqual(totals["completed_audits"], 1)
        self.assertEqual(totals["brightdata_operations"], 1)
        self.assertEqual(totals["brightdata_confirmed_results"], 5)
        self.assertIsNotNone(self.service_request(
            "GET", "/rest/v1/workshops", params={"id": f"eq.{workshop_id}"}
        ).json()[0]["purged_at"])
        auth_user = requests.get(
            f"{self.url}/auth/v1/admin/users/{user_id}",
            headers={"apikey": self.secret_key}, timeout=10,
        )
        self.assertEqual(auth_user.status_code, 404)
        storage_object = requests.get(
            f"{self.url}/storage/v1/object/audit-artifacts/{object_path}",
            headers={"apikey": self.secret_key}, timeout=10,
        )
        # Supabase Storage uses 400 with a not-found payload for this route.
        self.assertIn(storage_object.status_code, (400, 404))
        self.assertIn("not found", storage_object.text.lower())


if __name__ == "__main__":
    unittest.main()
