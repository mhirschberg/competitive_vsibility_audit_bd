import tempfile
import unittest
from pathlib import Path

from scripts.rerun_reddit_stage import find_audit_json, find_existing_reddit_result


class RerunRedditStageTests(unittest.TestCase):
    def test_finds_contextual_report_name_in_run_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_directory = root / "competitive-visibility-apple-20260930"
            run_directory.mkdir()
            report = run_directory / "2026-09-30_apple_iPhone_US_competitive_visibility_audit.json"
            report.write_text("{}", encoding="utf-8")
            self.assertEqual(find_audit_json(run_directory), report.resolve())
            self.assertEqual(find_audit_json(root), report.resolve())

    def test_reuse_falls_back_to_canonical_full_run_result(self):
        with tempfile.TemporaryDirectory() as directory:
            run_directory = Path(directory)
            audit_path = run_directory / "06_competitive_visibility_audit.json"
            retry_path = run_directory / "05_reddit_social.retry.json"
            canonical_path = run_directory / "05_reddit_social.json"
            canonical_path.write_text("{}\n", encoding="utf-8")

            result = find_existing_reddit_result(audit_path, retry_path)

            self.assertEqual(result, canonical_path)

    def test_reuse_prefers_retry_result_when_both_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            run_directory = Path(directory)
            audit_path = run_directory / "06_competitive_visibility_audit.json"
            retry_path = run_directory / "05_reddit_social.retry.json"
            canonical_path = run_directory / "05_reddit_social.json"
            retry_path.write_text("{}\n", encoding="utf-8")
            canonical_path.write_text("{}\n", encoding="utf-8")

            result = find_existing_reddit_result(audit_path, retry_path)

            self.assertEqual(result, retry_path)


if __name__ == "__main__":
    unittest.main()
