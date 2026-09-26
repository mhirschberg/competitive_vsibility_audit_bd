import unittest
from uuid import UUID

from fastapi.testclient import TestClient

from hosted.api import create_app
from hosted.cloud_run import CloudRunDispatcher, DispatchError
from hosted.reconcile import reconcile_once
from hosted.supabase_gateway import SupabaseGateway


AUDIT_ID = UUID("20000000-0000-0000-0000-000000000001")
USER_ID = UUID("00000000-0000-0000-0000-000000000001")
WORKSHOP_ID = UUID("40000000-0000-0000-0000-000000000001")
REQUEST_ID = UUID("30000000-0000-0000-0000-000000000001")
ARTIFACT_ID = UUID("70000000-0000-0000-0000-000000000001")


class FakeGateway:
    def __init__(self):
        self.token = None
        self.payload = None
        self.reserve_result = True
        self.status_result = {"id": str(AUDIT_ID), "status": "running", "steps": []}
        self.signed_url = "https://test-project.supabase.co/storage/v1/object/sign/test"

    def authenticate(self, token):
        self.token = token
        return USER_ID

    def submit_audit(self, **payload):
        self.payload = payload
        return AUDIT_ID

    def reserve_dispatch(self, audit_id):
        assert audit_id == AUDIT_ID
        return self.reserve_result

    def list_dispatch_candidates(self, limit):
        return [AUDIT_ID]

    def interrupt_stale_audits(self):
        return 0

    def read_audit_status(self, audit_id, token):
        assert audit_id == AUDIT_ID
        assert token == "user-jwt"
        return self.status_result

    def sign_artifact_for_user(self, audit_id, artifact_id, token):
        assert audit_id == AUDIT_ID
        assert artifact_id == ARTIFACT_ID
        assert token == "user-jwt"
        return self.signed_url


class FakeDispatcher:
    def __init__(self):
        self.calls = []
        self.fail = False

    def dispatch(self, audit_id):
        self.calls.append(audit_id)
        if self.fail:
            raise DispatchError("mock failure")
        return "operations/test"


class HostedApiTests(unittest.TestCase):
    def setUp(self):
        self.gateway = FakeGateway()
        self.dispatcher = FakeDispatcher()
        app = create_app(
            gateway=self.gateway,
            dispatcher=self.dispatcher,
            settings={
                "ENGINE_COMMIT": "test-commit",
                "METHODOLOGY_VERSION": "v1",
                "WEB_ORIGIN": "https://audit.example",
            },
        )
        self.client = TestClient(app)
        self.request = {
            "client_request_id": str(REQUEST_ID),
            "company_name": "Rayner",
            "company_domain": "rayner.com",
            "audit_focus": "RayOne Galaxy",
            "country_code": "gb",
            "search_engine": "auto",
            "include_reddit_analysis": True,
            "workshop_id": str(WORKSHOP_ID),
        }

    def test_submission_uses_verified_identity_and_dispatches_once(self):
        response = self.client.post(
            "/audits",
            headers={"Authorization": "Bearer user-jwt"},
            json=self.request,
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["dispatch_state"], "started")
        self.assertEqual(self.gateway.token, "user-jwt")
        self.assertEqual(self.gateway.payload["p_user_id"], str(USER_ID))
        self.assertEqual(self.gateway.payload["p_country_code"], "GB")
        self.assertEqual(
            self.gateway.payload["p_input_options"]["social_sources"],
            ["reddit"],
        )
        self.assertEqual(self.dispatcher.calls, [AUDIT_ID])

    def test_missing_authentication_or_workshop_is_rejected(self):
        no_auth = self.client.post("/audits", json=self.request)
        self.assertEqual(no_auth.status_code, 401)
        without_workshop = dict(self.request)
        without_workshop.pop("workshop_id")
        no_workshop = self.client.post(
            "/audits",
            headers={"Authorization": "Bearer user-jwt"},
            json=without_workshop,
        )
        self.assertEqual(no_workshop.status_code, 422)

    def test_duplicate_request_does_not_dispatch_again(self):
        self.gateway.reserve_result = False
        response = self.client.post(
            "/audits",
            headers={"Authorization": "Bearer user-jwt"},
            json=self.request,
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["dispatch_state"], "already_pending")
        self.assertEqual(self.dispatcher.calls, [])

    def test_dispatch_failure_keeps_durable_request_for_reconciliation(self):
        self.dispatcher.fail = True
        response = self.client.post(
            "/audits",
            headers={"Authorization": "Bearer user-jwt"},
            json=self.request,
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["dispatch_state"], "pending_retry")

    def test_status_can_be_reloaded_by_audit_id(self):
        response = self.client.get(
            f"/audits/{AUDIT_ID}",
            headers={"Authorization": "Bearer user-jwt"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "running")

    def test_status_is_not_visible_without_access(self):
        self.gateway.status_result = None
        response = self.client.get(
            f"/audits/{AUDIT_ID}",
            headers={"Authorization": "Bearer user-jwt"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get(f"/audits/{AUDIT_ID}").status_code, 401)

    def test_artifact_download_requires_membership(self):
        path = f"/audits/{AUDIT_ID}/artifacts/{ARTIFACT_ID}/download"
        self.assertEqual(self.client.get(path).status_code, 401)
        self.gateway.signed_url = None
        self.assertEqual(
            self.client.get(path, headers={"Authorization": "Bearer user-jwt"}).status_code,
            404,
        )
        self.gateway.signed_url = "https://test-project.supabase.co/storage/v1/object/sign/test"
        response = self.client.get(path, headers={"Authorization": "Bearer user-jwt"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["expires_in"], 300)

    def test_gateway_rejects_non_supabase_host_for_secret(self):
        with self.assertRaises(ValueError):
            SupabaseGateway(
                "https://example.com/project.supabase.co",
                "sb_publishable_fake",
                "sb_secret_fake",
            )

    def test_reconciler_reserves_before_dispatch(self):
        result = reconcile_once(self.gateway, self.dispatcher)
        self.assertEqual(result, {"started": 1, "failed": 0, "interrupted": 0})
        self.assertEqual(self.dispatcher.calls, [AUDIT_ID])

    def test_reconciler_skips_audit_claimed_elsewhere(self):
        self.gateway.reserve_result = False
        result = reconcile_once(self.gateway, self.dispatcher)
        self.assertEqual(result, {"started": 0, "failed": 0, "interrupted": 0})
        self.assertEqual(self.dispatcher.calls, [])


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeHttpSession:
    def __init__(self):
        self.posts = []

    def get(self, url, **kwargs):
        assert "metadata.google.internal" in url
        return FakeResponse({"access_token": "test-access-token"})

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return FakeResponse({"name": "operations/test"})


class CloudRunDispatcherTests(unittest.TestCase):
    def test_only_audit_id_is_overridden(self):
        session = FakeHttpSession()
        dispatcher = CloudRunDispatcher(
            "test-project", "europe-west3", "audit-worker", session=session
        )
        self.assertEqual(dispatcher.dispatch(AUDIT_ID), "operations/test")
        url, kwargs = session.posts[0]
        self.assertIn("jobs/audit-worker:run", url)
        self.assertEqual(
            kwargs["json"]["overrides"]["containerOverrides"][0]["env"],
            [{"name": "AUDIT_ID", "value": str(AUDIT_ID)}],
        )


if __name__ == "__main__":
    unittest.main()
