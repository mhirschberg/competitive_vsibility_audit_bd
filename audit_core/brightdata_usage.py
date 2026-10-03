"""Durable Bright Data result accounting shared by service and notebook.

This ledger counts returned records rather than treating every provider call as
one billable result. It has no HTTP or notebook dependency; its owner supplies
snapshot status and download methods when refreshing pending operations.
"""

import gzip
import hashlib
import json
from pathlib import Path
import re
from threading import Lock
import zlib


FAILED_STATUSES = {"failed", "error", "canceled", "cancelled", "aborted"}
DEFAULT_PRICE_PER_1000_RESULTS_USD = 1.5


class BrightDataUsageLedger:
    def __init__(self):
        self._usage_lock = Lock()
        self._usage_events = []
        self._usage_event_counter = 0
        self._usage_checkpoint_path = None
        self._snapshot_cache_directory = None
        self._usage_history_complete = True

    def configure_usage_checkpoint(self, path, restore=False):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._usage_lock:
            self._usage_checkpoint_path = path
            self._snapshot_cache_directory = path.parent / "provider_snapshots"
            if restore and path.exists():
                events = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(events, list):
                    raise ValueError("Usage checkpoint is invalid.")
                self._usage_events = events
                self._usage_event_counter = max(
                    (int(item.get("operation_id", 0)) for item in events),
                    default=0,
                )
                self._usage_history_complete = True
            elif restore:
                self._usage_history_complete = False
            else:
                self._usage_events = []
                self._usage_event_counter = 0
                self._usage_history_complete = True
            self._save_usage_checkpoint_unlocked()

    def _save_usage_checkpoint_unlocked(self):
        path = self._usage_checkpoint_path
        if path is None:
            return
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(
            json.dumps(self._usage_events, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)

    def start_usage_operation(
        self, operation, dataset_id="", input_count=1, expected_result_count=None,
        request_fingerprint=None,
    ):
        with self._usage_lock:
            self._usage_event_counter += 1
            event = {
                "operation_id": self._usage_event_counter,
                "operation": str(operation or "Bright Data operation"),
                "dataset_id": str(dataset_id or ""),
                "request_fingerprint": str(request_fingerprint or "") or None,
                "input_count": max(0, int(input_count or 0)),
                "expected_result_count": (
                    max(0, int(expected_result_count))
                    if expected_result_count is not None else None
                ),
                "snapshot_id": None,
                "status": "started",
                "result_count": None,
            }
            self._usage_events.append(event)
            self._save_usage_checkpoint_unlocked()
            return event["operation_id"]

    @staticmethod
    def request_fingerprint(dataset_id, payload):
        """Return a stable key for matching a retried provider request."""
        encoded = json.dumps(
            {"dataset_id": str(dataset_id or ""), "payload": payload},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def find_reusable_snapshot(self, dataset_id, payload):
        """Find a prior snapshot for this exact request without triggering it."""
        fingerprint = self.request_fingerprint(dataset_id, payload)
        with self._usage_lock:
            matches = [
                item for item in self._usage_events
                if item.get("dataset_id") == str(dataset_id or "")
                and item.get("request_fingerprint") == fingerprint
            ]
        ambiguous = [
            item for item in matches
            if item.get("status") == "started" and not item.get("snapshot_id")
        ]
        if ambiguous:
            raise RuntimeError(
                "A matching provider trigger was interrupted before its snapshot ID "
                "was saved; refusing to create a possible duplicate request."
            )
        reusable = [item for item in matches if item.get("snapshot_id")]
        if not reusable:
            return None
        reusable.sort(key=lambda item: int(item.get("operation_id") or 0))
        return str(reusable[0]["snapshot_id"])

    def cached_snapshot_records(self, snapshot_id):
        """Load already-downloaded snapshot data from the audit's raw cache."""
        if self._snapshot_cache_directory is None:
            return None
        snapshot_id = str(snapshot_id or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", snapshot_id):
            return None
        path = self._snapshot_cache_directory / f"{snapshot_id}.json.gz"
        if not path.is_file():
            return None
        try:
            data = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
        except (
            OSError, EOFError, UnicodeDecodeError, json.JSONDecodeError, zlib.error,
        ):
            return None
        return data if isinstance(data, list) else None

    def cache_snapshot_records(self, snapshot_id, records):
        """Persist downloaded rows atomically so a resumed audit needs no fetch."""
        if self._snapshot_cache_directory is None:
            return False
        snapshot_id = str(snapshot_id or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", snapshot_id):
            return False
        if not isinstance(records, list):
            return False
        directory = self._snapshot_cache_directory
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{snapshot_id}.json.gz"
        temporary = path.with_name(path.name + ".tmp")
        payload = json.dumps(
            records, ensure_ascii=False, separators=(",", ":"), default=str,
        ).encode("utf-8")
        temporary.write_bytes(gzip.compress(payload))
        temporary.replace(path)
        return True

    def update_usage_operation(
        self, operation_id, snapshot_id=None, status=None, result_count=None,
    ):
        with self._usage_lock:
            event = next(
                (
                    item for item in self._usage_events
                    if item["operation_id"] == operation_id
                ),
                None,
            )
            if event is None:
                return
            if snapshot_id:
                event["snapshot_id"] = str(snapshot_id)
            if status:
                event["status"] = str(status)
            if result_count is not None:
                event["result_count"] = max(0, int(result_count))
            self._save_usage_checkpoint_unlocked()

    def record_snapshot_results(self, snapshot_id, result_count):
        if not snapshot_id:
            return
        with self._usage_lock:
            for event in self._usage_events:
                if event.get("snapshot_id") == str(snapshot_id):
                    event["status"] = "success"
                    event["result_count"] = max(0, int(result_count))
            self._save_usage_checkpoint_unlocked()

    def record_recovered_snapshot(self, snapshot_id, result_count, dataset_id=""):
        with self._usage_lock:
            event = next(
                (item for item in self._usage_events
                 if item.get("snapshot_id") == snapshot_id),
                None,
            )
            if event is None:
                self._usage_event_counter += 1
                event = {
                    "operation_id": self._usage_event_counter,
                    "operation": "Google AI Mode recovered snapshot",
                    "dataset_id": dataset_id,
                    "input_count": 1,
                    "expected_result_count": 1,
                    "snapshot_id": snapshot_id,
                    "status": "success",
                    "result_count": max(0, int(result_count)),
                }
                self._usage_events.append(event)
            else:
                event["status"] = "success"
                event["result_count"] = max(0, int(result_count))
            self._save_usage_checkpoint_unlocked()

    def refresh_usage_results(self):
        with self._usage_lock:
            pending = [
                (item["operation_id"], item.get("snapshot_id"))
                for item in self._usage_events
                if item.get("snapshot_id")
                and item.get("result_count") is None
                and item.get("status") not in {"failed", "error"}
            ]
        for operation_id, snapshot_id in pending:
            try:
                status = self.snapshot_status(snapshot_id).get("status")
                if status in FAILED_STATUSES:
                    self.update_usage_operation(operation_id, status="failed")
                    continue
                if status != "ready":
                    continue
                records = self.download_snapshot(snapshot_id)
                materializing = (
                    len(records) == 1
                    and isinstance(records[0], dict)
                    and str(records[0].get("status") or "").lower()
                    in {"building", "collecting", "digesting", "running",
                        "processing", "pending"}
                )
                if not materializing:
                    self.record_snapshot_results(snapshot_id, len(records))
            except Exception:
                continue

    def usage_summary(
        self, price_per_1000=DEFAULT_PRICE_PER_1000_RESULTS_USD,
    ):
        with self._usage_lock:
            events = [dict(item) for item in self._usage_events]
            history_complete = self._usage_history_complete
        confirmed_results = sum(
            int(item["result_count"] or 0)
            for item in events if item.get("result_count") is not None
        )
        accepted = sum(
            1 for item in events
            if item.get("status") in {"triggered", "success"}
        )
        failed = sum(
            1 for item in events
            if item.get("status") in {"failed", "error"}
        )
        expected_pending_results = sum(
            int(item.get("expected_result_count") or 0)
            for item in events
            if item.get("result_count") is None
            and item.get("status") in {"triggered", "success"}
        )
        variable_pending = sum(
            1 for item in events
            if item.get("result_count") is None
            and item.get("expected_result_count") is None
            and item.get("status") in {"started", "triggered", "success"}
        )
        estimated_results = confirmed_results + expected_pending_results
        reddit_results = sum(
            int(item.get("result_count") or 0)
            for item in events
            if str(item.get("operation") or "").startswith("Reddit ")
            and item.get("operation") != "Reddit SERP"
        )
        price = float(price_per_1000)
        return {
            "data_operations_started": len(events),
            "accepted_operations": accepted,
            "confirmed_result_records": confirmed_results,
            "expected_fixed_cardinality_results": expected_pending_results,
            "estimated_billable_result_records": estimated_results,
            "reddit_raw_result_records": reddit_results,
            "variable_output_operations_pending": variable_pending,
            "unconfirmed_operations": variable_pending,
            "failed_operations": failed,
            "price_per_1000_results_usd": price,
            "estimated_cost_usd": round(estimated_results * price / 1000, 6),
            "estimate_is_lower_bound": bool(variable_pending or not history_complete),
            "checkpoint_history_complete": history_complete,
            "events": events,
        }
