"""Deterministic final report assembly and cost presentation.

No provider calls, PDF rendering, or audit file writes occur here.
"""

from collections import defaultdict


def build_source_appendix(
    sources,
):
    lines = [
        "",
        "",
        "## Observed AI Sources",
        "",
        "Sources returned by the measured AI visibility queries.",
        "",
    ]

    if not sources:
        lines.append(
            "No citation records were returned."
        )

        return "\n".join(lines)

    grouped = defaultdict(list)

    for source in sources:
        grouped[
            source["engine"]
        ].append(source)

    for engine in (
        "Google AI Mode",
        "ChatGPT",
        "Gemini",
        "Copilot",
    ):
        engine_sources = grouped.get(
            engine,
            [],
        )

        if not engine_sources:
            continue

        lines.append(
            f"### {engine}"
        )
        lines.append("")

        for index, source in enumerate(
            engine_sources,
            start=1,
        ):
            title = (
                source["title"]
                .replace("[", "")
                .replace("]", "")
            )

            lines.append(
                f"{index}. [{title}]"
                f"({source['canonical_url']})"
                f" — *{source['source_type']}*"
            )

        lines.append("")

    return "\n".join(lines)


def finalize_report_core(report, visibility, *, collect_sources, clean_boilerplate):
    """Add the source appendix once and retain the measured source records."""
    sources = collect_sources(visibility)
    appendix = build_source_appendix(sources)
    clean_report = clean_boilerplate(report)
    if "## Observed AI Sources" in clean_report:
        complete_report = clean_report
    else:
        complete_report = clean_report.rstrip() + appendix
    return {"report": complete_report, "sources": sources}


def build_bright_data_usage_section(usage):
    operations = int(usage.get("data_operations_started") or 0)
    accepted = int(usage.get("accepted_operations") or 0)
    confirmed = int(usage.get("confirmed_result_records") or 0)
    expected = int(usage.get("expected_fixed_cardinality_results") or 0)
    estimated = int(usage.get("estimated_billable_result_records") or 0)
    reddit_results = int(usage.get("reddit_raw_result_records") or 0)
    variable_pending = int(
        usage.get("variable_output_operations_pending") or 0
    )
    history_complete = bool(
        usage.get('checkpoint_history_complete', True)
    )
    failed = int(usage.get("failed_operations") or 0)
    rate = float(usage.get("price_per_1000_results_usd") or 0)
    cost = float(usage.get("estimated_cost_usd") or 0)
    qualifier = "At least " if variable_pending or not history_complete else ""
    cost_qualifier = "at least " if variable_pending or not history_complete else ""
    lines = [
        "",
        "",
        "## Bright Data Usage and Estimated Cost",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Data operations started | {operations} |",
        f"| Accepted operations, including race contenders | {accepted} |",
        f"| Confirmed raw result records returned | {confirmed} |",
        f"| Expected results from accepted one-result AI races | {expected} |",
        f"| Estimated billable result records | {qualifier}{estimated} |",
        f"| Reddit raw post/comment records before deduplication | {reddit_results} |",
        f"| Failed operations | {failed} |",
        f"| Variable-output operations pending at export | {variable_pending} |",
        f"| Rate used for estimate | ${rate:.2f} per 1,000 results |",
        f"| Estimated Bright Data cost | {cost_qualifier}${cost:.4f} |",
        "",
        (
            "Data operations are paid search, scrape, or dataset jobs initiated "
            "for this audit. Free status polling and snapshot downloads are excluded. "
            "Every accepted AI race contender is treated as a successful one-result "
            "operation, whether or not it won the race."
        ),
        "",
        (
            "Reddit billing uses raw records returned by every snapshot before the "
            "audit deduplicates posts or selects its final sample. The same post returned "
            "by multiple race contenders therefore counts multiple times."
        ),
    ]
    if not history_complete:
        lines.extend([
            '',
            'This audit was continued from a legacy checkpoint without '
            'a complete usage history. The estimate includes recovered '
            'snapshots but may omit earlier operations; it is a lower '
            'bound. The Bright Data billing dashboard is authoritative.',
        ])
    elif variable_pending:
        lines.extend(
            [
                "",
                (
                    "Some variable-output snapshots, such as Reddit discovery or comment "
                    "collection, had not exposed their final record count when the report "
                    "was exported. The result and cost figures are therefore lower bounds. "
                    "The Bright Data billing dashboard remains authoritative."
                ),
            ]
        )
    else:
        lines.extend(
            [
                "",
                "The Bright Data billing dashboard remains authoritative.",
            ]
        )
    return "\n".join(lines)


def clean_record_for_storage(
    record,
):
    """
    Remove unnecessarily large UI fields before writing records.
    """
    if not isinstance(record, dict):
        return record

    excluded_fields = {
        "answer_html",
        "additional_answer_html",
        "screenshot",
        "html",
    }

    return {
        key: value
        for key, value in record.items()
        if key not in excluded_fields
    }


def serialize_engine_result(result):
    """Drop heavyweight presentation fields from a measured engine result."""
    if not isinstance(result, dict):
        return result

    serialized = {
        key: value for key, value in result.items() if key != "record"
    }
    if isinstance(result.get("record"), dict):
        serialized["record"] = clean_record_for_storage(result["record"])
    return serialized


def serialize_profile_task(result, *, model_to_dict):
    """Return the stable, storage-safe representation of a profile task."""
    profile = result.get("profile")
    record = result.get("record")
    return {
        "status": result.get("status"),
        "job": result.get("job"),
        "profile": model_to_dict(profile) if profile is not None else None,
        "error": result.get("error"),
        "snapshot_id": result.get("snapshot_id"),
        "used_fallback": result.get("used_fallback", False),
        "record": (
            clean_record_for_storage(record)
            if isinstance(record, dict) else None
        ),
    }


def build_audit_record(
    *,
    run_id,
    run_timestamp,
    completed_at,
    total_duration,
    settings,
    include_reddit_analysis,
    target_profile,
    competitor_profiles,
    keyword_records,
    keyword_serp_results,
    competitor_candidates,
    selected_competitors,
    selection_result,
    visibility_result,
    reddit_social_result,
    bright_data_usage,
    report_result,
    final_report,
    final_sources,
    warnings,
    stage_durations,
    generator_name,
    model_to_dict,
    serialize_engine_result,
):
    """Assemble the structured audit record before artifact paths are added."""
    audit_data = {
            "run_id": run_id,
            "created_at": (
                run_timestamp.isoformat()
            ),
            "completed_at": (
                completed_at.isoformat()
            ),
            "configuration": {
                "company_name": settings[
                    "company_name"
                ],
                "company_url": settings[
                    "company_url"
                ],
                "company_domain": settings[
                    "company_domain"
                ],
                "country": settings[
                    "country"
                ],
                "audit_focus": settings.get(
                    "audit_focus",
                    "",
                ),
                "serp_zone": settings[
                    "serp_zone"
                ],
                "debug": settings.get(
                    "debug",
                    False,
                ),
                "include_reddit_analysis": (
                    include_reddit_analysis
                ),
            },
            "target": model_to_dict(
                target_profile
            ),
            "buyer_intent_keywords": [
                model_to_dict(item)
                for item in keyword_records
            ],
            "serp": {
                "keyword_results": (
                    keyword_serp_results
                ),
                "metrics": (
                    report_result[
                        "serp_metrics"
                    ]
                ),
                "competitor_candidates": [
                    model_to_dict(item)
                    for item in (
                        competitor_candidates
                    )
                ],
            },
            "competitor_selection": {
                "selected": [
                    model_to_dict(item)
                    for item in (
                        selected_competitors
                    )
                ],
                "rejected": (
                    selection_result.get(
                        "rejected",
                        [],
                    )
                ),
                "used_fallback": (
                    selection_result.get(
                        "used_fallback",
                        False,
                    )
                ),
            },
            "profiles": {
                "target": model_to_dict(
                    target_profile
                ),
                "competitors": [
                    model_to_dict(item)
                    for item in (
                        competitor_profiles
                    )
                ],
            },
            "ai_visibility": {
                "prompt": (
                    visibility_result["prompt"]
                ),
                "engines": {
                    engine: (
                        serialize_engine_result(
                            result
                        )
                    )
                    for engine, result in (
                        visibility_result[
                            "engines"
                        ].items()
                    )
                },
                "mentions": (
                    visibility_result[
                        "mentions"
                    ]
                ),
            },
            "reddit_social": reddit_social_result,
            "bright_data_usage": bright_data_usage,
            "final_report": {
                "generator": generator_name,
                "web_search": False,
                "snapshot_id": (
                    report_result[
                        "snapshot_id"
                    ]
                ),
                "evidence": (
                    report_result[
                        "evidence"
                    ]
                ),
                "prompt": (
                    report_result[
                        "prompt"
                    ]
                ),
                "markdown": final_report,
                "sources": final_sources,
            },
            "warnings": warnings,
            "durations": {
                **{
                    stage: round(
                        duration,
                        2,
                    )
                    for stage, duration in (
                        stage_durations.items()
                    )
                },
                "total_seconds": round(
                    total_duration,
                    2,
                ),
            },
            "files": {},
        }
    return audit_data
