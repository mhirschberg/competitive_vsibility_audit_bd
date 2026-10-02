"""Service and generated notebook must make the same scope/selection decisions."""

import json
import ast
import unittest
from types import SimpleNamespace
from unittest import mock

from audit_core import competitor_scope, primitives
from audit_core import domains
from notebook_builder import NOTEBOOK, SCOPE_END, SCOPE_START


def brand(name, *, role="", confidence=0.0, category="", description="",
          positioning="", products=()):
    return SimpleNamespace(
        brand_name=name,
        official_url=f"https://{name.lower()}.example",
        domain=f"{name.lower()}.example",
        category=category,
        description=description,
        positioning=positioning,
        primary_market_role=role,
        secondary_market_roles=[],
        offering_type="",
        value_chain_position="",
        substitute_definition="",
        classification_confidence=confidence,
        classification_evidence=[],
        target_customers=["buyers"],
        products=list(products),
    )


def notebook_scope_namespace():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    cell = next(
        item for item in notebook["cells"]
        if item.get("metadata", {}).get("id") == "runtime-utilities-merged"
    )
    source = "".join(cell["source"])
    embedded = source.split(SCOPE_START, 1)[1].split(SCOPE_END, 1)[0]
    namespace = {
        "normalize_confidence": primitives.normalize_confidence,
        "get_root_domain": domains.get_root_domain,
    }
    exec(embedded, namespace)
    return namespace


def result(name, *, status="success", direct=True, score=0.8, rank=1,
           prominence=1.0, observed=1.0, ineligible=None):
    return {
        "status": status,
        "validation": {"is_direct_competitor": direct},
        "selection_ineligible_reason": ineligible,
        "selection_score": score,
        "candidate_record": {
            "brand_name": name,
            "discovery_rank": rank,
            "market_prominence": prominence,
            "observed_score": observed,
        },
    }


class CompetitorScopeParityTests(unittest.TestCase):
    def test_shared_domain_rules_are_not_shadowed_in_generated_notebook(self):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        cell = next(
            item for item in notebook["cells"]
            if item.get("metadata", {}).get("id") == "runtime-utilities-merged"
        )
        definitions = [
            node.name for node in ast.parse("".join(cell["source"])).body
            if isinstance(node, ast.FunctionDef)
        ]
        for name in ("locked_scope_brand_family", "locked_scope_local_domain_bonus"):
            self.assertEqual(definitions.count(name), 1)

    def test_domain_family_and_locality_helpers_match_between_runners(self):
        notebook = notebook_scope_namespace()
        def get_root_domain(value):
            host = str(value or "").lower().removeprefix("www.")
            labels = host.split(".")
            suffix_size = 3 if host.endswith((
                ".co.uk", ".com.au", ".com.br", ".com.mx",
            )) else 2
            return ".".join(labels[-suffix_size:])
        with mock.patch.object(
            competitor_scope, "get_root_domain", side_effect=get_root_domain,
        ), mock.patch.object(
            competitor_scope.tldextract, "extract",
            side_effect=lambda value: SimpleNamespace(
                domain=value.split(".")[0],
            ),
        ):
            notebook["get_root_domain"] = get_root_domain
            for domain, expected in (
                ("www.example.com", "example"),
                ("shop.example.co.uk", "example"),
            ):
                self.assertEqual(
                    competitor_scope.locked_scope_brand_family(domain), expected,
                )
                self.assertEqual(
                    notebook["locked_scope_brand_family"](domain), expected,
                )

        with mock.patch.object(
            competitor_scope, "get_root_domain", side_effect=get_root_domain,
        ):
            notebook["get_root_domain"] = get_root_domain
            for domain, country, expected in (
                ("brand.de", "DE", 20),
                ("brand.com", "US", 20),
                ("brand.com.au", "AU", 20),
                ("brand.com", "DE", 0),
                ("brand.de", "ZZ", 0),
            ):
                self.assertEqual(
                    competitor_scope.locked_scope_local_domain_bonus(
                        domain, country,
                    ), expected,
                )
                self.assertEqual(
                    notebook["locked_scope_local_domain_bonus"](
                        domain, country,
                    ), expected,
                )

    def test_market_role_fixtures_match_notebook(self):
        notebook = notebook_scope_namespace()
        fixtures = (
            (
                brand(
                    "KEBA", category="Industrial automation",
                    description="Machine tool automation systems",
                    products=["CNC controls", "HMI panels"],
                ),
                {"country": "DE", "audit_focus": "machine tools automation"},
                "manufacturer", "heuristic_fallback",
            ),
            (
                brand("Apple", role="manufacturer", confidence=0.93,
                      category="Premium smartphones", products=["iPhone"]),
                {"country": "US", "audit_focus": "premium smartphone"},
                "manufacturer", "stage_1_ai",
            ),
            (
                brand("Samsung", role="product manufacturer", confidence=0.9,
                      category="Premium smartphones", products=["Galaxy S"]),
                {"country": "US", "audit_focus": "premium smartphone"},
                "manufacturer", "stage_1_ai",
            ),
            (
                brand("Google", role="other", confidence=0.95,
                      category="Premium consumer electronics / smartphones",
                      products=["Pixel"]),
                {"country": "US", "audit_focus": "premium smartphone"},
                "manufacturer", "heuristic_fallback",
            ),
        )
        for company, settings, role, source in fixtures:
            with self.subTest(company=company.brand_name):
                service = competitor_scope.build_locked_target_scope(company, settings)
                embedded = notebook["build_locked_target_scope"](company, settings)
                self.assertEqual(service, embedded)
                self.assertEqual(service["market_role"], role)
                self.assertEqual(service["classification_source"], source)

    def test_rank_filters_failures_and_preserves_stable_tiebreakers(self):
        notebook = notebook_scope_namespace()
        validations = [
            result("Sony", score=0.9, rank=3),
            result("Apple", score=0.9, rank=1),
            result("Vertu", score=0.99, rank=1, ineligible="different market"),
            result("Motorola", status="failed", score=0.95),
            result("Samsung", direct=False, score=0.97),
            result("Google", score=0.85, rank=2),
        ]
        original_order = [item["candidate_record"]["brand_name"] for item in validations]
        expected = ["Apple", "Sony", "Google"]
        for ranker in (
            competitor_scope.rank_valid_competitors,
            notebook["rank_valid_competitors"],
        ):
            ranked = ranker(validations)
            self.assertEqual(
                [item["candidate_record"]["brand_name"] for item in ranked],
                expected,
            )
        self.assertEqual(
            [item["candidate_record"]["brand_name"] for item in validations],
            original_order,
        )

    def test_scope_keeps_the_original_audit_date(self):
        company = brand("KEBA", role="manufacturer", confidence=0.9)
        scope = competitor_scope.build_locked_target_scope(
            company,
            {"country": "DE", "audit_as_of_date": "2026-09-15"},
        )
        self.assertEqual(scope["as_of_date"], "2026-09-15")

    def test_resume_preserves_saved_scope_and_backfills_old_date(self):
        company = brand("KEBA", role="manufacturer", confidence=0.9)
        saved = {"market_role": "manufacturer", "category": "Machine tools"}
        checkpoint = {"locked_target_scope": saved}
        restored = competitor_scope.restore_locked_target_scope(
            checkpoint, company,
            {"country": "DE", "audit_as_of_date": "2026-09-15"},
        )
        self.assertEqual(restored["as_of_date"], "2026-09-15")
        self.assertEqual(restored["category"], "Machine tools")
        self.assertNotIn("as_of_date", saved)
        self.assertEqual(
            competitor_scope.restore_locked_target_scope(
                {"locked_target_scope": {**saved, "as_of_date": "2026-09-14"}},
                company,
                {"country": "DE", "audit_as_of_date": "2026-09-15"},
            )["as_of_date"],
            "2026-09-14",
        )


if __name__ == "__main__":
    unittest.main()
