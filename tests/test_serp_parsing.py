"""Parsed-light Google results use the same normalizer in service and notebook."""

import json
from pathlib import Path
import unittest
from urllib.parse import urlparse

from audit_core.serp_parsing import (
    core_find_parsed_organic_results, normalize_parsed_serp_records,
)
from notebook_builder import (
    SERP_PARSING_END, SERP_PARSING_SOURCE, SERP_PARSING_START,
)
from tests.test_google_ai_timeout_safety import definition


NOTEBOOK = Path(__file__).resolve().parents[1] / "competitive_visibility_audit_bd.ipynb"


def root_domain(value):
    return (urlparse(value).hostname or "").removeprefix("www.")


class SerpParsingTests(unittest.TestCase):
    def test_nested_parsed_light_shape_preserves_rank_and_destination(self):
        data = {"payload": [{"webPages": {"value": [
            {"link": "https://example.com/a", "title": "A", "global_rank": 3},
            {"href": "https://example.org/b", "snippet": "B detail"},
        ]}}]}
        result = normalize_parsed_serp_records(
            data, "test query", "google", get_root_domain=root_domain
        )
        self.assertEqual(result["raw_result_count"], 2)
        self.assertEqual([item["rank"] for item in result["results"]], [3, 2])
        self.assertEqual([item["domain"] for item in result["results"]], [
            "example.com", "example.org"
        ])
        self.assertEqual(result["results"][1]["description"], "B detail")

    def test_notebook_wrapper_matches_importable_normalizer(self):
        data = {"payload": [{"organic": [
            {"link": "https://example.com/a", "title": "A", "rank": "4"},
        ]}]}
        namespace = {
            "core_find_parsed_organic_results": core_find_parsed_organic_results,
            "normalize_parsed_serp_records": normalize_parsed_serp_records,
            "get_root_domain": root_domain,
        }
        exec(definition("find_parsed_organic_results"), namespace)
        exec(definition("normalize_serp_records"), namespace)
        bundled = namespace["normalize_serp_records"](data, "question", "google")
        service = normalize_parsed_serp_records(
            data, "question", "google", get_root_domain=root_domain
        )
        self.assertEqual(bundled, service)

    def test_notebook_embeds_exact_source(self):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        cell = next(
            cell for cell in notebook["cells"]
            if cell.get("metadata", {}).get("id") == "final-core"
        )
        source = "".join(cell["source"])
        embedded = source.split(SERP_PARSING_START, 1)[1].split(
            SERP_PARSING_END, 1
        )[0].strip()
        self.assertEqual(embedded, SERP_PARSING_SOURCE.read_text().strip())


if __name__ == "__main__":
    unittest.main()
