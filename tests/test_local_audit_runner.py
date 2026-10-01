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
        self.assertEqual(default_args.reddit_comment_posts_per_cohort, 0)
        self.assertTrue(enabled_args.include_reddit)
        selected_args = run_local_audit.build_parser().parse_args(
            [*base_args, "--include-reddit", "--reddit-comment-posts-per-cohort", "2"]
        )
        self.assertEqual(selected_args.reddit_comment_posts_per_cohort, 2)

    def test_service_adapter_dry_run_selects_opt_in_builder(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / '.env.local'
            env_file.write_text(
                'BRIGHTDATA_API_TOKEN=test-token\nSERP_ZONE=test-zone\n',
                encoding='utf-8',
            )
            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch('runner_builder._build_runner_script') as old:
                    with mock.patch(
                        'runner_builder._build_service_runner_script',
                        return_value='print("dry run")\n',
                    ) as new:
                        result = run_local_audit.main([
                            '--company', 'Apple', '--domain', 'apple.com',
                            '--env-file', str(env_file), '--dry-run',
                            '--engine-mode', 'service_adapter',
                        ])
            self.assertEqual(result, 0)
            old.assert_not_called()
            new.assert_called_once()

    def test_process_tree_rss_includes_descendants(self):
        snapshot = '10 1 100\n11 10 200\n12 11 300\n13 1 400\n'
        with mock.patch.object(run_local_audit.subprocess, 'run') as run:
            run.return_value.stdout = snapshot
            self.assertEqual(run_local_audit.process_tree_rss_kib(10), 600)


if __name__ == "__main__":
    unittest.main()
