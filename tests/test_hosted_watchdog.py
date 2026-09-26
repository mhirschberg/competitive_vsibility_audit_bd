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

    def get_audit(self, audit_id):
        assert audit_id == AUDIT_ID
        return {"status": self.status}

    def interrupt_stale_audits(self):
        self.interrupt_calls += 1
        return 0

    def list_dispatch_candidates(self, limit):
        return []


class Scheduler:
    def __init__(self):
        self.calls = []

    def schedule(self, audit_id, sequence=0):
        self.calls.append((audit_id, sequence))


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
