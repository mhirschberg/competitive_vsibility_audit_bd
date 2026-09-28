import unittest
from uuid import UUID

from fastapi.testclient import TestClient

from hosted.watchdog import create_app
from hosted.watchdog_tasks import AuditWatchdogTasks


AUDIT_ID = UUID("20000000-0000-0000-0000-000000000001")


class Gateway:
    def __init__(self, status="running"):
        self.status = status
        self.interrupt_calls = 0
        self.mail_state = None
        self.mail_claims = 0

    def get_audit(self, audit_id):
        assert audit_id == AUDIT_ID
        return {"status": self.status, "company_name": "Rayner"}

    def interrupt_stale_audits(self):
        self.interrupt_calls += 1
        return 0

    def list_dispatch_candidates(self, limit):
        return []

    def audit_email_state(self, audit_id):
        assert audit_id == AUDIT_ID
        return self.mail_state

    def claim_audit_ready_email(self, audit_id):
        assert audit_id == AUDIT_ID
        self.mail_claims += 1
        return {"email": "member@example.com", "claim_token": "50000000-0000-0000-0000-000000000001"}

    def finish_audit_ready_email(self, audit_id, claim_token, message_id):
        self.mail_state = "sent"
        return True


class Scheduler:
    def __init__(self):
        self.calls = []

    def schedule(self, audit_id, sequence=0):
        self.calls.append((audit_id, sequence))


class Notifier:
    def __init__(self):
        self.calls = []

    def send_ready(self, *args):
        self.calls.append(args)
        return "mail-1"


class Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = payload or {"access_token": "test-token"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("request failed")

    def json(self):
        return self.payload


class Session:
    def __init__(self, task_status=200):
        self.task_status = task_status
        self.post_kwargs = None

    def get(self, *args, **kwargs):
        return Response()

    def post(self, *args, **kwargs):
        self.post_kwargs = kwargs
        return Response(self.task_status)


class WatchdogTests(unittest.TestCase):
    def test_running_audit_reconciles_and_reschedules(self):
        gateway = Gateway()
        scheduler = Scheduler()
        app = create_app(gateway=gateway, dispatcher=object(), scheduler=scheduler)
        response = TestClient(app).post(f"/watch/{AUDIT_ID}/3")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "rescheduled")
        self.assertEqual(gateway.interrupt_calls, 1)
        self.assertEqual(scheduler.calls, [(AUDIT_ID, 4)])

    def test_terminal_audit_ends_chain_without_reconcile(self):
        gateway = Gateway("completed")
        scheduler = Scheduler()
        app = create_app(gateway=gateway, dispatcher=object(), scheduler=scheduler)
        response = TestClient(app).post(f"/watch/{AUDIT_ID}/3")
        self.assertEqual(response.json()["status"], "terminal")
        self.assertEqual(gateway.interrupt_calls, 0)
        self.assertEqual(scheduler.calls, [])

    def test_terminal_audit_sends_one_opted_in_email(self):
        gateway = Gateway("completed")
        gateway.mail_state = "pending"
        notifier = Notifier()
        app = create_app(
            gateway=gateway, dispatcher=object(), scheduler=Scheduler(), notifier=notifier
        )
        client = TestClient(app)
        self.assertEqual(client.post(f"/watch/{AUDIT_ID}/3").json()["status"], "notification_sent")
        self.assertEqual(client.post(f"/watch/{AUDIT_ID}/3").json()["status"], "terminal")
        self.assertEqual(len(notifier.calls), 1)

    def test_pending_notification_reschedules_without_reopening_audit(self):
        gateway = Gateway("completed")
        gateway.mail_state = "retry"
        gateway.claim_audit_ready_email = lambda _audit_id: None
        scheduler = Scheduler()
        notifier = Notifier()
        app = create_app(
            gateway=gateway, dispatcher=object(), scheduler=scheduler, notifier=notifier
        )
        response = TestClient(app).post(f"/watch/{AUDIT_ID}/3")
        self.assertEqual(response.json()["status"], "notification_pending")
        self.assertEqual(gateway.status, "completed")
        self.assertEqual(scheduler.calls, [(AUDIT_ID, 4)])
        self.assertEqual(notifier.calls, [])

    def test_failed_audit_never_sends_email(self):
        gateway = Gateway("failed")
        scheduler = Scheduler()
        notifier = Notifier()
        app = create_app(
            gateway=gateway, dispatcher=object(), scheduler=scheduler, notifier=notifier
        )
        response = TestClient(app).post(f"/watch/{AUDIT_ID}/3")
        self.assertEqual(response.json()["status"], "terminal")
        self.assertEqual(notifier.calls, [])
        self.assertEqual(scheduler.calls, [])

    def test_task_uses_stable_name_and_private_oidc_target(self):
        session = Session(task_status=409)
        scheduler = AuditWatchdogTasks(
            "getmuzoboz", "europe-west1", "audit-watchdog",
            "https://audit-watchdog-abc-ew.a.run.app",
            "audit-task-invoker@getmuzoboz.iam.gserviceaccount.com",
            session=session,
        )
        scheduler.schedule(AUDIT_ID, 4)
        task = session.post_kwargs["json"]["task"]
        self.assertTrue(task["name"].endswith(f"watch-{AUDIT_ID.hex}-0000004"))
        self.assertTrue(task["httpRequest"]["url"].endswith(f"/watch/{AUDIT_ID}/4"))
        self.assertEqual(task["httpRequest"]["oidcToken"]["audience"], scheduler.target_url)


if __name__ == "__main__":
    unittest.main()
