import ast
import json
import unittest
from pathlib import Path

from app import _build_runner_script


ROOT = Path(__file__).resolve().parents[1]


class WebLongWaitTests(unittest.TestCase):
    def test_checkbox_is_sent_with_audit_request(self):
        html = (ROOT / "web/index.html").read_text(encoding="utf-8")
        js = (ROOT / "web/src/main.js").read_text(encoding="utf-8")
        self.assertIn('name="wait_longer_for_google_ai_mode" type="checkbox"', html)
        self.assertIn('wait_longer_for_google_ai_mode: data.get("wait_longer_for_google_ai_mode") === "on"', js)
        for engine in ("google_ai_mode", "chatgpt_visibility", "gemini_visibility", "copilot_visibility"):
            self.assertIn(f'name="include_{engine}" type="checkbox"', html)
            self.assertIn(f'include_{engine}: data.get("include_{engine}") === "on"', js)
        for engine in ("chatgpt", "gemini", "copilot"):
            self.assertIn(f'name="wait_longer_for_{engine}" type="checkbox"', html)
            self.assertIn(f'wait_longer_for_{engine}: data.get("wait_longer_for_{engine}") === "on"', js)

    def test_comment_collection_has_explicit_off_default(self):
        html = (ROOT / "web/index.html").read_text(encoding="utf-8")
        js = (ROOT / "web/src/main.js").read_text(encoding="utf-8")
        self.assertIn('name="reddit_comment_posts_per_cohort"', html)
        self.assertIn('<option value="0" selected>', html)
        self.assertIn('reddit_comment_posts_per_cohort: Number(data.get(', js)

    def test_runner_passes_engine_choices_without_rewriting_notebook_timeouts(self):
        args = ("Acme", "example.com", "widgets", "US", "auto", False, False)
        standard = _build_runner_script(*args)
        extended = _build_runner_script(*args, True)
        def config(source):
            assignment = next(
                node for node in ast.parse(source).body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "_WEB_CONFIG" for target in node.targets)
            )
            return json.loads(assignment.value.args[0].value)
        self.assertFalse(config(standard)["include_google_ai_mode"])
        self.assertFalse(config(extended)["include_google_ai_mode"])
        self.assertFalse(config(standard)["wait_longer_for_google_ai_mode"])
        self.assertTrue(config(extended)["wait_longer_for_google_ai_mode"])
        notebook = json.loads((ROOT / "competitive_visibility_audit_bd.ipynb").read_text(encoding="utf-8"))
        source = "\n".join("".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code")
        self.assertIn('if measure_google_ai_mode else []', source)
        self.assertIn('1800 if long_wait', source)
        self.assertIn('900 if wait_longer_for_copilot else 360', source)
        compile(extended, "<extended-runner>", "exec")


if __name__ == "__main__":
    unittest.main()
