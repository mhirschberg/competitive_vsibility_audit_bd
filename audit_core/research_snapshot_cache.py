"""Durable Google AI/research snapshot IDs for fresh and resumed audits."""

import hashlib
import json
from pathlib import Path
import re
from threading import RLock


class ResearchSnapshotCache:
    """Store prompt-to-snapshot mappings without notebook globals."""

    def __init__(self):
        self.path = None
        self.only_reuse = False
        self._lock = RLock()

    @staticmethod
    def key(prompt):
        return hashlib.sha256(str(prompt).encode("utf-8")).hexdigest()

    def configure(self, path, only_reuse=False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.only_reuse = bool(only_reuse)

    def read(self):
        if self.path is None or not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Research snapshot cache is invalid.")
        return data

    def cached(self, prompt):
        with self._lock:
            value = self.read().get(self.key(prompt), [])
            return list(value) if isinstance(value, list) else []

    def remember(self, prompt, snapshot_id):
        if self.path is None or not snapshot_id:
            return
        with self._lock:
            data = self.read()
            ids = data.setdefault(self.key(prompt), [])
            if snapshot_id in ids:
                return
            ids.append(snapshot_id)
            temporary = self.path.with_name(self.path.name + ".tmp")
            temporary.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(self.path)

    def all_ids(self):
        with self._lock:
            return {
                snapshot_id
                for ids in self.read().values()
                if isinstance(ids, list)
                for snapshot_id in ids
            }

    def import_ids(self, snapshot_ids, *, download_snapshot, record_recovered):
        """Recover IDs from provider records, preserving the legacy format."""
        if not snapshot_ids:
            return 0
        known = self.all_ids()
        imported = 0
        ids = dict.fromkeys(re.findall(r"sd_[A-Za-z0-9]+", str(snapshot_ids)))
        for snapshot_id in ids:
            if snapshot_id in known:
                continue
            records = download_snapshot(snapshot_id)
            if not records or not isinstance(records[0], dict):
                continue
            record = records[0]
            original_input = record.get("input") or {}
            prompt = record.get("prompt") or (
                original_input.get("prompt")
                if isinstance(original_input, dict) else None
            )
            if not prompt:
                continue
            self.remember(prompt, snapshot_id)
            record_recovered(snapshot_id, len(records))
            known.add(snapshot_id)
            imported += 1
        return imported
