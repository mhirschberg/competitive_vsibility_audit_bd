import unittest
from uuid import UUID

from hosted.supabase_gateway import SupabaseGateway


AUDIT_ID = UUID("20000000-0000-0000-0000-000000000001")
PUBLISHABLE_KEY = "sb_publishable_test"
SECRET_KEY = "sb_secret_test"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.ok = status_code < 400

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.calls = []
        self.read_payloads = []
        self.sign_payload = {
            "signedURL": "/object/sign/audit-artifacts/"
            "workspaces/w/audits/a/report.pdf?token=test"
        }

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if url.endswith("/auth/v1/user"):
            return FakeResponse({"id": "00000000-0000-0000-0000-000000000001"})
        return FakeResponse(self.read_payloads.pop(0))

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return FakeResponse(str(AUDIT_ID))

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return FakeResponse(self.sign_payload)


class SupabaseGatewayTests(unittest.TestCase):
    def setUp(self):
        self.session = FakeSession()
        self.gateway = SupabaseGateway(
            "https://test-project.supabase.co",
            PUBLISHABLE_KEY,
            SECRET_KEY,
            session=self.session,
        )

    def test_secret_is_used_only_server_side_and_not_as_bearer(self):
        self.gateway.authenticate("user-jwt")
        self.gateway.submit_audit(p_user_id="test")
        auth_headers = self.session.calls[0][2]["headers"]
        rpc_headers = self.session.calls[1][2]["headers"]
        self.assertEqual(auth_headers["apikey"], PUBLISHABLE_KEY)
        self.assertEqual(auth_headers["Authorization"], "Bearer user-jwt")
        self.assertEqual(rpc_headers["apikey"], SECRET_KEY)
        self.assertNotIn("Authorization", rpc_headers)

    def test_status_reads_all_related_rows_with_user_rls(self):
        self.session.read_payloads = [
            [{"id": str(AUDIT_ID), "status": "running"}],
            [{"step_key": "company_analysis", "status": "completed"}],
            [{"event_kind": "stage_started"}],
            [{"kind": "pdf_report"}],
        ]
        result = self.gateway.read_audit_status(AUDIT_ID, "user-jwt")
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["steps"][0]["step_key"], "company_analysis")
        self.assertEqual(result["events"][0]["event_kind"], "stage_started")
        self.assertEqual(result["artifacts"][0]["kind"], "pdf_report")
        for method, url, kwargs in self.session.calls:
            self.assertEqual(method, "GET")
            self.assertEqual(kwargs["headers"]["apikey"], PUBLISHABLE_KEY)
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer user-jwt")
            self.assertNotIn(SECRET_KEY, str(kwargs))

    def test_inaccessible_audit_does_not_query_child_rows(self):
        self.session.read_payloads = [[]]
        self.assertIsNone(self.gateway.read_audit_status(AUDIT_ID, "user-jwt"))
        self.assertEqual(len(self.session.calls), 1)

    def test_artifact_signing_checks_user_rls_before_secret_request(self):
        artifact_id = UUID("70000000-0000-0000-0000-000000000001")
        self.session.read_payloads = [[{
            "bucket_id": "audit-artifacts",
            "object_path": "workspaces/w/audits/a/report.pdf",
        }]]
        url = self.gateway.sign_artifact_for_user(AUDIT_ID, artifact_id, "user-jwt")
        self.assertEqual(
            url,
            "https://test-project.supabase.co/storage/v1/object/sign/"
            "audit-artifacts/workspaces/w/audits/a/report.pdf?token=test",
        )
        self.assertEqual(self.session.calls[0][2]["headers"]["apikey"], PUBLISHABLE_KEY)
        self.assertEqual(self.session.calls[1][2]["headers"]["apikey"], SECRET_KEY)
        self.assertEqual(self.session.calls[1][2]["json"], {"expiresIn": 300})

    def test_missing_artifact_cannot_be_signed(self):
        artifact_id = UUID("70000000-0000-0000-0000-000000000001")
        self.session.read_payloads = [[]]
        self.assertIsNone(
            self.gateway.sign_artifact_for_user(AUDIT_ID, artifact_id, "user-jwt")
        )
        self.assertEqual(len(self.session.calls), 1)

    def test_local_http_requires_explicit_opt_in_and_loopback_host(self):
        with self.assertRaises(ValueError):
            SupabaseGateway("http://127.0.0.1:54321", PUBLISHABLE_KEY, SECRET_KEY)
        gateway = SupabaseGateway(
            "http://127.0.0.1:54321",
            PUBLISHABLE_KEY,
            SECRET_KEY,
            allow_local_http=True,
        )
        self.assertEqual(gateway.url, "http://127.0.0.1:54321")
        with self.assertRaises(ValueError):
            SupabaseGateway(
                "http://192.168.1.2:54321",
                PUBLISHABLE_KEY,
                SECRET_KEY,
                allow_local_http=True,
            )


if __name__ == "__main__":
    unittest.main()
