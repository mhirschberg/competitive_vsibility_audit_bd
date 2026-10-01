"""Embedded notebook runtime: race independent research providers.

This source is embedded into the notebook by scripts/embed_research_fallback.py.
The measured Google AI Mode answers deliberately keep their own scraper path.
"""

import threading

# SERVICE-ONLY-IMPORTS: start
from audit_core.research_race import ResearchProviderAdapter
from audit_core.research_validation import (
    identify_research_task,
    snapshot_is_materializing,
    validate_research_answer,
)
# SERVICE-ONLY-IMPORTS: end


RESEARCH_PROVIDERS = ("chatgpt", "gemini")
RESEARCH_POLL_SECONDS = 5
_RESEARCH_RACE_SEMAPHORE = threading.BoundedSemaphore(3)


class ResearchRaceTimeoutError(SnapshotTimeoutError):
    def __init__(self, snapshot_ids, timeout_seconds):
        self.snapshot_ids = list(snapshot_ids)
        super().__init__(self.snapshot_ids[0], timeout_seconds)
        self.args = (
            "Research snapshots did not finish within "
            f"{timeout_seconds} seconds; already-triggered IDs: "
            + ", ".join(self.snapshot_ids),
        )


def _research_cache_prompt(provider, prompt):
    return f"research-provider-v1:{provider}:{prompt}"


def cached_research_snapshot_ids(prompt):
    """Compatibility wrapper for the notebook's resume UI and diagnostics."""
    return _research_provider_adapter().cached_snapshots(prompt)


def _trigger_research_snapshot(client, provider, prompt):
    """Compatibility wrapper for callers that trigger one research provider."""
    return _research_provider_adapter()._trigger_snapshot(client, provider, prompt)


def _research_provider_adapter():
    return ResearchProviderAdapter(
        providers=RESEARCH_PROVIDERS,
        cached_snapshot_ids=cached_google_ai_snapshot_ids,
        remember_snapshot=lambda cache_key, snapshot_id: (
            remember_google_ai_snapshot(cache_key, snapshot_id)
        ),
        localize_prompt=localize_google_ai_prompt,
        identify_task=identify_research_task,
        validate_answer=lambda answer, prompt: validate_research_answer(
            answer,
            prompt,
            parse_json=parse_ai_json,
            remove_boilerplate=remove_ai_boilerplate,
        ),
        is_materializing=snapshot_is_materializing,
        failed_statuses=FAILED_STATUSES,
        only_reuse=_GOOGLE_AI_ONLY_REUSE,
        semaphore=_RESEARCH_RACE_SEMAPHORE,
        poll_seconds=RESEARCH_POLL_SECONDS,
        error_type=BrightDataAPIError,
        timeout_type=ResearchRaceTimeoutError,
        legacy_snapshot_ids=cached_google_ai_snapshot_ids,
    )


def race_research_providers(self, prompt, timeout_seconds=720):
    """Use the shared race while preserving the notebook's snapshot cache."""
    return _research_provider_adapter().race(self, prompt, timeout_seconds)


# The visibility stage explicitly calls google_ai_mode_measured; every other
# existing google_ai_mode call is internal research and uses this race.
BrightDataClient.google_ai_mode_measured = google_ai_mode_market_consistent
BrightDataClient.google_ai_mode = race_research_providers
