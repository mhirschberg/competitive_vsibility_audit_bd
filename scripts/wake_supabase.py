"""Check or restore a paused Supabase project before a workshop.

Requires a scoped Management API token in SUPABASE_ACCESS_TOKEN. A database
cron or Edge Function cannot restore its own paused project, so this script is
meant to run outside Supabase (locally or via the manual GitHub Action).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://api.supabase.com/v1/projects"


def management_request(ref: str, token: str, method: str = "GET") -> dict:
    request = Request(
        f"{BASE_URL}/{ref}" + ("/restore" if method == "POST" else ""),
        data=b"{}" if method == "POST" else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read()
    except HTTPError as exc:
        # Never print a response body: Supabase errors may contain account data.
        raise RuntimeError(f"Supabase Management API returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("Supabase Management API is unreachable") from exc
    try:
        return json.loads(body) if body else {}
    except ValueError as exc:
        raise RuntimeError("Invalid Supabase Management API response") from exc


def wake_project(ref: str, token: str, *, restore: bool, timeout: int = 600) -> str:
    project = management_request(ref, token)
    status = project.get("status")
    if status == "ACTIVE_HEALTHY":
        return "Project is already active and healthy."
    if status != "INACTIVE":
        raise RuntimeError(f"Project status is {status or 'unknown'}; refusing automatic restore")
    if not restore:
        return "Project is paused. Run again with --restore to wake it."

    management_request(ref, token, "POST")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(10)
        status = management_request(ref, token).get("status")
        if status == "ACTIVE_HEALTHY":
            return "Project restored and healthy."
        if status not in {"INACTIVE", "COMING_UP", "RESTORING", "ACTIVE_UNHEALTHY"}:
            raise RuntimeError(f"Unexpected project status after restore: {status or 'unknown'}")
    raise RuntimeError("Restore was requested but did not become healthy before timeout")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-ref", required=True, help="Supabase project reference")
    parser.add_argument("--restore", action="store_true", help="Restore if paused; default is check only")
    parser.add_argument("--timeout", type=int, default=600, help="Maximum wait in seconds")
    args = parser.parse_args()
    if not args.project_ref.isalnum() or len(args.project_ref) > 40:
        parser.error("Invalid project reference")
    token = os.environ.get("SUPABASE_ACCESS_TOKEN", "").strip()
    if not token:
        parser.error("SUPABASE_ACCESS_TOKEN is required; never pass it as a command argument")
    try:
        print(wake_project(args.project_ref, token, restore=args.restore, timeout=args.timeout))
        return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
