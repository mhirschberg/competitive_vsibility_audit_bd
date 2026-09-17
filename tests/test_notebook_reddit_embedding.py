import json
import re
import unittest
from pathlib import Path
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
            2,
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
