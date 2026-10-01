"""Stage 4 profile checkpoint, progress, and warning handling."""

from datetime import datetime, timezone
import time


class ProfileStagePorts:
    def __init__(
        self, *, run_profiles, model_to_dict, serialize_task, write_json,
        stage_success, stage_warning,
    ):
        self.run_profiles = run_profiles
        self.model_to_dict = model_to_dict
        self.serialize_task = serialize_task
        self.write_json = write_json
        self.stage_success = stage_success
        self.stage_warning = stage_warning


async def run_profile_stage_core(
    target_brand, selected_competitors, *, audit_focus, company_domain,
    company_url, output_directory, started_at, ports,
):
    result = await ports.run_profiles(
        target_brand=target_brand,
        selected_competitors=selected_competitors,
        audit_focus=audit_focus,
    )
    target_profile = result["target_profile"]
    target_profile.domain = company_domain
    target_profile.official_url = company_url
    competitor_profiles = result["competitor_profiles"]
    all_profiles = result["all_profiles"]
    duration_seconds = time.monotonic() - started_at
    ports.stage_success(f"{len(all_profiles)}/3 profiles available")
    warnings = []
    if result["fallbacks"]:
        warning = f"{result['fallbacks']} profile fallback(s) used"
        warnings.append(warning)
        ports.stage_warning(warning)

    ports.write_json(output_directory / "04_brand_profiles.json", {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "target_profile": ports.model_to_dict(target_profile),
        "competitor_profiles": [
            ports.model_to_dict(item) for item in competitor_profiles
        ],
        "successful_profiles": result["successful"],
        "fallback_profiles": result["fallbacks"],
        "tasks": [ports.serialize_task(item) for item in result["task_results"]],
        "duration_seconds": round(duration_seconds, 2),
    })
    return {
        "target_profile": target_profile,
        "competitor_profiles": competitor_profiles,
        "all_profiles": all_profiles,
        "duration_seconds": duration_seconds,
        "warnings": warnings,
    }
