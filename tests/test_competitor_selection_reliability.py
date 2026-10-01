"""Regression checks for incomplete research and search-only candidates."""

import ast
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from audit_core import competitor_decisions, competitor_pipeline


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
            "core_canonical_candidate_validation_data": (
                competitor_decisions.core_canonical_candidate_validation_data
            ),
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
            "core_build_locked_scope_validation_prompt": (
                competitor_decisions.core_build_locked_scope_validation_prompt
            ),
            "core_build_locked_scope_validation_retry_prompt": (
                competitor_decisions.core_build_locked_scope_validation_retry_prompt
            ),
            "_competitor_decision_ports": lambda: competitor_decisions.CompetitorDecisionPorts(
                lambda _country: {"name": "United States", "code": "US"},
                lambda value: value,
                lambda value: value,
                lambda value: value,
                lambda _domain, _country: 0,
            ),
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
        pipeline = competitor_pipeline.CompetitorPipeline(
            query_json=lambda _prompt: None, decision_ports=None,
            local_domain_bonus=lambda *_args: 0, validation_workers=1,
        )
        pipeline.supports_retry = (
            lambda candidate, _scope, max_rank=5:
            candidate.get("discovery_rank", 999) <= max_rank
            and candidate.get("discovery_confidence", 0) >= 0.8
        )
        candidates = [
            {"brand_name": "Samsung", "discovery_rank": 1, "discovery_confidence": 0.99},
            {"brand_name": "Google", "discovery_rank": 2, "discovery_confidence": 0.97},
            {"brand_name": "Vertu", "discovery_rank": 999, "discovery_confidence": 0.0},
        ]
        results = [
            {"candidate_record": candidate, "validation": {"is_direct_competitor": True}}
            for candidate in candidates
        ]
        pipeline.mark_uncorroborated(candidates, results, {})
        self.assertNotIn("selection_ineligible_reason", results[0])
        self.assertNotIn("selection_ineligible_reason", results[1])
        self.assertIn("Only observed in search", results[2]["selection_ineligible_reason"])

    def test_search_candidate_remains_eligible_if_discovery_is_sparse(self):
        pipeline = competitor_pipeline.CompetitorPipeline(
            query_json=lambda _prompt: None, decision_ports=None,
            local_domain_bonus=lambda *_args: 0, validation_workers=1,
        )
        pipeline.supports_retry = (
            lambda candidate, _scope, max_rank=5:
            candidate.get("discovery_rank", 999) < 999
        )
        candidates = [{"discovery_rank": 1}, {"discovery_rank": 999}]
        results = [{"candidate_record": candidate} for candidate in candidates]
        pipeline.mark_uncorroborated(candidates, results, {})
        self.assertNotIn("selection_ineligible_reason", results[1])

    def test_shared_provider_adapter_uses_locked_scope_and_persists_results(self):
        scope = {
            "brand_name": "Apple", "domain": "apple.com",
            "official_url": "https://apple.com/", "country": "US",
            "category": "premium smartphones", "market_role": "manufacturer",
            "business_model": "hardware manufacturer",
            "primary_customers": ["smartphone buyers"],
            "core_offerings": ["premium smartphones"],
            "substitute_definition": "premium smartphones",
            "audit_focus": "premium smartphone",
        }
        discovered = [
            {
                "rank_by_directness": rank, "brand_name": name,
                "domain": domain, "official_url": f"https://{domain}/",
                "candidate_role": "manufacturer", "confidence": 0.95,
                "market_prominence": 0.9,
            }
            for rank, name, domain in (
                (1, "Samsung", "samsung.com"),
                (2, "Google", "google.com"),
            )
        ]

        class FakeClient:
            def __init__(self):
                self.prompts = []

            def google_ai_mode(self, prompt, timeout_seconds):
                self.prompts.append(prompt)
                return {"answer_text": "unused"}

            @staticmethod
            def answer_text(record):
                prompt = client.prompts[-1]
                if prompt.startswith("Identify the strongest active"):
                    answer = {"competitors": discovered}
                else:
                    candidate = next(item for item in discovered if item["brand_name"] in prompt)
                    answer = {
                        "candidate_name": candidate["brand_name"],
                        "candidate_domain": candidate["domain"],
                        "official_url": candidate["official_url"],
                        "candidate_role": "manufacturer",
                        "candidate_business_model": "hardware manufacturer",
                        "active_in_target_country": True,
                        "same_category": True,
                        "same_market_role": True,
                        "same_business_model": True,
                        "same_primary_customers": True,
                        "same_core_transaction": True,
                        "offering_is_substitute": True,
                        "is_direct_competitor": True,
                        "market_prominence": 0.9,
                        "reason": "Comparable premium smartphone maker.",
                        "evidence": ["Current smartphone product range."],
                        "confidence": 0.95,
                    }
                return json.dumps(answer)

        client = FakeClient()
        decision_ports = competitor_decisions.CompetitorDecisionPorts(
            lambda code: {"code": code, "name": "United States"},
            lambda value: value.split("//")[-1].split("/")[0],
            lambda value: value,
            lambda domain: domain,
            lambda _domain, _country: 0,
        )
        persisted = []
        with tempfile.TemporaryDirectory() as output:
            result = competitor_pipeline.select_competitors_with_provider(
                SimpleNamespace(brand_name="Apple"), [], ["premium smartphone"],
                scope=scope, client=client, parse_ai_json=json.loads,
                decision_ports=decision_ports,
                local_domain_bonus=lambda *_args: 0,
                validation_workers=2, validation_limit=12,
                only_reuse=False, cached_snapshot_ids=lambda _prompt: [],
                brand_family=lambda domain: domain,
                selected_factory=lambda **values: SimpleNamespace(**values),
                error_type=RuntimeError, output_dir=output,
                write_json=lambda path, payload: persisted.append((path, payload)),
                clean_record=lambda record: record,
            )

        self.assertEqual(result["locked_target_scope"], scope)
        self.assertEqual(
            [item.brand_name for item in result["selected"]],
            ["Samsung", "Google"],
        )
        self.assertEqual(len(client.prompts), 3)
        self.assertEqual(len(persisted), 1)
        self.assertTrue(str(persisted[0][0]).endswith("03_candidate_validation_records.json"))


if __name__ == "__main__":
    unittest.main()
