"""Race utility-only ChatGPT and Gemini snapshots without notebook globals."""

import json
import threading
import time
from concurrent.futures import (
    ThreadPoolExecutor as UtilityThreadPoolExecutor,
    as_completed as utility_as_completed,
    TimeoutError as UtilityFuturesTimeoutError,
)


_UTILITY_AI_RACE_ENGINES = ("gemini", "chatgpt")


def _utility_ai_build_engine_request(engine, prompt, dataset_ids):
    """Build provider-specific, country-free Bright Data utility payloads."""
    engine = str(engine or "").strip().lower()
    if engine == "chatgpt":
        item = {
            "url": "https://chatgpt.com/",
            "prompt": prompt,
            "index": 1,
            "web_search": False,
        }
        return {
            "engine": engine,
            "engine_name": "ChatGPT",
            "dataset_id": dataset_ids[engine],
            "payload": [item],
        }
    if engine == "gemini":
        item = {
            "url": "https://gemini.google.com/",
            "prompt": prompt,
            "index": 1,
        }
        return {
            "engine": engine,
            "engine_name": "Gemini",
            "dataset_id": dataset_ids[engine],
            "payload": {"input": [item]},
        }
    raise ValueError(f"Unsupported utility AI engine: {engine}")


def _utility_ai_normalize_validation_result(validation_result):
    """Allow validators to return either a bool or a result dictionary."""
    if isinstance(validation_result, dict):
        return {
            **validation_result,
            "valid": bool(validation_result.get("valid", False)),
        }
    return {
        "valid": bool(validation_result),
        "reason": f"Validator returned {bool(validation_result)}",
    }


def _utility_ai_snapshot_is_materializing(records):
    """A ready snapshot can briefly return a materialization-status record."""
    if len(records) != 1 or not isinstance(records[0], dict):
        return False
    status = str(records[0].get("status", "")).strip().lower()
    return status in {
        "building", "collecting", "digesting", "running",
        "processing", "pending",
    }


def _failure(request, snapshot_id, status, reason, started_at, error=None):
    return {
        "engine": request["engine"],
        "engine_name": request["engine_name"],
        "status": status,
        "snapshot_id": snapshot_id,
        "answer": "",
        "record": None,
        "validation": {"valid": False, "reason": reason},
        "duration_seconds": round(time.monotonic() - started_at, 2),
        "error": error or reason,
    }


def _utility_ai_poll_snapshot(
    client, request, snapshot_id, validator, timeout_seconds,
    stop_event, started_at, failed_statuses, poll_seconds,
):
    """Poll until a validated answer, terminal failure, timeout, or race loss."""
    engine_name = request["engine_name"]
    invalid_reasons = []
    while not stop_event.is_set():
        elapsed = time.monotonic() - started_at
        if elapsed >= timeout_seconds:
            return _failure(
                request, snapshot_id, "timeout",
                f"Timed out after {timeout_seconds} seconds.", started_at,
                f"{engine_name} utility snapshot timed out after {timeout_seconds} seconds.",
            )

        status_result = client.snapshot_status(snapshot_id)
        status = str(status_result.get("status", "unknown")).lower()
        if status in failed_statuses:
            return _failure(
                request, snapshot_id, "failed",
                f"Snapshot ended with status {status}.", started_at,
                f"{engine_name} snapshot {snapshot_id} ended with status {status}.",
            )
        if status != "ready":
            stop_event.wait(poll_seconds)
            continue

        try:
            records = client.download_snapshot(snapshot_id)
        except Exception as exc:
            client.log(
                f"{engine_name} utility snapshot download failed temporarily: {exc}",
                "yellow",
            )
            stop_event.wait(poll_seconds)
            continue

        if _utility_ai_snapshot_is_materializing(records):
            stop_event.wait(poll_seconds)
            continue

        client.record_snapshot_results(snapshot_id, len(records))
        answer_found = False
        for record in records:
            answer = client.answer_text(record)
            if not answer:
                continue
            answer_found = True
            try:
                validation = _utility_ai_normalize_validation_result(validator(answer))
            except Exception as exc:
                validation = {
                    "valid": False,
                    "reason": f"Validator raised {type(exc).__name__}: {exc}",
                }
            if validation["valid"]:
                return {
                    "engine": request["engine"],
                    "engine_name": engine_name,
                    "status": "success",
                    "snapshot_id": snapshot_id,
                    "answer": validation.get("cleaned_answer") or answer,
                    "record": record,
                    "validation": validation,
                    "duration_seconds": round(time.monotonic() - started_at, 2),
                    "error": None,
                }
            invalid_reasons.append(validation.get("reason", "Validation failed"))

        if answer_found:
            reason = "; ".join(invalid_reasons[-3:]) or "Answer failed validation."
            return _failure(
                request, snapshot_id, "invalid", reason, started_at,
                f"{engine_name} returned an answer that failed validation.",
            )
        return _failure(
            request, snapshot_id, "invalid",
            "Snapshot returned no answer text.", started_at,
            f"{engine_name} snapshot returned no answer text.",
        )

    return _failure(
        request, snapshot_id, "stopped", "Another utility engine won.", started_at,
        "Polling stopped because another utility engine won.",
    )


def race_utility_ai_core(
    client, prompt, *, validator, timeout_seconds, task_name,
    dataset_ids, failed_statuses, error_type=RuntimeError, poll_seconds=3,
):
    """Trigger both utility providers; only a validator-approved answer wins."""
    prompt = str(prompt or "").strip()
    if not prompt:
        raise ValueError("Utility AI prompt cannot be empty.")
    if len(prompt) > 4096:
        raise ValueError(f"Utility AI prompt is too long: {len(prompt)} characters.")
    if not callable(validator):
        raise TypeError("Utility AI validator must be callable.")
    if timeout_seconds <= 0:
        raise ValueError("Utility AI timeout must be positive.")

    started_at = time.monotonic()
    requests = {
        engine: _utility_ai_build_engine_request(engine, prompt, dataset_ids)
        for engine in _UTILITY_AI_RACE_ENGINES
    }
    snapshot_ids, trigger_errors = {}, {}
    client.log(f"Starting Gemini + ChatGPT race for {task_name}")

    with UtilityThreadPoolExecutor(max_workers=len(requests)) as pool:
        futures = {
            pool.submit(client.trigger_dataset, request["dataset_id"], request["payload"]): engine
            for engine, request in requests.items()
        }
        for future in utility_as_completed(futures):
            engine = futures[future]
            try:
                snapshot_id = future.result()
                snapshot_ids[engine] = snapshot_id
                client.log(
                    f"[{task_name}] {requests[engine]['engine_name']} utility snapshot: {snapshot_id}"
                )
            except Exception as exc:
                trigger_errors[engine] = f"{type(exc).__name__}: {exc}"
                client.log(
                    f"{requests[engine]['engine_name']} utility trigger failed: {exc}",
                    "yellow",
                )

    if not snapshot_ids:
        raise error_type(
            "Both Gemini and ChatGPT utility triggers failed. "
            + json.dumps(trigger_errors, ensure_ascii=False)
        )

    stop_event = threading.Event()
    poll_executor = UtilityThreadPoolExecutor(max_workers=len(snapshot_ids))
    poll_futures = {
        poll_executor.submit(
            _utility_ai_poll_snapshot, client, requests[engine], snapshot_id,
            validator, timeout_seconds, stop_event, started_at,
            failed_statuses, poll_seconds,
        ): engine
        for engine, snapshot_id in snapshot_ids.items()
    }
    completed_results, winner = [], None
    try:
        for future in utility_as_completed(poll_futures, timeout=timeout_seconds + 30):
            engine = poll_futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = _failure(
                    requests[engine], snapshot_ids.get(engine), "failed",
                    f"{type(exc).__name__}: {exc}", started_at, str(exc),
                )
            completed_results.append(result)
            if result.get("status") == "success" and result.get("validation", {}).get("valid"):
                winner = result
                stop_event.set()
                break
    except UtilityFuturesTimeoutError:
        stop_event.set()
    finally:
        poll_executor.shutdown(wait=False, cancel_futures=True)

    if winner is None:
        summary = [
            {
                "engine": result.get("engine_name"),
                "snapshot_id": result.get("snapshot_id"),
                "status": result.get("status"),
                "reason": result.get("validation", {}).get("reason"),
                "error": result.get("error"),
            }
            for result in completed_results
        ]
        summary.extend(
            {
                "engine": requests[engine]["engine_name"],
                "status": "trigger_failed",
                "reason": error,
                "error": error,
            }
            for engine, error in trigger_errors.items()
        )
        raise error_type(
            f"Neither Gemini nor ChatGPT returned a valid result for {task_name}. "
            + json.dumps(summary, ensure_ascii=False)
        )

    winner["task_name"] = task_name
    winner["all_snapshot_ids"] = {
        engine: snapshot_ids.get(engine) for engine in _UTILITY_AI_RACE_ENGINES
    }
    winner["trigger_errors"] = trigger_errors
    winner["race_duration_seconds"] = round(time.monotonic() - started_at, 2)
    client.log(
        f"{winner['engine_name']} won the {task_name} race in "
        f"{winner['race_duration_seconds']}s"
    )
    return winner


__all__ = [
    "race_utility_ai_core",
]
