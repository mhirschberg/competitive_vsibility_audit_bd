"""Generated notebook cells must match the service-side Python sources."""

import ast
import json
import tempfile
import unittest
from pathlib import Path

from audit_core import primitives
from audit_core.text_cleaning import remove_ai_boilerplate
from notebook_builder import TEXT_CLEANING_END, TEXT_CLEANING_START
from notebook_builder import (
    NOTEBOOK,
    PRIMITIVES_END,
    PRIMITIVES_START,
    build_notebook,
)


class NotebookBuilderTests(unittest.TestCase):
    def test_checked_in_notebook_is_current(self):
        self.assertEqual(build_notebook(), NOTEBOOK.read_bytes())

    def test_generated_primitives_match_importable_service_module(self):
        notebook = json.loads(build_notebook())
        cell = next(
            cell for cell in notebook["cells"]
            if cell.get("metadata", {}).get("id") == "final-core"
        )
        source = "".join(cell["source"])
        embedded = source.split(PRIMITIVES_START, 1)[1].split(PRIMITIVES_END, 1)[0]
        namespace = {}
        exec(embedded, namespace)

        samples = (
            ("ensure_string_list", (None, [None, " a ", 2], " hello ")),
            ("normalize_boolean", (True, " yes ", "no", 0)),
            ("normalize_confidence", (None, "67", 120, -1, 0.5)),
            ("shorten", ((" product title ", 9), ("short", 20))),
            ("slugify", (" Premium smartphone ", "À B!", "")),
        )
        for name, values in samples:
            for value in values:
                args = value if name == "shorten" else (value,)
                self.assertEqual(
                    namespace[name](*args),
                    getattr(primitives, name)(*args),
                    (name, args),
                )

    def test_shared_serializers_are_not_shadowed_by_legacy_copies(self):
        notebook = json.loads(build_notebook())
        cell = next(
            cell for cell in notebook["cells"]
            if cell.get("metadata", {}).get("id") == "final-orchestration"
        )
        tree = ast.parse("".join(cell["source"]))
        definitions = [
            node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        for name in ("serialize_engine_result", "serialize_profile_task"):
            self.assertEqual(definitions.count(name), 1)
        self.assertNotIn("format_duration", definitions)

    def test_shared_domain_helpers_are_not_shadowed_by_legacy_copies(self):
        notebook = json.loads(build_notebook())
        cell = next(
            cell for cell in notebook["cells"]
            if cell.get("metadata", {}).get("id") == "final-core"
        )
        tree = ast.parse("".join(cell["source"]))
        definitions = [
            node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        for name in (
            "extract_visible_url", "normalize_public_url", "get_hostname",
            "is_google_goto_url",
        ):
            self.assertEqual(definitions.count(name), 1)

    def test_shared_json_parser_is_not_shadowed_by_legacy_copies(self):
        notebook = json.loads(build_notebook())
        cell = next(
            cell for cell in notebook["cells"]
            if cell.get("metadata", {}).get("id") == "final-core"
        )
        tree = ast.parse("".join(cell["source"]))
        definitions = [
            node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(definitions.count("clean_ai_json_text"), 1)
        self.assertEqual(definitions.count("parse_ai_json"), 1)

    def test_shared_text_cleaner_is_not_shadowed_by_legacy_copies(self):
        notebook = json.loads(build_notebook())
        cell = next(
            cell for cell in notebook["cells"]
            if cell.get("metadata", {}).get("id") == "final-core"
        )
        source = "".join(cell["source"])
        tree = ast.parse(source)
        definitions = [
            node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(definitions.count("remove_ai_boilerplate"), 1)
        embedded = source.split(TEXT_CLEANING_START, 1)[1].split(
            TEXT_CLEANING_END, 1,
        )[0]
        namespace = {}
        exec(embedded, namespace)
        sample = "Here is the requested audit\nUseful findings\nLog in"
        self.assertEqual(
            namespace["remove_ai_boilerplate"](sample),
            remove_ai_boilerplate(sample),
        )

    def test_source_change_updates_only_owned_cell(self):
        original = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            changed_source = Path(directory) / "primitives.py"
            changed_source.write_text("VALUE = 17\n", encoding="utf-8")
            generated = json.loads(build_notebook(primitives_source=changed_source))
        for before, after in zip(original["cells"], generated["cells"]):
            if before.get("metadata", {}).get("id") == "final-core":
                self.assertNotEqual(before, after)
                self.assertIn("VALUE = 17", "".join(after["source"]))
            else:
                self.assertEqual(before, after)

    def test_missing_marker_fails_without_modifying_notebook(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notebook.ipynb"
            stale = NOTEBOOK.read_text(encoding="utf-8").replace(
                PRIMITIVES_START, "missing marker", 1
            )
            path.write_text(stale, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "marker pair"):
                build_notebook(notebook_path=path)
            self.assertEqual(path.read_text(encoding="utf-8"), stale)


if __name__ == "__main__":
    unittest.main()
