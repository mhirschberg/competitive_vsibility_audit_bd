"""Finish optional Reddit measurement and persist its diagnostics."""

from datetime import datetime, timezone


class SocialCompletionPorts:
    def __init__(
        self, *, print_stage, stage_success, stage_warning,
        format_duration, summarize_warning, write_json,
    ):
        self.print_stage = print_stage
        self.stage_success = stage_success
        self.stage_warning = stage_warning
        self.format_duration = format_duration
        self.summarize_warning = summarize_warning
        self.write_json = write_json


async def run_social_completion_stage_core(
    reddit_task, reddit_social_result, *, include_reddit_analysis,
    total_stages, output_directory, ports,
):
    if include_reddit_analysis:
        ports.print_stage(6, "Reddit conversation analysis", total_stages)
        reddit_social_result = await reddit_task
        duration_seconds = float(
            reddit_social_result.get("duration_seconds") or 0
        )
    else:
        duration_seconds = 0.0

    reddit_status = reddit_social_result.get("status", "failed")
    if reddit_status in {"success", "partial"}:
        if reddit_social_result.get("mode") == "competitive":
            comparison = reddit_social_result.get("comparison", [])
            cohort_summary = ", ".join(
                f"{item.get('brand')}: {item.get('relevant_posts', 0)} relevant / "
                f"{item.get('classified_posts', 0)} classified / "
                f"{item.get('sample_size', 0)} sampled"
                for item in comparison
            )
            ports.stage_success(
                f"Reddit competitive sample: {cohort_summary}; "
                f"{reddit_social_result.get('unique_thread_count', 0)} "
                "unique thread(s) in "
                f"{ports.format_duration(reddit_social_result.get('duration_seconds', 0))}"
            )
        else:
            ports.stage_success(
                f"Reddit sample: {len(reddit_social_result.get('sample', []))} "
                "thread(s) in "
                f"{ports.format_duration(reddit_social_result.get('duration_seconds', 0))}"
            )

    warnings = []
    summary_warning = ports.summarize_warning(reddit_social_result)
    if summary_warning:
        warnings.append(summary_warning)
        ports.stage_warning(summary_warning)

    ports.write_json(output_directory / "05_reddit_social.json", {
        "created_at": datetime.now(timezone.utc).isoformat(),
        **reddit_social_result,
    })
    ports.write_json(output_directory / "05_reddit_snapshot_manifest.json", {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "snapshots": reddit_social_result.get("snapshot_manifest", []),
    })
    return {
        "reddit_social_result": reddit_social_result,
        "duration_seconds": duration_seconds,
        "warnings": warnings,
    }
