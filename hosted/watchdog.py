"""Private Cloud Tasks target. One audit creates one self-ending check chain."""

from __future__ import annotations

import os
from uuid import UUID

from fastapi import FastAPI, HTTPException

from hosted.cloud_run import CloudRunDispatcher
from hosted.purge import purge_once
from hosted.reconcile import reconcile_once
from hosted.supabase_gateway import BackendError, SupabaseGateway
from hosted.watchdog_tasks import AuditWatchdogTasks, WatchdogError

ACTIVE = {"queued", "dispatching", "running"}


def create_app(*, gateway=None, dispatcher=None, scheduler=None, settings=None) -> FastAPI:
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

    app = FastAPI(title="Competitive Audit Watchdog")

    @app.post("/watch/{audit_id}/{sequence}")
    def watch(audit_id: UUID, sequence: int):
        if sequence < 0 or sequence > 1000000:
            raise HTTPException(status_code=400, detail="Invalid sequence")
        try:
            audit = gateway.get_audit(audit_id)
            if audit["status"] not in ACTIVE:
                return {"status": "terminal"}
            reconcile_once(gateway, dispatcher)
            audit = gateway.get_audit(audit_id)
            if audit["status"] in ACTIVE:
                scheduler.schedule(audit_id, sequence + 1)
                return {"status": "rescheduled"}
            return {"status": "terminal"}
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
