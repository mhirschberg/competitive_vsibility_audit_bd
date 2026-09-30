"""The hosted runner builder must stay independent of the legacy Gradio UI."""

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RunnerBuilderTests(unittest.TestCase):
    def test_importing_builder_does_not_load_gradio(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys, runner_builder; "
                    "assert 'gradio' not in sys.modules; "
                    "assert runner_builder.NOTEBOOK_PATH.is_file()"
                ),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_legacy_app_exports_same_builder_during_migration(self):
        import app
        import runner_builder

        self.assertIs(app._build_runner_script, runner_builder._build_runner_script)
        self.assertIs(app._build_config_cell, runner_builder._build_config_cell)


if __name__ == "__main__":
    unittest.main()
