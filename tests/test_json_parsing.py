"""AI JSON parsing behavior shared by the hosted service and notebook."""

import unittest

from audit_core.json_parsing import clean_ai_json_text, parse_ai_json
from notebook_builder import JSON_PARSING_END, JSON_PARSING_START, build_notebook


class JsonParsingTests(unittest.TestCase):
    def test_plain_fenced_and_intro_wrapped_objects(self):
        answers = (
            '{"brand": "Rayner"}',
            '```json\n{"brand": "Rayner"}\n```',
            'Here is the result:\n{"brand": "Rayner"}\nDone.',
        )
        for answer in answers:
            with self.subTest(answer=answer):
                self.assertEqual(parse_ai_json(answer), {"brand": "Rayner"})

    def test_markdown_escaped_braces_and_repairable_trailing_comma(self):
        self.assertEqual(
            parse_ai_json(r'\{"name": "Acme"\}'), {"name": "Acme"},
        )
        self.assertEqual(
            parse_ai_json('{"name": "Acme",}'), {"name": "Acme"},
        )

    def test_json_array_uses_first_object_and_invalid_answer_is_diagnostic(self):
        self.assertEqual(parse_ai_json('[{"id": 1}, {"id": 2}]'), {"id": 1})
        with self.assertRaisesRegex(ValueError, "AI returned empty answer text"):
            parse_ai_json("  ")
        with self.assertRaisesRegex(ValueError, "Response preview"):
            parse_ai_json("not JSON at all")

    def test_text_cleaning_preserves_plain_unwrapped_json(self):
        self.assertEqual(
            clean_ai_json_text("```JSON\n {\"id\": 1} \n```"),
            '{"id": 1}',
        )

    def test_notebook_embeds_the_same_parser_behavior(self):
        import json as json_module

        notebook = json_module.loads(build_notebook())
        cell = next(
            cell for cell in notebook["cells"]
            if cell.get("metadata", {}).get("id") == "final-core"
        )
        source = "".join(cell["source"])
        embedded = source.split(JSON_PARSING_START, 1)[1].split(
            JSON_PARSING_END, 1,
        )[0]
        namespace = {}
        exec(embedded, namespace)
        for answer in (
            '{"company": "Apple"}',
            '```json\n{"company": "Apple"}\n```',
            'Answer: {"company": "Apple",}',
        ):
            self.assertEqual(
                namespace["parse_ai_json"](answer), parse_ai_json(answer),
            )


if __name__ == "__main__":
    unittest.main()
