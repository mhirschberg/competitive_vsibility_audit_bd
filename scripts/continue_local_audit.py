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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint", type=Path, help="Incomplete audit directory with Stages 1–2")
    parser.add_argument("--no-copilot", action="store_true")
    parser.add_argument(
        "--allow-new-research", action="store_true",
        help="Reuse saved stages, but launch new research snapshots when prompts have changed",
    )
    args = parser.parse_args()
    load_env_file(ROOT / ".env.local")
    require_local_settings()

    source_dir = args.checkpoint.resolve()
    previous = json.loads((source_dir / "00_run_settings.json").read_text(encoding="utf-8"))
    company = json.loads((source_dir / "01_company_analysis.json").read_text(encoding="utf-8"))
    serp = json.loads((source_dir / "02_serp_results.json").read_text(encoding="utf-8"))
    if (source_dir / "06_competitive_visibility_audit.json").exists():
        raise ValueError("This audit has already completed; use an incomplete checkpoint.")
    domain_input = previous["company_domain"]
    domain_host = urlparse(domain_input if "://" in domain_input else "https://" + domain_input).hostname
    if not domain_host or domain_host.removeprefix("www.") != company["brand"]["domain"]:
        raise ValueError("Checkpoint company domain does not match its Stage 1 analysis.")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "local-runs" / f"continued-{slugify(previous['company_name'])}-{stamp}" / source_dir.name
    output.parent.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source_dir, output)

    source = _build_runner_script(
        previous["company_name"], previous["company_domain"], previous["audit_focus"],
        previous["country"], previous["search_engine"],
        previous.get("include_reddit_analysis", False), False,
        include_copilot_visibility=not args.no_copilot,
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
    settings = dict(namespace["AUDIT_SETTINGS"])
    settings["continue_last_audit"] = True
    settings["include_copilot_visibility"] = not args.no_copilot
    print("Continuing from:", source_dir)
    print("Writing to:", output)
    asyncio.run(namespace["run_competitive_visibility_audit"](settings))
    print("Completed:", output)
    selection = json.loads((output / "03_competitor_selection.json").read_text(encoding="utf-8"))
    print("Selected:", ", ".join(item["brand_name"] for item in selection["selected_competitors"]))


if __name__ == "__main__":
    main()
