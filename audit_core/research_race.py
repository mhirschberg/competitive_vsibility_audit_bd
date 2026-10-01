"""Race saved or newly triggered AI research snapshots without a notebook."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed


class ResearchRacePorts:
    def __init__(
        self, *, providers, cached_snapshot_ids, trigger_snapshot,
        localize_prompt, identify_task, validate_answer, is_materializing,
        failed_statuses, only_reuse, semaphore, poll_seconds,
        error_type, timeout_type,
    ):
        self.providers = providers
        self.cached_snapshot_ids = cached_snapshot_ids
        self.trigger_snapshot = trigger_snapshot
        self.localize_prompt = localize_prompt
        self.identify_task = identify_task
        self.validate_answer = validate_answer
        self.is_materializing = is_materializing
        self.failed_statuses = failed_statuses
        self.only_reuse = only_reuse
        self.semaphore = semaphore
        self.poll_seconds = poll_seconds
        self.error_type = error_type
        self.timeout_type = timeout_type


class ResearchProviderAdapter:
    """Bind an explicit snapshot client and cache to the provider-neutral race.

    This adapter owns the ChatGPT/Gemini-specific snapshot/cache conventions,
    while prompt interpretation, answer validation, throttling, and error
    types are injected by the caller. It has no notebook-global dependencies.
    """

    def __init__(
        self, *, providers, cached_snapshot_ids, remember_snapshot,
        localize_prompt, identify_task, validate_answer, is_materializing,
        failed_statuses, only_reuse, semaphore, poll_seconds,
        error_type, timeout_type, cache_key_prefix="research-provider-v1",
        legacy_snapshot_ids=None,
    ):
        self.providers = tuple(providers)
        self._cached_snapshot_ids = cached_snapshot_ids
        self._remember_snapshot = remember_snapshot
        self._localize_prompt = localize_prompt
        self._identify_task = identify_task
        self._validate_answer = validate_answer
        self._is_materializing = is_materializing
        self._failed_statuses = failed_statuses
        self._only_reuse = only_reuse
        self._semaphore = semaphore
        self._poll_seconds = poll_seconds
        self._error_type = error_type
        self._timeout_type = timeout_type
        self._cache_key_prefix = cache_key_prefix
        self._legacy_snapshot_ids = legacy_snapshot_ids

    def _cache_key(self, provider, localized_prompt):
        return f"{self._cache_key_prefix}:{provider}:{localized_prompt}"

    def cached_snapshots(self, prompt):
        """Load provider-specific checkpoints plus optional legacy checkpoints."""
        localized_prompt = self._localize_prompt(prompt)
        found = {
            provider: self._cached_snapshot_ids(
                self._cache_key(provider, localized_prompt)
            )
            for provider in self.providers
        }
        if self._legacy_snapshot_ids is not None:
            legacy = self._legacy_snapshot_ids(localized_prompt)
            if legacy:
                found["google_ai_mode"] = legacy
        return {provider: ids for provider, ids in found.items() if ids}

    def _trigger_snapshot(self, client, provider, localized_prompt):
        dataset_id, payload = client._engine_payload(
            engine=provider,
            prompt=localized_prompt,
            request_index=1,
            web_search=True,
        )
        snapshot_id = client.trigger_dataset(dataset_id, payload)
        self._remember_snapshot(
            self._cache_key(provider, localized_prompt), snapshot_id
        )
        return provider, snapshot_id

    def race(self, client, prompt, timeout_seconds):
        ports = ResearchRacePorts(
            providers=self.providers,
            cached_snapshot_ids=self.cached_snapshots,
            trigger_snapshot=self._trigger_snapshot,
            localize_prompt=self._localize_prompt,
            identify_task=self._identify_task,
            validate_answer=self._validate_answer,
            is_materializing=self._is_materializing,
            failed_statuses=self._failed_statuses,
            only_reuse=self._only_reuse,
            semaphore=self._semaphore,
            poll_seconds=self._poll_seconds,
            error_type=self._error_type,
            timeout_type=self._timeout_type,
        )
        return race_research_providers_core(
            client, prompt, timeout_seconds, ports
        )


def race_research_providers_core(client, prompt, timeout_seconds, ports):
    """Return the first task-valid answer, retaining the actual provider label."""
    original_prompt = str(prompt or "").strip()
    if not original_prompt:
        raise ValueError("Research prompt cannot be empty.")
    prompt = ports.localize_prompt(original_prompt)

    started_at = time.monotonic()
    task_type = ports.identify_task(prompt)
    if not ports.semaphore.acquire(timeout=timeout_seconds):
        raise TimeoutError("Timed out waiting for a research-race slot.")

    try:
        cached = ports.cached_snapshot_ids(original_prompt)
        snapshots = [
            (provider, snapshot_id)
            for provider, ids in cached.items()
            for snapshot_id in ids
        ]
        errors = []

        if snapshots:
            client.log(
                f"Resuming {task_type} from {len(snapshots)} saved "
                "research snapshot(s)"
            )
        elif ports.only_reuse:
            raise ports.error_type(
                f"No saved research snapshots for {task_type}; "
                "continuation will not launch replacement requests."
            )
        else:
            client.log(f"Starting ChatGPT/Gemini research race for {task_type}")
            with ThreadPoolExecutor(max_workers=len(ports.providers)) as pool:
                futures = {
                    pool.submit(ports.trigger_snapshot, client, provider, prompt):
                    provider for provider in ports.providers
                }
                for future in as_completed(futures):
                    provider = futures[future]
                    try:
                        result = future.result()
                        snapshots.append(result)
                        client.log(f"{provider} research snapshot: {result[1]}")
                    except Exception as exc:
                        errors.append(f"{provider}: {type(exc).__name__}: {exc}")
                        client.log(
                            f"{provider} research trigger failed: {exc}", "yellow"
                        )

        if not snapshots:
            raise ports.error_type(
                f"No research snapshots started for {task_type}: "
                + "; ".join(errors)
            )

        remaining = {snapshot_id: provider for provider, snapshot_id in snapshots}
        snapshot_ids = [snapshot_id for _, snapshot_id in snapshots]
        poll_round = 0

        while remaining:
            if time.monotonic() - started_at >= timeout_seconds:
                raise ports.timeout_type(snapshot_ids, timeout_seconds)

            items = list(remaining.items())
            offset = poll_round % len(items)
            items = items[offset:] + items[:offset]
            poll_round += 1

            for snapshot_id, provider in items:
                try:
                    status = str(
                        client.snapshot_status(snapshot_id).get("status", "unknown")
                    ).lower()
                except Exception as exc:
                    client.log(
                        f"Temporary research status error for {snapshot_id}: {exc}",
                        "yellow",
                    )
                    continue

                if status in ports.failed_statuses:
                    errors.append(f"{provider} {snapshot_id}: {status}")
                    remaining.pop(snapshot_id, None)
                    continue
                if status != "ready":
                    continue

                try:
                    records = client.download_snapshot(snapshot_id)
                except Exception as exc:
                    client.log(
                        f"Temporary research download error for {snapshot_id}: {exc}",
                        "yellow",
                    )
                    continue
                if ports.is_materializing(records):
                    continue

                client.record_snapshot_results(snapshot_id, len(records))
                for record in records:
                    answer = client.answer_text(record)
                    validation = ports.validate_answer(answer, prompt)
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
                    client.log(
                        f"{provider} won {task_type} research in "
                        f"{winner['_research_race']['duration_seconds']}s"
                    )
                    return winner

                remaining.pop(snapshot_id, None)

            if remaining:
                time.sleep(ports.poll_seconds)

        raise ports.error_type(
            f"All ChatGPT/Gemini research snapshots failed for {task_type}: "
            + "; ".join(errors)
        )
    finally:
        ports.semaphore.release()
