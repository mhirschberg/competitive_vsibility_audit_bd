import unittest
from uuid import UUID

from fastapi.testclient import TestClient

from hosted.api import create_app
from hosted.cloud_run import CloudRunDispatcher, DispatchError
from hosted.reconcile import reconcile_once
from hosted.supabase_gateway import AuthorizationError, SupabaseGateway, TrialQuotaError
from hosted.watchdog_tasks import WatchdogError


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
        self.organizer_allowed = True
        self.trial_allowed = True
        self.trial_quota_error = None
        self.admin_payload = None

    def authenticate(self, token):
        self.token = token
        return USER_ID

    def authenticate_google_organizer(self, token):
        self.token = token
        if not self.organizer_allowed:
            raise AuthorizationError("Sign in with Google to manage workshops")
        return USER_ID

    def authenticate_google_participant(self, token):
        self.token = token
        if not self.trial_allowed:
            raise AuthorizationError("Sign in with Google to run a personal trial")
        return USER_ID

    def trial_status(self, user_id):
        assert user_id == USER_ID
        return {"limit": 3, "used": 1, "remaining": 2, "can_submit": False,
                "next_available_at": "2026-09-27T12:00:00Z"}

    def public_workshop(self, slug):
        if slug != "test-event":
            return None
        return {"id": str(WORKSHOP_ID), "slug": slug, "name": "Test Event"}

    def admin_list_workshops(self, user_id):
        assert user_id == USER_ID
        return {
            "workspaces": [{"id": str(USER_ID), "name": "Organizer"}],
            "workshops": [],
        }

    def admin_create_workshop(self, **payload):
        self.admin_payload = payload
        return WORKSHOP_ID

    def admin_update_workshop(self, **payload):
        self.admin_payload = payload
        return WORKSHOP_ID

    def admin_set_workshop_retention(self, **payload):
        self.admin_payload = payload
        return WORKSHOP_ID

    def submit_audit(self, **payload):
        self.payload = payload
        return AUDIT_ID

    def submit_trial_audit(self, **payload):
        if self.trial_quota_error:
            raise TrialQuotaError(self.trial_quota_error)
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


class FakeWatchdog:
    def __init__(self):
        self.calls = []
        self.fail = False

    def schedule(self, audit_id, sequence=0):
        self.calls.append((audit_id, sequence))
        if self.fail:
            raise WatchdogError("mock failure")


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

    def test_health_endpoint_avoids_cloud_run_reserved_suffix(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_public_workshop_link_resolves_without_auth(self):
        response = self.client.get("/workshops/test-event")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(WORKSHOP_ID))
        self.assertEqual(self.client.get("/workshops/unknown").status_code, 404)

    def test_admin_requires_google_identity_and_records_verified_actor(self):
        self.assertEqual(self.client.get("/admin/workshops").status_code, 401)
        self.gateway.organizer_allowed = False
        self.assertEqual(
            self.client.get(
                "/admin/workshops", headers={"Authorization": "Bearer anonymous-jwt"}
            ).status_code,
            403,
        )
        self.gateway.organizer_allowed = True
        response = self.client.get(
            "/admin/workshops", headers={"Authorization": "Bearer google-jwt"}
        )
        self.assertEqual(response.status_code, 200)

    def test_admin_can_create_and_update_finite_workshop_limits(self):
        settings = {
            "name": "Berlin AI Day",
            "opens_at": None,
            "closes_at": None,
            "max_total_audits": 30,
            "max_concurrent_audits": 8,
            "max_audits_per_user": 1,
        }
        headers = {"Authorization": "Bearer google-jwt"}
        create = self.client.post(
            "/admin/workshops",
            headers=headers,
            json={
                **settings,
                "workspace_id": str(USER_ID),
                "slug": "berlin-ai-day",
            },
        )
        self.assertEqual(create.status_code, 201)
        self.assertEqual(self.gateway.admin_payload["p_user_id"], str(USER_ID))
        self.assertEqual(self.gateway.admin_payload["p_max_concurrent_audits"], 8)
        update = self.client.patch(
            f"/admin/workshops/{WORKSHOP_ID}",
            headers=headers,
            json={**settings, "max_total_audits": 40},
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(self.gateway.admin_payload["p_max_total_audits"], 40)
        self.assertEqual(
            self.client.post(
                "/admin/workshops",
                headers=headers,
                json={**settings, "workspace_id": str(USER_ID), "slug": "BAD SLUG"},
            ).status_code,
            422,
        )

    def test_admin_can_set_retention_but_anonymous_user_cannot(self):
        path = f"/admin/workshops/{WORKSHOP_ID}/retention"
        self.assertEqual(
            self.client.patch(path, json={"anonymous_retention_hours": 48}).status_code,
            401,
        )
        self.gateway.organizer_allowed = False
        self.assertEqual(
            self.client.patch(
                path, headers={"Authorization": "Bearer anonymous-jwt"},
                json={"anonymous_retention_hours": 48},
            ).status_code,
            403,
        )
        self.gateway.organizer_allowed = True
        response = self.client.patch(
            path, headers={"Authorization": "Bearer google-jwt"},
            json={"anonymous_retention_hours": 48},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.gateway.admin_payload["p_hours"], 48)
        self.assertEqual(
            self.client.patch(
                path, headers={"Authorization": "Bearer google-jwt"},
                json={"anonymous_retention_hours": 1},
            ).status_code,
            422,
        )

    def test_watchdog_is_scheduled_before_dispatch(self):
        watchdog = FakeWatchdog()
        app = create_app(
            gateway=self.gateway,
            dispatcher=self.dispatcher,
            scheduler=watchdog,
            settings={"ENGINE_COMMIT": "test-commit", "METHODOLOGY_VERSION": "v1"},
        )
        response = TestClient(app).post(
            "/audits", headers={"Authorization": "Bearer user-jwt"}, json=self.request
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(watchdog.calls, [(AUDIT_ID, 0)])
        self.assertEqual(self.dispatcher.calls, [AUDIT_ID])

    def test_failed_watchdog_enqueue_does_not_start_worker(self):
        watchdog = FakeWatchdog()
        watchdog.fail = True
        app = create_app(
            gateway=self.gateway,
            dispatcher=self.dispatcher,
            scheduler=watchdog,
            settings={"ENGINE_COMMIT": "test-commit", "METHODOLOGY_VERSION": "v1"},
        )
        response = TestClient(app).post(
            "/audits", headers={"Authorization": "Bearer user-jwt"}, json=self.request
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.dispatcher.calls, [])

    def test_missing_authentication_is_rejected_and_no_workshop_uses_trial(self):
        no_auth = self.client.post("/audits", json=self.request)
        self.assertEqual(no_auth.status_code, 401)
        without_workshop = dict(self.request)
        without_workshop.pop("workshop_id")
        no_workshop = self.client.post(
            "/audits",
            headers={"Authorization": "Bearer user-jwt"},
            json=without_workshop,
        )
        self.assertEqual(no_workshop.status_code, 202)
        self.assertNotIn("p_workshop_id", self.gateway.payload)

    def test_trial_requires_google_and_reports_allowance(self):
        trial_request = {**self.request, "workshop_id": None}
        self.assertEqual(self.client.get("/trial/status").status_code, 401)
        self.gateway.trial_allowed = False
        denied = self.client.post(
            "/audits", headers={"Authorization": "Bearer anonymous-jwt"},
            json=trial_request,
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(self.dispatcher.calls, [])
        self.gateway.trial_allowed = True
        status = self.client.get(
            "/trial/status", headers={"Authorization": "Bearer google-jwt"}
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["remaining"], 2)

    def test_trial_quota_returns_notebook_without_dispatch(self):
        self.gateway.trial_quota_error = "trial_daily_limit"
        response = self.client.post(
            "/audits", headers={"Authorization": "Bearer google-jwt"},
            json={**self.request, "workshop_id": None},
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["detail"]["code"], "trial_daily_limit")
        self.assertIn("github.com", response.json()["detail"]["notebook_url"])
        self.assertEqual(self.dispatcher.calls, [])

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
