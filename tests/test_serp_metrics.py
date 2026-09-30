"""Service/notebook parity for ordinary-search visibility accounting."""

import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import tldextract

from audit_core.domains import get_root_domain
from audit_core.serp_metrics import (
    calculate_all_serp_metrics,
    calculate_serp_metrics,
)


ROOT = Path(__file__).resolve().parents[1]


def embedded_namespace():
    notebook = json.loads((ROOT / "competitive_visibility_audit_bd.ipynb").read_text())
    cells = {cell.get("metadata", {}).get("id"): "".join(cell["source"])
             for cell in notebook["cells"]}
    namespace = {}
    for cell_id, label in (("final-core", "DOMAINS"),
                           ("final-orchestration", "SERP-METRICS")):
        source = cells[cell_id]
        start = f"# AUDIT-{label}: start\n"
        end = f"# AUDIT-{label}: end"
        code = source.split(start, 1)[1].split(end, 1)[0]
        exec(compile(code, f"embedded-{label}", "exec"), namespace)
    return namespace


class SerpMetricTests(unittest.TestCase):
    def setUp(self):
        # The public-suffix snapshot is bundled with the package; unit tests
        # must not need a writable home cache or a live network fetch.
        extractor = tldextract.TLDExtract(cache_dir=None, suffix_list_urls=())
        mock = patch("tldextract.extract", extractor)
        mock.start()
        self.addCleanup(mock.stop)
        self.keyword_results = [
            {
                "keyword": "project management software",
                "success": True,
                "results": [{
                    "rank": 3,
                    "domain": "microsoft.com",
                    "url": "https://microsoft.com/microsoft-365/planner",
                    "title": "Microsoft Planner",
                    "description": "Project management templates",
                }],
            },
            {
                "keyword": "collaborative workspace components",
                "success": True,
                "results": [{
                    "rank": "2",
                    "domain": "microsoft.com",
                    "url": "https://www.microsoft.com/microsoft-loop",
                    "title": "Microsoft Loop",
                    "description": "Collaborative Loop workspaces",
                }],
            },
            {"keyword": "unmeasured buyer question", "success": False, "results": []},
        ]

    def test_root_domain_matches_notebook_for_multilevel_suffix(self):
        notebook = embedded_namespace()
        for value in ("https://www.example.co.uk/path", "example.com/offer", ""):
            with self.subTest(value=value):
                self.assertEqual(get_root_domain(value), notebook["get_root_domain"](value))

    def test_shared_corporate_domain_requires_brand_evidence(self):
        metric = calculate_serp_metrics(
            "microsoft.com", self.keyword_results, brand_name="Microsoft Loop"
        )
        self.assertEqual(metric["appearances"], 1)
        self.assertEqual(metric["total_keywords"], 2)
        self.assertEqual(metric["coverage"], 0.5)
        self.assertEqual(metric["best_rank"], 2)
        self.assertEqual(metric["details"][0]["keyword"],
                         "collaborative workspace components")

    def test_service_and_notebook_metrics_match(self):
        notebook = embedded_namespace()
        profiles = [SimpleNamespace(domain="microsoft.com", brand_name="Microsoft Loop")]
        service = calculate_all_serp_metrics(profiles, self.keyword_results)
        bundled = notebook["calculate_all_serp_metrics"](profiles, self.keyword_results)
        self.assertEqual(service, bundled)

    def test_failed_search_does_not_change_denominator(self):
        metric = calculate_serp_metrics(
            "example.com", [{"keyword": "unavailable", "success": False,
                             "results": [{"domain": "example.com", "rank": 1}]}]
        )
        self.assertEqual(metric["total_keywords"], 0)
        self.assertEqual(metric["appearances"], 0)
        self.assertEqual(metric["coverage"], 0)


if __name__ == "__main__":
    unittest.main()
