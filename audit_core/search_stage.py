"""Stage 2 checkpoint handling for measured search and AI discovery."""

from datetime import datetime, timezone
import json
import time


class SearchStagePorts:
    def __init__(
        self, *, run_search, candidate_factory, model_to_dict, write_json,
        stage_success, stage_warning, format_duration,
    ):
        self.run_search = run_search
        self.candidate_factory = candidate_factory
        self.model_to_dict = model_to_dict
        self.write_json = write_json
        self.stage_success = stage_success
        self.stage_warning = stage_warning
        self.format_duration = format_duration


async def run_search_stage_core(
    keywords, target_domain, *, continuing, output_directory, started_at,
    ports,
):
    if continuing:
        checkpoint = json.loads((
            output_directory / "02_serp_results.json"
        ).read_text(encoding="utf-8"))
        result = {
            "keyword_results": checkpoint["keyword_results"],
            "candidates": [
                ports.candidate_factory(**item)
                for item in checkpoint["competitor_candidates"]
            ],
            "successful": checkpoint["successful"],
            "failed": checkpoint["failed"],
            "ai_mode_failed": checkpoint.get("ai_mode_failed", 0),
            "search_engine": checkpoint.get("search_engine"),
            "search_status": checkpoint.get("search_status", "unavailable"),
            "ai_mode_discovery": checkpoint.get("ai_mode_discovery"),
        }
    else:
        result = await ports.run_search(
            keywords=keywords, target_domain=target_domain,
        )

    keyword_results = result["keyword_results"]
    candidates = result["candidates"]
    duration_seconds = (
        checkpoint.get("duration_seconds", 0.0)
        if continuing else time.monotonic() - started_at
    )
    ports.stage_success(
        f"{result['successful']}/{len(keywords)} searches completed "
        f"in {ports.format_duration(duration_seconds)}"
    )
    warnings = []
    if result["failed"]:
        warning = f"{result['failed']} SERP request(s) failed"
        warnings.append(warning)
        ports.stage_warning(warning)
    if result["ai_mode_failed"]:
        warning = (
            f"{result['ai_mode_failed']}/3 Google AI Mode "
            "discovery answer(s) unavailable; incomplete "
            "coverage will not be scored"
        )
        warnings.append(warning)
        ports.stage_warning(warning)

    ports.write_json(output_directory / "02_serp_results.json", {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "keywords": keywords,
        "search_engine": result.get("search_engine"),
        "search_status": result.get("search_status"),
        "successful": result["successful"],
        "failed": result["failed"],
        "ai_mode_failed": result["ai_mode_failed"],
        "ai_mode_discovery": result.get("ai_mode_discovery"),
        "keyword_results": keyword_results,
        "competitor_candidates": [
            ports.model_to_dict(item) for item in candidates
        ],
        "duration_seconds": round(duration_seconds, 2),
    })
    return {
        "keyword_results": keyword_results,
        "candidates": candidates,
        "duration_seconds": duration_seconds,
        "search_engine": result.get("search_engine"),
        "search_status": result.get("search_status"),
        "ai_mode_discovery": result.get("ai_mode_discovery"),
        "warnings": warnings,
    }
