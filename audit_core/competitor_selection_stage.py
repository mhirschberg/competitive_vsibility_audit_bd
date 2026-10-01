"""Stage 3 orchestration around the shared competitor-selection engine."""

import asyncio
from datetime import datetime, timezone
import time


class CompetitorSelectionStagePorts:
    """Provider, persistence, progress, and social-prefetch operations."""

    def __init__(
        self, *, select_competitors, configure_race_cache, write_json,
        model_to_dict, clean_record, stage_warning, print_selected,
        social_notice, start_reddit_prefetch,
    ):
        self.select_competitors = select_competitors
        self.configure_race_cache = configure_race_cache
        self.write_json = write_json
        self.model_to_dict = model_to_dict
        self.clean_record = clean_record
        self.stage_warning = stage_warning
        self.print_selected = print_selected
        self.social_notice = social_notice
        self.start_reddit_prefetch = start_reddit_prefetch


async def run_competitor_selection_stage_core(
    target_brand, candidates, keywords, *, continuing, output_directory,
    raw_directory, started_at, include_reddit_analysis, audit_focus, ports,
):
    selection = await asyncio.to_thread(
        ports.select_competitors, target_brand, candidates, keywords,
    )
    selected = selection["selected"]
    warnings = []

    if continuing:
        ports.configure_race_cache(
            raw_directory / "google_ai_snapshot_cache.json", only_reuse=False,
        )
        skipped = selection.get("unvalidated_on_resume", 0)
        if skipped:
            warning = (
                f"{skipped} candidate(s) were not validated during "
                "continuation because no saved snapshots existed"
            )
            warnings.append(warning)
            ports.stage_warning(warning)

    duration_seconds = time.monotonic() - started_at
    if selection.get("used_fallback"):
        warning = "AI competitor validation failed; SERP-ranked fallback was used"
        warnings.append(warning)
        ports.stage_warning(warning)

    for competitor in selected:
        ports.print_selected(competitor)

    ports.write_json(output_directory / "03_competitor_selection.json", {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selected_competitors": [ports.model_to_dict(item) for item in selected],
        "rejected_candidates": selection.get("rejected", []),
        "used_fallback": selection.get("used_fallback", False),
        "validation_results": selection.get("validation_results", []),
        "duration_seconds": round(duration_seconds, 2),
    })
    if isinstance(selection.get("record"), dict):
        ports.write_json(
            raw_directory / "03_selection_ai_record.json",
            ports.clean_record(selection["record"]),
        )

    reddit_prefetch_task = None
    if include_reddit_analysis:
        ports.social_notice()
        reddit_prefetch_task = asyncio.create_task(
            ports.start_reddit_prefetch(
                target_brand=target_brand,
                selected_competitors=selected,
                keywords=keywords,
                audit_focus=audit_focus,
            )
        )
    return {
        "selection_result": selection,
        "selected_competitors": selected,
        "duration_seconds": duration_seconds,
        "warnings": warnings,
        "reddit_prefetch_task": reddit_prefetch_task,
    }
