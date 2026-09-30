"""Parity for the shared competitor shortlist, prompts, and AI verdict rules."""

import ast
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

from audit_core import competitor_decisions
from audit_core.competitor_scope import LOCKED_SCOPE_CONFLICT_RETRY_MAX_RANK


NOTEBOOK = Path(__file__).resolve().parents[1] / "competitive_visibility_audit_bd.ipynb"
CHECKS = (
    "active_in_target_country", "same_category", "same_market_role",
    "same_business_model", "same_primary_customers", "same_core_transaction",
    "offering_is_substitute",
)


def root_domain(value):
    value = str(value or "")
    parsed = urlparse(value if "://" in value else "https://" + value)
    return (parsed.hostname or "").removeprefix("www.")


def ports():
    return competitor_decisions.CompetitorDecisionPorts(
        lambda code: {"code": code, "name": "United States" if code == "US" else code},
        root_domain,
        lambda value: value if value.startswith("https://") else "https://" + value,
        root_domain,
        lambda _domain, _country: 0,
    )


def wrapper_namespace():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    cell = next(
        item for item in notebook["cells"]
        if item.get("metadata", {}).get("id") == "runtime-utilities-merged"
    )
    source = "".join(cell["source"])
    names = {
        "canonical_candidate_validation_data",
        "build_locked_scope_discovery_prompt",
        "build_locked_candidate_universe",
        "build_locked_scope_validation_prompt",
        "discovery_supports_consistency_retry",
        "build_locked_scope_validation_retry_prompt",
        "normalize_locked_scope_validation",
    }
    namespace = {
        "_competitor_decision_ports": ports,
        "LOCKED_SCOPE_CONFLICT_RETRY_MAX_RANK": LOCKED_SCOPE_CONFLICT_RETRY_MAX_RANK,
    }
    namespace.update({
        "core_" + name: getattr(competitor_decisions, "core_" + name)
        for name in names
    })
    tree = ast.parse(source)
    definitions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    if {node.name for node in definitions} != names:
        raise AssertionError("Missing notebook decision wrappers")
    for node in definitions:
        exec(ast.get_source_segment(source, node), namespace)
    return namespace


class CompetitorDecisionTests(unittest.TestCase):
    def setUp(self):
        self.scope = {
            "brand_name": "Apple", "official_url": "https://apple.com/",
            "domain": "apple.com", "category": "Premium smartphone",
            "market_role": "manufacturer", "business_model": "Makes smartphones",
            "primary_customers": ["Premium smartphone buyers"],
            "core_offerings": ["iPhone"], "audit_focus": "premium smartphone",
            "substitute_definition": "Flagship smartphones", "country": "US",
        }
        self.discovered = [
            {"brand_name": "Samsung", "domain": "samsung.com",
             "official_url": "https://samsung.com/", "rank_by_directness": 1,
             "market_prominence": 0.95, "confidence": 0.98,
             "candidate_role": "manufacturer", "reason": "Direct substitute"},
            {"brand_name": "Google", "domain": "google.com",
             "official_url": "https://google.com/", "rank_by_directness": 2,
             "market_prominence": 0.85, "confidence": 0.9,
             "candidate_role": "manufacturer", "reason": "Pixel smartphones"},
            {"brand_name": "Apple", "domain": "apple.com",
             "rank_by_directness": 3},
        ]
        self.observed = [
            SimpleNamespace(domain="samsung.com", homepage_url="https://samsung.com/",
                            frequency=3, total_score=85),
            SimpleNamespace(domain="google.com", homepage_url="https://google.com/",
                            frequency=1, total_score=30),
        ]

    def test_universe_and_prompts_match_notebook_wrappers(self):
        notebook = wrapper_namespace()
        service_universe = competitor_decisions.core_build_locked_candidate_universe(
            self.observed, self.discovered, self.scope, ports()
        )
        embedded_universe = notebook["build_locked_candidate_universe"](
            self.observed, self.discovered, self.scope
        )
        self.assertEqual(service_universe, embedded_universe)
        self.assertEqual(
            [item["brand_name"] for item in service_universe],
            ["Samsung", "Google"],
        )
        discovery_prompt = notebook["build_locked_scope_discovery_prompt"](
            self.scope, [item.domain for item in self.observed]
        )
        self.assertEqual(
            discovery_prompt,
            competitor_decisions.core_build_locked_scope_discovery_prompt(
                self.scope, [item.domain for item in self.observed], ports()
            ),
        )
        candidate = service_universe[0]
        validation_prompt = notebook["build_locked_scope_validation_prompt"](
            self.scope, candidate
        )
        self.assertEqual(
            validation_prompt,
            competitor_decisions.core_build_locked_scope_validation_prompt(
                self.scope, candidate, ports()
            ),
        )
        self.assertIn('"is_direct_competitor"', validation_prompt)
        self.assertIn("Samsung", validation_prompt)

    def test_structured_verdict_and_retry_match_notebook_wrappers(self):
        notebook = wrapper_namespace()
        candidate = competitor_decisions.core_build_locked_candidate_universe(
            self.observed, self.discovered, self.scope, ports()
        )[0]
        answer = {
            "candidate_name": "Samsung", "candidate_domain": "samsung.com",
            "official_url": "https://samsung.com/", "candidate_role": "manufacturer",
            "is_direct_competitor": True, "confidence": 0.95,
            "market_prominence": 0.9, "reason": "Competing flagship smartphones",
            **{check: True for check in CHECKS},
        }
        canonical = competitor_decisions.core_canonical_candidate_validation_data(
            answer, "manufacturer"
        )
        self.assertEqual(
            canonical,
            notebook["canonical_candidate_validation_data"](answer, "manufacturer"),
        )
        verdict = competitor_decisions.core_normalize_locked_scope_validation(
            answer, candidate, self.scope, ports()
        )
        self.assertEqual(
            verdict,
            notebook["normalize_locked_scope_validation"](
                answer, candidate, self.scope
            ),
        )
        self.assertTrue(verdict["is_direct_competitor"])
        self.assertEqual(verdict["candidate_role"], "manufacturer")
        retry = notebook["build_locked_scope_validation_retry_prompt"](
            self.scope, candidate, {**verdict, "is_direct_competitor": False}
        )
        self.assertEqual(
            retry,
            competitor_decisions.core_build_locked_scope_validation_retry_prompt(
                self.scope, candidate, {**verdict, "is_direct_competitor": False}
            ),
        )

    def test_incomplete_answer_is_not_a_negative_verdict(self):
        with self.assertRaisesRegex(ValueError, "lacks boolean"):
            competitor_decisions.core_canonical_candidate_validation_data(
                {"candidate_role": "manufacturer", "is_direct_competitor": False},
                "manufacturer",
            )


if __name__ == "__main__":
    unittest.main()
