"""Idempotent cleanup of expired, anonymous workshop data.

The scheduler only discovers due workshops. Each batch deletes physical Storage
objects first, then atomically records anonymous aggregate counts and removes
database rows. Failed batches are safe to retry; no registered user is targeted.
"""

from __future__ import annotations

from uuid import UUID


def purge_once(gateway, *, dry_run: bool = False, workshop_ids=None,
               max_batches: int = 10) -> dict:
    if max_batches < 1:
        raise ValueError("max_batches must be positive")
    ids = list(workshop_ids) if workshop_ids is not None else gateway.purge_due_workshops()
    result = {
        "workshops_checked": 0,
        "workshops_completed": 0,
        "audits_planned": 0,
        "audits_deleted": 0,
        "objects_planned": 0,
        "users_deleted_or_preserved": 0,
        "dry_run": dry_run,
    }
    for raw_id in ids:
        workshop_id = UUID(str(raw_id))
        result["workshops_checked"] += 1
        for _ in range(max_batches):
            batch = gateway.purge_workshop_batch(workshop_id, dry_run=dry_run)
            if batch["state"] != "ready":
                break
            audit_ids = batch["audit_ids"]
            paths = batch["object_paths"]
            result["audits_planned"] += len(audit_ids)
            result["objects_planned"] += len(paths)
            if dry_run:
                break
            if not audit_ids:
                break
            for offset in range(0, len(paths), 500):
                gateway.delete_storage_objects(paths[offset:offset + 500])
            result["audits_deleted"] += gateway.purge_finalize_batch(
                workshop_id, audit_ids
            )
        if dry_run or batch["state"] != "ready":
            continue
        for user_id in gateway.purge_workshop_users(workshop_id):
            gateway.delete_queued_anonymous_user(user_id)
            result["users_deleted_or_preserved"] += 1
        if gateway.purge_complete_workshop(workshop_id):
            result["workshops_completed"] += 1
    return result
