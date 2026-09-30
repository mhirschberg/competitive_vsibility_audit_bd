"""User-facing artifact names include the audit date and scope."""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from audit_core.artifact_names import (
    audit_export_prefix,
    is_final_report_json,
    report_filename,
)
from hosted.worker import _artifact_kind
from scripts.run_local_audit import collect_artifacts
from tests.test_google_ai_timeout_safety import definition


class ArtifactNameTests(unittest.TestCase):
    def test_prefix_includes_date_company_focus_and_country(self):
        started = datetime(2026, 9, 30, 10, 35, 12, 123456, tzinfo=timezone.utc)
        prefix = audit_export_prefix(
            started, "Samsung / Mobile", "premium smartphones", "US"
        )
        self.assertEqual(
            prefix,
            "2026-09-30_103512123456_samsung-mobile_premium-smartphones_US",
        )
        self.assertEqual(
            report_filename(prefix, "pdf"),
            prefix + "_competitive_visibility_audit.pdf",
        )

    def test_context_is_safe_for_paths_and_supports_unicode(self):
        prefix = audit_export_prefix(
            "2026-09-30T10:35:12+00:00", "Ромашка/../Shop", "crème: anti/age", "DE"
        )
        self.assertIn("ромашка-shop", prefix)
        self.assertIn("crème-anti-age", prefix)
        self.assertNotIn("/", prefix)
        self.assertNotIn("..", prefix)
        self.assertTrue(prefix.endswith("_DE"))

    def test_local_and_hosted_collectors_accept_new_and_legacy_names(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            run = root / "competitive-visibility-apple-20260930"
            run.mkdir()
            prefix = "2026-09-30_103512123456_apple_premium-smartphones_US"
            paths = [
                root / report_filename(prefix, "zip"),
                run / report_filename(prefix, "pdf"),
                run / report_filename(prefix, "md"),
                run / report_filename(prefix, "json"),
                run / "05_reddit_social.json",
            ]
            for path in paths:
                path.write_text("{}", encoding="utf-8")
            self.assertEqual(set(collect_artifacts(root)), set(paths))
            self.assertEqual(_artifact_kind(paths[3]), "json_report")
            self.assertEqual(_artifact_kind(paths[4]), "reddit_social")
            legacy = run / "06_competitive_visibility_audit.json"
            legacy.write_text("{}", encoding="utf-8")
            self.assertIn(legacy, collect_artifacts(root))
            self.assertTrue(is_final_report_json(legacy.name))

    def test_notebook_zip_uses_contextual_name_and_preserves_contents(self):
        namespace = {"Path": Path, "zipfile": zipfile}
        exec(definition("create_audit_zip"), namespace)
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "competitive-visibility-test"
            output.mkdir()
            (output / "00_run_settings.json").write_text("{}", encoding="utf-8")
            name = "2026-09-30_103512_apple_US_competitive_visibility_audit.zip"
            archive = namespace["create_audit_zip"](output, name)
            self.assertEqual(archive.name, name)
            with zipfile.ZipFile(archive) as contents:
                self.assertEqual(contents.namelist(), ["00_run_settings.json"])
            with self.assertRaises(ValueError):
                namespace["create_audit_zip"](output, "../escape.zip")

    def test_notebook_uses_prefix_for_all_final_files(self):
        notebook = json.loads(
            (Path(__file__).resolve().parents[1] / "competitive_visibility_audit_bd.ipynb")
            .read_text(encoding="utf-8")
        )
        source = "".join(notebook["cells"][5]["source"])
        for extension in ("pdf", "md", "json", "zip"):
            self.assertIn(f'report_filename(export_prefix, "{extension}")', source)


if __name__ == "__main__":
    unittest.main()
