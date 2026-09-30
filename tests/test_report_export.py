"""Final report and structured audit object remain deterministic."""

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from audit_core.report_export import (
    build_audit_record,
    build_bright_data_usage_section,
    finalize_report_core,
)


class ReportExportTests(unittest.TestCase):
    def test_finalization_adds_measured_sources_once(self):
        observed = [{
            "engine": "ChatGPT",
            "title": "Buyer [guide]",
            "canonical_url": "https://example.com/guide",
            "source_type": "Publisher",
        }]
        collect = lambda _visibility: observed
        first = finalize_report_core(
            "# Report\n", {"engines": {}},
            collect_sources=collect,
            clean_boilerplate=lambda text: text,
        )
        second = finalize_report_core(
            first["report"], {"engines": {}},
            collect_sources=collect,
            clean_boilerplate=lambda text: text,
        )
        self.assertEqual(first["report"], second["report"])
        self.assertEqual(first["sources"], observed)
        self.assertIn("[Buyer guide](https://example.com/guide)", first["report"])

    def test_usage_section_keeps_lower_bound_warning(self):
        section = build_bright_data_usage_section({
            "accepted_operations": 5,
            "confirmed_result_records": 9,
            "estimated_billable_result_records": 12,
            "variable_output_operations_pending": 1,
            "price_per_1000_results_usd": 1.5,
            "estimated_cost_usd": 0.018,
        })
        self.assertIn("At least 12", section)
        self.assertIn("at least $0.0180", section)
        self.assertIn("billing dashboard remains authoritative", section)

    def test_structured_audit_record_keeps_public_fields_and_engine_labels(self):
        target = SimpleNamespace(brand_name="Apple", domain="apple.com")
        competitor = SimpleNamespace(brand_name="Samsung", domain="samsung.com")
        stamp = datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc)
        result = build_audit_record(
            run_id="fixture-run",
            run_timestamp=stamp,
            completed_at=stamp,
            total_duration=12.345,
            settings={
                "company_name": "Apple", "company_url": "https://apple.com",
                "company_domain": "apple.com", "country": "US",
                "audit_focus": "premium smartphone", "serp_zone": "test-zone",
                "debug": False,
            },
            include_reddit_analysis=True,
            target_profile=target,
            competitor_profiles=[competitor],
            keyword_records=[{"keyword": "premium smartphone"}],
            keyword_serp_results=[{"keyword": "premium smartphone", "success": True}],
            competitor_candidates=[competitor],
            selected_competitors=[competitor],
            selection_result={"rejected": [], "used_fallback": False},
            visibility_result={
                "prompt": "Which smartphone?",
                "engines": {"gemini": {"engine_name": "Gemini", "status": "success"}},
                "mentions": {"gemini": []},
            },
            reddit_social_result={"status": "success"},
            bright_data_usage={"estimated_billable_result_records": 12},
            report_result={
                "serp_metrics": {"apple.com": {"appearances": 1}},
                "snapshot_id": None, "evidence": "facts", "prompt": "template",
            },
            final_report="# Report",
            final_sources=[{"engine": "Gemini", "canonical_url": "https://example.com"}],
            warnings=["partial Reddit sample"],
            stage_durations={"search": 3.456},
            generator_name="Deterministic template",
            model_to_dict=lambda item: vars(item) if hasattr(item, "__dict__") else item,
            serialize_engine_result=lambda item: item,
        )
        self.assertEqual(result["configuration"]["country"], "US")
        self.assertTrue(result["configuration"]["include_reddit_analysis"])
        self.assertEqual(result["serp"]["metrics"]["apple.com"]["appearances"], 1)
        self.assertEqual(result["ai_visibility"]["engines"]["gemini"]["engine_name"], "Gemini")
        self.assertEqual(result["final_report"]["generator"], "Deterministic template")
        self.assertEqual(result["durations"], {"search": 3.46, "total_seconds": 12.35})
        self.assertEqual(result["files"], {})


if __name__ == "__main__":
    unittest.main()
