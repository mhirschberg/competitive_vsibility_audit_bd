"""Embedded notebook runtime: race independent research providers.

This source is embedded into the notebook by scripts/embed_research_fallback.py.
The measured Google AI Mode answers deliberately keep their own scraper path.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time


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
    """Return the first task-valid ChatGPT/Gemini research record.

    A resumed Google-only audit may poll its saved Google snapshots, but new
    research runs never launch Google AI Mode. This avoids the current outage
    without mislabeling another provider's answer as a Google measurement.
    """
    original_prompt = str(prompt or "").strip()
    if not original_prompt:
        raise ValueError("Research prompt cannot be empty.")
    prompt = localize_google_ai_prompt(original_prompt)

    started_at = time.monotonic()
    task_type = identify_google_ai_research_task(prompt)
    if not _RESEARCH_RACE_SEMAPHORE.acquire(timeout=timeout_seconds):
        raise TimeoutError("Timed out waiting for a research-race slot.")

    try:
        cached = cached_research_snapshot_ids(original_prompt)
        snapshots = [
            (provider, snapshot_id)
            for provider, ids in cached.items()
            for snapshot_id in ids
        ]
        errors = []

        if snapshots:
            self.log(
                f"Resuming {task_type} from {len(snapshots)} saved "
                "research snapshot(s)"
            )
        elif _GOOGLE_AI_ONLY_REUSE:
            raise BrightDataAPIError(
                f"No saved research snapshots for {task_type}; "
                "continuation will not launch replacement requests."
            )
        else:
            self.log(
                f"Starting ChatGPT/Gemini research race for {task_type}"
            )
            with ThreadPoolExecutor(max_workers=len(RESEARCH_PROVIDERS)) as pool:
                futures = {
                    pool.submit(_trigger_research_snapshot, self, provider, prompt): provider
                    for provider in RESEARCH_PROVIDERS
                }
                for future in as_completed(futures):
                    provider = futures[future]
                    try:
                        result = future.result()
                        snapshots.append(result)
                        self.log(f"{provider} research snapshot: {result[1]}")
                    except Exception as exc:
                        errors.append(f"{provider}: {type(exc).__name__}: {exc}")
                        self.log(f"{provider} research trigger failed: {exc}", "yellow")

        if not snapshots:
            raise BrightDataAPIError(
                f"No research snapshots started for {task_type}: "
                + "; ".join(errors)
            )

        remaining = {
            snapshot_id: provider for provider, snapshot_id in snapshots
        }
        snapshot_ids = [snapshot_id for _, snapshot_id in snapshots]
        poll_round = 0

        while remaining:
            if time.monotonic() - started_at >= timeout_seconds:
                raise ResearchRaceTimeoutError(snapshot_ids, timeout_seconds)

            items = list(remaining.items())
            offset = poll_round % len(items)
            items = items[offset:] + items[:offset]
            poll_round += 1

            for snapshot_id, provider in items:
                try:
                    status = str(
                        self.snapshot_status(snapshot_id).get("status", "unknown")
                    ).lower()
                except Exception as exc:
                    self.log(
                        f"Temporary research status error for {snapshot_id}: {exc}",
                        "yellow",
                    )
                    continue

                if status in FAILED_STATUSES:
                    errors.append(f"{provider} {snapshot_id}: {status}")
                    remaining.pop(snapshot_id, None)
                    continue
                if status != "ready":
                    continue

                try:
                    records = self.download_snapshot(snapshot_id)
                except Exception as exc:
                    self.log(
                        f"Temporary research download error for {snapshot_id}: {exc}",
                        "yellow",
                    )
                    continue
                if google_ai_snapshot_is_materializing(records):
                    continue

                self.record_snapshot_results(snapshot_id, len(records))
                for record in records:
                    answer = self.answer_text(record)
                    validation = validate_google_ai_research_answer(answer, prompt)
                    if not validation.get("valid"):
                        errors.append(
                            f"{provider} {snapshot_id}: {validation.get('reason')}"
                        )
                        continue

                    winner = dict(record)
                    cleaned = validation.get("cleaned_answer")
                    if cleaned:
                        winner["answer_text"] = cleaned
                        winner["answer_text_markdown"] = cleaned
                    winner["_research_race"] = {
                        "provider": provider,
                        "task_type": task_type,
                        "winner_snapshot_id": snapshot_id,
                        "all_snapshot_ids": snapshot_ids,
                        "duration_seconds": round(time.monotonic() - started_at, 2),
                    }
                    self.log(
                        f"{provider} won {task_type} research in "
                        f"{winner['_research_race']['duration_seconds']}s"
                    )
                    return winner

                remaining.pop(snapshot_id, None)

            if remaining:
                time.sleep(RESEARCH_POLL_SECONDS)

        raise BrightDataAPIError(
            f"All ChatGPT/Gemini research snapshots failed for {task_type}: "
            + "; ".join(errors)
        )
    finally:
        _RESEARCH_RACE_SEMAPHORE.release()


# The visibility stage explicitly calls google_ai_mode_measured; every other
# existing google_ai_mode call is internal research and uses this race.
BrightDataClient.google_ai_mode_measured = google_ai_mode_market_consistent
BrightDataClient.google_ai_mode = race_research_providers
