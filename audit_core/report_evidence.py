"""Compact measured evidence for deterministic competitive audit reports."""

from collections import Counter

from .primitives import shorten


ENGINE_LABELS = (
    ("google_ai_mode", "Google AI Mode"),
    ("chatgpt", "ChatGPT"),
    ("gemini", "Gemini"),
    ("copilot", "Copilot"),
)


def _format_serp_metric(metric):
    appearances = metric["appearances"]
    total = metric["total_keywords"]
    if appearances == 0:
        return f"0/{total} SERPs"
    return (
        f"{appearances}/{total} SERPs, best #{metric['best_rank']}, "
        f"avg {metric['average_rank']}"
    )


def _format_engine_visibility(engine_name, result, mentions):
    status = result.get("status")
    if status != "success":
        if status == "partial":
            return (
                f"{engine_name}: partial; "
                f"answered={result.get('successful_questions', 0)}/"
                f"{result.get('question_count', 0)}; visibility not scored"
            )
        if status == "unavailable":
            return f"{engine_name}: unavailable; visibility not scored"
        return (
            f"{engine_name}: failed; "
            f"error={shorten(result.get('error'), 80)}"
        )

    ordered = [item["brand_name"] for item in mentions if item["mentioned"]]
    absent = [item["brand_name"] for item in mentions if not item["mentioned"]]
    target = next((item for item in mentions if item["role"] == "target"), None)
    target_coverage = (
        f"{target.get('answer_appearances', 0)}/"
        f"{target.get('answer_total', 0)}"
        if target else "0/0"
    )
    target_mentions = target.get("mention_count", 0) if target else 0
    return (
        f"{engine_name}: first_appearance_order="
        f"{' > '.join(ordered) or 'none'}; "
        f"target_answer_coverage={target_coverage}; "
        f"target_mentions={target_mentions}; "
        f"absent={', '.join(absent) or 'none'}; "
        f"citations={len(result.get('citations', []))}; "
        f"web_search={result.get('web_search_triggered')}."
    )


def build_report_evidence_core(
    target_profile,
    competitor_profiles,
    keywords,
    serp_metrics,
    visibility,
    *,
    search_engine,
    search_status,
    country,
    locked_scope,
    collect_sources,
):
    """Serialize measured inputs with the same bounded notebook evidence shape."""
    lines = [
        "TARGET:"
        f"{target_profile.brand_name}|{target_profile.domain}|"
        f"{shorten(target_profile.category, 60)}|"
        f"{shorten(target_profile.positioning, 130)}"
    ]
    target_metric = serp_metrics.get(target_profile.domain, {
        "appearances": 0, "total_keywords": len(keywords),
        "best_rank": None, "average_rank": None,
    })
    lines.append("TARGET_SERP:" + _format_serp_metric(target_metric))
    lines.append(
        "TARGET_STRENGTHS:"
        + shorten("; ".join(target_profile.differentiators[:4]), 180)
    )
    lines.append("KEYWORDS:" + ";".join(shorten(item, 44) for item in keywords))
    lines.append("COMPETITORS:")
    for profile in competitor_profiles:
        metric = serp_metrics.get(profile.domain, {
            "appearances": 0, "total_keywords": len(keywords),
            "best_rank": None, "average_rank": None,
        })
        lines.append(
            f"-{profile.brand_name}|{profile.domain}|"
            f"{_format_serp_metric(metric)}|"
            f"{shorten(profile.category, 40)}|"
            f"{shorten(profile.positioning, 65)}"
        )

    lines.append("AI_VISIBILITY:")
    for engine, display_name in ENGINE_LABELS:
        if engine in visibility.get("engines", {}):
            lines.append(_format_engine_visibility(
                display_name,
                visibility["engines"].get(engine, {}),
                visibility.get("mentions", {}).get(engine, []),
            ))

    sources = collect_sources(visibility, max_per_engine=10)
    source_type_counts = Counter(
        source.get("source_type", "Other source") for source in sources
    )
    if source_type_counts:
        source_mix = "; ".join(
            f"{source_type}={count}"
            for source_type, count in source_type_counts.most_common()
        )
        lines.append("SOURCE_MIX:" + shorten(source_mix, 240))

    evidence = "\n".join(lines)
    if len(evidence) > 2700:
        raise ValueError(
            f"Structured evidence is too long: {len(evidence)} characters."
        )

    scope = locked_scope or {}
    metadata = [
        f"SEARCH_ENGINE:{str(search_engine or '').title()}",
        f"SEARCH_STATUS:{search_status}",
        f"SEARCH_COUNTRY:{str(country or '').upper()}",
    ]
    if scope:
        metadata.append(
            "LOCKED_TARGET_SCOPE:"
            f"category={shorten(scope.get('category', ''), 90)}|"
            f"role={scope.get('market_role', '')}|"
            f"business_model={shorten(scope.get('business_model', ''), 100)}|"
            f"country={scope.get('country', '')}|"
            f"source={scope.get('category_source', '')}"
        )
    return "\n".join([*metadata, *evidence.splitlines()])
