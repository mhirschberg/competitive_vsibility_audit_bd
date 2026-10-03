"""Effective snapshot transport shared by service and notebook.

The caller owns credentials and usage accounting; these functions only
perform the same HTTP operations and polling as the existing audit.
"""

import json
import time

import requests


GOOGLE_AI_MODE_DATASET_ID = (
    "gd_mcswdt6z2elth3zqr2"
)

GOOGLE_AI_OUTPUT_FIELDS = (
    "prompt,answer_text,citations,answer_text_markdown,timestamp"
)

CHATGPT_DATASET_ID = (
    "gd_m7aof0k82r803d5bjm"
)

GEMINI_DATASET_ID = (
    "gd_mbz66arm2mf9cu856y"
)

COPILOT_DATASET_ID = (
    "gd_m7di5jy6s9geokz8w"
)

BD_REQUEST_URL = (
    "https://api.brightdata.com/request"
)

BD_SCRAPE_URL = (
    "https://api.brightdata.com/datasets/v3/scrape"
)

BD_TRIGGER_URL = (
    "https://api.brightdata.com/datasets/v3/trigger"
)

BD_PROGRESS_URL = (
    "https://api.brightdata.com/datasets/v3/progress"
)

BD_SNAPSHOT_URL = (
    "https://api.brightdata.com/datasets/v3/snapshot"
)

FAILED_STATUSES = {
    "failed",
    "error",
    "canceled",
    "cancelled",
    "aborted",
}

FAILED_STATUSES = {"failed", "error", "canceled", "cancelled", "aborted"}


class BrightDataAPIError(RuntimeError):
    pass


class SnapshotTimeoutError(TimeoutError):
    def __init__(
        self,
        snapshot_id,
        timeout_seconds,
    ):
        self.snapshot_id = snapshot_id
        self.timeout_seconds = (
            timeout_seconds
        )

        super().__init__(
            f"Snapshot {snapshot_id} did not finish "
            f"within {timeout_seconds} seconds."
        )


def decode_bright_data_response(
    response,
    context,
):
    """
    Decode JSON, JSON text, or NDJSON from a Bright Data response.
    """
    text = (
        response.text
        if response is not None
        else ""
    )

    text = str(
        text or ""
    ).strip()

    if not text:
        raise BrightDataAPIError(
            f"{context} returned an empty response. "
            f"HTTP status: "
            f"{getattr(response, 'status_code', 'unknown')}"
        )

    try:
        return response.json()
    except Exception:
        pass

    try:
        return json.loads(text)
    except Exception:
        pass

    # Some endpoints can return newline-delimited JSON.
    ndjson_records = []

    for line in text.splitlines():
        line = line.strip()

        if not line:
            continue

        try:
            ndjson_records.append(
                json.loads(line)
            )
        except Exception:
            ndjson_records = []
            break

    if ndjson_records:
        return ndjson_records

    raise BrightDataAPIError(
        f"{context} did not return valid JSON. "
        f"HTTP status: "
        f"{getattr(response, 'status_code', 'unknown')}. "
        f"Response preview: {text[:1000]}"
    )


def reliable_snapshot_status(
    self,
    snapshot_id,
):
    """
    Snapshot status that treats temporary empty/non-JSON responses as
    unknown rather than crashing the audit.
    """
    try:
        response = requests.get(
            f"{BD_PROGRESS_URL}/"
            f"{snapshot_id}",
            headers=self.headers,
            timeout=30,
        )

        if not response.ok:
            return {
                "status": "unknown",
                "details": (
                    response.text[:1000]
                ),
            }

        data = decode_bright_data_response(
            response,
            context=(
                f"Progress endpoint for "
                f"{snapshot_id}"
            ),
        )

        if not isinstance(data, dict):
            return {
                "status": "unknown",
                "details": data,
            }

        return {
            "status": str(
                data.get(
                    "status",
                    "unknown",
                )
            ).lower(),
            "details": data,
        }

    except Exception as exc:
        self.log(
            f"Temporary progress error for "
            f"{snapshot_id}: {exc}",
            "yellow",
        )

        return {
            "status": "unknown",
            "details": str(exc),
        }


def reliable_download_snapshot(
    self,
    snapshot_id,
    attempts=4,
):
    """
    Retry temporarily empty or non-JSON snapshot downloads.
    """
    last_error = None

    for attempt in range(
        1,
        attempts + 1,
    ):
        try:
            response = requests.get(
                f"{BD_SNAPSHOT_URL}/"
                f"{snapshot_id}",
                headers=self.headers,
                params={"format": "json"},
                timeout=90,
            )

            if not response.ok:
                raise BrightDataAPIError(
                    f"Snapshot download failed. "
                    f"HTTP {response.status_code}: "
                    f"{response.text[:1500]}"
                )

            data = (
                decode_bright_data_response(
                    response,
                    context=(
                        f"Snapshot download "
                        f"{snapshot_id}"
                    ),
                )
            )

            records = (
                self.normalize_records(
                    data
                )
            )

            if not records:
                raise BrightDataAPIError(
                    "Snapshot download returned "
                    "no records."
                )

            return records

        except Exception as exc:
            last_error = exc

            self.log(
                f"Snapshot download attempt "
                f"{attempt}/{attempts} failed "
                f"for {snapshot_id}: {exc}",
                "yellow",
            )

            if attempt < attempts:
                time.sleep(
                    attempt * 3
                )

    raise BrightDataAPIError(
        f"Could not download snapshot "
        f"{snapshot_id} after "
        f"{attempts} attempts: "
        f"{last_error}"
    )


def reliable_trigger_dataset(
    self,
    dataset_id,
    payload,
):
    payload_items = (
        payload.get("input")
        if isinstance(payload, dict)
        else payload
    )
    usage_operation_id = self.start_usage_operation(
        "Dataset trigger",
        dataset_id=dataset_id,
        request_fingerprint=(
            self.request_fingerprint(dataset_id, payload)
            if callable(getattr(self, "request_fingerprint", None)) else None
        ),
        input_count=(
            len(payload_items)
            if isinstance(payload_items, list)
            else 1
        ),
        expected_result_count=(
            len(payload_items)
            if (
                isinstance(payload_items, list)
                and dataset_id in {
                    GOOGLE_AI_MODE_DATASET_ID,
                    CHATGPT_DATASET_ID,
                    GEMINI_DATASET_ID,
                    COPILOT_DATASET_ID,
                }
            )
            else (
                1
                if dataset_id in {
                    GOOGLE_AI_MODE_DATASET_ID,
                    CHATGPT_DATASET_ID,
                    GEMINI_DATASET_ID,
                    COPILOT_DATASET_ID,
                }
                else None
            )
        ),
    )
    response = requests.post(
        BD_TRIGGER_URL,
        headers=self.headers,
        params={
            "dataset_id": dataset_id,
            "format": "json",
            "include_errors": "true",
        },
        json=payload,
        timeout=60,
    )

    if not response.ok:
        self.update_usage_operation(
            usage_operation_id,
            status="failed",
        )
        raise BrightDataAPIError(
            f"Snapshot trigger failed. "
            f"HTTP {response.status_code}: "
            f"{response.text[:2000]}"
        )

    data = decode_bright_data_response(
        response,
        context=(
            f"Snapshot trigger for "
            f"{dataset_id}"
        ),
    )

    snapshot_id = (
        data.get("snapshot_id")
        if isinstance(data, dict)
        else None
    )

    if not snapshot_id:
        self.update_usage_operation(
            usage_operation_id,
            status="failed",
        )
        raise BrightDataAPIError(
            "Snapshot trigger did not "
            f"return snapshot_id: {data}"
        )

    self.update_usage_operation(
        usage_operation_id,
        snapshot_id=snapshot_id,
        status="triggered",
    )
    return snapshot_id


def reliable_scrape_dataset(
    self,
    dataset_id,
    payload,
    timeout_seconds=600,
    custom_output_fields=None,
):
    payload_items = (
        payload.get("input")
        if isinstance(payload, dict)
        else payload
    )
    usage_operation_id = self.start_usage_operation(
        "Dataset scrape",
        dataset_id=dataset_id,
        input_count=(
            len(payload_items)
            if isinstance(payload_items, list)
            else 1
        ),
        expected_result_count=(
            len(payload_items)
            if (
                isinstance(payload_items, list)
                and dataset_id in {
                    GOOGLE_AI_MODE_DATASET_ID,
                    CHATGPT_DATASET_ID,
                    GEMINI_DATASET_ID,
                    COPILOT_DATASET_ID,
                }
            )
            else (
                1
                if dataset_id in {
                    GOOGLE_AI_MODE_DATASET_ID,
                    CHATGPT_DATASET_ID,
                    GEMINI_DATASET_ID,
                    COPILOT_DATASET_ID,
                }
                else None
            )
        ),
    )
    params = {
        "dataset_id": dataset_id,
        "format": "json",
        "notify": "false",
        "include_errors": "true",
    }

    if custom_output_fields:
        params[
            "custom_output_fields"
        ] = custom_output_fields

    response = requests.post(
        BD_SCRAPE_URL,
        headers=self.headers,
        params=params,
        json=payload,
        timeout=90,
    )

    if response.status_code not in {
        200,
        202,
    }:
        self.update_usage_operation(
            usage_operation_id,
            status="failed",
        )
        raise BrightDataAPIError(
            f"Dataset request failed. "
            f"HTTP {response.status_code}: "
            f"{response.text[:2000]}"
        )

    data = decode_bright_data_response(
        response,
        context=(
            f"Dataset request for "
            f"{dataset_id}"
        ),
    )

    if (
        isinstance(data, dict)
        and data.get("snapshot_id")
    ):
        snapshot_id = data[
            "snapshot_id"
        ]
        self.update_usage_operation(
            usage_operation_id,
            snapshot_id=snapshot_id,
            status="triggered",
        )

        self.log(
            f"Continuing snapshot "
            f"{snapshot_id}"
        )

        return self.wait_for_snapshot(
            snapshot_id,
            timeout_seconds=(
                timeout_seconds
            ),
        )

    records = self.normalize_records(data)
    self.update_usage_operation(
        usage_operation_id,
        status="success",
        result_count=len(records),
    )
    return records


def wait_for_snapshot(
        self,
        snapshot_id,
        timeout_seconds=600,
        poll_seconds=5,
    ):
        started_at = time.monotonic()
        last_debug_log = -30

        while True:
            elapsed = (
                time.monotonic()
                - started_at
            )

            if elapsed >= timeout_seconds:
                raise SnapshotTimeoutError(
                    snapshot_id,
                    timeout_seconds,
                )

            status_result = (
                self.snapshot_status(
                    snapshot_id
                )
            )

            status = status_result[
                "status"
            ]

            if (
                self.debug
                and elapsed
                - last_debug_log
                >= 30
            ):
                self.log(
                    f"Snapshot {snapshot_id}: "
                    f"{status} — "
                    f"{elapsed:.0f}s"
                )

                last_debug_log = elapsed

            if status == "ready":
                records = (
                    self.download_snapshot(
                        snapshot_id
                    )
                )

                # A ready snapshot can briefly return
                # a materialization-status object.
                if (
                    len(records) == 1
                    and isinstance(
                        records[0],
                        dict,
                    )
                    and str(
                        records[0].get(
                            "status",
                            "",
                        )
                    ).lower()
                    in {
                        "building",
                        "collecting",
                        "digesting",
                        "running",
                    }
                ):
                    time.sleep(
                        poll_seconds
                    )
                    continue

                self.record_snapshot_results(
                    snapshot_id,
                    len(records),
                )
                return records

            if status in FAILED_STATUSES:
                raise BrightDataAPIError(
                    f"Snapshot {snapshot_id} "
                    f"ended with status "
                    f"{status}."
                )

            time.sleep(poll_seconds)
