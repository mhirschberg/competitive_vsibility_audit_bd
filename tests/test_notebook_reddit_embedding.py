import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "competitive_visibility_audit_bd.ipynb"
MODULE = ROOT / "reddit_social.py"
START = "# REDDIT-SOCIAL-PATCH: start"
END = "# REDDIT-SOCIAL-PATCH: end"


class NotebookEmbeddingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))

    def test_embedded_module_matches_source_file(self):
        runtime = "".join(self.notebook["cells"][6]["source"])
        self.assertEqual(runtime.count(START), 1)
        self.assertEqual(runtime.count(END), 1)
        embedded = runtime.split(START, 1)[1].split(END, 1)[0].strip("\n")
        source = MODULE.read_text(encoding="utf-8").strip("\n")
        self.assertEqual(embedded, source)

    def test_orchestration_hooks_are_present_once(self):
        orchestration = "".join(self.notebook["cells"][5]["source"])
        for hook in (
            "run_reddit_social_stage(",
            'output_directory / "05_reddit_social.json"',
            "insert_reddit_report_section(",
            '"reddit_social": reddit_social_result',
        ):
            self.assertEqual(orchestration.count(hook), 1, hook)

    def test_modified_code_cells_compile(self):
        for index in range(2, 7):
            source = "".join(self.notebook["cells"][index]["source"])
            compile(source, f"notebook-cell-{index}", "exec")

        run_cell = "".join(self.notebook["cells"][7]["source"])
        web_run_cell = re.sub(
            r"AUDIT_RESULT\s*=\s*await\s+run_competitive_visibility_audit\(\s*AUDIT_SETTINGS\s*\)",
            "AUDIT_RESULT = asyncio.run(run_competitive_visibility_audit(AUDIT_SETTINGS))",
            run_cell,
            flags=re.MULTILINE,
        )
        compile(web_run_cell, "notebook-web-run-cell", "exec")


if __name__ == "__main__":
    unittest.main()
