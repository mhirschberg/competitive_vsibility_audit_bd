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


if __name__ == "__main__":
    unittest.main()
