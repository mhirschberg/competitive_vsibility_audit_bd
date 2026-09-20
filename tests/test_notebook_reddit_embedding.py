import json
import re
import unittest
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "competitive_visibility_audit_bd.ipynb"
MODULE = ROOT / "reddit_social.py"
START = "# REDDIT-SOCIAL-PATCH: start"
END = "# REDDIT-SOCIAL-PATCH: end"


class NotebookEmbeddingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))

    def test_embedded_module_matches_source_file(self):
        runtime = "".join(self.notebook["cells"][6]["source"])
        self.assertEqual(runtime.count(START), 1)
        self.assertEqual(runtime.count(END), 1)
        embedded = runtime.split(START, 1)[1].split(END, 1)[0].strip("\n")
        source = MODULE.read_text(encoding="utf-8").strip("\n")
        self.assertEqual(embedded, source)

    def test_orchestration_hooks_are_present_once(self):
        orchestration = "".join(self.notebook["cells"][5]["source"])
        for hook in (
            "start_reddit_discovery_prefetch(",
            "run_reddit_social_stage(",
            "discovery_prefetch_task=reddit_prefetch_task",
            'output_directory / "05_reddit_social.json"',
            'output_directory / "05_reddit_snapshot_manifest.json"',
            "insert_reddit_report_section(",
            '"reddit_social": reddit_social_result',
        ):
            self.assertEqual(orchestration.count(hook), 1, hook)
        self.assertEqual(
            orchestration.count('audit_focus=settings.get("audit_focus", "")'),
            3,
        )
        self.assertIn(
            'settings.get(\n            "include_reddit_analysis",\n            False,',
            orchestration,
        )
        self.assertIn("if include_reddit_analysis:", orchestration)
        self.assertIn('"status": "disabled"', orchestration)
        self.assertIn("total_stages = 7 if include_reddit_analysis else 6", orchestration)
        self.assertIn('"Reddit conversation analysis"', orchestration)
        self.assertNotIn("await asyncio.gather(\n            visibility_task", orchestration)

    def test_reddit_analysis_is_an_opt_in_notebook_setting(self):
        config_cell = next(
            cell
            for cell in self.notebook["cells"]
            if cell.get("metadata", {}).get("id") == "UsMNZ4-2jKg6"
        )
        config = "".join(config_cell["source"])

        self.assertIn("INCLUDE_REDDIT_ANALYSIS = False", config)
        self.assertIn(
            '"include_reddit_analysis": (\n        INCLUDE_REDDIT_ANALYSIS',
            config,
        )
        self.assertIn("may add up to 10 minutes", config)

    def test_modified_code_cells_compile(self):
        for index in range(2, 7):
            source = "".join(self.notebook["cells"][index]["source"])
            compile(source, f"notebook-cell-{index}", "exec")

        run_cell = "".join(self.notebook["cells"][7]["source"])
        web_run_cell = re.sub(
            r"AUDIT_RESULT\s*=\s*await\s+run_competitive_visibility_audit\(\s*AUDIT_SETTINGS\s*\)",
            "AUDIT_RESULT = asyncio.run(run_competitive_visibility_audit(AUDIT_SETTINGS))",
            run_cell,
            flags=re.MULTILINE,
        )
        compile(web_run_cell, "notebook-web-run-cell", "exec")

    def test_bright_data_usage_tracks_operations_results_and_cost(self):
        runtime = "".join(self.notebook["cells"][3]["source"])
        start = runtime.index("class BrightDataClient")
        end = runtime.index("# SERP competitor helpers")
        namespace = {"Lock": Lock}
        exec(runtime[start:end], namespace)
        client = namespace["BrightDataClient"](
            token="test-token",
            serp_zone="test-zone",
        )

        serp_id = client.start_usage_operation("Google SERP")
        client.update_usage_operation(
            serp_id,
            status="success",
            result_count=1,
        )
        dataset_id = client.start_usage_operation(
            "Reddit discovery",
            dataset_id="reddit-dataset",
        )
        client.update_usage_operation(
            dataset_id,
            snapshot_id="snapshot-1",
            status="triggered",
        )
        client.record_snapshot_results("snapshot-1", 15)
        failed_id = client.start_usage_operation("Gemini")
        client.update_usage_operation(failed_id, status="failed")

        summary = client.usage_summary(price_per_1000=1.5)

        self.assertEqual(summary["data_operations_started"], 3)
        self.assertEqual(summary["confirmed_result_records"], 16)
        self.assertEqual(summary["failed_operations"], 1)
        self.assertEqual(summary["unconfirmed_operations"], 0)
        self.assertAlmostEqual(summary["estimated_cost_usd"], 0.024)
        self.assertFalse(summary["estimate_is_lower_bound"])

        client.start_usage_operation("Late raced snapshot")
        self.assertTrue(
            client.usage_summary()["estimate_is_lower_bound"]
        )

    def test_bright_data_usage_section_explains_result_based_pricing(self):
        runtime = "".join(self.notebook["cells"][5]["source"])
        start = runtime.index("BRIGHT_DATA_PRICE_PER_1000_RESULTS_USD")
        end = runtime.index("def clean_record_for_storage")
        namespace = {}
        exec(runtime[start:end], namespace)
        section = namespace["build_bright_data_usage_section"](
            {
                "data_operations_started": 12,
                "confirmed_result_records": 40,
                "unconfirmed_operations": 2,
                "failed_operations": 1,
                "price_per_1000_results_usd": 1.5,
                "estimated_cost_usd": 0.06,
            }
        )

        self.assertIn("Bright Data Usage and Estimated Cost", section)
        self.assertIn("| Data operations started | 12 |", section)
        self.assertIn("| Confirmed result records returned | At least 40 |", section)
        self.assertIn("| Estimated Bright Data cost | at least $0.0600 |", section)
        self.assertIn("returned result records, not the number of API calls", section)
        self.assertIn("lower bounds", section)

    def test_locked_scope_recognizes_generic_physical_product_signals(self):
        runtime = "".join(self.notebook["cells"][6]["source"])
        start = runtime.index("def locked_scope_normalize_text")
        end = runtime.index("def infer_locked_business_model")
        namespace = {"re": re}
        exec(runtime[start:end], namespace)
        brand = SimpleNamespace(
            description="Premium hair styling solutions",
            positioning="Home and professional styling",
            products=["Multi-styler barrels", "Smoothing brushes"],
        )

        role = namespace["infer_locked_target_role"](
            brand,
            "Health and beauty / Premium consumer electronics / Hair care appliances",
        )

        self.assertEqual(role, "manufacturer")

    def test_profile_prompt_strictly_scopes_target_and_competitors(self):
        runtime = "".join(self.notebook["cells"][4]["source"])
        start = runtime.index("def build_profile_prompt")
        end = runtime.index("def clean_profile_label")
        namespace = {}
        exec(runtime[start:end], namespace)
        target_brand = SimpleNamespace(brand_name="KEBA")
        target_job = {
            "role": "target",
            "brand_name": "KEBA",
            "official_url": "https://keba.com/",
            "domain": "keba.com",
            "reason": "",
        }
        competitor_job = {
            "role": "competitor",
            "brand_name": "Beckhoff",
            "official_url": "https://beckhoff.com/",
            "domain": "beckhoff.com",
            "reason": "Comparable industrial automation offering",
        }

        for job in (target_job, competitor_job):
            prompt = namespace["build_profile_prompt"](
                job,
                target_brand,
                "machine tools automation",
            )
            self.assertIn("AUDIT SCOPE — STRICT REQUIREMENT", prompt)
            self.assertIn("machine tools automation", prompt)
            self.assertIn("Exclude unrelated business lines", prompt)
            self.assertIn("leave it empty or use unknown", prompt)

        unscoped = namespace["build_profile_prompt"](
            target_job,
            target_brand,
        )
        self.assertNotIn("AUDIT SCOPE — STRICT REQUIREMENT", unscoped)
        self.assertIn("Profile the primary offering", unscoped)

    def test_locked_scope_recognizes_consumer_product_brand(self):
        runtime = "".join(self.notebook["cells"][6]["source"])
        start = runtime.index("def locked_scope_normalize_text")
        end = runtime.index("def infer_locked_business_model")
        namespace = {"re": re}
        exec(runtime[start:end], namespace)
        brand = SimpleNamespace(
            description=(
                "Mass-market dermatological skincare products formulated "
                "for dry and sensitive skin"
            ),
            positioning="Dermatologist-developed skincare",
            products=["Moisturizing Cream"],
        )

        role = namespace["infer_locked_target_role"](
            brand,
            "Health/beauty product / mass-market dermatological skincare",
        )

        self.assertEqual(role, "manufacturer")

    def test_locked_scope_recognizes_industrial_automation_manufacturer(self):
        runtime = "".join(self.notebook["cells"][6]["source"])
        start = runtime.index("def locked_scope_normalize_text")
        end = runtime.index("def infer_locked_business_model")
        namespace = {"re": re}
        exec(runtime[start:end], namespace)
        brand = SimpleNamespace(
            description="Integrated automation solutions for machine builders",
            positioning="Automation specialist for machine tools",
            products=["KeControl C5", "KeDrive D3", "KeTop T150"],
        )

        role = namespace["infer_locked_target_role"](
            brand,
            "Automation solutions",
            "machine tools automation",
        )

        self.assertEqual(role, "manufacturer")

    def test_locked_scope_leaves_ambiguous_role_unclassified(self):
        runtime = "".join(self.notebook["cells"][6]["source"])
        start = runtime.index("def locked_scope_normalize_text")
        end = runtime.index("def infer_locked_business_model")
        namespace = {"re": re}
        exec(runtime[start:end], namespace)
        brand = SimpleNamespace(
            description="Integrated transformation solutions",
            positioning="Enterprise operations specialist",
            products=["Custom transformation program"],
        )

        role = namespace["infer_locked_target_role"](
            brand,
            "Enterprise transformation",
        )

        self.assertEqual(role, "other")

    def test_ambiguous_target_role_uses_validated_role_match(self):
        runtime = "".join(self.notebook["cells"][6]["source"])
        start = runtime.index("def normalize_locked_scope_validation")
        end = runtime.index("def validate_locked_scope_candidate")
        namespace = {
            "LOCKED_SCOPE_INACTIVE_TERMS": set(),
            "LOCKED_SCOPE_MIN_CONFIDENCE": 0.6,
            "LOCKED_SCOPE_REJECTED_ROLES": {
                "publisher_or_directory",
                "unrelated",
            },
            "locked_scope_role": lambda value: value,
            "locked_scope_normalize_text": lambda value: str(value).lower(),
            "normalize_boolean": bool,
            "normalize_confidence": lambda value: float(value or 0),
            "ensure_string_list": lambda value: list(value or []),
            "normalize_public_url": lambda value: value,
            "get_root_domain": lambda value: value,
        }
        exec(runtime[start:end], namespace)
        candidate = {
            "official_url": "https://manufacturer.example/",
            "representative_domain": "manufacturer.example",
            "brand_name": "Manufacturer",
        }
        validation = namespace["normalize_locked_scope_validation"](
            {
                "candidate_role": "manufacturer",
                "candidate_name": "Manufacturer",
                "candidate_domain": "manufacturer.example",
                "official_url": "https://manufacturer.example/",
                "active_in_target_country": True,
                "same_category": True,
                "same_market_role": True,
                "same_business_model": True,
                "same_primary_customers": True,
                "same_core_transaction": True,
                "offering_is_substitute": True,
                "is_direct_competitor": True,
                "confidence": 0.9,
            },
            candidate,
            {"market_role": "other"},
        )

        self.assertTrue(validation["role_matches_scope"])
        self.assertTrue(validation["is_direct_competitor"])

        rejected = namespace["normalize_locked_scope_validation"](
            {
                "candidate_role": "publisher_or_directory",
                "candidate_name": "Directory",
                "candidate_domain": "directory.example",
                "official_url": "https://directory.example/",
                "active_in_target_country": True,
                "same_category": True,
                "same_market_role": True,
                "same_business_model": True,
                "same_primary_customers": True,
                "same_core_transaction": True,
                "offering_is_substitute": True,
                "is_direct_competitor": True,
                "confidence": 0.9,
            },
            candidate,
            {"market_role": "other"},
        )

        self.assertFalse(rejected["role_matches_scope"])
        self.assertFalse(rejected["is_direct_competitor"])

    def test_locked_scope_keeps_service_provider_without_product_signal(self):
        runtime = "".join(self.notebook["cells"][6]["source"])
        start = runtime.index("def locked_scope_normalize_text")
        end = runtime.index("def infer_locked_business_model")
        namespace = {"re": re}
        exec(runtime[start:end], namespace)
        brand = SimpleNamespace(
            description="Independent strategy consultancy for enterprise teams",
            positioning="Professional advisory services",
            products=["Transformation advisory"],
        )

        role = namespace["infer_locked_target_role"](
            brand,
            "Management consulting",
        )

        self.assertEqual(role, "service_provider")

    def test_profile_label_removes_google_shopping_markup(self):
        runtime = "".join(self.notebook["cells"][4]["source"])
        start = runtime.index("def clean_profile_label")
        end = runtime.index("def normalize_brand_profile")
        namespace = {"re": re}
        exec(runtime[start:end], namespace)

        clean = namespace["clean_profile_label"]
        self.assertEqual(
            clean(
                "[CeraVe Moisturizing Cream](/search?ibp=oshop&prds=pvt:hg"
            ),
            "CeraVe Moisturizing Cream",
        )
        self.assertEqual(
            clean(
                "[Aveeno Daily Moisturizing Lotion](/search?id=123) "
                "Go to product viewer dialog for this item."
            ),
            "Aveeno Daily Moisturizing Lotion",
        )

    def test_zero_search_appearances_do_not_recommend_rank_optimization(self):
        runtime = "".join(self.notebook["cells"][6]["source"])
        start = runtime.index("def deterministic_number")
        end = runtime.index("def deterministic_ai_recommendation")
        namespace = {}
        exec(runtime[start:end], namespace)
        target = SimpleNamespace(brand_name="Notion", domain="notion.com")

        _, second = namespace["deterministic_search_recommendations"](
            target,
            [],
            {
                "notion.com": {
                    "appearances": 0,
                    "total_keywords": 8,
                    "best_rank": None,
                    "average_rank": None,
                }
            },
            8,
            True,
        )

        self.assertIn("no observed ranking", second["evidence"])
        self.assertNotIn("lower observed positions", second["action"])
        self.assertNotIn("—", second["evidence"])

    def test_recommendation_number_is_not_a_restartable_markdown_list(self):
        runtime = "".join(self.notebook["cells"][6]["source"])
        start = runtime.index("def deterministic_recommendation")
        end = runtime.index("def deterministic_search_recommendations")
        namespace = {}
        exec(runtime[start:end], namespace)

        rendered = namespace["deterministic_recommendation"](
            2,
            "Medium",
            "Do the work.",
            "The evidence.",
            "The impact.",
        )

        self.assertTrue(rendered.startswith("**Recommendation 2 - Priority:**"))
        self.assertFalse(rendered.startswith("2. "))

    def test_shared_corporate_domain_requires_product_brand_evidence(self):
        runtime = "".join(self.notebook["cells"][5]["source"])
        start = runtime.index("def serp_distinctive_brand_tokens")
        end = runtime.index("def format_serp_metric")

        def root_domain(value):
            parsed = urlparse(value if "://" in value else f"https://{value}")
            hostname = (parsed.hostname or "").removeprefix("www.")
            return ".".join(hostname.split(".")[-2:])

        namespace = {"re": re, "get_root_domain": root_domain}
        exec(runtime[start:end], namespace)
        keyword_results = [
            {
                "success": True,
                "keyword": "project management software",
                "results": [
                    {
                        "rank": 3,
                        "domain": "microsoft.com",
                        "url": "https://microsoft.com/microsoft-365/planner",
                        "title": "Microsoft Planner",
                        "description": "Project management templates",
                    }
                ],
            },
            {
                "success": True,
                "keyword": "collaborative workspace components",
                "results": [
                    {
                        "rank": 2,
                        "domain": "microsoft.com",
                        "url": "https://microsoft.com/microsoft-loop",
                        "title": "Microsoft Loop",
                        "description": "Collaborative Loop workspaces",
                    }
                ],
            },
        ]

        metric = namespace["calculate_serp_metrics"](
            "microsoft.com",
            keyword_results,
            brand_name="Microsoft Loop",
        )

        self.assertEqual(metric["appearances"], 1)
        self.assertEqual(metric["best_rank"], 2)
        self.assertEqual(
            metric["details"][0]["keyword"],
            "collaborative workspace components",
        )


if __name__ == "__main__":
    unittest.main()
