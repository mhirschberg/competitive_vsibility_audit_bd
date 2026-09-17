#!/usr/bin/env python3
"""Rerun only the Reddit stage from a completed local audit."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import _build_runner_script
from scripts.run_local_audit import DEFAULT_ENV_FILE, load_env_file, require_local_settings


def find_audit_json(path):
    path = Path(path).expanduser().resolve()
    if path.is_file():
        return path
    direct = path / "06_competitive_visibility_audit.json"
    if direct.is_file():
        return direct
    matches = sorted(path.glob("competitive-visibility-*/06_competitive_visibility_audit.json"))
    if len(matches) != 1:
        raise FileNotFoundError(
            f"Expected one completed audit JSON below {path}; found {len(matches)}."
        )
    return matches[0]


def find_existing_reddit_result(audit_path, retry_path):
    """Prefer a retry artifact, then reuse the canonical full-run result."""
    retry_path = Path(retry_path)
    if retry_path.is_file():
        return retry_path
    canonical_path = Path(audit_path).parent / "05_reddit_social.json"
    if canonical_path.is_file():
        return canonical_path
    raise FileNotFoundError(
        "Reddit result not found: "
        f"{retry_path} or {canonical_path}"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-run", required=True, type=Path)
    parser.add_argument(
        "--focus",
        default="",
        help="Audit focus override for runs created before focus was stored in JSON",
    )
    parser.add_argument(
        "--reuse-result",
        action="store_true",
        help="Reuse 05_reddit_social.retry.json and only rebuild report artifacts",
    )
    parser.add_argument(
        "--reclassify-fallbacks",
        action="store_true",
        help="Reuse collected cohorts and rerun only failed AI classifications",
    )
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    args = parser.parse_args(argv)

    load_env_file(args.env_file)
    require_local_settings()
    audit_path = find_audit_json(args.from_run)
    cache_directory = audit_path.parent / ".cache"
    cache_directory.mkdir(exist_ok=True)
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_directory))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    configuration = audit["configuration"]
    audit_focus = args.focus.strip() or str(
        configuration.get("audit_focus") or ""
    ).strip()

    runner_source = _build_runner_script(
        configuration["company_name"],
        configuration["company_domain"],
        audit_focus,
        configuration["country"],
        "auto",
        True,
        bool(configuration.get("debug")),
    )
    definitions = runner_source.split("#@title 4. Run Competitive Visibility Audit", 1)[0]
    namespace = {"__name__": "reddit_stage_runtime"}
    exec(compile(definitions, "reddit-stage-runtime", "exec"), namespace)

    profile_model = namespace["BrandProfile"]
    target = profile_model(**audit["profiles"]["target"])
    competitors = [
        profile_model(**item) for item in audit["profiles"]["competitors"]
    ]
    keywords = [item["keyword"] for item in audit["buyer_intent_keywords"]]
    keyword_serp_results = audit["serp"]["keyword_results"]
    measured_engines = [
        str(item.get("engine") or "").strip().lower()
        for item in keyword_serp_results
        if item.get("success") and str(item.get("engine") or "").strip()
    ]
    namespace["ACTIVE_SEARCH_ENGINE"] = (
        measured_engines[0] if measured_engines else None
    )
    namespace["ACTIVE_SEARCH_STATUS"] = (
        "available" if measured_engines else "unavailable"
    )

    output_path = audit_path.parent / "05_reddit_social.retry.json"
    if args.reuse_result or args.reclassify_fallbacks:
        source_path = find_existing_reddit_result(audit_path, output_path)
        result = json.loads(source_path.read_text(encoding="utf-8"))
    else:
        result = asyncio.run(
            namespace["run_reddit_social_stage"](
                target,
                competitors,
                keywords,
                keyword_serp_results,
                audit_focus,
            )
        )
    if args.reclassify_fallbacks:
        result = namespace["reanalyze_reddit_fallback_cohorts"](
            result,
            target,
            competitors,
        )
    result = namespace["normalize_reddit_result_offerings"](result)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    canonical_reddit_path = audit_path.parent / "05_reddit_social.json"
    canonical_reddit_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    audit["reddit_social"] = result
    configuration["audit_focus"] = audit_focus
    old_warnings = audit.get("warnings") or []
    cohort_labels = {
        str(cohort.get("brand") or "").strip()
        for reddit_result in (audit.get("reddit_social") or {}, result)
        for cohort in (reddit_result.get("cohorts") or [])
        if str(cohort.get("brand") or "").strip()
    }
    retained_warnings = [
        warning
        for warning in old_warnings
        if not (
            str(warning).startswith("Reddit ")
            or str(warning).startswith("No Reddit ")
            or any(
                str(warning).startswith(f"{label}: Reddit ")
                for label in cohort_labels
            )
        )
    ]
    audit["warnings"] = list(
        dict.fromkeys(retained_warnings + list(result.get("warnings") or []))
    )

    markdown_path = audit_path.parent / "06_competitive_visibility_audit.md"
    pdf_path = audit_path.parent / "06_competitive_visibility_audit.pdf"
    visibility = dict(audit["ai_visibility"])
    visibility["audited_domains"] = {
        profile.domain: profile.brand_name
        for profile in (target, *competitors)
    }
    report_result = namespace["generate_report_stage"](
        target,
        competitors,
        keywords,
        keyword_serp_results,
        visibility,
    )
    audit["serp"]["metrics"] = report_result["serp_metrics"]
    finalized = namespace["finalize_report"](
        report=report_result["report"],
        visibility=visibility,
    )
    updated_report = namespace["insert_reddit_report_section"](
        finalized["report"],
        result,
    )
    updated_report = namespace["clean_competitive_landscape_profile_links"](
        updated_report
    )
    markdown_path.write_text(updated_report.rstrip() + "\n", encoding="utf-8")
    namespace["create_styled_pdf_report"](
        updated_report,
        pdf_path,
        configuration["company_name"],
        configuration.get("company_url", ""),
        configuration.get("country", ""),
    )
    audit["final_report"] = {
        "generator": report_result.get("generator"),
        "snapshot_id": report_result.get("snapshot_id"),
        "web_search": False,
        "prompt": report_result.get("prompt"),
        "evidence": report_result.get("evidence"),
        "sources": finalized.get("sources", []),
        "markdown": updated_report,
    }
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    namespace["create_audit_zip"](audit_path.parent)

    print(f"status={result.get('status')}")
    print(f"threads={len(result.get('sample', []))}")
    for warning in result.get("warnings", []):
        print(f"warning={warning}")
    print(f"output={output_path}")
    return 0 if result.get("status") in {"success", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
