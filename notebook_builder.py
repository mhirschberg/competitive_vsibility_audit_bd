"""Deterministically embed shared Python sources into the standalone notebook.

Only tagged cells are generated for now. Other notebook cells remain untouched
until their logic has been extracted into service modules.
"""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
NOTEBOOK = ROOT / "competitive_visibility_audit_bd.ipynb"
REDDIT_SOURCE = ROOT / "reddit_social.py"
RESEARCH_SOURCE = ROOT / "research_fallback.py"
RESEARCH_RACE_SOURCE = ROOT / "audit_core" / "research_race.py"
PRIMITIVES_SOURCE = ROOT / "audit_core" / "primitives.py"
DOMAINS_SOURCE = ROOT / "audit_core" / "domains.py"
SERP_METRICS_SOURCE = ROOT / "audit_core" / "serp_metrics.py"
BRAND_MENTIONS_SOURCE = ROOT / "audit_core" / "brand_mentions.py"
VISIBILITY_STAGE_SOURCE = ROOT / "audit_core" / "visibility_stage.py"
VISIBILITY_PROMPT_SOURCE = ROOT / "audit_core" / "visibility_prompt.py"
VISIBILITY_SOURCES_SOURCE = ROOT / "audit_core" / "visibility_sources.py"
ARTIFACT_WRITES_SOURCE = ROOT / "audit_core" / "artifact_writes.py"
ARTIFACT_RESUME_SOURCE = ROOT / "audit_core" / "artifact_resume.py"
COMPANY_STAGE_SOURCE = ROOT / "audit_core" / "company_stage.py"
SEARCH_DISCOVERY_SOURCE = ROOT / "audit_core" / "search_discovery.py"
SEARCH_STAGE_SOURCE = ROOT / "audit_core" / "search_stage.py"
COMPETITOR_SELECTION_STAGE_SOURCE = ROOT / "audit_core" / "competitor_selection_stage.py"
PROFILE_RESEARCH_SOURCE = ROOT / "audit_core" / "profile_research.py"
PROFILE_STAGE_SOURCE = ROOT / "audit_core" / "profile_stage.py"
VISIBILITY_CHECKPOINT_STAGE_SOURCE = ROOT / "audit_core" / "visibility_checkpoint_stage.py"
SOCIAL_COMPLETION_STAGE_SOURCE = ROOT / "audit_core" / "social_completion_stage.py"
BRIGHTDATA_TRANSPORT_SOURCE = ROOT / "audit_core" / "brightdata_transport.py"
OFFICIAL_DOMAINS_SOURCE = ROOT / "audit_core" / "official_domains.py"
BRIGHTDATA_USAGE_SOURCE = ROOT / "audit_core" / "brightdata_usage.py"
SERP_TRANSPORT_SOURCE = ROOT / "audit_core" / "serp_transport.py"
SERP_SELECTION_SOURCE = ROOT / "audit_core" / "serp_selection.py"
SERP_PARSING_SOURCE = ROOT / "audit_core" / "serp_parsing.py"
SERP_MARKDOWN_SOURCE = ROOT / "audit_core" / "serp_markdown.py"
AI_LOCALIZATION_SOURCE = ROOT / "audit_core" / "ai_localization.py"
AI_VISIBILITY_RACE_SOURCE = ROOT / "audit_core" / "ai_visibility_race.py"
SCOPE_SOURCE = ROOT / "audit_core" / "competitor_scope.py"
COMPETITOR_RESEARCH_SOURCE = ROOT / "audit_core" / "competitor_research.py"
COMPETITOR_DECISIONS_SOURCE = ROOT / "audit_core" / "competitor_decisions.py"
COMPETITOR_PIPELINE_SOURCE = ROOT / "audit_core" / "competitor_pipeline.py"
COMPETITOR_STAGE_SOURCE = ROOT / "audit_core" / "competitor_stage.py"
REPORT_CONTENT_SOURCE = ROOT / "audit_core" / "report_content.py"
REPORT_STAGE_SOURCE = ROOT / "audit_core" / "report_stage.py"
REPORT_EXPORT_SOURCE = ROOT / "audit_core" / "report_export.py"
ARTIFACT_NAMES_SOURCE = ROOT / "audit_core" / "artifact_names.py"
PRIMITIVES_CELL_ID = "final-core"
PRIMITIVES_START = "# AUDIT-PRIMITIVES: start"
PRIMITIVES_END = "# AUDIT-PRIMITIVES: end"
DOMAINS_START = "# AUDIT-DOMAINS: start"
DOMAINS_END = "# AUDIT-DOMAINS: end"
SERP_METRICS_START = "# AUDIT-SERP-METRICS: start"
SERP_METRICS_END = "# AUDIT-SERP-METRICS: end"
BRAND_MENTIONS_START = "# AUDIT-BRAND-MENTIONS: start"
BRAND_MENTIONS_END = "# AUDIT-BRAND-MENTIONS: end"
VISIBILITY_STAGE_START = "# AUDIT-VISIBILITY-STAGE: start"
VISIBILITY_STAGE_END = "# AUDIT-VISIBILITY-STAGE: end"
VISIBILITY_PROMPT_START = "# AUDIT-VISIBILITY-PROMPT: start"
VISIBILITY_PROMPT_END = "# AUDIT-VISIBILITY-PROMPT: end"
VISIBILITY_SOURCES_START = "# AUDIT-VISIBILITY-SOURCES: start"
VISIBILITY_SOURCES_END = "# AUDIT-VISIBILITY-SOURCES: end"
ARTIFACT_WRITES_START = "# AUDIT-ARTIFACT-WRITES: start"
ARTIFACT_WRITES_END = "# AUDIT-ARTIFACT-WRITES: end"
ARTIFACT_RESUME_START = "# AUDIT-ARTIFACT-RESUME: start"
ARTIFACT_RESUME_END = "# AUDIT-ARTIFACT-RESUME: end"
COMPANY_STAGE_START = "# AUDIT-COMPANY-STAGE: start"
COMPANY_STAGE_END = "# AUDIT-COMPANY-STAGE: end"
COMPANY_STAGE_CALL_START = "# AUDIT-COMPANY-STAGE-CALL: start"
COMPANY_STAGE_CALL_END = "    # AUDIT-COMPANY-STAGE-CALL: end"
SEARCH_DISCOVERY_START = "# AUDIT-SEARCH-DISCOVERY: start"
SEARCH_DISCOVERY_END = "# AUDIT-SEARCH-DISCOVERY: end"
SEARCH_STAGE_START = "# AUDIT-SEARCH-STAGE: start"
SEARCH_STAGE_END = "# AUDIT-SEARCH-STAGE: end"
SEARCH_STAGE_CALL_START = "# AUDIT-SEARCH-STAGE-CALL: start"
SEARCH_STAGE_CALL_END = "    # AUDIT-SEARCH-STAGE-CALL: end"
COMPETITOR_SELECTION_STAGE_START = "# AUDIT-COMPETITOR-SELECTION-STAGE: start"
COMPETITOR_SELECTION_STAGE_END = "# AUDIT-COMPETITOR-SELECTION-STAGE: end"
COMPETITOR_SELECTION_STAGE_CALL_START = "# AUDIT-COMPETITOR-SELECTION-STAGE-CALL: start"
COMPETITOR_SELECTION_STAGE_CALL_END = "    # AUDIT-COMPETITOR-SELECTION-STAGE-CALL: end"
PROFILE_RESEARCH_START = "# AUDIT-PROFILE-RESEARCH: start"
PROFILE_RESEARCH_END = "# AUDIT-PROFILE-RESEARCH: end"
PROFILE_STAGE_START = "# AUDIT-PROFILE-STAGE: start"
PROFILE_STAGE_END = "# AUDIT-PROFILE-STAGE: end"
PROFILE_STAGE_CALL_START = "# AUDIT-PROFILE-STAGE-CALL: start"
PROFILE_STAGE_CALL_END = "    # AUDIT-PROFILE-STAGE-CALL: end"
VISIBILITY_CHECKPOINT_STAGE_START = "# AUDIT-VISIBILITY-CHECKPOINT-STAGE: start"
VISIBILITY_CHECKPOINT_STAGE_END = "# AUDIT-VISIBILITY-CHECKPOINT-STAGE: end"
VISIBILITY_CHECKPOINT_STAGE_CALL_START = "# AUDIT-VISIBILITY-CHECKPOINT-STAGE-CALL: start"
VISIBILITY_CHECKPOINT_STAGE_CALL_END = "    # AUDIT-VISIBILITY-CHECKPOINT-STAGE-CALL: end"
SOCIAL_COMPLETION_STAGE_START = "# AUDIT-SOCIAL-COMPLETION-STAGE: start"
SOCIAL_COMPLETION_STAGE_END = "# AUDIT-SOCIAL-COMPLETION-STAGE: end"
SOCIAL_COMPLETION_STAGE_CALL_START = "# AUDIT-SOCIAL-COMPLETION-STAGE-CALL: start"
SOCIAL_COMPLETION_STAGE_CALL_END = "    # AUDIT-SOCIAL-COMPLETION-STAGE-CALL: end"
BRIGHTDATA_TRANSPORT_START = "# AUDIT-BRIGHTDATA-TRANSPORT: start"
BRIGHTDATA_TRANSPORT_END = "# AUDIT-BRIGHTDATA-TRANSPORT: end"
OFFICIAL_DOMAINS_START = "# AUDIT-OFFICIAL-DOMAINS: start"
OFFICIAL_DOMAINS_END = "# AUDIT-OFFICIAL-DOMAINS: end"
BRIGHTDATA_USAGE_START = "# AUDIT-BRIGHTDATA-USAGE: start"
BRIGHTDATA_USAGE_END = "# AUDIT-BRIGHTDATA-USAGE: end"
SERP_TRANSPORT_START = "# AUDIT-SERP-TRANSPORT: start"
SERP_TRANSPORT_END = "# AUDIT-SERP-TRANSPORT: end"
SERP_SELECTION_START = "# AUDIT-SERP-SELECTION: start"
SERP_SELECTION_END = "# AUDIT-SERP-SELECTION: end"
SERP_PARSING_START = "# AUDIT-SERP-PARSING: start"
SERP_PARSING_END = "# AUDIT-SERP-PARSING: end"
SERP_MARKDOWN_START = "# AUDIT-SERP-MARKDOWN: start"
SERP_MARKDOWN_END = "# AUDIT-SERP-MARKDOWN: end"
AI_LOCALIZATION_START = "# AUDIT-AI-LOCALIZATION: start"
AI_LOCALIZATION_END = "# AUDIT-AI-LOCALIZATION: end"
AI_VISIBILITY_RACE_START = "# AUDIT-AI-VISIBILITY-RACE: start"
AI_VISIBILITY_RACE_END = "# AUDIT-AI-VISIBILITY-RACE: end"
SCOPE_CELL_ID = "runtime-utilities-merged"
SCOPE_START = "# AUDIT-COMPETITOR-SCOPE: start"
SCOPE_END = "# AUDIT-COMPETITOR-SCOPE: end"
SCOPE_PACKAGE_IMPORT = "from .primitives import normalize_confidence\n"
COMPETITOR_RESEARCH_START = "# AUDIT-COMPETITOR-RESEARCH: start"
COMPETITOR_RESEARCH_END = "# AUDIT-COMPETITOR-RESEARCH: end"
COMPETITOR_DECISIONS_START = "# AUDIT-COMPETITOR-DECISIONS: start"
COMPETITOR_DECISIONS_END = "# AUDIT-COMPETITOR-DECISIONS: end"
COMPETITOR_PIPELINE_START = "# AUDIT-COMPETITOR-PIPELINE: start"
COMPETITOR_PIPELINE_END = "# AUDIT-COMPETITOR-PIPELINE: end"
COMPETITOR_STAGE_START = "# AUDIT-COMPETITOR-STAGE: start"
COMPETITOR_STAGE_END = "# AUDIT-COMPETITOR-STAGE: end"
REPORT_CONTENT_START = "# AUDIT-REPORT-CONTENT: start"
REPORT_CONTENT_END = "# AUDIT-REPORT-CONTENT: end"
REPORT_STAGE_START = "# AUDIT-REPORT-STAGE: start"
REPORT_STAGE_END = "# AUDIT-REPORT-STAGE: end"
REPORT_EXPORT_START = "# AUDIT-REPORT-EXPORT: start"
REPORT_EXPORT_END = "# AUDIT-REPORT-EXPORT: end"
ARTIFACT_NAMES_START = "# AUDIT-ARTIFACT-NAMES: start"
ARTIFACT_NAMES_END = "# AUDIT-ARTIFACT-NAMES: end"
SERVICE_IMPORTS_START = "# SERVICE-ONLY-IMPORTS: start"
SERVICE_IMPORTS_END = "# SERVICE-ONLY-IMPORTS: end"
REDDIT_CELL_ID = "runtime-utilities-merged"
RESEARCH_CELL_ID = "research-provider-race"
RESEARCH_RACE_START = "# AUDIT-RESEARCH-RACE: start"
RESEARCH_RACE_END = "# AUDIT-RESEARCH-RACE: end"
REDDIT_START = "# REDDIT-SOCIAL-PATCH: start"
REDDIT_END = "# REDDIT-SOCIAL-PATCH: end"
RESEARCH_HEADER = (
    "#@title 3E. Load resilient research providers\n"
    "#@markdown Race ChatGPT and Gemini for internal research; "
    "keep Google AI Mode measured separately.\n\n"
)
COMPANY_STAGE_CALL_SOURCE = '''    def set_company_locked_scope(scope):
        global LOCKED_TARGET_SCOPE
        LOCKED_TARGET_SCOPE = scope

    company_stage = await run_company_stage_core(
        settings,
        continuing=continuing,
        output_directory=output_directory,
        raw_directory=raw_directory,
        run_timestamp=run_timestamp,
        started_at=stage_started_at,
        ports=CompanyStagePorts(
            analyze=analyze_company_stage,
            intake_factory=CompanyIntake,
            brand_factory=BrandAnalysis,
            keyword_factory=BuyerIntentKeyword,
            get_locked_scope=lambda: LOCKED_TARGET_SCOPE,
            set_locked_scope=set_company_locked_scope,
            restore_locked_scope=restore_locked_target_scope,
            model_to_dict=model_to_dict,
            write_json=write_json,
            clean_record=clean_record_for_storage,
            stage_success=print_stage_success,
        ),
    )
    LOCKED_TARGET_SCOPE = company_stage["locked_scope"]
    target_brand = company_stage["target_brand"]
    keyword_records = company_stage["keyword_records"]
    keywords = company_stage["keywords"]
    stage_durations["company_analysis"] = company_stage["duration_seconds"]'''
SEARCH_STAGE_CALL_SOURCE = '''    search_stage = await run_search_stage_core(
        keywords, target_brand.domain,
        continuing=continuing,
        output_directory=output_directory,
        started_at=stage_started_at,
        ports=SearchStagePorts(
            run_search=run_serp_stage,
            candidate_factory=CompetitorCandidate,
            model_to_dict=model_to_dict,
            write_json=write_json,
            stage_success=print_stage_success,
            stage_warning=print_stage_warning,
            format_duration=format_duration,
        ),
    )
    keyword_serp_results = search_stage["keyword_results"]
    competitor_candidates = search_stage["candidates"]
    stage_durations["serp_discovery"] = search_stage["duration_seconds"]
    ACTIVE_SEARCH_ENGINE = search_stage["search_engine"]
    ACTIVE_SEARCH_STATUS = search_stage["search_status"]
    LAST_AI_MODE_DISCOVERY = search_stage["ai_mode_discovery"]
    bd_client.active_search_engine = ACTIVE_SEARCH_ENGINE
    warnings.extend(search_stage["warnings"])'''
COMPETITOR_SELECTION_STAGE_CALL_SOURCE = '''    competitor_stage = await run_competitor_selection_stage_core(
        target_brand, competitor_candidates, keywords,
        continuing=continuing,
        output_directory=output_directory,
        raw_directory=raw_directory,
        started_at=stage_started_at,
        include_reddit_analysis=include_reddit_analysis,
        audit_focus=settings.get("audit_focus", ""),
        ports=CompetitorSelectionStagePorts(
            select_competitors=select_competitors_stage,
            configure_race_cache=configure_google_ai_race_cache,
            write_json=write_json,
            model_to_dict=model_to_dict,
            clean_record=clean_record_for_storage,
            stage_warning=print_stage_warning,
            print_selected=lambda competitor: console.print(
                f"      ✓ {competitor.brand_name}"
            ),
            social_notice=lambda: console.print(
                "      [cyan]↗ Social discovery started in parallel; "
                "snapshots are labelled [Social · …].[/cyan]"
            ),
            start_reddit_prefetch=start_reddit_discovery_prefetch,
        ),
    )
    selected_competitors = competitor_stage["selected_competitors"]
    stage_durations["competitor_selection"] = competitor_stage["duration_seconds"]
    warnings.extend(competitor_stage["warnings"])
    reddit_prefetch_task = competitor_stage["reddit_prefetch_task"]'''
PROFILE_RESEARCH_ADAPTER_SOURCE = '''async def run_profile_stage(
    target_brand, selected_competitors, audit_focus="",
):
    return await run_profile_research_core(
        target_brand, selected_competitors, audit_focus,
        ports=ProfileResearchPorts(
            generate_profile=generate_profile_sync,
            recover_profile=recover_profile_sync,
            fallback_profile=fallback_profile,
            root_domain=get_root_domain,
            pending_notice=lambda count: console.print(
                f"      Waiting for {count} late profile snapshot(s)..."
            ),
        ),
    )'''
PROFILE_STAGE_CALL_SOURCE = '''    profile_stage = await run_profile_stage_core(
        target_brand, selected_competitors,
        audit_focus=settings.get("audit_focus", ""),
        company_domain=settings["company_domain"],
        company_url=settings["company_url"],
        output_directory=output_directory,
        started_at=stage_started_at,
        ports=ProfileStagePorts(
            run_profiles=run_profile_stage,
            model_to_dict=model_to_dict,
            serialize_task=serialize_profile_task,
            write_json=write_json,
            stage_success=print_stage_success,
            stage_warning=print_stage_warning,
        ),
    )
    target_profile = profile_stage["target_profile"]
    competitor_profiles = profile_stage["competitor_profiles"]
    all_profiles = profile_stage["all_profiles"]
    stage_durations["brand_profiles"] = profile_stage["duration_seconds"]
    warnings.extend(profile_stage["warnings"])'''
VISIBILITY_CHECKPOINT_STAGE_CALL_SOURCE = '''    visibility_stage = await run_visibility_checkpoint_stage_core(
        target_profile, competitor_profiles, all_profiles, keywords,
        keyword_serp_results,
        include_copilot=include_copilot_visibility,
        include_google_ai_mode=include_google_ai_mode,
        include_chatgpt=include_chatgpt_visibility,
        include_gemini=include_gemini_visibility,
        wait_longer_for_chatgpt=bool(settings.get("wait_longer_for_chatgpt", False)),
        wait_longer_for_gemini=bool(settings.get("wait_longer_for_gemini", False)),
        wait_longer_for_copilot=bool(settings.get("wait_longer_for_copilot", False)),
        include_reddit_analysis=include_reddit_analysis,
        audit_focus=settings.get("audit_focus", ""),
        reddit_prefetch_task=reddit_prefetch_task,
        output_directory=output_directory,
        started_at=stage_started_at,
        ports=VisibilityCheckpointPorts(
            run_visibility=run_visibility_stage,
            run_reddit_social=run_reddit_social_stage,
            serialize_engine_result=serialize_engine_result,
            write_json=write_json,
            stage_success=print_stage_success,
            stage_warning=print_stage_warning,
            format_duration=format_duration,
        ),
    )
    visibility_result = visibility_stage["visibility_result"]
    reddit_task = visibility_stage["reddit_task"]
    reddit_social_result = visibility_stage["reddit_social_result"]
    stage_durations["ai_visibility"] = visibility_stage["duration_seconds"]
    warnings.extend(visibility_stage["warnings"])'''
SOCIAL_COMPLETION_STAGE_CALL_SOURCE = '''    social_stage = await run_social_completion_stage_core(
        reddit_task, reddit_social_result,
        include_reddit_analysis=include_reddit_analysis,
        total_stages=total_stages,
        output_directory=output_directory,
        ports=SocialCompletionPorts(
            print_stage=print_stage,
            stage_success=print_stage_success,
            stage_warning=print_stage_warning,
            format_duration=format_duration,
            summarize_warning=summarize_reddit_audit_warning,
            write_json=write_json,
        ),
    )
    reddit_social_result = social_stage["reddit_social_result"]
    stage_durations["reddit_social"] = social_stage["duration_seconds"]
    warnings.extend(social_stage["warnings"])'''


def _unique_cell(notebook, cell_id):
    matches = [
        cell for cell in notebook["cells"]
        if cell.get("metadata", {}).get("id") == cell_id
    ]
    if len(matches) != 1 or matches[0].get("cell_type") != "code":
        raise ValueError(f"Expected exactly one code cell with id {cell_id!r}")
    return matches[0]


def _replace_embedded_source(cell, start, end, source):
    text = "".join(cell["source"])
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"Expected exactly one {start!r}/{end!r} marker pair")
    prefix, remainder = text.split(start, 1)
    _, suffix = remainder.split(end, 1)
    if start in suffix or end in prefix:
        raise ValueError("Embedded source markers are out of order")
    cell["source"] = (
        prefix + start + "\n" + source.rstrip("\n") + "\n" + end + suffix
    ).splitlines(keepends=True)


def _without_service_imports(source):
    if (source.count(SERVICE_IMPORTS_START) != 1
            or source.count(SERVICE_IMPORTS_END) != 1):
        raise ValueError("Expected one service-only import block")
    before, remainder = source.split(SERVICE_IMPORTS_START, 1)
    _, after = remainder.split(SERVICE_IMPORTS_END, 1)
    return before.rstrip("\n") + "\n\n" + after.lstrip("\n")


def build_notebook(notebook_path=NOTEBOOK, reddit_source=REDDIT_SOURCE,
                   research_source=RESEARCH_SOURCE,
                   research_race_source=RESEARCH_RACE_SOURCE,
                   primitives_source=PRIMITIVES_SOURCE,
                   domains_source=DOMAINS_SOURCE,
                   serp_metrics_source=SERP_METRICS_SOURCE,
                   brand_mentions_source=BRAND_MENTIONS_SOURCE,
                   visibility_stage_source=VISIBILITY_STAGE_SOURCE,
                   visibility_prompt_source=VISIBILITY_PROMPT_SOURCE,
                   visibility_sources_source=VISIBILITY_SOURCES_SOURCE,
                   artifact_writes_source=ARTIFACT_WRITES_SOURCE,
                   artifact_resume_source=ARTIFACT_RESUME_SOURCE,
                   company_stage_source=COMPANY_STAGE_SOURCE,
                   search_discovery_source=SEARCH_DISCOVERY_SOURCE,
                   search_stage_source=SEARCH_STAGE_SOURCE,
                   competitor_selection_stage_source=COMPETITOR_SELECTION_STAGE_SOURCE,
                   profile_research_source=PROFILE_RESEARCH_SOURCE,
                   profile_stage_source=PROFILE_STAGE_SOURCE,
                   visibility_checkpoint_stage_source=VISIBILITY_CHECKPOINT_STAGE_SOURCE,
                   social_completion_stage_source=SOCIAL_COMPLETION_STAGE_SOURCE,
                   brightdata_transport_source=BRIGHTDATA_TRANSPORT_SOURCE,
                   official_domains_source=OFFICIAL_DOMAINS_SOURCE,
                   brightdata_usage_source=BRIGHTDATA_USAGE_SOURCE,
                   serp_transport_source=SERP_TRANSPORT_SOURCE,
                   serp_selection_source=SERP_SELECTION_SOURCE,
                   serp_parsing_source=SERP_PARSING_SOURCE,
                   serp_markdown_source=SERP_MARKDOWN_SOURCE,
                   ai_localization_source=AI_LOCALIZATION_SOURCE,
                   ai_visibility_race_source=AI_VISIBILITY_RACE_SOURCE,
                   scope_source=SCOPE_SOURCE,
                   competitor_research_source=COMPETITOR_RESEARCH_SOURCE,
                   competitor_decisions_source=COMPETITOR_DECISIONS_SOURCE,
                   competitor_pipeline_source=COMPETITOR_PIPELINE_SOURCE,
                   competitor_stage_source=COMPETITOR_STAGE_SOURCE,
                   report_content_source=REPORT_CONTENT_SOURCE,
                   report_stage_source=REPORT_STAGE_SOURCE,
                   report_export_source=REPORT_EXPORT_SOURCE,
                   artifact_names_source=ARTIFACT_NAMES_SOURCE):
    """Return notebook bytes with generated cells synchronized to sources."""
    notebook = json.loads(Path(notebook_path).read_text(encoding="utf-8"))
    primitives_cell = _unique_cell(notebook, PRIMITIVES_CELL_ID)
    _replace_embedded_source(
        primitives_cell,
        PRIMITIVES_START,
        PRIMITIVES_END,
        Path(primitives_source).read_text(encoding="utf-8"),
    )
    _replace_embedded_source(
        primitives_cell,
        DOMAINS_START,
        DOMAINS_END,
        Path(domains_source).read_text(encoding="utf-8"),
    )
    _replace_embedded_source(
        primitives_cell,
        BRIGHTDATA_TRANSPORT_START,
        BRIGHTDATA_TRANSPORT_END,
        Path(brightdata_transport_source).read_text(encoding="utf-8"),
    )
    _replace_embedded_source(
        primitives_cell,
        OFFICIAL_DOMAINS_START,
        OFFICIAL_DOMAINS_END,
        Path(official_domains_source).read_text(encoding="utf-8"),
    )
    _replace_embedded_source(
        primitives_cell,
        ARTIFACT_NAMES_START,
        ARTIFACT_NAMES_END,
        Path(artifact_names_source).read_text(encoding="utf-8"),
    )
    _replace_embedded_source(
        primitives_cell,
        BRIGHTDATA_USAGE_START,
        BRIGHTDATA_USAGE_END,
        Path(brightdata_usage_source).read_text(encoding="utf-8"),
    )
    _replace_embedded_source(
        primitives_cell,
        SERP_TRANSPORT_START,
        SERP_TRANSPORT_END,
        _without_service_imports(
            Path(serp_transport_source).read_text(encoding="utf-8")
        ),
    )
    _replace_embedded_source(
        primitives_cell,
        SERP_SELECTION_START,
        SERP_SELECTION_END,
        _without_service_imports(
            Path(serp_selection_source).read_text(encoding="utf-8")
        ),
    )
    _replace_embedded_source(
        primitives_cell,
        SERP_PARSING_START,
        SERP_PARSING_END,
        Path(serp_parsing_source).read_text(encoding="utf-8"),
    )
    _replace_embedded_source(
        primitives_cell,
        SERP_MARKDOWN_START,
        SERP_MARKDOWN_END,
        _without_service_imports(
            Path(serp_markdown_source).read_text(encoding="utf-8")
        ),
    )
    _replace_embedded_source(
        primitives_cell,
        AI_VISIBILITY_RACE_START,
        AI_VISIBILITY_RACE_END,
        _without_service_imports(
            Path(ai_visibility_race_source).read_text(encoding="utf-8")
        ),
    )
    scope_text = Path(scope_source).read_text(encoding="utf-8")
    if scope_text.count(SCOPE_PACKAGE_IMPORT) != 1:
        raise ValueError("Expected one service-only primitives import")
    scope_text = scope_text.replace(SCOPE_PACKAGE_IMPORT, "", 1)
    scope_cell = _unique_cell(notebook, SCOPE_CELL_ID)
    _replace_embedded_source(
        scope_cell,
        AI_LOCALIZATION_START,
        AI_LOCALIZATION_END,
        _without_service_imports(
            Path(ai_localization_source).read_text(encoding="utf-8")
        ),
    )
    _replace_embedded_source(
        scope_cell,
        SCOPE_START,
        SCOPE_END,
        scope_text,
    )
    _replace_embedded_source(
        scope_cell,
        COMPETITOR_RESEARCH_START,
        COMPETITOR_RESEARCH_END,
        Path(competitor_research_source).read_text(encoding="utf-8"),
    )
    decisions_text = _without_service_imports(
        Path(competitor_decisions_source).read_text(encoding="utf-8")
    )
    _replace_embedded_source(
        scope_cell,
        COMPETITOR_DECISIONS_START,
        COMPETITOR_DECISIONS_END,
        decisions_text,
    )
    _replace_embedded_source(
        scope_cell,
        COMPETITOR_PIPELINE_START,
        COMPETITOR_PIPELINE_END,
        _without_service_imports(
            Path(competitor_pipeline_source).read_text(encoding="utf-8")
        ),
    )
    _replace_embedded_source(
        scope_cell,
        COMPETITOR_STAGE_START,
        COMPETITOR_STAGE_END,
        _without_service_imports(
            Path(competitor_stage_source).read_text(encoding="utf-8")
        ),
    )
    _replace_embedded_source(
        scope_cell,
        REPORT_CONTENT_START,
        REPORT_CONTENT_END,
        Path(report_content_source).read_text(encoding="utf-8"),
    )
    _replace_embedded_source(
        scope_cell,
        REPORT_STAGE_START,
        REPORT_STAGE_END,
        _without_service_imports(
            Path(report_stage_source).read_text(encoding="utf-8")
        ),
    )
    analysis_cell = _unique_cell(notebook, "final-analysis")
    _replace_embedded_source(
        analysis_cell,
        SEARCH_DISCOVERY_START,
        SEARCH_DISCOVERY_END,
        Path(search_discovery_source).read_text(encoding="utf-8"),
    )
    _replace_embedded_source(
        analysis_cell,
        PROFILE_RESEARCH_START,
        PROFILE_RESEARCH_END,
        Path(profile_research_source).read_text(encoding="utf-8")
        + "\n\n" + PROFILE_RESEARCH_ADAPTER_SOURCE,
    )
    orchestration_cell = _unique_cell(notebook, "final-orchestration")
    _replace_embedded_source(
        orchestration_cell,
        VISIBILITY_PROMPT_START,
        VISIBILITY_PROMPT_END,
        Path(visibility_prompt_source).read_text(encoding="utf-8"),
    )
    _replace_embedded_source(
        orchestration_cell,
        BRAND_MENTIONS_START,
        BRAND_MENTIONS_END,
        _without_service_imports(
            Path(brand_mentions_source).read_text(encoding="utf-8")
        ),
    )
    _replace_embedded_source(
        orchestration_cell,
        VISIBILITY_STAGE_START,
        VISIBILITY_STAGE_END,
        _without_service_imports(
            Path(visibility_stage_source).read_text(encoding="utf-8")
        ),
    )
    _replace_embedded_source(
        orchestration_cell,
        SERP_METRICS_START,
        SERP_METRICS_END,
        _without_service_imports(
            Path(serp_metrics_source).read_text(encoding="utf-8")
        ),
    )
    _replace_embedded_source(
        orchestration_cell,
        VISIBILITY_SOURCES_START,
        VISIBILITY_SOURCES_END,
        _without_service_imports(
            Path(visibility_sources_source).read_text(encoding="utf-8")
        ),
    )
    _replace_embedded_source(
        orchestration_cell,
        ARTIFACT_WRITES_START,
        ARTIFACT_WRITES_END,
        _without_service_imports(
            Path(artifact_writes_source).read_text(encoding="utf-8")
        ),
    )
    _replace_embedded_source(
        orchestration_cell,
        ARTIFACT_RESUME_START,
        ARTIFACT_RESUME_END,
        Path(artifact_resume_source).read_text(encoding="utf-8"),
    )
    _replace_embedded_source(
        orchestration_cell,
        COMPANY_STAGE_START,
        COMPANY_STAGE_END,
        Path(company_stage_source).read_text(encoding="utf-8"),
    )
    _replace_embedded_source(
        orchestration_cell,
        COMPANY_STAGE_CALL_START,
        COMPANY_STAGE_CALL_END,
        COMPANY_STAGE_CALL_SOURCE,
    )
    _replace_embedded_source(
        orchestration_cell,
        SEARCH_STAGE_START,
        SEARCH_STAGE_END,
        Path(search_stage_source).read_text(encoding="utf-8"),
    )
    _replace_embedded_source(
        orchestration_cell,
        SEARCH_STAGE_CALL_START,
        SEARCH_STAGE_CALL_END,
        SEARCH_STAGE_CALL_SOURCE,
    )
    _replace_embedded_source(
        orchestration_cell,
        COMPETITOR_SELECTION_STAGE_START,
        COMPETITOR_SELECTION_STAGE_END,
        Path(competitor_selection_stage_source).read_text(encoding="utf-8"),
    )
    _replace_embedded_source(
        orchestration_cell,
        COMPETITOR_SELECTION_STAGE_CALL_START,
        COMPETITOR_SELECTION_STAGE_CALL_END,
        COMPETITOR_SELECTION_STAGE_CALL_SOURCE,
    )
    _replace_embedded_source(
        orchestration_cell,
        PROFILE_STAGE_START,
        PROFILE_STAGE_END,
        Path(profile_stage_source).read_text(encoding="utf-8"),
    )
    _replace_embedded_source(
        orchestration_cell,
        PROFILE_STAGE_CALL_START,
        PROFILE_STAGE_CALL_END,
        PROFILE_STAGE_CALL_SOURCE,
    )
    _replace_embedded_source(
        orchestration_cell,
        VISIBILITY_CHECKPOINT_STAGE_START,
        VISIBILITY_CHECKPOINT_STAGE_END,
        Path(visibility_checkpoint_stage_source).read_text(encoding="utf-8"),
    )
    _replace_embedded_source(
        orchestration_cell,
        VISIBILITY_CHECKPOINT_STAGE_CALL_START,
        VISIBILITY_CHECKPOINT_STAGE_CALL_END,
        VISIBILITY_CHECKPOINT_STAGE_CALL_SOURCE,
    )
    _replace_embedded_source(
        orchestration_cell,
        SOCIAL_COMPLETION_STAGE_START,
        SOCIAL_COMPLETION_STAGE_END,
        Path(social_completion_stage_source).read_text(encoding="utf-8"),
    )
    _replace_embedded_source(
        orchestration_cell,
        SOCIAL_COMPLETION_STAGE_CALL_START,
        SOCIAL_COMPLETION_STAGE_CALL_END,
        SOCIAL_COMPLETION_STAGE_CALL_SOURCE,
    )
    _replace_embedded_source(
        orchestration_cell,
        REPORT_EXPORT_START,
        REPORT_EXPORT_END,
        Path(report_export_source).read_text(encoding="utf-8"),
    )
    reddit_cell = _unique_cell(notebook, REDDIT_CELL_ID)
    _replace_embedded_source(
        reddit_cell,
        REDDIT_START,
        REDDIT_END,
        Path(reddit_source).read_text(encoding="utf-8"),
    )
    research_cell = _unique_cell(notebook, RESEARCH_CELL_ID)
    research_cell["source"] = (
        RESEARCH_HEADER
        + RESEARCH_RACE_START + "\n"
        + Path(research_race_source).read_text(encoding="utf-8")
        + RESEARCH_RACE_END + "\n\n"
        + _without_service_imports(
            Path(research_source).read_text(encoding="utf-8")
        )
    ).splitlines(keepends=True)
    return (json.dumps(notebook, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
