"""Completion mail is opt-in, private, and independent of audit success."""

import unittest
from uuid import UUID

from hosted.notifications import NotificationError, ResendEmailSender, deliver_ready_email_once


AUDIT_ID = UUID("20000000-0000-0000-0000-000000000001")
CLAIM_ID = UUID("50000000-0000-0000-0000-000000000001")


class Response:
    ok = True
    status_code = 200

    def json(self):
        return {"id": "provider-message-1"}


class Session:
    def __init__(self):
        self.request = None

    def post(self, url, **kwargs):
        self.request = (url, kwargs)
        return Response()


class Gateway:
    def __init__(self):
        self.state = "pending"
        self.claims = 0
        self.finished = []
        self.deferred = []

    def audit_email_state(self, _audit_id):
        return self.state

    def claim_audit_ready_email(self, _audit_id):
        self.claims += 1
        return {"email": "member@example.com", "claim_token": str(CLAIM_ID), "attempts": 1}

    def get_audit(self, _audit_id):
        return {"status": "completed", "company_name": "Rayner"}

    def finish_audit_ready_email(self, audit_id, token, message_id):
        self.finished.append((audit_id, token, message_id))
        self.state = "sent"
        return True

    def defer_audit_ready_email(self, audit_id, token, error_code):
        self.deferred.append((audit_id, token, error_code))
        self.state = "retry"
        return True


class Sender:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def send_ready(self, *args):
        self.calls.append(args)
        if self.fail:
            raise NotificationError("provider_unreachable")
        return "provider-message-1"


class AuditEmailNotificationTests(unittest.TestCase):
    def test_sender_uses_stable_key_and_private_history_link(self):
        session = Session()
        sender = ResendEmailSender(
            "re_test", "reports@example.com", "https://audit.example", session=session
        )
        message_id = sender.send_ready(AUDIT_ID, "member@example.com", "Rayner")
        self.assertEqual(message_id, "provider-message-1")
        url, request = session.request
        self.assertEqual(url, "https://api.resend.com/emails")
        self.assertEqual(request["headers"]["Idempotency-Key"], f"audit-ready/{AUDIT_ID}")
        self.assertIn("https://audit.example/#history", request["json"]["text"])
        self.assertNotIn("pdf", request["json"])

    def test_completion_is_recorded_only_after_provider_accepts(self):
        gateway = Gateway()
        sender = Sender()
        self.assertEqual(deliver_ready_email_once(gateway, sender, AUDIT_ID), "sent")
        self.assertEqual(gateway.finished, [(AUDIT_ID, CLAIM_ID, "provider-message-1")])
        self.assertEqual(deliver_ready_email_once(gateway, sender, AUDIT_ID), "terminal")
        self.assertEqual(len(sender.calls), 1)

    def test_provider_failure_keeps_report_completed_and_mail_retryable(self):
        gateway = Gateway()
        sender = Sender(fail=True)
        self.assertEqual(deliver_ready_email_once(gateway, sender, AUDIT_ID), "pending")
        self.assertEqual(gateway.get_audit(AUDIT_ID)["status"], "completed")
        self.assertEqual(gateway.deferred, [(AUDIT_ID, CLAIM_ID, "provider_unreachable")])
        self.assertEqual(gateway.finished, [])

    def test_no_opt_in_row_never_contacts_provider(self):
        gateway = Gateway()
        gateway.state = None
        sender = Sender()
        self.assertEqual(deliver_ready_email_once(gateway, sender, AUDIT_ID), "terminal")
        self.assertEqual(sender.calls, [])


if __name__ == "__main__":
    unittest.main()
