"""Native Python entry point for a single hosted audit execution."""

import asyncio
import json
import logging
import os
from pathlib import Path

from hosted.google_redirects import GoogleRedirectResolver
from hosted.service_adapter import (
    build_brightdata_provider, run_with_legacy_runtime,
)
from hosted.service_pdf import create_styled_pdf_report


def build_runtime(settings):
    """Build explicit service ports from worker settings and secret env vars."""
    missing = [
        name for name in ("BRIGHTDATA_API_TOKEN", "SERP_ZONE")
        if not os.getenv(name, "").strip()
    ]
    if missing:
        raise RuntimeError("Missing service secret(s): " + ", ".join(missing))

    client = build_brightdata_provider(
        token=os.environ["BRIGHTDATA_API_TOKEN"],
        serp_zone=os.environ["SERP_ZONE"],
        country=settings.get("country", "US"),
        debug=bool(settings.get("debug_mode", False)),
        logger=lambda message, style="dim": logging.getLogger(
            "competitive_audit"
        ).log(
            logging.WARNING if style in {"warning", "yellow"} else logging.INFO,
            "%s", message,
        ),
    )

    def render_pdf(**kwargs):
        return create_styled_pdf_report(
            **kwargs, audit_focus=settings.get("audit_focus", ""),
        )

    return {
        "bd_client": client,
        "resolve_google_goto_url": GoogleRedirectResolver(),
        "create_styled_pdf_report": render_pdf,
    }


def run_service_audit(settings, *, output_directory):
    """Execute the service-owned coordinator and return its normalized result."""
    runtime = build_runtime(settings)
    return asyncio.run(run_with_legacy_runtime(
        settings, runtime, base_directory=Path(output_directory),
    ))


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )
    settings = json.loads(os.environ["AUDIT_SETTINGS_JSON"])
    output_directory = Path(os.environ["AUDIT_OUTPUT_DIRECTORY"])
    run_service_audit(settings, output_directory=output_directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
