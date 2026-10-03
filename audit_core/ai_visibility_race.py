"""The measured ChatGPT/Gemini/Copilot answer race shared with the notebook."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# SERVICE-ONLY-IMPORTS: start
from .brightdata_transport import BrightDataAPIError
# SERVICE-ONLY-IMPORTS: end


AI_VISIBILITY_RACE_ENGINE_NAMES = {
    "chatgpt": "ChatGPT", "gemini": "Gemini", "copilot": "Copilot",
}


def race_ai_visibility_core(
    client, engine, prompt, redundancy=3, timeout_seconds=600, *,
    failed_statuses, canonical_source_url,
):
    """Return the first usable measured answer under its real provider label.

    The client's payload builder owns country compatibility; this core owns
    trigger redundancy, snapshot polling, citations, and result accounting.
    """
    engine_name = AI_VISIBILITY_RACE_ENGINE_NAMES[engine]
    started_at = time.monotonic()

    reuse_snapshot = getattr(client, "find_reusable_snapshot", None)
    request_plans = []
    recovery_failures = []
    for index in range(1, redundancy + 1):
        dataset_id, payload = client._engine_payload(
            engine=engine, prompt=prompt, request_index=index, web_search=True
        )
        snapshot_id = None
        if callable(reuse_snapshot):
            try:
                snapshot_id = reuse_snapshot(dataset_id, payload)
            except Exception as exc:
                recovery_failures.append(str(exc))
        request_plans.append({
            "request_index": index,
            "dataset_id": dataset_id,
            "payload": payload,
            "snapshot_id": snapshot_id,
        })

    if recovery_failures:
        raise BrightDataAPIError(
            f"Could not safely resume {engine_name} snapshots; no replacement "
            f"requests were started. First error: {recovery_failures[0][:500]}"
        )

    def trigger_one(plan):
        return {
            "request_index": plan["request_index"],
            "snapshot_id": client.trigger_dataset(
                plan["dataset_id"], plan["payload"]
            ),
        }

    trigger_results = [
        {
            "request_index": plan["request_index"],
            "snapshot_id": plan["snapshot_id"],
            "resumed": True,
        }
        for plan in request_plans if plan["snapshot_id"]
    ]
    trigger_failures = []
    missing_plans = [plan for plan in request_plans if not plan["snapshot_id"]]
    with ThreadPoolExecutor(max_workers=max(1, len(missing_plans))) as executor:
        futures = [
            executor.submit(trigger_one, plan)
            for plan in missing_plans
        ]
        for future in as_completed(futures):
            try:
                trigger_results.append(future.result())
            except Exception as exc:
                trigger_failures.append(str(exc))
                client.log(f"{engine_name} trigger failed: {exc}", "yellow")

    if not trigger_results:
        transient = any(
            marker in failure.lower()
            for failure in trigger_failures
            for marker in ("429", "500", "502", "503", "504", "timeout")
        )
        if transient:
            for attempt in range(3):
                time.sleep(2 ** (attempt + 1))
                try:
                    trigger_results.append(trigger_one(request_plans[0]))
                    break
                except Exception as exc:
                    trigger_failures.append(str(exc))
                    client.log(
                        f"{engine_name} rescue trigger failed: {exc}", "yellow"
                    )

    if not trigger_results:
        raise BrightDataAPIError(
            f"All {engine_name} triggers failed. First error: "
            f"{trigger_failures[0][:500] if trigger_failures else 'unknown'}"
        )

    if engine == "copilot":
        client.log(f"Copilot snapshot: {trigger_results[0]['snapshot_id']}", "cyan")
    for item in trigger_results:
        if item.get("resumed"):
            client.log(
                f"Reusing saved {engine_name} snapshot "
                f"{item['snapshot_id']} (request {item['request_index']})",
                "cyan",
            )

    invalid_snapshots = set()
    failed_snapshots = set()
    while True:
        elapsed = time.monotonic() - started_at
        if elapsed >= timeout_seconds:
            raise TimeoutError(
                f"No valid {engine_name} snapshot became ready within "
                f"{timeout_seconds}s. Snapshot IDs: "
                f"{[item['snapshot_id'] for item in trigger_results]}"
            )

        for item in trigger_results:
            snapshot_id = item["snapshot_id"]
            if snapshot_id in invalid_snapshots or snapshot_id in failed_snapshots:
                continue
            cache_records = getattr(client, "cached_snapshot_records", None)
            records = (
                cache_records(snapshot_id)
                if callable(cache_records) else None
            )
            if not records:
                status = client.snapshot_status(snapshot_id)["status"]
                if status in failed_statuses:
                    failed_snapshots.add(snapshot_id)
                    continue
                if status != "ready":
                    continue
                records = client.download_snapshot(snapshot_id)

            materializing = (
                len(records) == 1
                and isinstance(records[0], dict)
                and str(records[0].get("status") or "").lower()
                in {"building", "collecting", "digesting", "running",
                    "processing", "pending"}
            )
            if materializing:
                continue

            cache_results = getattr(client, "cache_snapshot_records", None)
            if callable(cache_results):
                try:
                    cache_results(snapshot_id, records)
                except Exception as exc:
                    client.log(
                        f"Could not cache {engine_name} snapshot "
                        f"{snapshot_id}: {exc}", "yellow",
                    )
            client.record_snapshot_results(snapshot_id, len(records))
            for record in records:
                answer = (
                    str(record.get("answer_text") or "").strip()
                    if engine == "copilot" and isinstance(record, dict)
                    else client.answer_text(record)
                )
                if not answer:
                    continue
                citations = (
                    [
                        {**source, "url": canonical_source_url(source.get("url"))}
                        for source in (record.get("sources") or [])
                        if isinstance(source, dict) and source.get("url")
                        and source.get("cited") is not False
                    ]
                    if engine == "copilot"
                    else (record.get("citations") or record.get("search_sources") or [])
                )
                stored_record = (
                    {
                        key: record[key]
                        for key in (
                            "url", "prompt", "answer_text", "sources",
                            "timestamp", "index", "input",
                        )
                        if key in record
                    }
                    if engine == "copilot" else record
                )
                return {
                    "engine": engine,
                    "engine_name": engine_name,
                    "status": "success",
                    "winner_snapshot_id": snapshot_id,
                    "winner_request_index": item["request_index"],
                    "all_snapshot_ids": [
                        trigger["snapshot_id"] for trigger in trigger_results
                    ],
                    "resumed_snapshot_ids": [
                        trigger["snapshot_id"] for trigger in trigger_results
                        if trigger.get("resumed")
                    ],
                    "duration_seconds": round(elapsed, 2),
                    "answer": answer,
                    "record": stored_record,
                    "citations": citations,
                    "web_search_triggered": record.get("web_search_triggered"),
                }

            invalid_snapshots.add(snapshot_id)

        if len(failed_snapshots) + len(invalid_snapshots) >= len(trigger_results):
            raise BrightDataAPIError(
                f"All {engine_name} snapshots failed or returned no answer."
            )
        time.sleep(5)
