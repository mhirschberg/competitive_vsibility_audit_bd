#!/usr/bin/env python3
"""Rerun only the Reddit stage from a completed local audit."""

import argparse
import asyncio
import json
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-run", required=True, type=Path)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    args = parser.parse_args(argv)

    load_env_file(args.env_file)
    require_local_settings()
    audit_path = find_audit_json(args.from_run)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    configuration = audit["configuration"]

    runner_source = _build_runner_script(
        configuration["company_name"],
        configuration["company_domain"],
        "",
        configuration["country"],
        "auto",
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

    result = asyncio.run(
        namespace["run_reddit_social_stage"](
            target,
            competitors,
            keywords,
            keyword_serp_results,
        )
    )
    output_path = audit_path.parent / "05_reddit_social.retry.json"
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"status={result.get('status')}")
    print(f"threads={len(result.get('sample', []))}")
    for warning in result.get("warnings", []):
        print(f"warning={warning}")
    print(f"output={output_path}")
    return 0 if result.get("status") in {"success", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
