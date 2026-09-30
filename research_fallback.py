"""Embedded notebook runtime: race independent research providers.

This source is embedded into the notebook by scripts/embed_research_fallback.py.
The measured Google AI Mode answers deliberately keep their own scraper path.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

# SERVICE-ONLY-IMPORTS: start
from audit_core.research_race import ResearchRacePorts, race_research_providers_core
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
    """Find both new provider snapshots and old Google-only checkpoints."""
    prompt = localize_google_ai_prompt(prompt)
    found = {
        provider: cached_google_ai_snapshot_ids(
            _research_cache_prompt(provider, prompt)
        )
        for provider in RESEARCH_PROVIDERS
    }
    old_google_ids = cached_google_ai_snapshot_ids(prompt)
    if old_google_ids:
        found["google_ai_mode"] = old_google_ids
    return {provider: ids for provider, ids in found.items() if ids}


def _trigger_research_snapshot(client, provider, prompt):
    dataset_id, payload = client._engine_payload(
        engine=provider,
        prompt=prompt,
        request_index=1,
        web_search=True,
    )
    snapshot_id = client.trigger_dataset(dataset_id, payload)
    remember_google_ai_snapshot(
        _research_cache_prompt(provider, prompt), snapshot_id
    )
    return provider, snapshot_id


def race_research_providers(self, prompt, timeout_seconds=720):
    """Use the shared race while preserving the notebook's snapshot cache."""
    ports = ResearchRacePorts(
        providers=RESEARCH_PROVIDERS,
        cached_snapshot_ids=cached_research_snapshot_ids,
        trigger_snapshot=_trigger_research_snapshot,
        localize_prompt=localize_google_ai_prompt,
        identify_task=identify_google_ai_research_task,
        validate_answer=validate_google_ai_research_answer,
        is_materializing=google_ai_snapshot_is_materializing,
        failed_statuses=FAILED_STATUSES,
        only_reuse=_GOOGLE_AI_ONLY_REUSE,
        semaphore=_RESEARCH_RACE_SEMAPHORE,
        poll_seconds=RESEARCH_POLL_SECONDS,
        error_type=BrightDataAPIError,
        timeout_type=ResearchRaceTimeoutError,
    )
    return race_research_providers_core(self, prompt, timeout_seconds, ports)


# The visibility stage explicitly calls google_ai_mode_measured; every other
# existing google_ai_mode call is internal research and uses this race.
BrightDataClient.google_ai_mode_measured = google_ai_mode_market_consistent
BrightDataClient.google_ai_mode = race_research_providers
