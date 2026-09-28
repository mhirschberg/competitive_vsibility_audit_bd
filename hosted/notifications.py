"""Opt-in audit completion mail; delivery is independent of audit success."""

from __future__ import annotations

from html import escape
from urllib.parse import urlparse
from uuid import UUID

import requests

from hosted.supabase_gateway import BackendError


class NotificationError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ResendEmailSender:
    def __init__(self, api_key: str, from_email: str, web_url: str, *, session=None):
        parsed = urlparse(web_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("Notification web URL must be an HTTPS origin")
        if not api_key.startswith("re_"):
            raise ValueError("RESEND_API_KEY is missing or invalid")
        if "@" not in from_email or any(ch in from_email for ch in "\r\n"):
            raise ValueError("NOTIFICATION_FROM_EMAIL is invalid")
        self.api_key = api_key
        self.from_email = from_email
        self.web_url = web_url.rstrip("/")
        self.session = session or requests.Session()

    def send_ready(self, audit_id: UUID, recipient: str, company_name: str) -> str:
        if "@" not in recipient or any(ch in recipient for ch in "\r\n"):
            raise NotificationError("invalid_recipient")
        name = company_name.strip()[:80] or "your company"
        link = f"{self.web_url}/#history"
        body = {
            "from": self.from_email,
            "to": [recipient],
            "subject": f"Your {name} visibility audit is ready",
            "text": (
                f"Your visibility audit for {name} is ready. "
                f"Sign in with Google to view and download it: {link}\n\n"
                "This is a report-ready notification, not a marketing email."
            ),
            "html": (
                '<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;'
                'color:#18352e;line-height:1.6">'
                '<p style="font-size:12px;letter-spacing:.14em;color:#e46f40">'
                'COMPETITIVE VISIBILITY</p>'
                '<h1 style="font-size:28px;line-height:1.2">Your audit is ready.</h1>'
                f'<p>The visibility audit for <strong>{escape(name)}</strong> has finished.</p>'
                f'<p><a href="{escape(link, quote=True)}">Sign in and open your audits →</a></p>'
                '<p style="font-size:12px;color:#69766e">No report is attached to this email. '
                'The link opens your private audit history.</p></div>'
            ),
        }
        try:
            response = self.session.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": f"audit-ready/{audit_id}",
                },
                json=body,
                timeout=20,
            )
        except requests.RequestException as exc:
            raise NotificationError("provider_unreachable") from exc
        if not response.ok:
            raise NotificationError(f"provider_http_{response.status_code}")
        try:
            message_id = response.json()["id"]
        except (KeyError, TypeError, ValueError) as exc:
            raise NotificationError("provider_invalid_response") from exc
        if not isinstance(message_id, str) or not message_id:
            raise NotificationError("provider_invalid_response")
        return message_id


def deliver_ready_email_once(gateway, sender, audit_id: UUID) -> str:
    """Return sent, pending, or terminal without changing the audit outcome."""
    state = gateway.audit_email_state(audit_id)
    if state in {None, "sent", "abandoned"}:
        return "terminal"
    claim = gateway.claim_audit_ready_email(audit_id)
    if claim is None:
        return "pending"
    claim_token = UUID(claim["claim_token"])
    try:
        audit = gateway.get_audit(audit_id)
        if audit["status"] != "completed":
            raise NotificationError("audit_not_completed")
        message_id = sender.send_ready(
            audit_id, claim["email"], audit["company_name"]
        )
    except NotificationError as exc:
        gateway.defer_audit_ready_email(audit_id, claim_token, exc.code)
        return (
            "terminal"
            if gateway.audit_email_state(audit_id) in {"sent", "abandoned"}
            else "pending"
        )
    if not gateway.finish_audit_ready_email(audit_id, claim_token, message_id):
        raise BackendError("Email notification claim was lost")
    return "sent"
