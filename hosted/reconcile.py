"""Scheduled, bounded re-dispatch of queued or uncertain Cloud Run jobs."""

from __future__ import annotations

import os

from hosted.cloud_run import CloudRunDispatcher, DispatchError
from hosted.supabase_gateway import SupabaseGateway


def reconcile_once(gateway, dispatcher, limit=50):
    interrupted = gateway.interrupt_stale_audits()
    started = 0
    failed = 0
    for audit_id in gateway.list_dispatch_candidates(limit):
        if not gateway.reserve_dispatch(audit_id):
            continue
        try:
            dispatcher.dispatch(audit_id)
            started += 1
        except DispatchError:
            # Leave the row dispatching for the next timed retry.
            failed += 1
    return {"started": started, "failed": failed, "interrupted": interrupted}


def main():
    gateway = SupabaseGateway(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_PUBLISHABLE_KEY"],
        os.environ["SUPABASE_SECRET_KEY"],
    )
    dispatcher = CloudRunDispatcher(
        os.environ["GOOGLE_CLOUD_PROJECT"],
        os.environ["CLOUD_RUN_REGION"],
        os.environ["CLOUD_RUN_JOB_NAME"],
    )
    result = reconcile_once(gateway, dispatcher)
    print(
        f"Dispatch reconciled: {result['started']} started, "
        f"{result['failed']} failed, {result['interrupted']} interrupted"
    )
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
