"""Shared Stage 2 candidate aggregation behavior."""

import ast
import json
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from audit_core import search_discovery


NOTEBOOK = Path(__file__).resolve().parents[1] / "competitive_visibility_audit_bd.ipynb"


def candidate(**values):
    return SimpleNamespace(**values)


class SearchDiscoveryCandidateTests(unittest.TestCase):
    def setUp(self):
        self.root_domains = {
            "www.acme.example": "acme.example",
            "shop.acme.example": "acme.example",
            "acme.example": "acme.example",
            "rival.example": "rival.example",
            "blog.rival.example": "rival.example",
            "careers.example": "careers.example",
            "linkedin.com": "linkedin.com",
            "google.com": "google.com",
            "publisher.example": "publisher.example",
        }
        self.root_patch = patch.object(
            search_discovery, "get_root_domain",
            side_effect=lambda domain: self.root_domains.get(
                str(domain).lower().removeprefix("www."),
                str(domain).lower().removeprefix("www."),
            ),
        )
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_serp_aggregation_deduplicates_per_keyword_and_filters_noise(self):
        results = [
            {
                "keyword": "query one", "success": True,
                "results": [
                    {"url": "https://shop.acme.example/item", "rank": 1},
                    {"url": "https://rival.example/product", "rank": 2,
                     "title": "Rival"},
                    {"url": "https://blog.rival.example/article", "rank": 3},
                    {"url": "https://linkedin.com/company/rival", "rank": 4},
                    {"url": "https://careers.example/jobs/role", "rank": 5},
                ],
            },
            {
                "keyword": "query two", "success": True,
                "results": [
                    {"url": "https://www.rival.example/", "rank": 1,
                     "title": "Rival"},
                    {"url": "https://publisher.example/guide", "rank": 2},
                ],
            },
            {"keyword": "query three", "success": False, "results": []},
        ]

        candidates = search_discovery.aggregate_competitor_domains(
            results, "acme.example", 3, candidate_factory=candidate,
        )

        self.assertEqual([item.domain for item in candidates], [
            "rival.example", "publisher.example",
        ])
        rival = candidates[0]
        self.assertEqual(rival.frequency, 2)
        self.assertEqual(rival.keyword_coverage, round(2 / 3, 4))
        self.assertEqual(rival.best_rank, 1)
        self.assertEqual(rival.preferred_hostname, "rival.example")
        self.assertEqual(rival.serp_urls, [
            "https://rival.example/product", "https://www.rival.example/",
        ])

    def test_ai_candidates_exclude_target_and_deduplicate_citations(self):
        results = [
            {
                "question": "buyer question one", "success": True,
                "citations": [
                    {"domain": "acme.example", "position": 1,
                     "url": "https://acme.example/", "title": "Target"},
                    {"domain": "google.com", "position": 2,
                     "url": "https://google.com/", "title": "Search"},
                    {"domain": "publisher.example", "position": 3,
                     "url": "https://publisher.example/a", "title": "Guide"},
                    {"domain": "publisher.example", "position": 4,
                     "url": "https://publisher.example/b", "title": "Guide 2"},
                ],
            },
            {
                "question": "buyer question two", "success": True,
                "citations": [
                    {"domain": "publisher.example", "position": 1,
                     "url": "https://publisher.example/c", "title": "Guide 3"},
                ],
            },
        ]

        candidates = search_discovery.build_ai_mode_source_candidates(
            results, "acme.example", candidate_factory=candidate,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].domain, "publisher.example")
        self.assertEqual(candidates[0].frequency, 2)
        self.assertEqual(candidates[0].best_rank, 1)
        self.assertEqual(len(candidates[0].serp_urls), 2)

    def test_merge_adds_ai_evidence_without_replacing_serp_rank_metrics(self):
        serp = candidate(
            domain="rival.example", total_score=125.0, frequency=2,
            average_rank=2.0, matched_keywords=["question one"],
            serp_urls=["https://rival.example/a"],
            serp_titles=["SERP result"],
        )
        ai = candidate(
            domain="rival.example", total_score=100.0, frequency=2,
            rank_score=1.5, average_rank=1.5,
            matched_keywords=["question one", "question two"],
            serp_urls=["https://rival.example/a", "https://rival.example/b"],
            serp_titles=["AI source", "AI source 2"],
        )

        merged = search_discovery.merge_discovery_candidates([serp], [ai])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].average_rank, 2.0)
        self.assertEqual(merged[0].total_score, 220.0)
        self.assertEqual(merged[0].matched_keywords, [
            "question one", "AI Mode: question one", "AI Mode: question two",
        ])
        self.assertEqual(merged[0].serp_urls, [
            "https://rival.example/a", "https://rival.example/b",
        ])

    def test_notebook_has_no_shadowed_stage_two_implementations(self):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        counts = {}
        for cell in notebook["cells"]:
            if cell["cell_type"] != "code":
                continue
            try:
                tree = ast.parse("".join(cell["source"]))
            except SyntaxError:
                continue
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    counts[node.name] = counts.get(node.name, 0) + 1

        for name in (
            "is_non_competitor_domain", "looks_like_irrelevant_result",
            "preferred_homepage_url", "aggregate_competitor_domains",
            "build_ai_mode_source_candidates", "merge_discovery_candidates",
            "run_serp_stage",
        ):
            self.assertEqual(counts.get(name), 1, name)
        self.assertEqual(counts.get("normalize_citation", 0), 0)


if __name__ == "__main__":
    unittest.main()
