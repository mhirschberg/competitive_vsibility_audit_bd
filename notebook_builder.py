"""Deterministically embed shared Python sources into the standalone notebook.

Only tagged cells are generated for now. Other notebook cells remain untouched
until their logic has been extracted into service modules.
"""

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
NOTEBOOK = ROOT / "competitive_visibility_audit_bd.ipynb"
REDDIT_SOURCE = ROOT / "reddit_social.py"
RESEARCH_SOURCE = ROOT / "research_fallback.py"
RESEARCH_RACE_SOURCE = ROOT / "audit_core" / "research_race.py"
RESEARCH_VALIDATION_SOURCE = ROOT / "audit_core" / "research_validation.py"
PRIMITIVES_SOURCE = ROOT / "audit_core" / "primitives.py"
DOMAINS_SOURCE = ROOT / "audit_core" / "domains.py"
SERP_METRICS_SOURCE = ROOT / "audit_core" / "serp_metrics.py"
BRAND_MENTIONS_SOURCE = ROOT / "audit_core" / "brand_mentions.py"
VISIBILITY_STAGE_SOURCE = ROOT / "audit_core" / "visibility_stage.py"
VISIBILITY_PROMPT_SOURCE = ROOT / "audit_core" / "visibility_prompt.py"
VISIBILITY_SOURCES_SOURCE = ROOT / "audit_core" / "visibility_sources.py"
ARTIFACT_WRITES_SOURCE = ROOT / "audit_core" / "artifact_writes.py"
ARTIFACT_RESUME_SOURCE = ROOT / "audit_core" / "artifact_resume.py"
AUDIT_PREPARATION_SOURCE = ROOT / "audit_core" / "audit_preparation.py"
COMPANY_STAGE_SOURCE = ROOT / "audit_core" / "company_stage.py"
COMPANY_ANALYSIS_SOURCE = ROOT / "audit_core" / "company_analysis.py"
SEARCH_DISCOVERY_SOURCE = ROOT / "audit_core" / "search_discovery.py"
SEARCH_STAGE_SOURCE = ROOT / "audit_core" / "search_stage.py"
COMPETITOR_SELECTION_STAGE_SOURCE = ROOT / "audit_core" / "competitor_selection_stage.py"
PROFILE_RESEARCH_SOURCE = ROOT / "audit_core" / "profile_research.py"
PROFILE_PROVIDER_SOURCE = ROOT / "audit_core" / "profile_provider.py"
PROFILE_STAGE_SOURCE = ROOT / "audit_core" / "profile_stage.py"
VISIBILITY_CHECKPOINT_STAGE_SOURCE = ROOT / "audit_core" / "visibility_checkpoint_stage.py"
SOCIAL_COMPLETION_STAGE_SOURCE = ROOT / "audit_core" / "social_completion_stage.py"
REPORT_RENDER_STAGE_SOURCE = ROOT / "audit_core" / "report_render_stage.py"
AUDIT_FINALIZE_STAGE_SOURCE = ROOT / "audit_core" / "audit_finalize_stage.py"
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
UTILITY_AI_RACE_SOURCE = ROOT / "audit_core" / "utility_ai_race.py"
COMPANY_MODELS_SOURCE = ROOT / "audit_core" / "company_models.py"
PRIMITIVES_CELL_ID = "final-core"
PRIMITIVES_START = "# AUDIT-PRIMITIVES: start"
PRIMITIVES_END = "# AUDIT-PRIMITIVES: end"
DOMAINS_START = "# AUDIT-DOMAINS: start"
DOMAINS_END = "# AUDIT-DOMAINS: end"
JSON_PARSING_START = "# AUDIT-JSON-PARSING: start"
JSON_PARSING_END = "# AUDIT-JSON-PARSING: end"
TEXT_CLEANING_START = "# AUDIT-TEXT-CLEANING: start"
TEXT_CLEANING_END = "# AUDIT-TEXT-CLEANING: end"
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
AUDIT_PREPARATION_START = "# AUDIT-PREPARATION: start"
AUDIT_PREPARATION_END = "# AUDIT-PREPARATION: end"
AUDIT_PREPARATION_CALL_START = "    # AUDIT-PREPARATION-CALL: start"
AUDIT_PREPARATION_CALL_END = "    # AUDIT-PREPARATION-CALL: end"
COMPANY_STAGE_START = "# AUDIT-COMPANY-STAGE: start"
COMPANY_STAGE_END = "# AUDIT-COMPANY-STAGE: end"
COMPANY_STAGE_CALL_START = "# AUDIT-COMPANY-STAGE-CALL: start"
COMPANY_STAGE_CALL_END = "    # AUDIT-COMPANY-STAGE-CALL: end"
COMPANY_ANALYSIS_PROVIDER_START = "# AUDIT-COMPANY-ANALYSIS-PROVIDER: start"
COMPANY_ANALYSIS_PROVIDER_END = "# AUDIT-COMPANY-ANALYSIS-PROVIDER: end"
COMPANY_MODELS_START = "# AUDIT-COMPANY-MODELS: start"
COMPANY_MODELS_END = "# AUDIT-COMPANY-MODELS: end"
COMPANY_INTAKE_ADAPTER_SOURCE = '''def normalize_company_intake(data, company_name, company_url):
    return normalize_company_intake_core(
        data, company_name, company_url, intake_model=CompanyIntake,
    )
'''
COMPANY_KEYWORD_COMPLETION_ADAPTER_SOURCE = '''def complete_company_keywords(
    settings, brand, current_keywords,
):
    return complete_company_keywords_core(
        settings,
        brand,
        current_keywords,
        run_utility=run_chatgpt_without_web,
        parse_json=parse_ai_json,
        model_to_dict=model_to_dict,
        keyword_model=BuyerIntentKeyword,
    )
'''
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
PROFILE_PROVIDER_START = "# AUDIT-PROFILE-PROVIDER: start"
PROFILE_PROVIDER_END = "# AUDIT-PROFILE-PROVIDER: end"
COMPETITOR_PROVIDER_START = "# AUDIT-COMPETITOR-PROVIDER: start"
COMPETITOR_PROVIDER_END = "# AUDIT-COMPETITOR-PROVIDER: end"
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
REPORT_RENDER_STAGE_START = "# AUDIT-REPORT-RENDER-STAGE: start"
REPORT_RENDER_STAGE_END = "# AUDIT-REPORT-RENDER-STAGE: end"
REPORT_RENDER_STAGE_CALL_START = "# AUDIT-REPORT-RENDER-STAGE-CALL: start"
REPORT_RENDER_STAGE_CALL_END = "    # AUDIT-REPORT-RENDER-STAGE-CALL: end"
AUDIT_FINALIZE_STAGE_START = "# AUDIT-FINALIZE-STAGE: start"
AUDIT_FINALIZE_STAGE_END = "# AUDIT-FINALIZE-STAGE: end"
AUDIT_FINALIZE_STAGE_CALL_START = "# AUDIT-FINALIZE-STAGE-CALL: start"
AUDIT_FINALIZE_STAGE_CALL_END = "    # AUDIT-FINALIZE-STAGE-CALL: end"
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
SCOPE_PACKAGE_IMPORTS = (
    "from .primitives import normalize_confidence\n",
    "from .domains import get_root_domain\n",
)
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
UTILITY_AI_RACE_START = "# AUDIT-UTILITY-AI-RACE: start"
UTILITY_AI_RACE_END = "# AUDIT-UTILITY-AI-RACE: end"
UTILITY_AI_RACE_ADAPTER_SOURCE = '''def race_utility_ai(
    prompt, validator=None, timeout_seconds=UTILITY_RACE_TIMEOUT_SECONDS,
    task_name="utility task",
):
    global LAST_UTILITY_AI_RESULT
    result = race_utility_ai_core(
        bd_client,
        prompt,
        validator=validator or validate_utility_json_answer,
        timeout_seconds=timeout_seconds,
        task_name=task_name,
        dataset_ids={
            "chatgpt": CHATGPT_DATASET_ID,
            "gemini": GEMINI_DATASET_ID,
        },
        failed_statuses=FAILED_STATUSES,
        error_type=BrightDataAPIError,
        poll_seconds=UTILITY_RACE_POLL_SECONDS,
    )
    LAST_UTILITY_AI_RESULT = result
    return result
'''
SERVICE_IMPORTS_START = "# SERVICE-ONLY-IMPORTS: start"
SERVICE_IMPORTS_END = "# SERVICE-ONLY-IMPORTS: end"
REDDIT_CELL_ID = "runtime-utilities-merged"
RESEARCH_CELL_ID = "research-provider-race"
RESEARCH_VALIDATION_START = "# RESEARCH-VALIDATION: start"
RESEARCH_VALIDATION_END = "# RESEARCH-VALIDATION: end"
RESEARCH_RACE_START = "# AUDIT-RESEARCH-RACE: start"
RESEARCH_RACE_END = "# AUDIT-RESEARCH-RACE: end"
REDDIT_START = "# REDDIT-SOCIAL-PATCH: start"
REDDIT_END = "# REDDIT-SOCIAL-PATCH: end"
RESEARCH_HEADER = (
    "#@title 3E. Load resilient research providers\n"
    "#@markdown Race ChatGPT and Gemini for internal research; "
    "keep Google AI Mode measured separately.\n\n"
)
AUDIT_PREPARATION_CALL_SOURCE = '''    def set_audit_output_directory(path):
        global CURRENT_AUDIT_OUTPUT_DIRECTORY
        CURRENT_AUDIT_OUTPUT_DIRECTORY = path

    prepared = await prepare_audit_run_core(
        settings,
        base_directory=Path('/content'),
        ports=AuditPreparationPorts(
            resolve_official_site=resolve_official_site,
            get_root_domain=get_root_domain,
            find_latest_audit_to_continue=find_latest_audit_to_continue,
            slugify=slugify,
            audit_export_prefix=audit_export_prefix,
            configure_usage_checkpoint=bd_client.configure_usage_checkpoint,
            write_json=write_json,
            configure_google_ai_race_cache=configure_google_ai_race_cache,
            import_google_ai_snapshot_ids=import_google_ai_snapshot_ids,
            notice=console.print,
            set_output_directory=set_audit_output_directory,
        ),
    )
    settings = prepared['settings']
    site_resolution = prepared['site_resolution']
    continuing = prepared['continuing']
    run_timestamp = prepared['run_timestamp']
    run_id = prepared['run_id']
    output_directory = prepared['output_directory']
    raw_directory = prepared['raw_directory']
    export_prefix = prepared['export_prefix']
    audit_started_at = prepared['audit_started_at']
    include_reddit_analysis = bool(settings.get('include_reddit_analysis', False))
    include_copilot_visibility = bool(settings.get('include_copilot_visibility', False))
    include_google_ai_mode = bool(settings.get('include_google_ai_mode', True))
    include_chatgpt_visibility = bool(settings.get('include_chatgpt_visibility', True))
    include_gemini_visibility = bool(settings.get('include_gemini_visibility', True))
    total_stages = 7 if include_reddit_analysis else 6
'''
COMPANY_STAGE_CALL_SOURCE = '''    def set_company_locked_scope(scope):
        global LOCKED_TARGET_SCOPE
        LOCKED_TARGET_SCOPE = scope

    def run_company_analysis(settings):
        return run_company_analysis_core(
            settings,
            ports=CompanyAnalysisPorts(
                client=bd_client,
                run_utility=run_chatgpt_without_web,
                parse_json=parse_ai_json,
                normalize_intake=normalize_company_intake,
                select_relevant_research=select_relevant_company_research,
                complete_keywords=complete_company_keywords,
                proofread_keywords=proofread_buyer_keywords,
                build_locked_scope=build_locked_target_scope,
                error_type=BrightDataAPIError,
            ),
        )

    company_stage = await run_company_stage_core(
        settings,
        continuing=continuing,
        output_directory=output_directory,
        raw_directory=raw_directory,
        run_timestamp=run_timestamp,
        started_at=stage_started_at,
        ports=CompanyStagePorts(
            analyze=run_company_analysis,
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
AI_MODE_QUESTION_ADAPTER_SOURCE = '''async def run_ai_mode_question(
    question, question_index, timeout_seconds=720, max_attempts=None,
):
    """Notebook adapter for the shared measured Google AI Mode runner."""
    return await run_google_ai_mode_question_core(
        question,
        question_index,
        client=bd_client,
        country_code=AUDIT_SETTINGS.get("country"),
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        is_google_goto_url=is_google_goto_url,
        resolve_google_goto_url=resolve_google_goto_url,
        get_root_domain=get_root_domain,
        country_details_fn=get_ai_country_details,
        market_language_fn=get_market_language,
        acknowledge_market_fn=answer_acknowledges_target_market,
        timeout_error_type=SnapshotTimeoutError,
    )
'''
COMPETITOR_SELECTION_STAGE_CALL_SOURCE = '''    competitor_stage = await run_competitor_selection_stage_core(
        target_brand, competitor_candidates, keywords,
        locked_scope=company_stage["locked_scope"],
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
    selection_result = competitor_stage["selection_result"]
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
PROFILE_PROVIDER_ADAPTER_SOURCE = '''def build_profile_prompt(job, target_brand, audit_focus=""):
    return build_profile_prompt_core(job, target_brand, audit_focus)


def clean_profile_label(value):
    return clean_profile_label_core(value)


def normalize_brand_profile(data, job):
    return normalize_brand_profile_core(
        data,
        job,
        profile_factory=BrandProfile,
        normalize_public_url=normalize_public_url,
        get_root_domain=get_root_domain,
        ensure_string_list=ensure_string_list,
        normalize_confidence=normalize_confidence,
    )


def generate_profile_sync(job, target_brand, audit_focus=""):
    return generate_profile_sync_core(
        job,
        target_brand,
        audit_focus,
        client=bd_client,
        parse_ai_json=parse_ai_json,
        normalize_profile=normalize_brand_profile,
        snapshot_timeout_error=SnapshotTimeoutError,
    )


def recover_profile_sync(task_result):
    return recover_profile_sync_core(
        task_result,
        client=bd_client,
        parse_ai_json=parse_ai_json,
        normalize_profile=normalize_brand_profile,
        provider_error=BrightDataAPIError,
    )


def fallback_profile(job, target_brand):
    return fallback_profile_core(
        job, target_brand, profile_factory=BrandProfile,
    )'''
COMPETITOR_PROVIDER_ADAPTER_SOURCE = '''def select_competitors_stage(
    target_brand, candidates, keywords, locked_scope=None,
):
    return select_competitors_with_provider(
        target_brand,
        candidates,
        keywords,
        scope=locked_scope or require_locked_target_scope(target_brand),
        client=bd_client,
        parse_ai_json=parse_ai_json,
        decision_ports=_competitor_decision_ports(),
        local_domain_bonus=locked_scope_local_domain_bonus,
        validation_workers=LOCKED_SCOPE_VALIDATION_WORKERS,
        validation_limit=LOCKED_SCOPE_VALIDATION_LIMIT,
        only_reuse=_GOOGLE_AI_ONLY_REUSE,
        cached_snapshot_ids=cached_research_snapshot_ids,
        brand_family=locked_scope_brand_family,
        selected_factory=SelectedCompetitor,
        error_type=BrightDataAPIError,
        output_dir=globals().get("CURRENT_AUDIT_OUTPUT_DIRECTORY"),
        write_json=write_json,
        clean_record=clean_record_for_storage,
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
REPORT_RENDER_STAGE_CALL_SOURCE = '''    rendered_report = await run_report_render_stage_core(
        target_profile, competitor_profiles, keywords, keyword_serp_results,
        visibility_result, reddit_social_result,
        locked_scope=company_stage["locked_scope"],
        site_resolution=site_resolution,
        country=settings["country"],
        run_timestamp=run_timestamp,
        export_prefix=export_prefix,
        output_directory=output_directory,
        raw_directory=raw_directory,
        started_at=stage_started_at,
        price_per_1000=BRIGHT_DATA_PRICE_PER_1000_RESULTS_USD,
        ports=ReportRenderPorts(
            generate_report=lambda *args: generate_report_stage(*args[:5]),
            finalize_report=finalize_report,
            insert_reddit_section=insert_reddit_report_section,
            refresh_usage=bd_client.refresh_usage_results,
            usage_summary=bd_client.usage_summary,
            build_usage_section=build_bright_data_usage_section,
            write_json=write_json,
            write_text=write_text,
            report_filename=report_filename,
            create_pdf=create_styled_pdf_report,
            clean_record=clean_record_for_storage,
            stage_success=print_stage_success,
            stage_warning=print_stage_warning,
            format_duration=format_duration,
        ),
    )
    report_result = rendered_report["report_result"]
    final_report = rendered_report["final_report"]
    final_sources = rendered_report["final_sources"]
    bright_data_usage = rendered_report["bright_data_usage"]
    report_markdown_path = rendered_report["markdown_path"]
    report_pdf_path = rendered_report["pdf_path"]
    stage_durations["final_report"] = rendered_report["duration_seconds"]
    warnings.extend(rendered_report["warnings"])'''
AUDIT_FINALIZE_STAGE_CALL_SOURCE = '''    audit_data = run_audit_finalize_stage_core(
        {
            "run_id": run_id,
            "run_timestamp": run_timestamp,
            "settings": settings,
            "include_reddit_analysis": include_reddit_analysis,
            "target_profile": target_profile,
            "competitor_profiles": competitor_profiles,
            "keyword_records": keyword_records,
            "keyword_serp_results": keyword_serp_results,
            "competitor_candidates": competitor_candidates,
            "selected_competitors": selected_competitors,
            "selection_result": selection_result,
            "visibility_result": visibility_result,
            "reddit_social_result": reddit_social_result,
            "bright_data_usage": bright_data_usage,
            "report_result": report_result,
            "final_report": final_report,
            "final_sources": final_sources,
            "warnings": warnings,
            "stage_durations": stage_durations,
        },
        audit_started_at=audit_started_at,
        site_resolution=site_resolution,
        output_directory=output_directory,
        export_prefix=export_prefix,
        markdown_path=report_markdown_path,
        pdf_path=report_pdf_path,
        ports=AuditFinalizePorts(
            build_record=build_audit_record,
            model_to_dict=model_to_dict,
            serialize_engine_result=serialize_engine_result,
            generator_name=globals().get(
                "LAST_UTILITY_REPORT_RESULT", {}
            ).get("engine_name", "Unknown"),
            report_filename=report_filename,
            write_json=write_json,
            create_zip=create_audit_zip,
            stage_success=print_stage_success,
            completion_notice=lambda message: console.print(
                f"\\n[bold green]{message}[/bold green]"
            ),
            format_duration=format_duration,
        ),
    )'''


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


def _replace_python_function_before_marker(cell, name, marker, replacement):
    """Replace the legacy function that precedes a generated source marker."""
    source = "".join(cell["source"])
    marker_line = source[:source.index(marker)].count("\n") + 1
    tree = ast.parse(source)
    candidates = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name and node.lineno < marker_line
    ]
    if len(candidates) != 1:
        raise ValueError(
            f"Expected one legacy {name} definition before {marker!r}"
        )
    node = candidates[0]
    start_line = min(
        [node.lineno] + [item.lineno for item in node.decorator_list]
    )
    lines = source.splitlines(keepends=True)
    lines[start_line - 1:node.end_lineno] = [
        replacement.rstrip("\n") + "\n"
    ]
    cell["source"] = lines


def _replace_python_function_occurrence(cell, name, occurrence, replacement):
    """Replace one zero-based top-level definition of a function."""
    source = "".join(cell["source"])
    tree = ast.parse(source)
    matches = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if occurrence >= len(matches):
        raise ValueError(
            f"Could not find occurrence {occurrence} of function {name!r}"
        )
    node = matches[occurrence]
    start_line = min(
        [node.lineno] + [item.lineno for item in node.decorator_list]
    )
    lines = source.splitlines(keepends=True)
    lines[start_line - 1:node.end_lineno] = [replacement.rstrip("\n") + "\n"]
    cell["source"] = lines


def _replace_python_classes_with_source(cell, names, start, end, source):
    """Replace legacy top-level classes with one tagged shared source region."""
    text = "".join(cell["source"])
    if start in text or end in text:
        _replace_embedded_source(cell, start, end, source)
        return

    tree = ast.parse(text)
    classes = [
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in set(names)
    ]
    found = {node.name for node in classes}
    if found != set(names):
        raise ValueError(
            f"Expected model classes {sorted(names)!r}, found {sorted(found)!r}"
        )

    lines = text.splitlines(keepends=True)
    first_line = min(node.lineno for node in classes)
    removed = {
        line_index
        for node in classes
        for line_index in range(node.lineno - 1, node.end_lineno)
    }
    output = []
    for index, line in enumerate(lines):
        if index == first_line - 1:
            output.extend([start + "\n", source.rstrip("\n") + "\n", end + "\n"])
        if index not in removed:
            output.append(line)
    cell["source"] = output


def _replace_last_python_function(cell, name, replacement):
    """Replace the final notebook definition of a function with an adapter."""
    source = "".join(cell["source"])
    tree = ast.parse(source)
    matches = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if not matches:
        raise ValueError(f"Could not find notebook function {name!r}")
    node = matches[-1]
    start_line = min(
        [node.lineno] + [item.lineno for item in node.decorator_list]
    )
    lines = source.splitlines(keepends=True)
    lines[start_line - 1:node.end_lineno] = [replacement.rstrip("\n") + "\n"]
    cell["source"] = lines


def _remove_python_function_occurrences(cell, removals, *, before_marker=None):
    """Remove selected zero-based definitions, optionally before a marker."""
    source = "".join(cell["source"])
    tree = ast.parse(source)
    marker_line = (
        source[:source.index(before_marker)].count("\n") + 1
        if before_marker else None
    )
    definitions = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if marker_line and node.lineno >= marker_line:
                continue
            definitions.setdefault(node.name, []).append(node)
    removed_lines = set()
    for name, indexes in removals.items():
        matches = definitions.get(name, [])
        for index in indexes:
            if index >= len(matches):
                continue
            node = matches[index]
            start_line = min(
                [node.lineno] + [item.lineno for item in node.decorator_list]
            )
            removed_lines.update(range(start_line - 1, node.end_lineno))
    lines = source.splitlines(keepends=True)
    cell["source"] = [
        line for index, line in enumerate(lines) if index not in removed_lines
    ]


def _remove_shadowed_python_functions(cell, names):
    """Keep the last definition of each named function in a generated cell."""
    source = "".join(cell["source"])
    tree = ast.parse(source)
    definitions = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            definitions.setdefault(node.name, []).append(node)

    removed_lines = set()
    for name in names:
        matches = definitions.get(name, [])
        for node in matches[:-1]:
            start_line = min(
                [node.lineno] + [item.lineno for item in node.decorator_list]
            )
            removed_lines.update(range(start_line - 1, node.end_lineno))

    lines = source.splitlines(keepends=True)
    cell["source"] = [
        line for index, line in enumerate(lines) if index not in removed_lines
    ]


def _replace_json_parsing_source(cell, source):
    text = "".join(cell["source"])
    if JSON_PARSING_START in text or JSON_PARSING_END in text:
        _replace_embedded_source(
            cell, JSON_PARSING_START, JSON_PARSING_END, source,
        )
        return

    wrapped = (
        JSON_PARSING_START + "\n" + source.rstrip("\n")
        + "\n" + JSON_PARSING_END
    )
    _replace_last_python_function(cell, "parse_ai_json", wrapped)


def _replace_text_cleaning_source(cell, source):
    text = "".join(cell["source"])
    if TEXT_CLEANING_START in text or TEXT_CLEANING_END in text:
        _replace_embedded_source(
            cell, TEXT_CLEANING_START, TEXT_CLEANING_END, source,
        )
        return

    wrapped = (
        TEXT_CLEANING_START + "\n" + source.rstrip("\n")
        + "\n" + TEXT_CLEANING_END
    )
    _replace_last_python_function(cell, "remove_ai_boilerplate", wrapped)


def _replace_source_region(cell, start, end, source):
    text = "".join(cell["source"])
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"Expected exactly one {start!r}/{end!r} region")
    begin = text.index(start)
    finish = text.index(end)
    if finish < begin:
        raise ValueError("Generated source region markers are out of order")
    cell["source"] = (
        text[:begin] + source.rstrip("\n") + "\n\n" + text[finish:]
    ).splitlines(keepends=True)


def _replace_profile_provider_source(cell, source):
    wrapped = (
        PROFILE_PROVIDER_START + "\n" + source.rstrip("\n")
        + "\n" + PROFILE_PROVIDER_END
    )
    text = "".join(cell["source"])
    if PROFILE_PROVIDER_START in text or PROFILE_PROVIDER_END in text:
        _replace_embedded_source(
            cell, PROFILE_PROVIDER_START, PROFILE_PROVIDER_END, source,
        )
        return

    legacy_start = "def build_profile_prompt(\n"
    generated_start = "def build_profile_prompt_core("
    start = legacy_start if legacy_start in text else generated_start
    _replace_source_region(cell, start, PROFILE_RESEARCH_START, wrapped)


def _replace_competitor_provider_source(cell, source):
    wrapped = (
        COMPETITOR_PROVIDER_START + "\n" + source.rstrip("\n")
        + "\n" + COMPETITOR_PROVIDER_END
    )
    text = "".join(cell["source"])
    if COMPETITOR_PROVIDER_START in text or COMPETITOR_PROVIDER_END in text:
        _replace_embedded_source(
            cell, COMPETITOR_PROVIDER_START, COMPETITOR_PROVIDER_END, source,
        )
        return

    legacy_start = "def select_competitors_stage(target_brand, candidates, keywords):"
    if legacy_start not in text:
        raise ValueError("Could not find legacy competitor provider adapter")
    _replace_source_region(
        cell, legacy_start, "# Add locked scope to report evidence", wrapped,
    )


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
                   research_validation_source=RESEARCH_VALIDATION_SOURCE,
                   primitives_source=PRIMITIVES_SOURCE,
                   domains_source=DOMAINS_SOURCE,
                   serp_metrics_source=SERP_METRICS_SOURCE,
                   brand_mentions_source=BRAND_MENTIONS_SOURCE,
                   visibility_stage_source=VISIBILITY_STAGE_SOURCE,
                   visibility_prompt_source=VISIBILITY_PROMPT_SOURCE,
                   visibility_sources_source=VISIBILITY_SOURCES_SOURCE,
                   artifact_writes_source=ARTIFACT_WRITES_SOURCE,
                   artifact_resume_source=ARTIFACT_RESUME_SOURCE,
                   audit_preparation_source=AUDIT_PREPARATION_SOURCE,
                   company_stage_source=COMPANY_STAGE_SOURCE,
                   company_analysis_source=COMPANY_ANALYSIS_SOURCE,
                   search_discovery_source=SEARCH_DISCOVERY_SOURCE,
                   search_stage_source=SEARCH_STAGE_SOURCE,
                   competitor_selection_stage_source=COMPETITOR_SELECTION_STAGE_SOURCE,
                   profile_research_source=PROFILE_RESEARCH_SOURCE,
                   profile_provider_source=PROFILE_PROVIDER_SOURCE,
                   profile_stage_source=PROFILE_STAGE_SOURCE,
                   visibility_checkpoint_stage_source=VISIBILITY_CHECKPOINT_STAGE_SOURCE,
                   social_completion_stage_source=SOCIAL_COMPLETION_STAGE_SOURCE,
                   report_render_stage_source=REPORT_RENDER_STAGE_SOURCE,
                   audit_finalize_stage_source=AUDIT_FINALIZE_STAGE_SOURCE,
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
                   artifact_names_source=ARTIFACT_NAMES_SOURCE,
                   utility_ai_race_source=UTILITY_AI_RACE_SOURCE,
                   json_parsing_source=ROOT / "audit_core" / "json_parsing.py",
                   text_cleaning_source=ROOT / "audit_core" / "text_cleaning.py"):
    """Return notebook bytes with generated cells synchronized to sources."""
    notebook = json.loads(Path(notebook_path).read_text(encoding="utf-8"))
    primitives_cell = _unique_cell(notebook, PRIMITIVES_CELL_ID)
    _replace_python_classes_with_source(
        primitives_cell,
        {"BuyerIntentKeyword", "BrandAnalysis", "CompanyIntake"},
        COMPANY_MODELS_START,
        COMPANY_MODELS_END,
        Path(COMPANY_MODELS_SOURCE).read_text(encoding="utf-8"),
    )
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
    _replace_json_parsing_source(
        primitives_cell,
        Path(json_parsing_source).read_text(encoding="utf-8"),
    )
    _replace_text_cleaning_source(
        primitives_cell,
        Path(text_cleaning_source).read_text(encoding="utf-8"),
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
    for import_line in SCOPE_PACKAGE_IMPORTS:
        if scope_text.count(import_line) != 1:
            raise ValueError(f"Expected one service-only import: {import_line.strip()}")
        scope_text = scope_text.replace(import_line, "", 1)
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
    _replace_competitor_provider_source(
        scope_cell, COMPETITOR_PROVIDER_ADAPTER_SOURCE,
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
    _replace_profile_provider_source(
        analysis_cell,
        Path(profile_provider_source).read_text(encoding="utf-8")
        + "\n\n" + PROFILE_PROVIDER_ADAPTER_SOURCE,
    )
    _replace_python_function_occurrence(
        analysis_cell,
        "normalize_company_intake",
        0,
        COMPANY_INTAKE_ADAPTER_SOURCE,
    )
    _replace_python_function_occurrence(
        analysis_cell,
        "complete_company_keywords",
        0,
        COMPANY_KEYWORD_COMPLETION_ADAPTER_SOURCE,
    )
    _replace_embedded_source(
        analysis_cell,
        SEARCH_DISCOVERY_START,
        SEARCH_DISCOVERY_END,
        _without_service_imports(
            Path(search_discovery_source).read_text(encoding="utf-8")
        ),
    )
    _replace_last_python_function(
        analysis_cell, "run_ai_mode_question", AI_MODE_QUESTION_ADAPTER_SOURCE,
    )
    _replace_last_python_function(
        _unique_cell(notebook, "runtime-utilities-merged"),
        "run_ai_mode_question",
        AI_MODE_QUESTION_ADAPTER_SOURCE,
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
        AUDIT_PREPARATION_START,
        AUDIT_PREPARATION_END,
        Path(audit_preparation_source).read_text(encoding="utf-8"),
    )
    _replace_embedded_source(
        orchestration_cell,
        AUDIT_PREPARATION_CALL_START,
        AUDIT_PREPARATION_CALL_END,
        AUDIT_PREPARATION_CALL_SOURCE,
    )
    _replace_embedded_source(
        orchestration_cell,
        COMPANY_STAGE_START,
        COMPANY_STAGE_END,
        Path(company_stage_source).read_text(encoding="utf-8").rstrip()
        + "\n\n"
        + COMPANY_ANALYSIS_PROVIDER_START + "\n"
        + _without_service_imports(
            Path(company_analysis_source).read_text(encoding="utf-8")
        )
        + "\n" + COMPANY_ANALYSIS_PROVIDER_END,
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
        REPORT_RENDER_STAGE_START,
        REPORT_RENDER_STAGE_END,
        Path(report_render_stage_source).read_text(encoding="utf-8"),
    )
    _replace_embedded_source(
        orchestration_cell,
        REPORT_RENDER_STAGE_CALL_START,
        REPORT_RENDER_STAGE_CALL_END,
        REPORT_RENDER_STAGE_CALL_SOURCE,
    )
    _replace_embedded_source(
        orchestration_cell,
        AUDIT_FINALIZE_STAGE_START,
        AUDIT_FINALIZE_STAGE_END,
        Path(audit_finalize_stage_source).read_text(encoding="utf-8"),
    )
    _replace_embedded_source(
        orchestration_cell,
        AUDIT_FINALIZE_STAGE_CALL_START,
        AUDIT_FINALIZE_STAGE_CALL_END,
        AUDIT_FINALIZE_STAGE_CALL_SOURCE,
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
        _without_service_imports(
            Path(reddit_source).read_text(encoding="utf-8")
        ),
    )
    utility_cell = _unique_cell(notebook, SCOPE_CELL_ID)
    utility_text = "".join(utility_cell["source"])
    if UTILITY_AI_RACE_START not in utility_text and UTILITY_AI_RACE_END not in utility_text:
        utility_cell["source"] = (
            utility_text.rstrip("\n") + "\n\n"
            + UTILITY_AI_RACE_START + "\n"
            + UTILITY_AI_RACE_END + "\n"
        ).splitlines(keepends=True)
    _replace_embedded_source(
        utility_cell,
        UTILITY_AI_RACE_START,
        UTILITY_AI_RACE_END,
        Path(utility_ai_race_source).read_text(encoding="utf-8"),
    )
    _replace_python_function_before_marker(
        utility_cell,
        "race_utility_ai",
        UTILITY_AI_RACE_START,
        UTILITY_AI_RACE_ADAPTER_SOURCE,
    )
    research_cell = _unique_cell(notebook, RESEARCH_CELL_ID)
    research_cell["source"] = (
        RESEARCH_HEADER
        + RESEARCH_VALIDATION_START + "\n"
        + RESEARCH_VALIDATION_END + "\n\n"
        + RESEARCH_RACE_START + "\n"
        + Path(research_race_source).read_text(encoding="utf-8")
        + RESEARCH_RACE_END + "\n\n"
        + _without_service_imports(
            Path(research_source).read_text(encoding="utf-8")
        )
    ).splitlines(keepends=True)
    _replace_embedded_source(
        research_cell,
        RESEARCH_VALIDATION_START,
        RESEARCH_VALIDATION_END,
        _without_service_imports(
            Path(research_validation_source).read_text(encoding="utf-8")
        ),
    )
    _remove_python_function_occurrences(
        primitives_cell,
        {
            "is_non_competitor_domain": [0],
            "looks_like_irrelevant_result": [0],
            "preferred_homepage_url": [0],
            "aggregate_competitor_domains": [0],
        },
    )
    _remove_python_function_occurrences(
        primitives_cell,
        {"is_google_goto_url": [1]},
    )
    primitive_tree = ast.parse("".join(primitives_cell["source"]))
    if sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "model_to_dict"
        for node in primitive_tree.body
    ) > 1:
        _remove_python_function_occurrences(
            primitives_cell,
            {"model_to_dict": [0]},
        )
    _remove_shadowed_python_functions(
        primitives_cell,
        {
            "extract_visible_url", "normalize_public_url", "get_hostname",
            "is_google_goto_url",
            "clean_ai_json_text", "parse_ai_json",
            "remove_ai_boilerplate",
        },
    )
    _remove_python_function_occurrences(
        analysis_cell,
        {
            "normalize_keyword_records": [0],
            "normalize_citation": [0],
            "select_relevant_company_research": [0],
            "build_ai_mode_source_candidates": [0],
            "merge_discovery_candidates": [0],
            "run_serp_stage": [0],
        },
        before_marker=SEARCH_DISCOVERY_START,
    )
    _remove_python_function_occurrences(
        scope_cell,
        {
            "locked_scope_brand_family": [1],
            "locked_scope_local_domain_bonus": [1],
        },
    )
    _remove_python_function_occurrences(
        orchestration_cell,
        {
            "serialize_engine_result": [1],
            "serialize_profile_task": [1],
            "format_duration": [0],
        },
    )
    return (json.dumps(notebook, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
