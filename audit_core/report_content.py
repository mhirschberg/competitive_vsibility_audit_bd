"""Pure deterministic Markdown report content shared by service and notebook.

Provider requests, metrics calculation, PDF rendering, and persistence live
outside this module. Country and search availability are explicit inputs.
"""

import re

from collections import (
    Counter as DeterministicCounter,
)


DETERMINISTIC_REPORT_GENERATOR = (
    "Deterministic template"
)


DETERMINISTIC_ENGINE_NAMES = {
    "google_ai_mode": (
        "Google AI Mode"
    ),
    "chatgpt": "ChatGPT",
    "gemini": "Gemini",
    "copilot": "Copilot",
}


def deterministic_text(
    value,
):
    text = re.sub(
        r"\s+",
        " ",
        str(value or "").strip(),
    )

    return re.sub(
        r"\[([^\]]+)\]\([^)]*\)",
        r"\1",
        text,
    )


def deterministic_markdown_text(
    value,
):
    return (
        deterministic_text(value)
        .replace("|", "\\|")
    )


def deterministic_number(
    value,
):
    if value is None:
        return "—"

    if isinstance(value, float):
        if value.is_integer():
            return str(
                int(value)
            )

        return (
            f"{value:.2f}"
            .rstrip("0")
            .rstrip(".")
        )

    return str(value)


def deterministic_rank(
    value,
):
    if value is None:
        return "—"

    return (
        "#"
        + deterministic_number(
            value
        )
    )


def deterministic_metric_for_profile(
    profile,
    serp_metrics,
    total_keywords,
):
    metric = serp_metrics.get(
        profile.domain,
        {},
    )

    return {
        "appearances": int(
            metric.get(
                "appearances",
                0,
            )
            or 0
        ),
        "total_keywords": int(
            metric.get(
                "total_keywords",
                total_keywords,
            )
            or total_keywords
        ),
        "best_rank": metric.get(
            "best_rank"
        ),
        "average_rank": metric.get(
            "average_rank"
        ),
        "coverage": metric.get(
            "coverage",
            0,
        ),
        "details": metric.get(
            "details",
            [],
        ),
    }


def deterministic_profile_summary(
    profile,
):
    category = deterministic_text(
        profile.category
    )

    positioning = deterministic_text(
        profile.positioning
    )

    products = [
        deterministic_text(item)
        for item in (
            profile.relevant_products
            or []
        )[:3]
        if deterministic_text(item)
    ]

    parts = []

    if category:
        parts.append(category)

    if positioning:
        parts.append(positioning)

    if products:
        parts.append(
            "Relevant offerings: "
            + "; ".join(products)
        )

    return (
        ". ".join(parts)
        or "No additional profile description "
        "was available."
    )


def deterministic_target_mention(
    mentions,
):
    return next(
        (
            item
            for item in mentions
            if item.get("role")
            == "target"
        ),
        None,
    )


def deterministic_mention_order(
    mentions,
):
    return [
        item.get(
            "brand_name",
            "",
        )
        for item in mentions
        if item.get("mentioned")
    ]


def deterministic_absent_brands(
    mentions,
):
    return [
        item.get(
            "brand_name",
            "",
        )
        for item in mentions
        if (
            item.get("role")
            == "competitor"
            and not item.get(
                "mentioned"
            )
        )
    ]


def deterministic_web_search_status(
    value,
):
    if value is True:
        return "Reported as enabled"

    if value is False:
        return "Reported as disabled"

    return "Not reported"


def deterministic_source_counts(
    visibility,
    collect_sources,
):
    measured_visibility = dict(visibility)
    measured_visibility["engines"] = {
        name: result
        for name, result in visibility.get("engines", {}).items()
        if result.get("status") == "success"
    }
    sources = collect_sources(
        measured_visibility,
        max_per_engine=10,
    )

    counts = DeterministicCounter(
        source.get(
            "source_type",
            "Other source",
        )
        for source in sources
    )

    return sources, counts


def deterministic_search_is_measured(
    keyword_serp_results,
    search_status,
):
    active_status = str(search_status or "unavailable").lower()

    successful = [
        result
        for result in (
            keyword_serp_results
        )
        if result.get("success")
    ]

    return (
        active_status in {"available", "partial"}
        and bool(successful)
    )


def deterministic_search_summary(
    target_profile,
    competitor_profiles,
    serp_metrics,
    total_keywords,
):
    profiles = [
        target_profile,
        *competitor_profiles,
    ]

    records = []

    for profile in profiles:
        metric = (
            deterministic_metric_for_profile(
                profile,
                serp_metrics,
                total_keywords,
            )
        )

        records.append(
            {
                "profile": profile,
                "metric": metric,
            }
        )

    return records


def deterministic_ai_engine_summary(
    visibility,
    engine,
):
    result = visibility.get(
        "engines",
        {},
    ).get(
        engine,
        {},
    )

    mentions = visibility.get(
        "mentions",
        {},
    ).get(
        engine,
        [],
    )

    target = deterministic_target_mention(
        mentions
    )

    return {
        "engine": engine,
        "engine_name": (
            DETERMINISTIC_ENGINE_NAMES.get(
                engine,
                engine,
            )
        ),
        "status": result.get(
            "status",
            "failed",
        ),
        "successful_questions": result.get(
            "successful_questions", 0,
        ),
        "question_count": result.get(
            "question_count", 0,
        ),
        "target_appearances": (
            target.get(
                "answer_appearances",
                0,
            )
            if target
            else 0
        ),
        "answer_total": (
            target.get(
                "answer_total",
                0,
            )
            if target
            else 0
        ),
        "target_mentions": (
            target.get(
                "mention_count",
                0,
            )
            if target
            else 0
        ),
        "order": (
            deterministic_mention_order(
                mentions
            )
        ),
        "absent": (
            deterministic_absent_brands(
                mentions
            )
        ),
        "citations": len(
            result.get(
                "citations",
                [],
            )
        ),
        "web_search": (
            deterministic_web_search_status(
                result.get(
                    "web_search_triggered"
                )
            )
        ),
        "error": result.get(
            "error"
        ),
    }


def deterministic_recommendation(
    number,
    priority,
    action,
    evidence,
    expected_impact,
):
    return "\n".join(
        [
            (
                f"**Recommendation {number} - "
                f"Priority:** {priority}"
            ),
            "",
            (
                f"   - **Action:** "
                f"{action}"
            ),
            "",
            (
                f"   - **Evidence:** "
                f"{evidence}"
            ),
            "",
            (
                f"   - **Expected Impact:** "
                f"{expected_impact}"
            ),
        ]
    )


def deterministic_search_recommendations(
    target_profile,
    competitor_profiles,
    serp_metrics,
    total_keywords,
    search_measured,
):
    target_metric = (
        deterministic_metric_for_profile(
            target_profile,
            serp_metrics,
            total_keywords,
        )
    )

    if search_measured:
        missing = max(
            0,
            total_keywords
            - target_metric[
                "appearances"
            ],
        )

        first = {
            "priority": "High",
            "action": (
                "Review the landing pages and "
                "content mapped to the "
                f"{missing} measured search "
                "queries where the target did "
                "not appear."
            ),
            "evidence": (
                f"{target_profile.brand_name} "
                f"appeared in "
                f"{target_metric['appearances']}/"
                f"{total_keywords} measured "
                "searches."
            ),
            "impact": (
                "Provides a defined set of search "
                "visibility gaps for content and "
                "technical review."
            ),
        }

        if target_metric["appearances"]:
            second = {
                "priority": "Medium",
                "action": (
                    "Review queries where the target "
                    "appeared at its lower observed "
                    "positions and compare page "
                    "relevance with the higher-ranking "
                    "results."
                ),
                "evidence": (
                    f"The target's best observed rank "
                    f"was "
                    f"{deterministic_rank(target_metric['best_rank'])} "
                    f"and its average rank, only where "
                    f"it appeared, was "
                    f"{deterministic_number(target_metric['average_rank'])}."
                ),
                "impact": (
                    "Supports prioritization of pages "
                    "with measurable placement gaps "
                    "without treating rank as traffic."
                ),
            }
        else:
            second = {
                "priority": "Medium",
                "action": (
                    "Compare the first-page results for "
                    "the measured buyer searches with "
                    "the target's existing product, "
                    "use-case, and comparison pages."
                ),
                "evidence": (
                    f"The target had no observed ranking "
                    f"in any of the {total_keywords} "
                    "measured searches, so rank-based "
                    "optimization is not yet applicable."
                ),
                "impact": (
                    "Identifies the content and category "
                    "signals needed to establish initial "
                    "search visibility."
                ),
            }

    else:
        first = {
            "priority": "High",
            "action": (
                "Repeat the traditional-search "
                "collection after confirming SERP "
                "availability."
            ),
            "evidence": (
                "Traditional search was not "
                "measured in this audit."
            ),
            "impact": (
                "Establishes the missing search "
                "visibility baseline."
            ),
        }

        second = {
            "priority": "Medium",
            "action": (
                "Retain the same buyer searches, "
                "country, and engine when the "
                "search measurement is repeated."
            ),
            "evidence": (
                f"The audit generated "
                f"{total_keywords} buyer searches "
                "but did not obtain a measured "
                "traditional-search result set."
            ),
            "impact": (
                "Supports a comparable future "
                "measurement."
            ),
        }

    return first, second


def deterministic_ai_recommendation(
    ai_summaries,
):
    successful = [
        item
        for item in ai_summaries
        if (
            item["status"]
            == "success"
            and item[
                "answer_total"
            ] > 0
        )
    ]

    if not successful:
        return {
            "priority": "High",
            "action": (
                "Repeat AI answer-engine "
                "measurement after confirming "
                "scraper availability."
            ),
            "evidence": (
                "No successful AI visibility "
                "measurement was available."
            ),
            "impact": (
                "Establishes the missing AI "
                "visibility baseline."
            ),
        }

    weakest = min(
        successful,
        key=lambda item: (
            item[
                "target_appearances"
            ]
            / item[
                "answer_total"
            ]
        ),
    )

    return {
        "priority": "Medium",
        "action": (
            "Review whether official pages clearly "
            "describe the target's category, "
            "offerings, audience, and relevant "
            "comparison criteria."
        ),
        "evidence": (
            f"{weakest['engine_name']} included "
            f"the target in "
            f"{weakest['target_appearances']}/"
            f"{weakest['answer_total']} measured "
            "answers."
        ),
        "impact": (
            "Creates clearer machine-readable "
            "information for future answer-engine "
            "measurements."
        ),
    }


def deterministic_source_recommendation(
    source_counts,
):
    official = sum(
        count
        for source_type, count
        in source_counts.items()
        if source_type.startswith(
            "Official"
        )
    )

    total = sum(
        source_counts.values()
    )

    external = max(
        0,
        total - official,
    )

    return {
        "priority": "Medium",
        "action": (
            "Review official product, category, "
            "help, and company pages for clear, "
            "current, and internally consistent "
            "information."
        ),
        "evidence": (
            f"The observed source set contained "
            f"{official} official source(s) and "
            f"{external} external source(s)."
        ),
        "impact": (
            "Supports more consistent information "
            "across official pages that answer "
            "engines may cite."
        ),
    }


def deterministic_competitor_recommendation(
    competitor_profiles,
    serp_metrics,
    total_keywords,
    search_measured,
):
    if not competitor_profiles:
        return {
            "priority": "Low",
            "action": (
                "Review competitor selection before "
                "the next audit."
            ),
            "evidence": (
                "No validated competitor profile "
                "was available."
            ),
            "impact": (
                "Maintains a defined comparison set."
            ),
        }

    if search_measured:
        strongest = max(
            competitor_profiles,
            key=lambda profile: (
                deterministic_metric_for_profile(
                    profile,
                    serp_metrics,
                    total_keywords,
                )[
                    "appearances"
                ]
            ),
        )

        metric = (
            deterministic_metric_for_profile(
                strongest,
                serp_metrics,
                total_keywords,
            )
        )

        evidence = (
            f"{strongest.brand_name} appeared in "
            f"{metric['appearances']}/"
            f"{total_keywords} measured searches."
        )

    else:
        strongest = (
            competitor_profiles[0]
        )

        evidence = (
            f"{strongest.brand_name} is part of "
            "the validated competitor set."
        )

    return {
        "priority": "Low",
        "action": (
            f"Repeat the same comparison against "
            f"{strongest.brand_name} using the "
            "same scope and query set."
        ),
        "evidence": evidence,
        "impact": (
            "Supports consistent competitor "
            "visibility tracking over time."
        ),
    }


def build_deterministic_report(
    target_profile,
    competitor_profiles,
    keywords,
    keyword_serp_results,
    serp_metrics,
    visibility,
    *,
    country,
    search_engine,
    search_status,
    collect_sources,
):
    country = str(country or "").upper()

    search_engine = str(search_engine or "Unavailable").title()

    search_measured = (
        deterministic_search_is_measured(
            keyword_serp_results, search_status
        )
    )

    requested_keywords = len(keywords)
    total_keywords = sum(
        bool(result.get("success"))
        for result in keyword_serp_results
    )
    measured_questions = {
        result.get("keyword") for result in keyword_serp_results
        if result.get("success")
    }
    unmeasured_questions = [
        keyword for keyword in keywords if keyword not in measured_questions
    ]

    search_records = (
        deterministic_search_summary(
            target_profile,
            competitor_profiles,
            serp_metrics,
            total_keywords,
        )
    )

    target_metric = search_records[
        0
    ]["metric"]

    ai_summaries = [
        deterministic_ai_engine_summary(
            visibility,
            engine,
        )
        for engine in ("google_ai_mode", "chatgpt", "gemini", "copilot")
        if engine in visibility.get("engines", {})
    ]

    sources, source_counts = (
        deterministic_source_counts(
            visibility, collect_sources
        )
    )

    competitor_names = [
        profile.brand_name
        for profile in (
            competitor_profiles
        )
    ]

    report = [
        "# Competitive Visibility Audit",
        "",
        "## Executive Summary",
        "",
    ]

    scope_description = (
        deterministic_text(
            target_profile.category
        )
        or "the locked audit category"
    )

    report.append(
        f"This audit measures the visibility of "
        f"**{target_profile.brand_name}** within "
        f"**{scope_description}** in "
        f"**{country or 'the selected market'}**. "
        f"The validated comparison set consists of "
        f"{', '.join(f'**{name}**' for name in competitor_names) or 'no available competitors'}."
    )

    report.append("")

    if search_measured and total_keywords < requested_keywords:
        report.append(
            f"Search answered **{total_keywords}/{requested_keywords}** "
            "planned buyer questions. All visibility ratios below "
            "use only the measured questions; missing searches "
            "are not treated as brand absences."
        )
        report.append("")
        report.append(
            "Unmeasured question(s): " + "; ".join(
                f"`{deterministic_markdown_text(keyword)}`"
                for keyword in unmeasured_questions
            ) + "."
        )
        report.append("")

    if search_measured:
        report.append(
            f"Traditional search was measured on "
            f"**{search_engine}** across "
            f"**{total_keywords}** buyer searches. "
            f"The target's official domain appeared in "
            f"**{target_metric['appearances']}/"
            f"{total_keywords}** searches, with a "
            f"best observed rank of "
            f"**{deterministic_rank(target_metric['best_rank'])}** "
            f"and an average rank of "
            f"**{deterministic_number(target_metric['average_rank'])}** "
            f"only across searches where it appeared."
        )
    else:
        report.append(
            "Traditional search was not measured. "
            "No zero-coverage conclusion is drawn "
            "from an unavailable search result set."
        )

    report.append("")

    successful_ai = [
        item
        for item in ai_summaries
        if item["status"]
        == "success"
    ]

    if successful_ai:
        coverage_text = "; ".join(
            (
                f"{item['engine_name']}: "
                f"{item['target_appearances']}/"
                f"{item['answer_total']}"
            )
            for item in successful_ai
        )

        report.append(
            "Measured target answer coverage was "
            + coverage_text
            + ". These are point-in-time visibility "
            "measurements, not market share or a "
            "formal engine ranking."
        )

    report.extend(
        [
            "",
            "## Competitive Landscape",
            "",
            (
                f"**Target — "
                f"{target_profile.brand_name}:** "
                f"{deterministic_profile_summary(target_profile)}"
            ),
            "",
        ]
    )

    for profile in competitor_profiles:
        report.extend(
            [
                (
                    f"- **{profile.brand_name}:** "
                    f"{deterministic_profile_summary(profile)}"
                ),
                "",
            ]
        )

    report.extend(
        [
            "The target scope and competitor set were validated before report generation. This section does not reclassify them.",
            "",
            "## Search Visibility",
            "",
        ]
    )

    if search_measured:
        report.extend(
            [
                (
                    f"Search was measured using "
                    f"**{search_engine}**, requesting "
                    f"**{country}** localization. The returned "
                    "location was not independently verified."
                ),
                "",
                (
                    "| Brand | Role | Coverage | "
                    "Best rank | Average rank |"
                ),
                (
                    "|---|---|---:|---:|---:|"
                ),
            ]
        )

        for index, record in enumerate(
            search_records
        ):
            profile = record[
                "profile"
            ]

            metric = record[
                "metric"
            ]

            role = (
                "Target"
                if index == 0
                else "Competitor"
            )

            report.append(
                f"| {deterministic_markdown_text(profile.brand_name)} "
                f"| {role} "
                f"| {metric['appearances']}/"
                f"{metric['total_keywords']} "
                f"| {deterministic_rank(metric['best_rank'])} "
                f"| {deterministic_number(metric['average_rank'])} |"
            )

    else:
        report.append(
            "Traditional search was not measured "
            "because no active search result set "
            "was available."
        )

    report.extend(
        [
            "",
            "### Buyer Searches",
            "",
        ]
    )

    for index, keyword in enumerate(
        keywords,
        start=1,
    ):
        report.append(
            f"{index}. `{keyword}`"
        )

    report.extend(
        [
            "",
            (
                "> **Interpretation:** SERP coverage "
                "counts official audited domains, not "
                "mentions on publisher pages. It is the primary "
                "search-visibility "
                "metric. Best and average ranks apply "
                "only where a brand appeared. A high "
                "rank on one query does not outweigh "
                "broader measured coverage."
            ),
            "",
            "## AI Answer-Engine Visibility",
            "",
        ]
    )

    for item in ai_summaries:
        report.append(
            f"### {item['engine_name']}"
        )

        report.append("")

        if item["status"] != "success":
            if item["status"] == "partial":
                report.append(
                    "Only "
                    f"{item['successful_questions']}/"
                    f"{item['question_count']} answers completed. "
                    "Google AI Mode visibility is not scored "
                    "from this incomplete sample."
                )
            elif item["status"] == "unavailable":
                report.append(
                    "Google AI Mode was unavailable. Its visibility "
                    "was not measured or scored in this audit."
                )
            else:
                report.append(
                    "Measurement failed or returned no "
                    "usable answer."
                )

            # Detailed provider errors remain in JSON/logs; the
            # reader-facing report only states the coverage gap.
            report.append("")
            continue

        order = (
            " > ".join(
                item["order"]
            )
            or "No audited brand appeared"
        )

        absent = (
            ", ".join(
                item["absent"]
            )
            or "None"
        )

        report.extend(
            [
                (
                    f"- **Target answer coverage:** "
                    f"{item['target_appearances']}/"
                    f"{item['answer_total']}"
                ),
                (
                    f"- **Target mentions:** "
                    f"{item['target_mentions']}"
                ),
                (
                    f"- **First appearance among "
                    f"audited brands:** {order}"
                ),
                (
                    f"- **Absent competitors:** "
                    f"{absent}"
                ),
                (
                    f"- **Citations returned:** "
                    f"{item['citations']}"
                ),
                (
                    f"- **Web-search status:** "
                    f"{item['web_search']}"
                ),
                "",
            ]
        )

    report.extend(
        [
            (
                "Mention counts and first appearance "
                "are supporting observations. They "
                "are not market share, recommendation "
                "rank, or evidence of engine preference."
            ),
            "",
            "## Source Influence",
            "",
        ]
    )

    if source_counts:
        report.extend(
            [
                "| Source type | Unique sources |",
                "|---|---:|",
            ]
        )

        for source_type, count in (
            source_counts.most_common()
        ):
            report.append(
                f"| {deterministic_markdown_text(source_type)} "
                f"| {count} |"
            )

        report.extend(
            [
                "",
                (
                    f"The measured answers returned "
                    f"{len(sources)} unique source "
                    f"URLs after deduplication. Source "
                    f"counts describe the observed "
                    f"answers only and do not establish "
                    f"causation."
                ),
            ]
        )

    else:
        report.append(
            "No usable citation records were "
            "returned by the measured engines."
        )

    report.extend(
        [
            "",
            "## Positioning and Information Gaps",
            "",
        ]
    )

    if search_measured:
        competitor_coverages = [
            (
                profile.brand_name,
                deterministic_metric_for_profile(
                    profile,
                    serp_metrics,
                    total_keywords,
                )[
                    "appearances"
                ],
            )
            for profile in (
                competitor_profiles
            )
        ]

        report.append(
            f"- **Search coverage:** The target "
            f"appeared in "
            f"{target_metric['appearances']}/"
            f"{total_keywords} measured searches."
        )

        if competitor_coverages:
            comparison = "; ".join(
                f"{name}: {appearances}/"
                f"{total_keywords}"
                for name, appearances
                in competitor_coverages
            )

            report.append(
                f"- **Competitor comparison:** "
                f"{comparison}."
            )

    else:
        report.append(
            "- **Search measurement gap:** "
            "Traditional-search visibility was "
            "not available."
        )

    for item in successful_ai:
        report.append(
            f"- **{item['engine_name']} coverage:** "
            f"The target appeared in "
            f"{item['target_appearances']}/"
            f"{item['answer_total']} measured answers."
        )

    official_sources = sum(
        count
        for source_type, count
        in source_counts.items()
        if source_type.startswith(
            "Official"
        )
    )

    total_sources = sum(
        source_counts.values()
    )

    external_sources = max(
        0,
        total_sources
        - official_sources,
    )

    report.append(
        f"- **Source composition:** "
        f"{official_sources} official source(s) "
        f"and {external_sources} external source(s) "
        f"were observed."
    )

    report.extend(
        [
            "",
            "## Prioritized Recommendations",
            "",
        ]
    )

    search_one, search_two = (
        deterministic_search_recommendations(
            target_profile,
            competitor_profiles,
            serp_metrics,
            total_keywords,
            search_measured,
        )
    )

    recommendations = [
        search_one,
        search_two,
        deterministic_ai_recommendation(
            ai_summaries
        ),
        deterministic_source_recommendation(
            source_counts
        ),
        deterministic_competitor_recommendation(
            competitor_profiles,
            serp_metrics,
            total_keywords,
            search_measured,
        ),
        {
            "priority": "Low",
            "action": (
                "Repeat the audit using the same "
                "locked scope, country, competitors, "
                "and buyer searches."
            ),
            "evidence": (
                "Search and AI answers are "
                "point-in-time measurements."
            ),
            "impact": (
                "Creates comparable observations "
                "for identifying changes over time."
            ),
        },
    ]

    for index, item in enumerate(
        recommendations,
        start=1,
    ):
        report.append(
            deterministic_recommendation(
                number=index,
                priority=item[
                    "priority"
                ],
                action=item[
                    "action"
                ],
                evidence=item[
                    "evidence"
                ],
                expected_impact=item[
                    "impact"
                ],
            )
        )

        report.append("")

    report.extend(
        [
            "## Methodology and Limitations",
            "",
            (
                f"This audit used a locked target "
                f"scope and validated competitor set. "
                f"Traditional search was "
                f"{'measured on ' + search_engine if search_measured else 'not measured'} "
                f"in {country or 'the selected country'} "
                f"across {total_keywords} buyer "
                f"searches."
            ),
            "",
            (
                "SERP coverage is the primary "
                "traditional-search metric. Best and "
                "average ranks apply only to searches "
                "where a brand appeared."
            ),
            "",
            (
                "Answer coverage is the primary AI "
                "visibility metric. Mention counts, "
                "citation totals, and first appearance "
                "are supporting observations."
            ),
            "",
            (
                "`web_search=None` is reported as "
                "“Not reported.” It provides no "
                "evidence about retrieval, training "
                "data, closed models, internal "
                "knowledge, or offline behavior."
            ),
            "",
            (
                "The audit is a point-in-time, "
                "directional measurement. It does not "
                "measure traffic, click-through rate, "
                "market share, revenue impact, engine "
                "preference, or causation."
            ),
        ]
    )

    return "\n".join(
        report
    ).strip()


def deterministic_human_join(
    values,
):
    """
    Join display values using natural English list punctuation.
    """
    values = [
        str(value)
        for value in values
        if str(value).strip()
    ]

    if not values:
        return ""

    if len(values) == 1:
        return values[0]

    if len(values) == 2:
        return (
            values[0]
            + " and "
            + values[1]
        )

    return (
        ", ".join(values[:-1])
        + ", and "
        + values[-1]
    )


def apply_final_cosmetic_polish(
    report,
    competitor_profiles,
):
    """
    Apply cosmetic corrections to the generated report body.

    Source appendix content is preserved if already present.
    """
    report = str(
        report or ""
    )

    if not report:
        return report

    source_heading = re.search(
        r"(?im)^##\s+"
        r"Observed AI Sources\s*$",
        report,
    )

    if source_heading:
        body = report[
            :source_heading.start()
        ]

        source_appendix = report[
            source_heading.start():
        ]
    else:
        body = report
        source_appendix = ""

    competitor_names = [
        f"**{profile.brand_name}**"
        for profile in (
            competitor_profiles
            or []
        )
    ]

    if competitor_names:
        comma_list = ", ".join(
            competitor_names
        )

        natural_list = (
            deterministic_human_join(
                competitor_names
            )
        )

        old_sentence = (
            "The validated comparison set "
            "consists of "
            + comma_list
            + "."
        )

        new_sentence = (
            "The validated comparison set "
            "consists of "
            + natural_list
            + "."
        )

        body = body.replace(
            old_sentence,
            new_sentence,
            1,
        )

    # Replace exactly two periods. Negative lookaround preserves
    # ellipses containing three or more periods.
    body = re.sub(
        r"(?<!\.)\.\.(?!\.)",
        ".",
        body,
    )

    body = body.rstrip()

    if source_appendix:
        return (
            body
            + "\n\n"
            + source_appendix.lstrip()
        )

    return body


def build_report_content(
    target_profile,
    competitor_profiles,
    keywords,
    keyword_serp_results,
    serp_metrics,
    visibility,
    *,
    country,
    search_engine,
    search_status,
    collect_sources,
):
    """Render the final Markdown body with its established cosmetic polish."""
    report = build_deterministic_report(
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
    return apply_final_cosmetic_polish(report, competitor_profiles)
