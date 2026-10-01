#!/usr/bin/env python3
"""Run the audit notebook headlessly with local, uncommitted credentials."""

import argparse
import json
import os
import re
import resource
import subprocess
import sys
import threading
import time
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
    parser.add_argument(
        "--include-reddit",
        action="store_true",
        help=(
            "Include the optional Reddit conversation analysis; this may add "
            "up to 10 minutes and uses additional Bright Data dataset requests"
        ),
    )
    parser.add_argument(
        "--reddit-comment-posts-per-cohort",
        type=int,
        choices=range(0, 11),
        default=0,
        metavar="0-10",
        help=(
            "Reddit posts per group to scrape comments from (default: 0/off). "
            "This does not cap comments returned by each post."
        ),
    )
    parser.add_argument(
        "--no-copilot",
        action="store_true",
        help="Skip the optional Microsoft Copilot AI visibility answer",
    )
    parser.add_argument("--debug", action="store_true", help="Enable notebook debug logs")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--engine-mode", choices=("notebook", "service_adapter"),
        default="notebook", help="Audit coordinator (default: notebook)",
    )
    parser.add_argument(
        "--measure-memory", action="store_true",
        help="Sample peak RSS of this runner and its child processes",
    )
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
        "*_competitive_visibility_audit.zip",
        "competitive-visibility-*.zip",
        "competitive-visibility-*/*_competitive_visibility_audit.pdf",
        "competitive-visibility-*/*_competitive_visibility_audit.md",
        "competitive-visibility-*/*_competitive_visibility_audit.json",
        "competitive-visibility-*/05_reddit_social.json",
    )
    artifacts = []
    for pattern in patterns:
        artifacts.extend(path for path in run_directory.glob(pattern) if path.is_file())
    return sorted(dict.fromkeys(artifacts))


def process_tree_rss_kib(root_pid):
    """Read resident memory for a process and all of its descendants."""
    rows = subprocess.run(
        ["ps", "-A", "-o", "pid=,ppid=,rss="],
        check=True, capture_output=True, text=True,
    ).stdout
    processes = {}
    for line in rows.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        try:
            pid, ppid, rss = map(int, parts)
        except ValueError:
            continue
        processes[pid] = (ppid, rss)
    descendants = {root_pid}
    while True:
        newly_found = {
            pid for pid, (ppid, _) in processes.items()
            if ppid in descendants
        }
        if newly_found <= descendants:
            break
        descendants.update(newly_found)
    return sum(processes[pid][1] for pid in descendants if pid in processes)


def main(argv=None):
    args = build_parser().parse_args(argv)
    load_env_file(args.env_file)
    require_local_settings()

    # Keep the CLI on the lightweight builder path, without loading the web UI.
    sys.path.insert(0, str(ROOT))
    from runner_builder import _build_runner_script, _build_service_runner_script

    builder = (
        _build_service_runner_script
        if args.engine_mode == "service_adapter" else _build_runner_script
    )
    runner_source = builder(
        args.company,
        args.domain,
        args.focus,
        args.country.strip().upper(),
        args.search_engine,
        args.include_reddit,
        args.debug,
        include_copilot_visibility=not args.no_copilot,
        reddit_comment_posts_per_cohort=args.reddit_comment_posts_per_cohort,
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

    started_at = time.monotonic()
    stop_sampling = threading.Event()
    peak_rss_kib = [0]

    def sample_memory():
        while not stop_sampling.is_set():
            try:
                peak_rss_kib[0] = max(
                    peak_rss_kib[0], process_tree_rss_kib(os.getpid())
                )
            except (OSError, subprocess.SubprocessError):
                pass
            stop_sampling.wait(1)

    sampler = None
    if args.measure_memory:
        sampler = threading.Thread(target=sample_memory, daemon=True)
        sampler.start()

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
    finally:
        stop_sampling.set()
        if sampler is not None:
            sampler.join(timeout=5)

    if args.measure_memory:
        child_peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        child_peak_mib = (
            child_peak / (1024 * 1024)
            if sys.platform == 'darwin' else child_peak / 1024
        )
        metrics = {
            "engine_mode": args.engine_mode,
            "elapsed_seconds": round(time.monotonic() - started_at, 2),
            "peak_process_tree_rss_mib": (
                round(peak_rss_kib[0] / 1024, 1) if peak_rss_kib[0] else None
            ),
            "peak_child_rss_mib": round(child_peak_mib, 1),
            "exit_code": return_code,
        }
        (run_directory / "run_metrics.json").write_text(
            json.dumps(metrics, indent=2) + "\n", encoding="utf-8",
        )
        if metrics['peak_process_tree_rss_mib'] is not None:
            print(f"Peak process-tree memory: {metrics['peak_process_tree_rss_mib']} MiB")
        else:
            print(f"Peak runner memory: {metrics['peak_child_rss_mib']} MiB (process-tree sampling unavailable)")

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
