"""Shared file writers and audit-resume behavior, without provider calls."""

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from audit_core.artifact_resume import find_latest_audit_to_continue
from audit_core.artifact_writes import (
    create_audit_zip, write_json, write_json_with_scope, write_text,
)
from tests.test_google_ai_timeout_safety import definition


SETTINGS = {
    "company_domain": "apple.com", "audit_focus": "iPhone", "country": "US",
    "search_engine": "auto", "serp_zone": "serp_api2",
    "include_reddit_analysis": False,
}


class ArtifactIOTests(unittest.TestCase):
    def test_named_and_legacy_final_json_keep_locked_scope(self):
        with tempfile.TemporaryDirectory() as root:
            for name in (
                "06_competitive_visibility_audit.json",
                "2026-09-30_apple_iphone_US_competitive_visibility_audit.json",
            ):
                payload = {"configuration": {"country": "US"}}
                path = Path(root) / name
                result = write_json_with_scope(
                    path, payload,
                    locked_target_scope={"role": "manufacturer"},
                    market_category_override="premium smartphone",
                )
                self.assertEqual(result, path)
                saved = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(saved["locked_target_scope"], {
                    "role": "manufacturer",
                })
                self.assertEqual(
                    saved["configuration"]["market_category_override"],
                    "premium smartphone",
                )

    def test_notebook_scope_adapter_matches_service_writer(self):
        namespace = {
            "write_json_with_scope": write_json_with_scope,
            "_write_json_before_scope_lock": write_json,
            "LOCKED_TARGET_SCOPE": {"role": "manufacturer"},
            "AUDIT_SETTINGS": {"market_category_override": "premium smartphone"},
        }
        exec(definition("write_json", last=True), namespace)
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "2026-09-30_apple_US_competitive_visibility_audit.json"
            namespace["write_json"](path, {"configuration": {}})
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["locked_target_scope"],
                {"role": "manufacturer"},
            )

    def test_checkpoint_text_and_zip_share_one_output_directory(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "competitive-visibility-apple"
            write_json(output / "01_company_analysis.json", {"brand": "Apple"})
            write_text(output / "report.md", "# Audit")
            archive = create_audit_zip(output, "2026-09-30_apple_US_competitive_visibility_audit.zip")
            with zipfile.ZipFile(archive) as packed:
                self.assertEqual(
                    set(packed.namelist()),
                    {"01_company_analysis.json", "report.md"},
                )
            with self.assertRaisesRegex(ValueError, "must be a filename"):
                create_audit_zip(output, "../escape.zip")

    def test_resume_restores_matching_archive_without_new_audit(self):
        with tempfile.TemporaryDirectory() as root:
            archive = Path(root) / "competitive-visibility-apple-saved.zip"
            with zipfile.ZipFile(archive, "w") as packed:
                packed.writestr("01_company_analysis.json", json.dumps({
                    "brand": {"domain": "apple.com"},
                }))
                packed.writestr("02_serp_results.json", "{}")
                packed.writestr("00_run_settings.json", json.dumps(SETTINGS))
            restored = find_latest_audit_to_continue(SETTINGS, root)
            self.assertTrue((restored / "02_serp_results.json").is_file())
            self.assertEqual(
                find_latest_audit_to_continue(SETTINGS, root), restored,
            )

    def test_resume_rejects_unsafe_archive_members(self):
        with tempfile.TemporaryDirectory() as root:
            archive = Path(root) / "competitive-visibility-unsafe.zip"
            with zipfile.ZipFile(archive, "w") as packed:
                packed.writestr("01_company_analysis.json", json.dumps({
                    "brand": {"domain": "apple.com"},
                }))
                packed.writestr("02_serp_results.json", "{}")
                packed.writestr("../escape.txt", "escape")
            with self.assertRaisesRegex(ValueError, "unsafe paths"):
                find_latest_audit_to_continue(SETTINGS, root)
            self.assertFalse((Path(root).parent / "escape.txt").exists())


if __name__ == "__main__":
    unittest.main()
