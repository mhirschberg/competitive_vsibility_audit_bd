"""Continue a saved local audit in a new directory without repeating Stages 1–2."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("TLDEXTRACT_CACHE", str(ROOT / "local-runs" / ".cache" / "tldextract"))
sys.path.insert(0, str(ROOT))

from runner_builder import _build_runner_script  # noqa: E402
from scripts.run_local_audit import load_env_file, require_local_settings, slugify  # noqa: E402


CONTINUATION_SETTINGS = (
    "country", "search_engine", "serp_zone", "include_reddit_analysis",
    "reddit_comment_posts_per_cohort", "include_google_ai_mode",
    "include_chatgpt_visibility", "include_gemini_visibility",
    "include_copilot_visibility", "wait_longer_for_google_ai_mode",
    "wait_longer_for_chatgpt", "wait_longer_for_gemini",
    "wait_longer_for_copilot", "debug_mode",
)


def restore_continuation_settings(settings, previous, *, no_copilot=False):
    """Keep all saved audit options unless the caller explicitly disables one."""
    settings = dict(settings)
    settings.update({
        key: previous[key] for key in CONTINUATION_SETTINGS if key in previous
    })
    if no_copilot:
        settings["include_copilot_visibility"] = False
    return settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint", type=Path, help="Incomplete audit directory with Stages 1–2")
    parser.add_argument("--no-copilot", action="store_true")
    parser.add_argument(
        "--env-file", type=Path, default=ROOT / ".env.local",
        help="Local credentials file (defaults to .env.local in this checkout)",
    )
    parser.add_argument(
        "--allow-new-research", action="store_true",
        help="Reuse saved stages, but launch new research snapshots when prompts have changed",
    )
    args = parser.parse_args()
    load_env_file(args.env_file)
    require_local_settings()

    source_dir = args.checkpoint.resolve()
    previous = json.loads((source_dir / "00_run_settings.json").read_text(encoding="utf-8"))
    company = json.loads((source_dir / "01_company_analysis.json").read_text(encoding="utf-8"))
    serp = json.loads((source_dir / "02_serp_results.json").read_text(encoding="utf-8"))
    if any(source_dir.glob("*_competitive_visibility_audit.json")):
        raise ValueError("This audit has already completed; use an incomplete checkpoint.")
    domain_input = previous["company_domain"]
    domain_host = urlparse(domain_input if "://" in domain_input else "https://" + domain_input).hostname
    if not domain_host or domain_host.removeprefix("www.") != company["brand"]["domain"]:
        raise ValueError("Checkpoint company domain does not match its Stage 1 analysis.")
    include_copilot = bool(
        previous.get("include_copilot_visibility", True)
    ) and not args.no_copilot

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "local-runs" / f"continued-{slugify(previous['company_name'])}-{stamp}" / source_dir.name
    output.parent.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source_dir, output)

    source = _build_runner_script(
        previous["company_name"], previous["company_domain"], previous["audit_focus"],
        previous["country"], previous["search_engine"],
        previous.get("include_reddit_analysis", False),
        previous.get("debug_mode", False),
        wait_longer_for_google_ai_mode=previous.get(
            "wait_longer_for_google_ai_mode", False,
        ),
        include_copilot_visibility=include_copilot,
        reddit_comment_posts_per_cohort=previous.get(
            "reddit_comment_posts_per_cohort", 0,
        ),
        include_google_ai_mode=previous.get("include_google_ai_mode", False),
        include_chatgpt_visibility=previous.get("include_chatgpt_visibility", True),
        wait_longer_for_chatgpt=previous.get("wait_longer_for_chatgpt", False),
        include_gemini_visibility=previous.get("include_gemini_visibility", True),
        wait_longer_for_gemini=previous.get("wait_longer_for_gemini", False),
        wait_longer_for_copilot=previous.get("wait_longer_for_copilot", False),
    )
    definitions, marker, _ = source.partition("#@title 4. Run Competitive Visibility Audit")
    if not marker:
        raise RuntimeError("Could not isolate notebook definitions")
    namespace = {"__name__": "__local_continuation__"}
    exec(compile(definitions, "notebook-definitions", "exec"), namespace)
    namespace["LOCKED_TARGET_SCOPE"] = company["locked_target_scope"]
    namespace["ACTIVE_SEARCH_ENGINE"] = serp["keyword_results"][0]["engine"]
    namespace["ACTIVE_SEARCH_STATUS"] = "available"
    namespace["find_latest_audit_to_continue"] = lambda _settings: output
    if args.allow_new_research:
        configure_cache = namespace["configure_google_ai_race_cache"]

        def configure_with_new_research(path, only_reuse=False):
            return configure_cache(path, only_reuse=False)

        namespace["configure_google_ai_race_cache"] = configure_with_new_research
    settings = restore_continuation_settings(
        namespace["AUDIT_SETTINGS"], previous, no_copilot=args.no_copilot,
    )
    settings["continue_last_audit"] = True
    print("Continuing from:", source_dir)
    print("Writing to:", output)
    asyncio.run(namespace["run_competitive_visibility_audit"](settings))
    print("Completed:", output)
    selection = json.loads((output / "03_competitor_selection.json").read_text(encoding="utf-8"))
    print("Selected:", ", ".join(item["brand_name"] for item in selection["selected_competitors"]))


if __name__ == "__main__":
    main()
