"""Guardrails for the hosted-audit schema until a local Supabase stack is wired in."""

import re
import unittest
from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "20260926000000_audit_foundation.sql"
)
ADMIN_MIGRATION = MIGRATION.with_name("20260926010000_workshop_admin.sql")
PURGE_MIGRATION = MIGRATION.with_name("20260926020000_workshop_anonymous_purge.sql")


class SupabaseMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8").lower()

    def test_every_app_table_has_row_level_security(self):
        tables = set(re.findall(r"create table public\.(\w+)", self.sql))
        protected = set(
            re.findall(
                r"alter table public\.(\w+) enable row level security",
                self.sql,
            )
        )
        self.assertEqual(tables, protected)

    def test_browser_cannot_write_and_artifact_bucket_is_private(self):
        self.assertIn("from public, anon, authenticated", self.sql)
        self.assertIn("to authenticated", self.sql)
        self.assertNotRegex(
            self.sql,
            r"grant\s+(?:insert|update|delete|all)\b[^;]*\bto\s+"
            r"(?:anon|authenticated)\b",
        )
        self.assertIn("values ('audit-artifacts', 'audit-artifacts', false)", self.sql)

    def test_paid_work_has_idempotency_and_usage_ledger(self):
        self.assertIn("unique (created_by, client_request_id)", self.sql)
        self.assertIn("audit_executions_one_running_idx", self.sql)
        self.assertIn("create table public.brightdata_operations", self.sql)
        self.assertIn("confirmed_result_count integer check", self.sql)

    def test_admin_writes_are_service_only_and_audited(self):
        sql = ADMIN_MIGRATION.read_text(encoding="utf-8").lower()
        self.assertIn("create table public.workshop_admin_events", sql)
        self.assertIn("alter table public.workshop_admin_events enable row level security", sql)
        self.assertIn("revoke all on public.workshop_admin_events from public, anon, authenticated", sql)
        for function in ("admin_list_workshops", "admin_create_workshop", "admin_update_workshop"):
            self.assertIn(f"create function public.{function}", sql)
            self.assertRegex(
                sql,
                rf"revoke all on function public\.{function}\([^;]+from public, anon, authenticated",
            )
            self.assertRegex(
                sql,
                rf"grant execute on function public\.{function}\([^;]+to service_role",
            )
        self.assertIn("m.role in ('owner', 'admin')", sql)
        self.assertIn("'active_audits', counts.active_audits", sql)

    def test_anonymous_purge_is_opt_in_for_existing_events_and_service_only(self):
        sql = PURGE_MIGRATION.read_text(encoding="utf-8").lower()
        self.assertIn("add column anonymous_retention_hours integer", sql)
        self.assertIn("alter column anonymous_retention_hours set default 48", sql)
        self.assertIn("create table public.workshop_purge_totals", sql)
        self.assertIn("create table public.workshop_purge_users", sql)
        self.assertIn("alter table public.workshop_purge_totals enable row level security", sql)
        self.assertIn("alter table public.workshop_purge_users enable row level security", sql)
        for function in (
            "purge_due_workshops", "purge_workshop_batch", "purge_finalize_batch",
            "purge_workshop_users", "purge_complete_workshop",
        ):
            self.assertIn(f"create function public.{function}", sql)
            self.assertRegex(
                sql,
                rf"revoke all on function public\.{function}\([^;]+from public, anon, authenticated",
            )
        self.assertIn("u.is_anonymous is true", sql)
        self.assertIn("w.purged_at is null", sql)


if __name__ == "__main__":
    unittest.main()
