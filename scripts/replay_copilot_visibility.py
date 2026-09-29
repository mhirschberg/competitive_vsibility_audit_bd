"""Measure Copilot using a completed audit's locked scope, without rerunning search.

This is an integration check, not a new full audit. Existing measurements are
preserved and labeled as replayed evidence in the output directory.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("TLDEXTRACT_CACHE", str(ROOT / "local-runs" / ".cache" / "tldextract"))
sys.path.insert(0, str(ROOT))

from scripts.run_local_audit import load_env_file, require_local_settings  # noqa: E402
from app import _build_runner_script  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Completed 06_competitive_visibility_audit.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--snapshot-id", help="Reuse an already triggered Copilot snapshot")
    parser.add_argument("--reuse-existing-copilot", action="store_true", help="Regenerate the report without new API calls")
    args = parser.parse_args()
    load_env_file(ROOT / ".env.local")
    require_local_settings()
    previous = json.loads(args.source.read_text(encoding="utf-8"))
    config = previous["configuration"]
    source = _build_runner_script(
        config["company_name"], config["company_domain"], config.get("audit_focus", ""),
        config["country"], "auto", False, False, include_copilot_visibility=True,
    )
    before_run, marker, _ = source.partition("#@title 4. Run Competitive Visibility Audit")
    if not marker:
        raise RuntimeError("Could not find final audit invocation")
    namespace = {"__name__": "__copilot_replay__"}
    exec(compile(before_run, "notebook-definitions", "exec"), namespace)

    visibility = json.loads(json.dumps(previous["ai_visibility"]))
    profiles = [
        namespace["BrandProfile"](**previous["profiles"]["target"]),
        *[namespace["BrandProfile"](**item) for item in previous["profiles"]["competitors"]],
    ]
    visibility["audited_domains"] = {profile.domain: profile.brand_name for profile in profiles}
    namespace["ACTIVE_SEARCH_ENGINE"] = previous["serp"]["keyword_results"][0]["engine"]
    namespace["ACTIVE_SEARCH_STATUS"] = "available"
    if args.snapshot_id and args.reuse_existing_copilot:
        parser.error("Choose either --snapshot-id or --reuse-existing-copilot")
    if args.snapshot_id:
        client = namespace["bd_client"]
        original_trigger = client.trigger_dataset

        def reuse_snapshot(dataset_id, payload):
            if dataset_id != namespace["COPILOT_DATASET_ID"]:
                return original_trigger(dataset_id, payload)
            return args.snapshot_id

        client.trigger_dataset = reuse_snapshot

    if args.reuse_existing_copilot:
        result = visibility["engines"].get("copilot")
        mentions = visibility["mentions"].get("copilot")
        if not result or not mentions:
            raise ValueError("Source audit has no completed Copilot measurement")
    else:
        result = namespace["bd_client"].race_ai_engine(
            "copilot", visibility["prompt"], redundancy=1, timeout_seconds=360,
        )
        visibility["engines"]["copilot"] = result
        mentions = namespace["find_brand_mentions"](result["answer"], profiles)
        for mention in mentions:
            mention["answer_appearances"] = int(mention["mentioned"])
            mention["answer_total"] = 1
            mention["answer_coverage"] = float(mention["mentioned"])
        visibility["mentions"]["copilot"] = mentions

    report = namespace["build_deterministic_report"](
        target_profile=profiles[0], competitor_profiles=profiles[1:],
        keywords=previous["buyer_intent_keywords"],
        keyword_serp_results=previous["serp"]["keyword_results"],
        serp_metrics=previous["serp"]["metrics"], visibility=visibility,
    )
    report = namespace["finalize_report"](report, visibility)["report"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or ROOT / "local-runs" / f"copilot-replay-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    (output / "copilot-visibility.json").write_text(
        json.dumps({
            "source_audit": str(args.source),
            "note": "Copilot was measured later; other engine/search data are replayed from source audit.",
            "copilot": namespace["serialize_engine_result"](result),
            "mentions": mentions,
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    (output / "comparison.md").write_text(report, encoding="utf-8")
    namespace["create_styled_pdf_report"](
        report, output / "comparison.pdf", profiles[0].brand_name,
        profiles[0].official_url, config["country"],
        datetime.now(timezone.utc).isoformat(),
    )
    print(f"Copilot ready; answer_chars={len(result['answer'])}; sources={len(result['citations'])}")
    print(f"Replay files: {output}")


if __name__ == "__main__":
    main()
