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
