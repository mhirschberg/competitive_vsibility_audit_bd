import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import run_local_audit


class LocalAuditRunnerTests(unittest.TestCase):
    def test_load_env_file_keeps_existing_values_and_parses_quotes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.local"
            path.write_text(
                "BRIGHTDATA_API_TOKEN='file-token'\nSERP_ZONE=zone-from-file\n",
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {"BRIGHTDATA_API_TOKEN": "existing-token"},
                clear=True,
            ):
                loaded = run_local_audit.load_env_file(path)
                self.assertEqual(os.environ["BRIGHTDATA_API_TOKEN"], "existing-token")
                self.assertEqual(os.environ["SERP_ZONE"], "zone-from-file")
                self.assertEqual(loaded, {"BRIGHTDATA_API_TOKEN", "SERP_ZONE"})

    def test_create_run_directory_never_reuses_a_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            first = run_local_audit.create_run_directory(directory, "Acme Inc.")
            second = run_local_audit.create_run_directory(directory, "Acme Inc.")
            self.assertNotEqual(first, second)
            self.assertTrue(first.is_dir())
            self.assertTrue(second.is_dir())

    def test_reddit_analysis_is_opt_in(self):
        base_args = ["--company", "Acme", "--domain", "example.com"]

        default_args = run_local_audit.build_parser().parse_args(base_args)
        enabled_args = run_local_audit.build_parser().parse_args(
            [*base_args, "--include-reddit"]
        )

        self.assertFalse(default_args.include_reddit)
        self.assertTrue(enabled_args.include_reddit)


if __name__ == "__main__":
    unittest.main()
