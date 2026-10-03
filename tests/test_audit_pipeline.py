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
from audit_core.audit_preparation import (
    AuditPreparationPorts, prepare_audit_run_core,
)
from audit_core.company_stage import CompanyStagePorts, run_company_stage_core
from audit_core.competitor_selection_stage import (
    CompetitorSelectionStagePorts, run_competitor_selection_stage_core,
)
from audit_core.profile_stage import ProfileStagePorts, run_profile_stage_core
from audit_core.report_export import serialize_profile_task
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
    def make_ports(self, events, *, scenario="baseline"):
        scope = {"value": {"market": "smartphones"}}

        def write_json(path, data):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding="utf-8")

        def analyze(settings):
            events.append("analyze")
            keywords = [Model(keyword="premium smartphone")]
            if scenario == "partial_search":
                keywords.append(Model(keyword="best premium smartphone"))
            return {
                "intake": Model(
                    brand=Model(
                        brand_name="Apple", domain="apple.com",
                        official_url="https://apple.com/",
                        category="premium smartphones",
                        positioning="premium devices",
                        target_customers=[], products=[], key_features=[],
                        differentiators=[], confidence=0.0, evidence=[],
                    ),
                    buyer_intent_keywords=keywords,
                ),
                "record": {"company": "fixture"},
            }

        async def search(**kwargs):
            events.append("search")
            if scenario == "partial_search":
                return {
                    "keyword_results": [
                        {
                            "keyword": "premium smartphone", "success": True,
                            "results": [{"domain": "samsung.com"}],
                        },
                        {
                            "keyword": "best premium smartphone", "success": False,
                            "error": "fixture timeout", "results": [],
                        },
                    ],
                    "candidates": [Model(
                        brand_name="Samsung", domain="samsung.com",
                    )],
                    "successful": 1, "failed": 1, "ai_mode_failed": 0,
                    "search_engine": "google", "search_status": "available",
                    "ai_mode_discovery": None,
                }
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

        def select(target, candidates, keywords, _locked_scope):
            events.append("select")
            if scenario == "no_competitors":
                return {
                    "selected": [], "record": {"selection": "no-valid-candidates"},
                    "rejected": [{"brand_name": "Samsung", "reason": "not direct"}],
                    "validation_results": [{"status": "rejected"}],
                    "used_fallback": False,
                }
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
                category="premium smartphones", positioning="premium devices",
                differentiators=["ecosystem"], relevant_products=["iPhone"],
            )
            competitor = Model(
                brand_name="Samsung", domain="samsung.com",
                official_url="https://samsung.com/", direct_competitor=True,
                category="premium smartphones", positioning="Android devices",
                differentiators=["choice"], relevant_products=["Galaxy"],
            )
            selected = kwargs["selected_competitors"]
            competitors = [competitor] if selected else []
            return {
                "target_profile": target,
                "competitor_profiles": competitors,
                "all_profiles": [target, *competitors],
                "task_results": [{"status": "success"} for _ in [target, *competitors]],
                "successful": len([target, *competitors]), "fallbacks": 0,
            }

        async def visibility(**kwargs):
            events.append("visibility")
            if scenario == "chatgpt_unavailable":
                return {
                    "prompt": "Which premium smartphone?",
                    "engines": {
                        "chatgpt": {
                            "status": "failed", "engine_name": "ChatGPT",
                            "duration_seconds": 1.0, "error": "fixture unavailable",
                        },
                    },
                    "mentions": {"chatgpt": []},
                }
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
                "status": "partial" if scenario == "partial_reddit" else "success",
                "mode": "competitive",
                "comparison": [{
                    "brand": "Apple", "relevant_posts": 1,
                    "classified_posts": 1, "sample_size": 1,
                }],
                "unique_thread_count": 1,
                "snapshot_manifest": [{"snapshot_id": "snap-1"}],
                "duration_seconds": 2.0,
                "warnings": (
                    ["One Reddit cohort was unavailable"]
                    if scenario == "partial_reddit" else []
                ),
            }

        def summarize_social_warning(result):
            return "; ".join(result.get("warnings") or [])

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
                selected_factory=Model,
                clean_record=dict,
                stage_warning=lambda message: None,
                print_selected=lambda competitor: None,
                social_notice=lambda: None,
                start_reddit_prefetch=prefetch,
            ),
            profile_stage=ProfileStagePorts(
                run_profiles=profiles, model_to_dict=as_dict,
                serialize_task=lambda result: serialize_profile_task(
                    result, model_to_dict=as_dict,
                ),
                write_json=write_json,
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
                summarize_warning=summarize_social_warning,
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

    def run_fixture(self, root, *, reddit, scenario="baseline"):
        events = []
        output = Path(root) / "competitive-visibility-apple-20260930-000000"
        context = AuditRunContext(
            run_id="apple-20260930-000000", run_timestamp=datetime(
                2026, 9, 30, tzinfo=timezone.utc,
            ),
            export_prefix="20260930-apple-us", output_directory=output,
            raw_directory=output / "raw",
            site_resolution={
                "submitted_url": "https://apple.com/",
                "submitted_hostname": "apple.com",
                "canonical_url": "https://apple.com/",
                "canonical_hostname": "apple.com",
                "redirect_chain": [],
                "submitted_domain": "apple.com",
                "canonical_domain": "apple.com",
                "final_http_status": 200,
                "verification": "verified_response",
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
            settings, context, ports=self.make_ports(events, scenario=scenario),
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
        pipeline = source.split(
            "# AUDIT-PIPELINE: start\n", 1,
        )[1].split("# AUDIT-PIPELINE: end", 1)[0]
        function = source[
            source.index("async def run_competitive_visibility_audit("):
            source.index("# Report display")
        ]
        self.assertIn("async def run_audit_pipeline(", pipeline)
        self.assertEqual(function.count("run_audit_pipeline("), 1)
        self.assertIn(
            "return await run_audit_pipeline(settings, context, ports=ports)",
            function,
        )
        self.assertIn("serialize_task=lambda result:", function)
        self.assertIn("result, model_to_dict=model_to_dict,", function)
        for duplicated_stage_call in (
            "run_company_stage_core(", "run_search_stage_core(",
            "run_competitor_selection_stage_core(",
            "run_profile_stage_core(",
            "run_visibility_checkpoint_stage_core(",
            "run_social_completion_stage_core(",
            "run_report_render_stage_core(",
            "run_audit_finalize_stage_core(",
        ):
            self.assertNotIn(duplicated_stage_call, function)

    def test_fixture_result_matches_notebook_orchestration(self):
        notebook = json.loads(build_notebook().decode("utf-8"))
        source = "".join(next(
            cell["source"] for cell in notebook["cells"]
            if cell.get("metadata", {}).get("id") == "final-orchestration"
        ))
        pipeline_source = source.split(
            "# AUDIT-PIPELINE: start\n", 1,
        )[1].split("# AUDIT-PIPELINE: end", 1)[0]
        function_source = source[
            source.index("async def run_competitive_visibility_audit("):
            source.index("# Report display")
        ]

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 9, 30, tzinfo=tz or timezone.utc)

        volatile_fields = {
            "duration_seconds", "audit_started_at", "completed_at",
            "stage_durations", "elapsed_seconds",
            "created_at", "updated_at", "run_id", "audit_as_of_date",
        }

        def normalize(value, roots):
            if isinstance(value, dict):
                return {
                    key: normalize(item, roots)
                    for key, item in value.items()
                    if key not in volatile_fields
                }
            if isinstance(value, list):
                return [normalize(item, roots) for item in value]
            if isinstance(value, str):
                for root in roots:
                    value = value.replace(str(root), "<OUTPUT>")
            return value

        def output_artifacts(root, *, exclude_run_settings=False):
            files = sorted(path for path in root.rglob("*") if path.is_file())
            artifacts = {}
            for path in files:
                relative = path.relative_to(root)
                if exclude_run_settings and relative.name == "00_run_settings.json":
                    continue
                if path.suffix == ".json":
                    artifacts[str(relative)] = normalize(
                        json.loads(path.read_text(encoding="utf-8")),
                        (root,),
                    )
                elif path.suffix in {".md", ".txt"}:
                    content = path.read_text(encoding="utf-8")
                    for candidate_root in (root,):
                        content = content.replace(str(candidate_root), "<OUTPUT>")
                    artifacts[str(relative)] = content
                else:
                    artifacts[str(relative)] = path.read_bytes()
            return artifacts

        def differing_paths(left, right, prefix=""):
            if isinstance(left, dict) and isinstance(right, dict):
                result = []
                for key in sorted(set(left) | set(right)):
                    path = f"{prefix}.{key}" if prefix else str(key)
                    if key not in left or key not in right:
                        result.append(path)
                    else:
                        result.extend(differing_paths(left[key], right[key], path))
                return result
            if isinstance(left, list) and isinstance(right, list):
                if len(left) != len(right):
                    return [f"{prefix}.length"]
                result = []
                for index, (left_item, right_item) in enumerate(zip(left, right)):
                    result.extend(differing_paths(left_item, right_item, f"{prefix}[{index}]"))
                return result
            return [] if left == right else [prefix]

        scenarios = (
            ("baseline", False),
            ("baseline_reddit", True),
            ("partial_search", False),
            ("chatgpt_unavailable", False),
            ("no_competitors", False),
            ("partial_reddit", True),
        )
        for scenario, reddit in scenarios:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as root:
                service_root = Path(root) / "service"
                notebook_root = Path(root) / "notebook"
                service_root.mkdir()
                notebook_root.mkdir()
                _, service_result, _ = self.run_fixture(
                    service_root, reddit=reddit, scenario=scenario,
                )
                events = []
                fixture = self.make_ports(events, scenario=scenario)
                final_ports = fixture.finalize_stage_factory()
                client = Model(
                    configure_usage_checkpoint=lambda path, restore: None,
                    active_search_engine=None,
                    refresh_usage_results=fixture.report_stage.refresh_usage,
                    usage_summary=fixture.report_stage.usage_summary,
                )
                namespace = {
                    "asyncio": asyncio,
                    "datetime": FixedDateTime,
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
                        "final_http_status": 200,
                        "verification": "verified_response",
                    },
                    "get_root_domain": lambda host: host,
                    "slugify": lambda value: value.lower(),
                    "audit_export_prefix": lambda *args: "20260930-apple-us",
                    "AuditPreparationPorts": AuditPreparationPorts,
                    "prepare_audit_run_core": prepare_audit_run_core,
                    "find_latest_audit_to_continue": lambda settings: None,
                    "import_google_ai_snapshot_ids": lambda ids: 0,
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
                    "CompanyAnalysisPorts": Model,
                    "run_company_analysis_core": lambda _settings, ports:
                        fixture.company_stage.analyze(_settings),
                    "run_chatgpt_without_web": lambda *_args, **_kwargs: None,
                    "parse_ai_json": json.loads,
                    "normalize_company_intake": lambda **kwargs: kwargs,
                    "select_relevant_company_research": lambda **kwargs: "",
                    "complete_company_keywords": lambda **kwargs: {},
                    "proofread_buyer_keywords": lambda **kwargs: {},
                    "build_locked_target_scope": lambda *_args: {},
                    "BrightDataAPIError": RuntimeError,
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
                    "SelectedCompetitor": Model,
                    "select_competitors_stage": fixture.competitor_stage.select_competitors,
                    "start_reddit_discovery_prefetch": fixture.competitor_stage.start_reddit_prefetch,
                    "run_profile_stage_core": run_profile_stage_core,
                    "ProfileStagePorts": ProfileStagePorts,
                    "run_profile_stage": fixture.profile_stage.run_profiles,
                    "serialize_profile_task": serialize_profile_task,
                    "run_visibility_checkpoint_stage_core": run_visibility_checkpoint_stage_core,
                    "VisibilityCheckpointPorts": VisibilityCheckpointPorts,
                    "run_visibility_stage": fixture.visibility_stage.run_visibility,
                    "run_reddit_social_stage": fixture.visibility_stage.run_reddit_social,
                    "serialize_engine_result": dict,
                    "run_social_completion_stage_core": run_social_completion_stage_core,
                    "SocialCompletionPorts": SocialCompletionPorts,
                    "summarize_reddit_audit_warning": lambda result: "; ".join(
                        result.get("warnings") or []
                    ),
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
                executable_source = pipeline_source + "\n\n" + rendered_source
                exec(compile(
                    executable_source, "notebook-audit-function", "exec",
                ), namespace)
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
                notebook_output = Path(
                    namespace["CURRENT_AUDIT_OUTPUT_DIRECTORY"]
                )
                service_artifacts = output_artifacts(
                    service_root / "competitive-visibility-apple-20260930-000000",
                )
                notebook_artifacts = output_artifacts(
                    notebook_output, exclude_run_settings=True,
                )
                self.assertEqual(set(service_artifacts), set(notebook_artifacts))
                for artifact_name in service_artifacts:
                    with self.subTest(reddit=reddit, artifact=artifact_name):
                        if isinstance(service_artifacts[artifact_name], dict):
                            self.assertEqual(
                                set(service_artifacts[artifact_name]),
                                set(notebook_artifacts[artifact_name]),
                            )
                        self.assertEqual(
                            service_artifacts[artifact_name],
                            notebook_artifacts[artifact_name],
                            msg="Differing normalized fields: " + ", ".join(
                                differing_paths(
                                    service_artifacts[artifact_name],
                                    notebook_artifacts[artifact_name],
                                )[:20]
                            ),
                        )
                self.assertEqual(
                    service_result["usage"]["estimated_cost_usd"],
                    notebook_result["usage"]["estimated_cost_usd"],
                )
                if scenario == "partial_search":
                    self.assertIn("1 SERP request(s) failed", service_result["warnings"])
                elif scenario == "chatgpt_unavailable":
                    self.assertTrue(any(
                        warning.startswith("ChatGPT visibility failed")
                        for warning in service_result["warnings"]
                    ))
                elif scenario == "no_competitors":
                    self.assertEqual(service_result["selected"], [])
                elif scenario == "partial_reddit":
                    self.assertEqual(service_result["social_status"], "partial")
                    self.assertIn(
                        "One Reddit cohort was unavailable",
                        service_result["warnings"],
                    )
                self.assertEqual(
                    service_result["visibility"]["chatgpt"]["engine_name"],
                    notebook_result["visibility"]["chatgpt"]["engine_name"],
                )


if __name__ == "__main__":
    unittest.main()
