"""Service/notebook parity for neutral prompts and reported AI citations."""

import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import tldextract

from audit_core.domains import canonical_source_url, get_root_domain
from audit_core.visibility_prompt import build_visibility_prompt_core
from audit_core.visibility_sources import (
    collect_visibility_sources_core,
    collect_visibility_sources_service,
)


NOTEBOOK = Path(__file__).resolve().parents[1] / "competitive_visibility_audit_bd.ipynb"


def notebook_cell(fragment):
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return next(
        "".join(cell["source"]) for cell in notebook["cells"]
        if cell.get("cell_type") == "code"
        and fragment in "".join(cell["source"])
    )


class VisibilityInputTests(unittest.TestCase):
    def setUp(self):
        extractor = tldextract.TLDExtract(cache_dir=None, suffix_list_urls=())
        offline = patch("tldextract.extract", extractor)
        offline.start()
        self.addCleanup(offline.stop)

    def test_neutral_prompt_matches_notebook_adapter(self):
        profile = SimpleNamespace(category="premium smartphone", brand_name="Apple")
        keywords = ["best camera phone", "phone battery life"]
        source = notebook_cell("# AUDIT-VISIBILITY-PROMPT: start")
        code = source.split("# AUDIT-VISIBILITY-PROMPT: start\n", 1)[1]
        code = code.split("# Brand mention detection", 1)[0]
        namespace = {"AUDIT_SETTINGS": {"audit_focus": "mobile photography"}}
        exec(compile(code, "notebook-prompt", "exec"), namespace)
        notebook_prompt = namespace["build_visibility_prompt"](profile, keywords)
        service_prompt = build_visibility_prompt_core(
            profile, keywords, audit_focus="mobile photography"
        )
        self.assertEqual(service_prompt, notebook_prompt)
        self.assertIn("mobile photography", service_prompt)
        self.assertNotIn("Apple", service_prompt)

    def test_prompt_limit_is_preserved(self):
        profile = SimpleNamespace(category="phones")
        with self.assertRaisesRegex(ValueError, "too long"):
            build_visibility_prompt_core(profile, ["x" * 4096])

    def test_sources_match_notebook_and_filter_unresolved_google_urls(self):
        visibility = {
            "audited_domains": {"rayner.com": "Rayner"},
            "engines": {
                "google_ai_mode": {"citations": [
                    {"url": "https://www.google.com/goto/opaque", "title": "Redirect"},
                    {"url": "https://rayner.com/products/lens?utm_source=ai", "title": "Lens"},
                    {"url": "https://reddit.com/r/eyes/comments/1", "title": "Experience"},
                    {"url": "https://google.com/search?q=lens", "title": "Interface"},
                ]},
                "chatgpt": {"citations": [
                    {"url": "https://rayner.com/products/lens?src=chatgpt", "title": "Duplicate"},
                    {"link": "https://marketsandmarkets.com/report/1", "name": "Market report"},
                    {"url": "https://forbes.com/review/1", "title": "Review"},
                ]},
            },
        }
        resolver = lambda url: (
            "https://forbes.com/review/goto" if "/goto/" in url else url
        )
        goto = lambda url: "/goto/" in url

        source = notebook_cell("# AUDIT-VISIBILITY-SOURCES: start")
        code = source.split("# AUDIT-VISIBILITY-SOURCES: start\n", 1)[1]
        code = code.split("# AUDIT-REPORT-EXPORT: start", 1)[0]
        namespace = {
            "canonical_source_url": canonical_source_url,
            "get_root_domain": get_root_domain,
            "resolve_google_goto_url": resolver,
            "is_google_goto_url": goto,
            "collect_visibility_sources_service": collect_visibility_sources_service,
        }
        exec(compile(code, "notebook-sources", "exec"), namespace)
        notebook_base = namespace["collect_visibility_sources"](visibility)
        service_base = collect_visibility_sources_core(
            visibility, resolve_google_goto_url=resolver,
            is_google_goto_url=goto,
        )
        self.assertEqual(notebook_base, service_base)

        quality_source = notebook_cell("# Remove unresolved Google interface URLs")
        quality_code = quality_source.split(
            "# Remove unresolved Google interface URLs from source reporting\n", 1
        )[1].split("# Strengthen final-report instructions", 1)[0]
        exec(compile(
            quality_code,
            "notebook-source-quality", "exec",
        ), namespace)
        notebook_effective = namespace["collect_visibility_sources"](visibility)
        service_effective = collect_visibility_sources_service(
            visibility, resolve_google_goto_url=resolver,
            is_google_goto_url=goto,
        )
        self.assertEqual(notebook_effective, service_effective)
        self.assertEqual(
            [item["source_type"] for item in service_effective],
            ["Publisher or editorial", "Official audited brand",
             "Social or community", "Market research or directory",
             "Publisher or editorial"],
        )
        self.assertNotIn("google.com", [item["domain"] for item in service_effective])

    def test_canonical_url_deduplicates_query_and_fragment(self):
        self.assertEqual(
            canonical_source_url("https://EXAMPLE.com/a/?x=1#section"),
            "https://example.com/a",
        )


if __name__ == "__main__":
    unittest.main()
