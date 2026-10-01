"""Stage 5 orchestration and measured AI visibility checkpoint."""

import asyncio
from datetime import datetime, timezone
import time


class VisibilityCheckpointPorts:
    def __init__(
        self, *, run_visibility, run_reddit_social, serialize_engine_result,
        write_json, stage_success, stage_warning, format_duration,
    ):
        self.run_visibility = run_visibility
        self.run_reddit_social = run_reddit_social
        self.serialize_engine_result = serialize_engine_result
        self.write_json = write_json
        self.stage_success = stage_success
        self.stage_warning = stage_warning
        self.format_duration = format_duration


async def run_visibility_checkpoint_stage_core(
    target_profile, competitor_profiles, all_profiles, keywords,
    keyword_serp_results, *, include_copilot, include_google_ai_mode,
    include_chatgpt, include_gemini, wait_longer_for_chatgpt,
    wait_longer_for_gemini, wait_longer_for_copilot,
    include_reddit_analysis, audit_focus, reddit_prefetch_task,
    output_directory, started_at, ports,
):
    visibility_task = asyncio.create_task(ports.run_visibility(
        target_profile=target_profile,
        all_profiles=all_profiles,
        keywords=keywords,
        include_copilot=include_copilot,
        include_google_ai_mode=include_google_ai_mode,
        include_chatgpt=include_chatgpt,
        include_gemini=include_gemini,
        wait_longer_for_chatgpt=wait_longer_for_chatgpt,
        wait_longer_for_gemini=wait_longer_for_gemini,
        wait_longer_for_copilot=wait_longer_for_copilot,
    ))

    reddit_task = None
    reddit_social_result = None
    if include_reddit_analysis:
        reddit_task = asyncio.create_task(ports.run_reddit_social(
            target_profile=target_profile,
            competitor_profiles=competitor_profiles,
            keywords=keywords,
            keyword_serp_results=keyword_serp_results,
            audit_focus=audit_focus,
            discovery_prefetch_task=reddit_prefetch_task,
        ))
    else:
        reddit_social_result = {
            "status": "disabled", "mode": "disabled",
            "queries": [], "sample": [], "metrics": {}, "cohorts": [],
            "comparison": [], "warnings": [], "duration_seconds": 0.0,
        }

    visibility_result = await visibility_task
    duration_seconds = time.monotonic() - started_at
    warnings = []
    for engine in (
        item for item in ("chatgpt", "gemini", "copilot")
        if item in visibility_result["engines"]
    ):
        engine_result = visibility_result["engines"][engine]
        engine_name = engine_result.get("engine_name", engine.title())
        if engine_result.get("status") == "success":
            ports.stage_success(
                f"{engine_name} completed in "
                f"{ports.format_duration(engine_result['duration_seconds'])}"
            )
        else:
            warning = (
                f"{engine_name} visibility failed: "
                f"{engine_result.get('error', 'unknown error')}"
            )
            warnings.append(warning)
            ports.stage_warning(warning)

    ports.write_json(output_directory / "05_ai_visibility.json", {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "prompt": visibility_result["prompt"],
        "engines": {
            engine: ports.serialize_engine_result(result)
            for engine, result in visibility_result["engines"].items()
        },
        "mentions": visibility_result["mentions"],
        "duration_seconds": round(duration_seconds, 2),
    })
    return {
        "visibility_result": visibility_result,
        "reddit_task": reddit_task,
        "reddit_social_result": reddit_social_result,
        "duration_seconds": duration_seconds,
        "warnings": warnings,
    }
