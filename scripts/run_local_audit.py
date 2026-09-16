#!/usr/bin/env python3
"""Run the audit notebook headlessly with local, uncommitted credentials."""

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = ROOT / ".env.local"
DEFAULT_OUTPUT_ROOT = ROOT / "local-runs"


def load_env_file(path):
    """Load a small KEY=VALUE file without printing or overwriting secrets."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Local environment file not found: {path}")

    loaded = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid environment entry on line {line_number}.")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f"Invalid environment key on line {line_number}.")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)
        loaded.add(key)
    return loaded


def slugify(value):
    value = re.sub(r"[^a-z0-9]+", "-", str(value).casefold()).strip("-")
    return value[:60] or "audit"


def build_parser():
    parser = argparse.ArgumentParser(
        description="Run the competitive visibility notebook without Colab or Gradio."
    )
    parser.add_argument("--company", required=True, help="Company or brand name")
    parser.add_argument("--domain", required=True, help="Official website or domain")
    parser.add_argument("--focus", default="", help="Optional product/category focus")
    parser.add_argument("--country", default="US", help="Two-letter country code")
    parser.add_argument(
        "--search-engine",
        choices=("auto", "google", "bing", "none"),
        default="auto",
    )
    parser.add_argument("--debug", action="store_true", help="Enable notebook debug logs")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and compile the runner without making Bright Data calls",
    )
    return parser


def require_local_settings():
    missing = [
        name
        for name in ("BRIGHTDATA_API_TOKEN", "SERP_ZONE")
        if not os.getenv(name, "").strip()
    ]
    if missing:
        raise RuntimeError("Missing local setting(s): " + ", ".join(missing))


def create_run_directory(output_root, company):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = Path(output_root).expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    candidate = base / f"{stamp}-{slugify(company)}"
    suffix = 1
    while candidate.exists():
        suffix += 1
        candidate = base / f"{stamp}-{slugify(company)}-{suffix}"
    candidate.mkdir()
    return candidate


def collect_artifacts(run_directory):
    patterns = (
        "competitive-visibility-*.zip",
        "competitive-visibility-*/06_competitive_visibility_audit.pdf",
        "competitive-visibility-*/06_competitive_visibility_audit.md",
        "competitive-visibility-*/06_competitive_visibility_audit.json",
        "competitive-visibility-*/05_reddit_social.json",
    )
    artifacts = []
    for pattern in patterns:
        artifacts.extend(path for path in run_directory.glob(pattern) if path.is_file())
    return sorted(dict.fromkeys(artifacts))


def main(argv=None):
    args = build_parser().parse_args(argv)
    load_env_file(args.env_file)
    require_local_settings()

    # Import only after local settings are loaded. Importing app does not launch Gradio.
    sys.path.insert(0, str(ROOT))
    from app import _build_runner_script

    runner_source = _build_runner_script(
        args.company,
        args.domain,
        args.focus,
        args.country.strip().upper(),
        args.search_engine,
        args.debug,
    )
    compile(runner_source, "local-notebook-runner", "exec")

    if args.dry_run:
        print("✓ Local settings found")
        print("✓ Generated notebook runner compiles")
        print("✓ Dry run complete; no Bright Data calls were made")
        return 0

    run_directory = create_run_directory(args.output_root, args.company)
    runner_path = run_directory / "notebook_runner.py"
    log_path = run_directory / "audit.log"
    runner_path.write_text(runner_source, encoding="utf-8")

    print(f"Run directory: {run_directory}")
    print(f"Log file: {log_path}")
    print()

    child_env = os.environ.copy()
    child_env["PYTHONUNBUFFERED"] = "1"
    cache_directory = run_directory / ".cache"
    cache_directory.mkdir()
    child_env.setdefault("XDG_CACHE_HOME", str(cache_directory))
    process = subprocess.Popen(
        [sys.executable, "-u", str(runner_path)],
        cwd=run_directory,
        env=child_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    try:
        assert process.stdout is not None
        with log_path.open("w", encoding="utf-8") as log_file:
            for line in process.stdout:
                print(line, end="")
                log_file.write(line)
                log_file.flush()
        return_code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait(timeout=15)
        print("\nAudit interrupted.", file=sys.stderr)
        return 130

    artifacts = collect_artifacts(run_directory)
    print()
    if return_code:
        print(f"✗ Audit failed with exit code {return_code}", file=sys.stderr)
        print(f"Full log: {log_path}", file=sys.stderr)
        return return_code

    print("✓ Audit completed")
    for artifact in artifacts:
        print(f"  {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
