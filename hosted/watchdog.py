"""Private Cloud Tasks target. One audit creates one self-ending check chain."""

from __future__ import annotations

import os
from uuid import UUID

from fastapi import FastAPI, HTTPException

from hosted.cloud_run import CloudRunDispatcher
from hosted.notifications import ResendEmailSender, deliver_ready_email_once
from hosted.purge import purge_once
from hosted.reconcile import reconcile_once
from hosted.supabase_gateway import BackendError, SupabaseGateway
from hosted.watchdog_tasks import AuditWatchdogTasks, WatchdogError

ACTIVE = {"queued", "dispatching", "running"}


def create_app(*, gateway=None, dispatcher=None, scheduler=None, notifier=None, settings=None) -> FastAPI:
    settings = settings or os.environ
    if gateway is None:
        gateway = SupabaseGateway(
            settings["SUPABASE_URL"],
            settings["SUPABASE_PUBLISHABLE_KEY"],
            settings["SUPABASE_SECRET_KEY"],
        )
    if dispatcher is None:
        dispatcher = CloudRunDispatcher(
            settings["GOOGLE_CLOUD_PROJECT"],
            settings["CLOUD_RUN_REGION"],
            settings["CLOUD_RUN_JOB_NAME"],
        )
    if scheduler is None:
        scheduler = AuditWatchdogTasks(
            settings["GOOGLE_CLOUD_PROJECT"],
            settings["CLOUD_RUN_REGION"],
            settings["WATCHDOG_QUEUE"],
            settings["WATCHDOG_URL"],
            settings["WATCHDOG_INVOKER_EMAIL"],
        )
    if notifier is None and all(settings.get(key) for key in (
        "RESEND_API_KEY", "NOTIFICATION_FROM_EMAIL", "NOTIFICATION_WEB_URL"
    )):
        notifier = ResendEmailSender(
            settings["RESEND_API_KEY"],
            settings["NOTIFICATION_FROM_EMAIL"],
            settings["NOTIFICATION_WEB_URL"],
        )

    app = FastAPI(title="Competitive Audit Watchdog")

    def finish_or_continue_notification(audit_id: UUID, sequence: int):
        if notifier is not None:
            delivery = deliver_ready_email_once(gateway, notifier, audit_id)
            if delivery == "pending":
                scheduler.schedule(audit_id, sequence + 1)
                return {"status": "notification_pending"}
            if delivery == "sent":
                return {"status": "notification_sent"}
        return {"status": "terminal"}

    @app.post("/watch/{audit_id}/{sequence}")
    def watch(audit_id: UUID, sequence: int):
        if sequence < 0 or sequence > 1000000:
            raise HTTPException(status_code=400, detail="Invalid sequence")
        try:
            audit = gateway.get_audit(audit_id)
            if audit["status"] not in ACTIVE:
                return finish_or_continue_notification(audit_id, sequence)
            reconcile_once(gateway, dispatcher)
            audit = gateway.get_audit(audit_id)
            if audit["status"] in ACTIVE:
                scheduler.schedule(audit_id, sequence + 1)
                return {"status": "rescheduled"}
            return finish_or_continue_notification(audit_id, sequence)
        except (BackendError, WatchdogError) as exc:
            # Cloud Tasks retries non-2xx responses, preserving the same task ID.
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/purge")
    def purge(dry_run: bool = False):
        if not dry_run and settings.get("PURGE_ENABLED") != "true":
            raise HTTPException(status_code=503, detail="Workshop purge is not enabled")
        try:
            return purge_once(gateway, dry_run=dry_run)
        except BackendError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return app
