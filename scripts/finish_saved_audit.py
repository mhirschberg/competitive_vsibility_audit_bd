"""Finish report export from complete saved stages without provider requests.

Use this only when a run has saved stages 1-5 but failed during final export.
The measured answers and search results are replayed, not re-collected.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audit_core.artifact_names import audit_export_prefix, report_filename  # noqa: E402
from audit_core.brightdata_usage import BrightDataUsageLedger  # noqa: E402
from runner_builder import _build_runner_script  # noqa: E402
from scripts.run_local_audit import load_env_file, require_local_settings  # noqa: E402


STAGES = {
    "company": "01_company_analysis.json",
    "serp": "02_serp_results.json",
    "selection": "03_competitor_selection.json",
    "profiles": "04_brand_profiles.json",
    "visibility": "05_ai_visibility.json",
    "reddit": "05_reddit_social.json",
}


def read_complete_stages(directory):
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"Audit directory not found: {directory}")
    existing_reports = list(directory.glob("*_competitive_visibility_audit.json"))
    if existing_reports:
        if len(existing_reports) != 1 or not json.loads(
            existing_reports[0].read_text(encoding="utf-8")
        ).get("recovery", {}).get("final_export_rebuilt_from_saved_stages"):
            raise ValueError(f"Final audit JSON already exists: {existing_reports[0]}")
    settings_path = directory / "00_run_settings.json"
    if not settings_path.is_file():
        raise FileNotFoundError(f"Saved settings not found: {settings_path}")
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    stages = {}
    for key, name in STAGES.items():
        path = directory / name
        if not path.is_file():
            raise FileNotFoundError(f"Required completed stage not found: {path}")
        stages[key] = json.loads(path.read_text(encoding="utf-8"))
    if stages["company"]["brand"]["domain"] != settings["company_domain"]:
        raise ValueError("Saved company does not match run settings")
    if not stages["serp"]["keyword_results"]:
        raise ValueError("Saved search results are empty")
    if len(stages["profiles"]["competitor_profiles"]) != len(
        stages["selection"]["selected_competitors"]
    ):
        raise ValueError("Saved competitor profiles do not match selection")
    if not stages["visibility"].get("engines"):
        raise ValueError("Saved AI visibility is empty")
    return directory, settings, stages


def finish_saved_audit(directory, env_file, canonical_target_domain=None):
    directory, saved_settings, stages = read_complete_stages(directory)
    os.environ.setdefault(
        "TLDEXTRACT_CACHE", str(Path(tempfile.gettempdir()) / "qaviso-tldextract-cache")
    )
    os.environ.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir()) / "qaviso-cache"))
    load_env_file(env_file)
    require_local_settings()
    source = _build_runner_script(
        saved_settings["company_name"],
        saved_settings["company_domain"],
        saved_settings.get("audit_focus") or "",
        saved_settings["country"],
        saved_settings.get("search_engine") or "auto",
        bool(saved_settings.get("include_reddit_analysis")),
        False,
        include_copilot_visibility=bool(saved_settings.get("include_copilot_visibility")),
        reddit_comment_posts_per_cohort=saved_settings.get("reddit_comment_posts_per_cohort", 0),
        include_google_ai_mode=bool(saved_settings.get("include_google_ai_mode")),
        include_chatgpt_visibility=bool(saved_settings.get("include_chatgpt_visibility", True)),
        include_gemini_visibility=bool(saved_settings.get("include_gemini_visibility", True)),
    )
    definitions, marker, _invocation = source.partition(
        "#@title 4. Run Competitive Visibility Audit"
    )
    if not marker:
        raise RuntimeError("Could not isolate notebook definitions")
    namespace = {"__name__": "__saved_audit_export__"}
    exec(compile(definitions, "saved-audit-definitions", "exec"), namespace)

    # An export-only replay must never trigger a new paid provider operation.
    client = namespace["bd_client"]

    def provider_call_forbidden(*_args, **_kwargs):
        raise RuntimeError("Provider calls are forbidden during saved-audit export")

    for method in ("trigger_dataset", "scrape", "google_ai_mode", "race_ai_engine"):
        if hasattr(client, method):
            setattr(client, method, provider_call_forbidden)

    settings = {**namespace["AUDIT_SETTINGS"], **saved_settings}
    namespace["ACTIVE_SEARCH_ENGINE"] = stages["serp"].get("search_engine")
    namespace["ACTIVE_SEARCH_STATUS"] = stages["serp"].get("search_status", "unavailable")
    namespace["LOCKED_TARGET_SCOPE"] = stages["company"].get("locked_target_scope")

    profile_type = namespace["BrandProfile"]
    target = profile_type(**stages["profiles"]["target_profile"])
    if canonical_target_domain:
        canonical_target_domain = canonical_target_domain.strip().lower()
        if namespace["get_root_domain"](canonical_target_domain) != canonical_target_domain:
            raise ValueError("Canonical target domain must be a registrable domain")
        target.domain = canonical_target_domain
    competitors = [
        profile_type(**item) for item in stages["profiles"]["competitor_profiles"]
    ]
    visibility = {
        "prompt": stages["visibility"]["prompt"],
        "engines": stages["visibility"]["engines"],
        "mentions": stages["visibility"]["mentions"],
        "audited_domains": {
            profile.domain: profile.brand_name for profile in [target, *competitors]
        },
    }
    started = time.monotonic()
    report_result = namespace["generate_report_stage"](
        target, competitors, stages["serp"]["keywords"],
        stages["serp"]["keyword_results"], visibility,
    )
    finalized = namespace["finalize_report"](report_result["report"], visibility)
    report = namespace["insert_reddit_report_section"](
        finalized["report"], stages["reddit"]
    )
    if canonical_target_domain and canonical_target_domain != saved_settings["company_domain"]:
        note = (
            f"> **Official-domain correction:** The submitted address "
            f"`{saved_settings['company_domain']}` redirects to "
            f"`{canonical_target_domain}`. Search coverage and source ownership "
            "are measured against the canonical domain.\n\n"
        )
        report = report.replace("# Competitive Visibility Audit\n\n", "# Competitive Visibility Audit\n\n" + note, 1)

    usage_checkpoint = directory / "raw" / "bright_data_usage_events.json"
    if not usage_checkpoint.is_file():
        raise FileNotFoundError(f"Usage checkpoint not found: {usage_checkpoint}")
    ledger = BrightDataUsageLedger()
    ledger.configure_usage_checkpoint(usage_checkpoint, restore=True)
    usage = ledger.usage_summary(price_per_1000=namespace["BRIGHT_DATA_PRICE_PER_1000_RESULTS_USD"])
    report = report.rstrip() + namespace["build_bright_data_usage_section"](usage)

    run_timestamp = datetime.fromisoformat(stages["company"]["created_at"])
    prefix = audit_export_prefix(
        run_timestamp, settings["company_name"],
        settings.get("audit_focus", ""), settings["country"],
    )
    markdown_path = directory / report_filename(prefix, "md")
    pdf_path = directory / report_filename(prefix, "pdf")
    json_path = directory / report_filename(prefix, "json")
    zip_path = directory.parent / report_filename(prefix, "zip")

    warnings = []
    if stages["selection"].get("used_fallback"):
        warnings.append("AI competitor validation failed; SERP-ranked fallback was used")
    for engine, result in visibility["engines"].items():
        if result.get("status") == "failed":
            warnings.append(f"{engine.title()} visibility unavailable: {result.get('error') or 'no answer'}")
    warnings.extend(stages["reddit"].get("warnings") or [])
    durations = {
        key: float(stages[stage].get("duration_seconds") or 0)
        for key, stage in (
            ("company_analysis", "company"),
            ("serp_discovery", "serp"),
            ("competitor_selection", "selection"),
            ("brand_profiles", "profiles"),
            ("ai_visibility", "visibility"),
            ("reddit_social", "reddit"),
        )
    }
    durations["final_report"] = time.monotonic() - started
    record = namespace["build_audit_record"](
        run_id=directory.name.removeprefix("competitive-visibility-"),
        run_timestamp=run_timestamp,
        completed_at=datetime.now(timezone.utc),
        total_duration=sum(durations.values()),
        settings=settings,
        include_reddit_analysis=bool(settings.get("include_reddit_analysis")),
        target_profile=target,
        competitor_profiles=competitors,
        keyword_records=[
            namespace["BuyerIntentKeyword"](**item)
            for item in stages["company"]["buyer_intent_keywords"]
        ],
        keyword_serp_results=stages["serp"]["keyword_results"],
        competitor_candidates=[
            namespace["CompetitorCandidate"](**item)
            for item in stages["serp"]["competitor_candidates"]
        ],
        selected_competitors=[
            namespace["BrandAnalysis"](**item)
            for item in stages["selection"]["selected_competitors"]
        ],
        selection_result={
            "rejected": stages["selection"]["rejected_candidates"],
            "used_fallback": stages["selection"].get("used_fallback", False),
        },
        visibility_result=visibility,
        reddit_social_result=stages["reddit"],
        bright_data_usage=usage,
        report_result=report_result,
        final_report=report,
        final_sources=finalized["sources"],
        warnings=warnings,
        stage_durations=durations,
        generator_name=namespace["LAST_UTILITY_REPORT_RESULT"]["engine_name"],
        model_to_dict=namespace["model_to_dict"],
        serialize_engine_result=namespace["serialize_engine_result"],
    )
    record["recovery"] = {"final_export_rebuilt_from_saved_stages": True}
    if canonical_target_domain and canonical_target_domain != saved_settings["company_domain"]:
        record["domain_resolution"] = {
            "submitted_domain": saved_settings["company_domain"],
            "canonical_domain": canonical_target_domain,
            "evidence": "Verified HTTP 301 redirect from the submitted address",
        }
    record["files"] = {
        "output_directory": str(directory),
        "markdown_report": str(markdown_path),
        "pdf_report": str(pdf_path),
        "json_report": str(json_path),
        "zip_archive": str(zip_path),
    }

    namespace["write_text"](markdown_path, report)
    try:
        namespace["create_styled_pdf_report"](
            markdown_text=report,
            output_path=pdf_path,
            company_name=target.brand_name,
            company_url=target.official_url,
            country=settings["country"],
            generated_at=run_timestamp,
        )
    except Exception as exc:
        warnings.append(f"PDF generation failed: {type(exc).__name__}: {exc}")
        record["files"]["pdf_report"] = None
    namespace["write_json"](directory / "06_bright_data_usage.json", usage)
    namespace["write_json"](directory / "raw" / "06_final_report_record.json", report_result["record"])
    namespace["write_json"](json_path, record)
    namespace["create_audit_zip"](directory, zip_path.name)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Audit output directory with stages 1-5")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.local")
    parser.add_argument(
        "--canonical-target-domain",
        help="Verified final official domain when the submitted domain redirects",
    )
    args = parser.parse_args(argv)
    record = finish_saved_audit(
        args.directory, args.env_file, args.canonical_target_domain
    )
    print("Report export completed from saved stages; no provider calls made")
    for name, value in record["files"].items():
        if name != "output_directory" and value:
            print(f"{name}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
