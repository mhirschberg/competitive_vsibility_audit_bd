import unittest
from uuid import UUID

from hosted.purge import purge_once


WORKSHOP_ID = UUID("10000000-0000-4000-8000-000000000001")
AUDIT_ID = UUID("20000000-0000-4000-8000-000000000001")
USER_ID = UUID("30000000-0000-4000-8000-000000000001")


class FakeGateway:
    def __init__(self, *, fail_storage=False):
        self.calls = []
        self.fail_storage = fail_storage
        self.batch_count = 0

    def purge_due_workshops(self):
        self.calls.append("due")
        return [WORKSHOP_ID]

    def purge_workshop_batch(self, workshop_id, *, dry_run=False):
        self.calls.append(("batch", workshop_id, dry_run))
        self.batch_count += 1
        if self.batch_count == 1:
            return {"state": "ready", "audit_ids": [AUDIT_ID],
                    "object_paths": ["workspaces/w/audits/a/report.pdf"]}
        return {"state": "ready", "audit_ids": [], "object_paths": []}

    def delete_storage_objects(self, paths):
        self.calls.append(("storage", paths))
        if self.fail_storage:
            raise RuntimeError("Storage unavailable")

    def purge_finalize_batch(self, workshop_id, audit_ids):
        self.calls.append(("finalize", workshop_id, audit_ids))
        return len(audit_ids)

    def purge_workshop_users(self, workshop_id):
        self.calls.append(("users", workshop_id))
        return [USER_ID]

    def delete_queued_anonymous_user(self, user_id):
        self.calls.append(("delete_user", user_id))

    def purge_complete_workshop(self, workshop_id):
        self.calls.append(("complete", workshop_id))
        return True


class PurgeTests(unittest.TestCase):
    def test_storage_is_deleted_before_database_and_auth_user(self):
        gateway = FakeGateway()
        result = purge_once(gateway)
        self.assertEqual(result["audits_deleted"], 1)
        self.assertEqual(result["workshops_completed"], 1)
        names = [call[0] if isinstance(call, tuple) else call for call in gateway.calls]
        self.assertLess(names.index("storage"), names.index("finalize"))
        self.assertLess(names.index("finalize"), names.index("delete_user"))
        self.assertLess(names.index("delete_user"), names.index("complete"))

    def test_dry_run_makes_no_deletion_calls(self):
        gateway = FakeGateway()
        result = purge_once(gateway, dry_run=True)
        self.assertEqual(result["audits_planned"], 1)
        self.assertEqual(result["objects_planned"], 1)
        self.assertEqual(result["audits_deleted"], 0)
        self.assertEqual([call for call in gateway.calls
                          if isinstance(call, tuple) and call[0] in {
                              "storage", "finalize", "delete_user", "complete"
                          }], [])

    def test_storage_failure_never_deletes_database_rows(self):
        gateway = FakeGateway(fail_storage=True)
        with self.assertRaises(RuntimeError):
            purge_once(gateway)
        self.assertNotIn("finalize", [call[0] if isinstance(call, tuple)
                                      else call for call in gateway.calls])


if __name__ == "__main__":
    unittest.main()
