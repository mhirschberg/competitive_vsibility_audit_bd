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
USERS_MIGRATION = MIGRATION.with_name("20260927000000_registered_users_admin.sql")
COST_MIGRATION = MIGRATION.with_name("20260927010000_admin_cost_overview.sql")
EMAIL_MIGRATION = MIGRATION.with_name("20260928000000_audit_email_notifications.sql")


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

    def test_registered_users_are_site_admin_only_and_exclude_anonymous_accounts(self):
        sql = USERS_MIGRATION.read_text(encoding="utf-8").lower()
        self.assertIn("create table public.site_admins", sql)
        self.assertIn("(select count(*) from existing_owners) = 1", sql)
        self.assertIn("alter table public.site_admins enable row level security", sql)
        self.assertIn("revoke all on public.site_admins from public, anon, authenticated", sql)
        self.assertIn("from public.site_admins sa where sa.user_id = p_user_id", sql)
        self.assertIn("u.is_anonymous is not true", sql)
        self.assertIn("i.provider = 'google'", sql)
        self.assertIn("a.workshop_id is null", sql)
        self.assertRegex(sql, r"revoke all on function public\.admin_list_registered_users\([^;]+from public, anon, authenticated")
        self.assertRegex(sql, r"grant execute on function public\.admin_list_registered_users\([^;]+to service_role")

    def test_cost_overview_is_site_admin_only_and_includes_purged_totals(self):
        sql = COST_MIGRATION.read_text(encoding="utf-8").lower()
        self.assertIn("from public.site_admins where user_id = p_user_id", sql)
        self.assertIn("from public.workshop_purge_totals", sql)
        self.assertIn("brightdata_unknown_cost_operations", sql)
        self.assertRegex(sql, r"revoke all on function public\.admin_cost_overview\([^;]+from public, anon, authenticated")
        self.assertRegex(sql, r"grant execute on function public\.admin_cost_overview\([^;]+to service_role")

    def test_completion_email_outbox_is_opt_in_and_service_only(self):
        sql = EMAIL_MIGRATION.read_text(encoding="utf-8").lower()
        self.assertIn("create table public.audit_email_notifications", sql)
        self.assertIn("alter table public.audit_email_notifications enable row level security", sql)
        self.assertIn("revoke all on public.audit_email_notifications from public, anon, authenticated", sql)
        self.assertIn("new.workshop_id is null", sql)
        self.assertIn("new.input_options ->> 'email_when_ready' = 'true'", sql)
        self.assertIn("on conflict (audit_id) do nothing", sql)
        self.assertIn("and claim_token = p_claim_token", sql)
        for name in ("claim_audit_ready_email", "finish_audit_ready_email", "defer_audit_ready_email"):
            self.assertRegex(sql, rf"revoke all on function public\.{name}\([^;]+from public, anon, authenticated")
            self.assertRegex(sql, rf"grant execute on function public\.{name}\([^;]+to service_role")


if __name__ == "__main__":
    unittest.main()
