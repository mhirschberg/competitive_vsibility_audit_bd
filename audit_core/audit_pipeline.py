"""Run the complete audit through importable stages and explicit ports.

The caller prepares canonical settings, output paths, provider clients, and
their stage ports. This module imports neither the notebook nor the web app.
"""

from dataclasses import dataclass
from pathlib import Path
import time

from .audit_finalize_stage import run_audit_finalize_stage_core
from .company_stage import run_company_stage_core
from .competitor_selection_stage import run_competitor_selection_stage_core
from .profile_stage import run_profile_stage_core
from .report_render_stage import run_report_render_stage_core
from .search_stage import run_search_stage_core
from .social_completion_stage import run_social_completion_stage_core
from .visibility_checkpoint_stage import run_visibility_checkpoint_stage_core


@dataclass(frozen=True)
class AuditRunContext:
    run_id: str
    run_timestamp: object
    export_prefix: str
    output_directory: Path
    raw_directory: Path
    site_resolution: dict
    continuing: bool = False
    audit_started_at: float | None = None


@dataclass
class AuditPipelinePorts:
    company_stage: object
    search_stage: object
    competitor_stage: object
    profile_stage: object
    visibility_stage: object
    social_stage: object
    report_stage: object
    finalize_stage_factory: object
    stage_banner: object
    price_per_1000: float = 1.5
    after_search: object = None


async def run_audit_pipeline(settings, context, *, ports):
    """Run one prepared audit and return its structured final record."""
    settings = dict(settings)
    context.output_directory.mkdir(parents=True, exist_ok=True)
    context.raw_directory.mkdir(parents=True, exist_ok=True)
    include_reddit = bool(settings.get("include_reddit_analysis", False))
    total_stages = 7 if include_reddit else 6
    audit_started_at = (
        context.audit_started_at
        if context.audit_started_at is not None else time.monotonic()
    )
    stage_durations = {}
    warnings = []

    ports.stage_banner(1, "Company analysis and buyer keywords", total_stages)
    company = await run_company_stage_core(
        settings, continuing=context.continuing,
        output_directory=context.output_directory,
        raw_directory=context.raw_directory,
        run_timestamp=context.run_timestamp,
        started_at=time.monotonic(), ports=ports.company_stage,
    )
    target_brand = company["target_brand"]
    keyword_records = company["keyword_records"]
    keywords = company["keywords"]
    stage_durations["company_analysis"] = company["duration_seconds"]

    ports.stage_banner(
        2,
        "Web Search and Google AI Mode measurement"
        if settings.get("include_google_ai_mode", True)
        else "Web Search competitor discovery",
        total_stages,
    )
    search = await run_search_stage_core(
        keywords, target_brand.domain, continuing=context.continuing,
        output_directory=context.output_directory,
        started_at=time.monotonic(), ports=ports.search_stage,
    )
    keyword_serp_results = search["keyword_results"]
    competitor_candidates = search["candidates"]
    if ports.after_search is not None:
        ports.after_search(search)
    stage_durations["serp_discovery"] = search["duration_seconds"]
    warnings.extend(search["warnings"])

    ports.stage_banner(3, "Direct competitor selection", total_stages)
    selection = await run_competitor_selection_stage_core(
        target_brand, competitor_candidates, keywords,
        locked_scope=company["locked_scope"],
        continuing=context.continuing,
        output_directory=context.output_directory,
        raw_directory=context.raw_directory,
        started_at=time.monotonic(),
        include_reddit_analysis=include_reddit,
        audit_focus=settings.get("audit_focus", ""),
        ports=ports.competitor_stage,
    )
    selected_competitors = selection["selected_competitors"]
    stage_durations["competitor_selection"] = selection["duration_seconds"]
    warnings.extend(selection["warnings"])

    ports.stage_banner(4, "Target and competitor profiles", total_stages)
    profiles = await run_profile_stage_core(
        target_brand, selected_competitors,
        audit_focus=settings.get("audit_focus", ""),
        company_domain=settings["company_domain"],
        company_url=settings["company_url"],
        output_directory=context.output_directory,
        started_at=time.monotonic(), ports=ports.profile_stage,
    )
    target_profile = profiles["target_profile"]
    competitor_profiles = profiles["competitor_profiles"]
    all_profiles = profiles["all_profiles"]
    stage_durations["brand_profiles"] = profiles["duration_seconds"]
    warnings.extend(profiles["warnings"])

    ports.stage_banner(5, "Cross-engine AI visibility", total_stages)
    visibility = await run_visibility_checkpoint_stage_core(
        target_profile, competitor_profiles, all_profiles, keywords,
        keyword_serp_results,
        include_copilot=bool(settings.get("include_copilot_visibility", False)),
        include_google_ai_mode=bool(settings.get("include_google_ai_mode", True)),
        include_chatgpt=bool(settings.get("include_chatgpt_visibility", True)),
        include_gemini=bool(settings.get("include_gemini_visibility", True)),
        wait_longer_for_chatgpt=bool(settings.get("wait_longer_for_chatgpt", False)),
        wait_longer_for_gemini=bool(settings.get("wait_longer_for_gemini", False)),
        wait_longer_for_copilot=bool(settings.get("wait_longer_for_copilot", False)),
        include_reddit_analysis=include_reddit,
        audit_focus=settings.get("audit_focus", ""),
        reddit_prefetch_task=selection["reddit_prefetch_task"],
        output_directory=context.output_directory,
        started_at=time.monotonic(), ports=ports.visibility_stage,
    )
    visibility_result = visibility["visibility_result"]
    stage_durations["ai_visibility"] = visibility["duration_seconds"]
    warnings.extend(visibility["warnings"])

    social = await run_social_completion_stage_core(
        visibility["reddit_task"], visibility["reddit_social_result"],
        include_reddit_analysis=include_reddit,
        total_stages=total_stages,
        output_directory=context.output_directory,
        ports=ports.social_stage,
    )
    reddit_social_result = social["reddit_social_result"]
    stage_durations["reddit_social"] = social["duration_seconds"]
    warnings.extend(social["warnings"])

    ports.stage_banner(
        7 if include_reddit else 6, "Final report and export", total_stages,
    )
    rendered = await run_report_render_stage_core(
        target_profile, competitor_profiles, keywords,
        keyword_serp_results, visibility_result, reddit_social_result,
        site_resolution=context.site_resolution,
        country=settings["country"],
        run_timestamp=context.run_timestamp,
        export_prefix=context.export_prefix,
        output_directory=context.output_directory,
        raw_directory=context.raw_directory,
        started_at=time.monotonic(),
        price_per_1000=ports.price_per_1000,
        ports=ports.report_stage,
    )
    stage_durations["final_report"] = rendered["duration_seconds"]
    warnings.extend(rendered["warnings"])

    return run_audit_finalize_stage_core(
        {
            "run_id": context.run_id,
            "run_timestamp": context.run_timestamp,
            "settings": settings,
            "include_reddit_analysis": include_reddit,
            "target_profile": target_profile,
            "competitor_profiles": competitor_profiles,
            "keyword_records": keyword_records,
            "keyword_serp_results": keyword_serp_results,
            "competitor_candidates": competitor_candidates,
            "selected_competitors": selected_competitors,
            "selection_result": selection["selection_result"],
            "visibility_result": visibility_result,
            "reddit_social_result": reddit_social_result,
            "bright_data_usage": rendered["bright_data_usage"],
            "report_result": rendered["report_result"],
            "final_report": rendered["final_report"],
            "final_sources": rendered["final_sources"],
            "warnings": warnings,
            "stage_durations": stage_durations,
        },
        audit_started_at=audit_started_at,
        site_resolution=context.site_resolution,
        output_directory=context.output_directory,
        export_prefix=context.export_prefix,
        markdown_path=rendered["markdown_path"],
        pdf_path=rendered["pdf_path"],
        ports=ports.finalize_stage_factory(),
    )
