"""Re-evaluate Stage 3 from a saved audit without starting paid snapshots."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("TLDEXTRACT_CACHE", str(ROOT / "local-runs" / ".cache" / "tldextract"))
sys.path.insert(0, str(ROOT))

from runner_builder import _build_runner_script  # noqa: E402
from scripts.run_local_audit import load_env_file, require_local_settings  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint", type=Path, help="Directory containing Stages 1–2 and raw snapshot cache")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    load_env_file(ROOT / ".env.local")
    require_local_settings()

    checkpoint = args.checkpoint.resolve()
    company = json.loads((checkpoint / "01_company_analysis.json").read_text(encoding="utf-8"))
    serp = json.loads((checkpoint / "02_serp_results.json").read_text(encoding="utf-8"))
    settings = json.loads((checkpoint / "00_run_settings.json").read_text(encoding="utf-8"))
    source = _build_runner_script(
        settings["company_name"], settings["company_domain"], settings["audit_focus"],
        settings["country"], settings["search_engine"],
        settings.get("include_reddit_analysis", False), False,
        include_copilot_visibility=False,
    )
    definitions, marker, _ = source.partition("#@title 4. Run Competitive Visibility Audit")
    if not marker:
        raise RuntimeError("Could not isolate notebook definitions")
    namespace = {"__name__": "__stage3_replay__"}
    exec(compile(definitions, "notebook-definitions", "exec"), namespace)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or ROOT / "local-runs" / f"stage3-replay-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    (output / "raw").mkdir()
    namespace["LOCKED_TARGET_SCOPE"] = company["locked_target_scope"]
    namespace["CURRENT_AUDIT_OUTPUT_DIRECTORY"] = output
    namespace["configure_google_ai_race_cache"](
        checkpoint / "raw" / "google_ai_snapshot_cache.json", only_reuse=True,
    )
    target = namespace["BrandAnalysis"](**company["brand"])
    candidates = [
        namespace["CompetitorCandidate"](**item)
        for item in serp["competitor_candidates"]
    ]
    keywords = [item["keyword"] for item in company["buyer_intent_keywords"]]
    result = namespace["select_competitors_stage"](target, candidates, keywords)
    summary = {
        "source_checkpoint": str(checkpoint),
        "no_new_snapshots": True,
        "selected": [namespace["model_to_dict"](item) for item in result["selected"]],
        "rejected": result.get("rejected", []),
    }
    (output / "selection.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    print("Selected:", ", ".join(item["brand_name"] for item in summary["selected"]))
    print("Diagnostics:", output)


if __name__ == "__main__":
    main()
