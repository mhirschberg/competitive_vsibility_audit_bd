"""Offline end-to-end coverage for the importable audit scheduler."""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from audit_core.audit_finalize_stage import (
    AuditFinalizePorts, run_audit_finalize_stage_core,
)
from audit_core.audit_pipeline import (
    AuditPipelinePorts, AuditRunContext, run_audit_pipeline,
)
from audit_core.company_stage import CompanyStagePorts, run_company_stage_core
from audit_core.competitor_selection_stage import (
    CompetitorSelectionStagePorts, run_competitor_selection_stage_core,
)
from audit_core.profile_stage import ProfileStagePorts, run_profile_stage_core
from audit_core.report_render_stage import ReportRenderPorts, run_report_render_stage_core
from audit_core.search_stage import SearchStagePorts, run_search_stage_core
from audit_core.social_completion_stage import (
    SocialCompletionPorts, run_social_completion_stage_core,
)
from audit_core.visibility_checkpoint_stage import (
    VisibilityCheckpointPorts, run_visibility_checkpoint_stage_core,
)
from notebook_builder import build_notebook


class Model:
    def __init__(self, **values):
        self.__dict__.update(values)


def as_dict(item):
    return vars(item).copy()


class AuditPipelineTests(unittest.TestCase):
    def make_ports(self, events):
        scope = {"value": {"market": "smartphones"}}

        def write_json(path, data):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding="utf-8")

        def analyze(settings):
            events.append("analyze")
            return {
                "intake": Model(
                    brand=Model(
                        brand_name="Apple", domain="apple.com",
                        official_url="https://apple.com/",
                    ),
                    buyer_intent_keywords=[Model(keyword="premium smartphone")],
                ),
                "record": {"company": "fixture"},
            }

        async def search(**kwargs):
            events.append("search")
            return {
                "keyword_results": [{
                    "keyword": "premium smartphone", "success": True,
                    "results": [{"domain": "samsung.com"}],
                }],
                "candidates": [Model(brand_name="Samsung", domain="samsung.com")],
                "successful": 1, "failed": 0, "ai_mode_failed": 0,
                "search_engine": "google", "search_status": "available",
                "ai_mode_discovery": None,
            }

        def select(target, candidates, keywords):
            events.append("select")
            return {
                "selected": [Model(
                    brand_name="Samsung", domain="samsung.com",
                    official_url="https://samsung.com/", reason="Phones",
                )],
                "record": {"selection": "fixture"},
                "rejected": [], "validation_results": [],
                "used_fallback": False,
            }

        async def prefetch(**kwargs):
            events.append("prefetch")
            return {"snapshot_ids": ["snap-1"]}

        async def profiles(**kwargs):
            events.append("profiles")
            target = Model(
                brand_name="Apple", domain="apple.com",
                official_url="https://apple.com/", direct_competitor=False,
            )
            competitor = Model(
                brand_name="Samsung", domain="samsung.com",
                official_url="https://samsung.com/", direct_competitor=True,
            )
            return {
                "target_profile": target,
                "competitor_profiles": [competitor],
                "all_profiles": [target, competitor],
                "task_results": [{"status": "success"}],
                "successful": 2, "fallbacks": 0,
            }

        async def visibility(**kwargs):
            events.append("visibility")
            return {
                "prompt": "Which premium smartphone?",
                "engines": {
                    "chatgpt": {
                        "status": "success", "engine_name": "ChatGPT",
                        "duration_seconds": 1.0, "answer": "Apple and Samsung",
                    },
                },
                "mentions": {"chatgpt": [{"brand_name": "Apple"}]},
            }

        async def social(**kwargs):
            events.append("social")
            await kwargs["discovery_prefetch_task"]
            return {
                "status": "success", "mode": "competitive",
                "comparison": [{
                    "brand": "Apple", "relevant_posts": 1,
                    "classified_posts": 1, "sample_size": 1,
                }],
                "unique_thread_count": 1,
                "snapshot_manifest": [{"snapshot_id": "snap-1"}],
                "duration_seconds": 2.0,
            }

        def report(*args):
            events.append("report")
            return {
                "report": "# Competitive Visibility Audit\n\nFixture\n",
                "record": {"report": "fixture"},
            }

        def create_pdf(**kwargs):
            kwargs["output_path"].write_bytes(b"%PDF-fixture")

        def create_zip(directory, name):
            path = directory / name
            path.write_bytes(b"zip-fixture")
            return path

        def build_record(**kwargs):
            events.append("finalize")
            return {
                "run_id": kwargs["run_id"],
                "selected": [item.brand_name for item in kwargs["selected_competitors"]],
                "selection_record": kwargs["selection_result"]["record"],
                "search_results": kwargs["keyword_serp_results"],
                "visibility": kwargs["visibility_result"]["engines"],
                "social_status": kwargs["reddit_social_result"]["status"],
                "usage": kwargs["bright_data_usage"],
                "warnings": kwargs["warnings"],
                "stage_names": sorted(kwargs["stage_durations"]),
            }

        def format_duration(seconds):
            return f"{seconds:.1f}s"

        return AuditPipelinePorts(
            company_stage=CompanyStagePorts(
                analyze=analyze, intake_factory=Model,
                brand_factory=Model, keyword_factory=Model,
                get_locked_scope=lambda: scope["value"],
                set_locked_scope=lambda value: scope.__setitem__("value", value),
                restore_locked_scope=lambda checkpoint, target, settings: dict(
                    checkpoint.get("locked_target_scope") or {}
                ),
                model_to_dict=as_dict, write_json=write_json,
                clean_record=dict, stage_success=lambda message: None,
            ),
            search_stage=SearchStagePorts(
                run_search=search, candidate_factory=Model,
                model_to_dict=as_dict, write_json=write_json,
                stage_success=lambda message: None,
                stage_warning=lambda message: events.append("search warning"),
                format_duration=format_duration,
            ),
            competitor_stage=CompetitorSelectionStagePorts(
                select_competitors=select,
                configure_race_cache=lambda path, only_reuse: None,
                write_json=write_json, model_to_dict=as_dict,
                clean_record=dict,
                stage_warning=lambda message: None,
                print_selected=lambda competitor: None,
                social_notice=lambda: None,
                start_reddit_prefetch=prefetch,
            ),
            profile_stage=ProfileStagePorts(
                run_profiles=profiles, model_to_dict=as_dict,
                serialize_task=dict, write_json=write_json,
                stage_success=lambda message: None,
                stage_warning=lambda message: None,
            ),
            visibility_stage=VisibilityCheckpointPorts(
                run_visibility=visibility, run_reddit_social=social,
                serialize_engine_result=dict, write_json=write_json,
                stage_success=lambda message: None,
                stage_warning=lambda message: None,
                format_duration=format_duration,
            ),
            social_stage=SocialCompletionPorts(
                print_stage=lambda *args: events.append(("stage", *args)),
                stage_success=lambda message: None,
                stage_warning=lambda message: None,
                format_duration=format_duration,
                summarize_warning=lambda result: "",
                write_json=write_json,
            ),
            report_stage=ReportRenderPorts(
                generate_report=report,
                finalize_report=lambda **kwargs: {
                    "report": kwargs["report"], "sources": [],
                },
                insert_reddit_section=lambda text, result: text,
                refresh_usage=lambda: None,
                usage_summary=lambda **kwargs: {
                    "estimated_cost_usd": 0.03,
                    "price_per_1000": kwargs["price_per_1000"],
                },
                build_usage_section=lambda usage: "\nUsage: $0.03\n",
                write_json=write_json,
                write_text=lambda path, text: path.write_text(text, encoding="utf-8"),
                report_filename=lambda prefix, ext: f"{prefix}.{ext}",
                create_pdf=create_pdf, clean_record=dict,
                stage_success=lambda message: None,
                stage_warning=lambda message: None,
                format_duration=format_duration,
            ),
            finalize_stage_factory=lambda: AuditFinalizePorts(
                build_record=build_record,
                model_to_dict=as_dict,
                serialize_engine_result=dict,
                generator_name="ChatGPT",
                report_filename=lambda prefix, ext: f"{prefix}.{ext}",
                write_json=write_json,
                create_zip=create_zip,
                stage_success=lambda message: None,
                completion_notice=lambda message: None,
                format_duration=format_duration,
            ),
            stage_banner=lambda *args: events.append(("stage", *args)),
        )

    def run_fixture(self, root, *, reddit):
        events = []
        output = Path(root) / "competitive-visibility-apple"
        context = AuditRunContext(
            run_id="apple-fixture", run_timestamp=datetime(
                2026, 9, 30, tzinfo=timezone.utc,
            ),
            export_prefix="20260930-apple-us", output_directory=output,
            raw_directory=output / "raw",
            site_resolution={
                "submitted_domain": "apple.com",
                "canonical_domain": "apple.com",
            },
        )
        settings = {
            "company_name": "Apple", "company_domain": "apple.com",
            "company_url": "https://apple.com/", "country": "US",
            "audit_focus": "premium smartphone",
            "include_reddit_analysis": reddit,
            "include_google_ai_mode": False,
            "include_chatgpt_visibility": True,
            "include_gemini_visibility": False,
            "include_copilot_visibility": False,
        }
        result = asyncio.run(run_audit_pipeline(
            settings, context, ports=self.make_ports(events),
        ))
        return context, result, events

    def test_complete_non_social_run_writes_all_artifacts(self):
        with tempfile.TemporaryDirectory() as root:
            context, result, events = self.run_fixture(root, reddit=False)
            self.assertEqual(result["selected"], ["Samsung"])
            self.assertEqual(result["selection_record"], {"selection": "fixture"})
            self.assertEqual(result["social_status"], "disabled")
            self.assertEqual(result["usage"]["estimated_cost_usd"], 0.03)
            self.assertEqual(result["warnings"], [])
            self.assertEqual(len(result["stage_names"]), 7)
            self.assertEqual(
                [item[1] for item in events if isinstance(item, tuple)],
                [1, 2, 3, 4, 5, 6],
            )
            self.assertEqual(
                [item for item in events if isinstance(item, str)],
                ["analyze", "search", "select", "profiles", "visibility",
                 "report", "finalize"],
            )
            for name in (
                "01_company_analysis.json", "02_serp_results.json",
                "03_competitor_selection.json", "04_brand_profiles.json",
                "05_ai_visibility.json", "05_reddit_social.json",
                "05_reddit_snapshot_manifest.json", "06_bright_data_usage.json",
                "20260930-apple-us.md", "20260930-apple-us.pdf",
                "20260930-apple-us.json", "20260930-apple-us.zip",
            ):
                self.assertTrue((context.output_directory / name).is_file(), name)

    def test_social_run_preserves_parallel_prefetch_and_seventh_stage(self):
        with tempfile.TemporaryDirectory() as root:
            context, result, events = self.run_fixture(root, reddit=True)
            self.assertEqual(result["social_status"], "success")
            self.assertIn("prefetch", events)
            self.assertIn("social", events)
            self.assertLess(events.index("select"), events.index("prefetch"))
            self.assertLess(events.index("visibility"), events.index("report"))
            self.assertEqual(
                [item[1] for item in events if isinstance(item, tuple)],
                [1, 2, 3, 4, 5, 6, 7],
            )
            manifest = json.loads((
                context.output_directory / "05_reddit_snapshot_manifest.json"
            ).read_text())
            self.assertEqual(manifest["snapshots"], [{"snapshot_id": "snap-1"}])

    def test_notebook_embeds_same_stages_in_pipeline_order(self):
        notebook = json.loads(build_notebook().decode("utf-8"))
        source = "".join(next(
            cell["source"] for cell in notebook["cells"]
            if cell.get("metadata", {}).get("id") == "final-orchestration"
        ))
        markers = [
            "AUDIT-COMPANY-STAGE-CALL: start",
            "AUDIT-SEARCH-STAGE-CALL: start",
            "AUDIT-COMPETITOR-SELECTION-STAGE-CALL: start",
            "AUDIT-PROFILE-STAGE-CALL: start",
            "AUDIT-VISIBILITY-CHECKPOINT-STAGE-CALL: start",
            "AUDIT-SOCIAL-COMPLETION-STAGE-CALL: start",
            "AUDIT-REPORT-RENDER-STAGE-CALL: start",
            "AUDIT-FINALIZE-STAGE-CALL: start",
        ]
        self.assertEqual([source.count(marker) for marker in markers], [1] * 8)
        self.assertEqual(sorted(source.index(marker) for marker in markers),
                         [source.index(marker) for marker in markers])

    def test_fixture_result_matches_notebook_orchestration(self):
        notebook = json.loads(build_notebook().decode("utf-8"))
        source = "".join(next(
            cell["source"] for cell in notebook["cells"]
            if cell.get("metadata", {}).get("id") == "final-orchestration"
        ))
        function_source = source[
            source.index("async def run_competitive_visibility_audit("):
            source.index("# Report display")
        ]

        for reddit in (False, True):
            with self.subTest(reddit=reddit), tempfile.TemporaryDirectory() as root:
                service_root = Path(root) / "service"
                notebook_root = Path(root) / "notebook"
                service_root.mkdir()
                notebook_root.mkdir()
                _, service_result, _ = self.run_fixture(service_root, reddit=reddit)
                events = []
                fixture = self.make_ports(events)
                final_ports = fixture.finalize_stage_factory()
                client = Model(
                    configure_usage_checkpoint=lambda path, restore: None,
                    active_search_engine=None,
                    refresh_usage_results=fixture.report_stage.refresh_usage,
                    usage_summary=fixture.report_stage.usage_summary,
                )
                namespace = {
                    "asyncio": asyncio,
                    "datetime": datetime,
                    "timezone": timezone,
                    "json": json,
                    "time": __import__("time"),
                    "Path": Path,
                    "CURRENT_AUDIT_OUTPUT_DIRECTORY": None,
                    "ACTIVE_SEARCH_ENGINE": None,
                    "ACTIVE_SEARCH_STATUS": "unavailable",
                    "LAST_AI_MODE_DISCOVERY": None,
                    "LOCKED_TARGET_SCOPE": None,
                    "LAST_UTILITY_REPORT_RESULT": {"engine_name": "ChatGPT"},
                    "resolve_official_site": lambda url: {
                        "submitted_url": url, "submitted_hostname": "apple.com",
                        "canonical_url": "https://apple.com/",
                        "canonical_hostname": "apple.com", "redirect_chain": [],
                    },
                    "get_root_domain": lambda host: host,
                    "slugify": lambda value: value.lower(),
                    "audit_export_prefix": lambda *args: "20260930-apple-us",
                    "console": Model(print=lambda message: None),
                    "bd_client": client,
                    "write_json": fixture.company_stage.write_json,
                    "write_text": fixture.report_stage.write_text,
                    "configure_google_ai_race_cache": lambda *args, **kwargs: None,
                    "print_stage": lambda *args: None,
                    "print_stage_success": lambda message: None,
                    "print_stage_warning": lambda message: None,
                    "format_duration": fixture.report_stage.format_duration,
                    "run_company_stage_core": run_company_stage_core,
                    "CompanyStagePorts": CompanyStagePorts,
                    "analyze_company_stage": fixture.company_stage.analyze,
                    "CompanyIntake": Model,
                    "BrandAnalysis": Model,
                    "BuyerIntentKeyword": Model,
                    "restore_locked_target_scope": fixture.company_stage.restore_locked_scope,
                    "model_to_dict": as_dict,
                    "clean_record_for_storage": dict,
                    "run_search_stage_core": run_search_stage_core,
                    "SearchStagePorts": SearchStagePorts,
                    "run_serp_stage": fixture.search_stage.run_search,
                    "CompetitorCandidate": Model,
                    "run_competitor_selection_stage_core": run_competitor_selection_stage_core,
                    "CompetitorSelectionStagePorts": CompetitorSelectionStagePorts,
                    "select_competitors_stage": fixture.competitor_stage.select_competitors,
                    "start_reddit_discovery_prefetch": fixture.competitor_stage.start_reddit_prefetch,
                    "run_profile_stage_core": run_profile_stage_core,
                    "ProfileStagePorts": ProfileStagePorts,
                    "run_profile_stage": fixture.profile_stage.run_profiles,
                    "serialize_profile_task": dict,
                    "run_visibility_checkpoint_stage_core": run_visibility_checkpoint_stage_core,
                    "VisibilityCheckpointPorts": VisibilityCheckpointPorts,
                    "run_visibility_stage": fixture.visibility_stage.run_visibility,
                    "run_reddit_social_stage": fixture.visibility_stage.run_reddit_social,
                    "serialize_engine_result": dict,
                    "run_social_completion_stage_core": run_social_completion_stage_core,
                    "SocialCompletionPorts": SocialCompletionPorts,
                    "summarize_reddit_audit_warning": lambda result: "",
                    "run_report_render_stage_core": run_report_render_stage_core,
                    "ReportRenderPorts": ReportRenderPorts,
                    "generate_report_stage": fixture.report_stage.generate_report,
                    "finalize_report": fixture.report_stage.finalize_report,
                    "insert_reddit_report_section": fixture.report_stage.insert_reddit_section,
                    "build_bright_data_usage_section": fixture.report_stage.build_usage_section,
                    "report_filename": fixture.report_stage.report_filename,
                    "create_styled_pdf_report": fixture.report_stage.create_pdf,
                    "BRIGHT_DATA_PRICE_PER_1000_RESULTS_USD": 1.5,
                    "run_audit_finalize_stage_core": run_audit_finalize_stage_core,
                    "AuditFinalizePorts": AuditFinalizePorts,
                    "build_audit_record": final_ports.build_record,
                    "create_audit_zip": final_ports.create_zip,
                }
                rendered_source = function_source.replace(
                    "Path('/content')", f"Path({str(notebook_root)!r})"
                )
                exec(compile(rendered_source, "notebook-audit-function", "exec"),
                     namespace)
                settings = {
                    "company_name": "Apple", "company_domain": "apple.com",
                    "company_url": "https://apple.com/", "country": "US",
                    "audit_focus": "premium smartphone",
                    "include_reddit_analysis": reddit,
                    "include_google_ai_mode": False,
                    "include_chatgpt_visibility": True,
                    "include_gemini_visibility": False,
                    "include_copilot_visibility": False,
                }
                notebook_result = asyncio.run(
                    namespace["run_competitive_visibility_audit"](settings)
                )
                stable_fields = (
                    "selected", "selection_record", "search_results",
                    "visibility", "social_status", "usage", "warnings",
                    "stage_names",
                )
                self.assertEqual(
                    {key: service_result[key] for key in stable_fields},
                    {key: notebook_result[key] for key in stable_fields},
                )


if __name__ == "__main__":
    unittest.main()
