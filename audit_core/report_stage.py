"""Provider-free report stage shared by service and generated notebook."""

from datetime import datetime, timezone

# SERVICE-ONLY-IMPORTS: start
from .report_content import DETERMINISTIC_REPORT_GENERATOR, build_report_content
# SERVICE-ONLY-IMPORTS: end


def generate_report_stage_core(
    target_profile,
    competitor_profiles,
    keywords,
    keyword_serp_results,
    visibility,
    *,
    country,
    search_engine,
    search_status,
    calculate_serp_metrics,
    collect_sources,
    build_evidence,
    now_utc=None,
):
    """Create Markdown and metadata from measured data without AI calls."""
    all_profiles = [target_profile, *competitor_profiles]
    serp_metrics = calculate_serp_metrics(
        profiles=all_profiles,
        keyword_serp_results=keyword_serp_results,
    )
    report = build_report_content(
        target_profile,
        competitor_profiles,
        keywords,
        keyword_serp_results,
        serp_metrics,
        visibility,
        country=country,
        search_engine=search_engine,
        search_status=search_status,
        collect_sources=collect_sources,
    )
    try:
        evidence = build_evidence(
            target_profile=target_profile,
            competitor_profiles=competitor_profiles,
            keywords=keywords,
            serp_metrics=serp_metrics,
            visibility=visibility,
        )
    except Exception as exc:
        evidence = (
            "Deterministic report generated directly from structured audit data. "
            "Compact evidence serialization was unavailable: "
            f"{type(exc).__name__}: {exc}"
        )

    generated_at = (now_utc or datetime.now(timezone.utc)).isoformat()
    record = {
        "generator": DETERMINISTIC_REPORT_GENERATOR,
        "generated_at": generated_at,
        "ai_generation": False,
        "web_search": False,
        "report_length": len(report),
    }
    return {
        "report": report,
        "record": record,
        "snapshot_id": None,
        "prompt": "Deterministic Markdown template; no AI report-generation prompt.",
        "evidence": evidence,
        "serp_metrics": serp_metrics,
        "generator": DETERMINISTIC_REPORT_GENERATOR,
    }
