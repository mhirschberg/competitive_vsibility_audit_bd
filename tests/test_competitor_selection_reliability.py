"""Regression checks for incomplete research and search-only candidates."""

import ast
import json
from pathlib import Path
import unittest


NOTEBOOK = Path(__file__).resolve().parents[1] / "competitive_visibility_audit_bd.ipynb"
CHECKS = (
    "active_in_target_country", "same_category", "same_market_role",
    "same_business_model", "same_primary_customers", "same_core_transaction",
    "offering_is_substitute",
)


def notebook_definition(name):
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    matches = []
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue
        source = "".join(cell["source"])
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                matches.append(ast.get_source_segment(source, node))
    return matches[-1]


class CompetitorSelectionReliabilityTests(unittest.TestCase):
    @staticmethod
    def schema_namespace():
        namespace = {
            "LOCKED_SCOPE_VALIDATION_CHECKS": CHECKS,
            "json": json,
            "identify_google_ai_research_task": lambda _prompt: "candidate_validation_json",
            "parse_ai_json": json.loads,
        }
        exec(notebook_definition("canonical_candidate_validation_data"), namespace)
        exec(notebook_definition("validate_google_ai_research_answer"), namespace)
        return namespace

    def test_identity_only_answer_is_not_a_negative_verdict(self):
        namespace = self.schema_namespace()
        answer = json.dumps({
            "candidate_name": "Samsung Electronics",
            "candidate_domain": "samsung.com",
            "official_url": "https://samsung.com/us/",
        })
        result = namespace["validate_google_ai_research_answer"](answer, "candidate prompt")
        self.assertFalse(result["valid"])
        self.assertIn("lacks boolean", result["reason"])
        with self.assertRaisesRegex(ValueError, "lacks boolean"):
            namespace["canonical_candidate_validation_data"](json.loads(answer), "manufacturer")

    def test_complete_nested_provider_answer_is_canonicalized(self):
        namespace = self.schema_namespace()
        answer = {
            "candidate_name": "Samsung Electronics",
            "candidate_domain": "samsung.com",
            "matches_target_scope": True,
            "validation": {
                **{key: True for key in CHECKS if key != "offering_is_substitute"},
                "realistic_substitute": True,
            },
            "decision": "VALID_DIRECT_COMPETITOR",
            "evidence": {"category_and_role": "Galaxy Ultra is a US flagship smartphone."},
        }
        result = namespace["validate_google_ai_research_answer"](
            json.dumps(answer), "candidate prompt"
        )
        self.assertTrue(result["valid"])
        canonical = namespace["canonical_candidate_validation_data"](
            result["parsed"], "manufacturer"
        )
        self.assertEqual(canonical["candidate_role"], "manufacturer")
        self.assertTrue(canonical["is_direct_competitor"])
        self.assertTrue(canonical["offering_is_substitute"])
        self.assertEqual(canonical["evidence"], ["Galaxy Ultra is a US flagship smartphone."])

    def test_flat_aliases_keep_explicit_false(self):
        namespace = self.schema_namespace()
        answer = {
            "candidate_name": "Carrier",
            "candidate_role": "service_provider",
            **{key: True for key in CHECKS if key != "offering_is_substitute"},
            "realistic_substitute": False,
            "direct_competitor": False,
        }
        canonical = namespace["canonical_candidate_validation_data"](answer)
        self.assertFalse(canonical["offering_is_substitute"])
        self.assertFalse(canonical["is_direct_competitor"])

    def test_nested_rejection_without_role_is_inconclusive(self):
        namespace = self.schema_namespace()
        answer = {
            "candidate_name": "Unknown",
            "matches_target_scope": False,
            "validation": {key: False for key in CHECKS},
            "decision": "REJECT",
        }
        result = namespace["validate_google_ai_research_answer"](
            json.dumps(answer), "candidate prompt"
        )
        self.assertFalse(result["valid"])
        self.assertIn("lacks a market role", result["reason"])

    def test_candidate_prompts_keep_complete_schema_under_provider_limit(self):
        namespace = {
            "json": json,
            "locked_scope_country_details": lambda _country: {"name": "United States", "code": "US"},
        }
        exec(notebook_definition("identify_google_ai_research_task"), namespace)
        exec(notebook_definition("build_locked_scope_validation_prompt"), namespace)
        exec(notebook_definition("build_locked_scope_validation_retry_prompt"), namespace)
        scope = {
            "brand_name": "Apple", "category": "premium smartphone", "market_role": "manufacturer",
            "business_model": "Creates and sells its own products " * 20,
            "primary_customers": ["premium buyers" * 20] * 8,
            "core_offerings": ["high-end smartphones" * 20] * 8,
            "substitute_definition": "Comparable flagship phones " * 30,
            "audit_focus": "premium smartphone", "country": "US",
        }
        candidate = {
            "brand_name": "Google", "representative_domain": "google.com",
            "official_url": "https://store.google.com/us/",
            "domains": ["google.com"], "observed_frequency": 0,
            "discovery_rank": 2,
            "discovery_record": {
                "candidate_role": "manufacturer", "reason": "Direct substitute. " * 100,
                "confidence": 0.99,
            },
        }
        prompt = namespace["build_locked_scope_validation_prompt"](scope, candidate)
        self.assertEqual(
            namespace["identify_google_ai_research_task"](prompt),
            "candidate_validation_json",
        )
        retry = namespace["build_locked_scope_validation_retry_prompt"](
            scope, candidate, {"reason": "conflict", "is_direct_competitor": False}
        )
        for answer_prompt in (prompt, retry):
            self.assertLess(len(answer_prompt), 3800)
            self.assertIn('"is_direct_competitor"', answer_prompt)
            self.assertTrue(answer_prompt.endswith("}" if answer_prompt is retry else "Return JSON only."))

    def test_search_only_candidate_cannot_replace_credible_shortlist(self):
        namespace = {
            "discovery_supports_consistency_retry": (
                lambda candidate, _scope, max_rank=5:
                candidate.get("discovery_rank", 999) <= max_rank
                and candidate.get("discovery_confidence", 0) >= 0.8
            ),
        }
        exec(notebook_definition("mark_uncorroborated_search_candidates"), namespace)
        candidates = [
            {"brand_name": "Samsung", "discovery_rank": 1, "discovery_confidence": 0.99},
            {"brand_name": "Google", "discovery_rank": 2, "discovery_confidence": 0.97},
            {"brand_name": "Vertu", "discovery_rank": 999, "discovery_confidence": 0.0},
        ]
        results = [
            {"candidate_record": candidate, "validation": {"is_direct_competitor": True}}
            for candidate in candidates
        ]
        namespace["mark_uncorroborated_search_candidates"](candidates, results, {})
        self.assertNotIn("selection_ineligible_reason", results[0])
        self.assertNotIn("selection_ineligible_reason", results[1])
        self.assertIn("Only observed in search", results[2]["selection_ineligible_reason"])

    def test_search_candidate_remains_eligible_if_discovery_is_sparse(self):
        namespace = {
            "discovery_supports_consistency_retry": (
                lambda candidate, _scope, max_rank=5: candidate.get("discovery_rank", 999) < 999
            ),
        }
        exec(notebook_definition("mark_uncorroborated_search_candidates"), namespace)
        candidates = [{"discovery_rank": 1}, {"discovery_rank": 999}]
        results = [{"candidate_record": candidate} for candidate in candidates]
        namespace["mark_uncorroborated_search_candidates"](candidates, results, {})
        self.assertNotIn("selection_ineligible_reason", results[1])


if __name__ == "__main__":
    unittest.main()
