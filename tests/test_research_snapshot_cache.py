"""Offline contract tests for service-owned research snapshot persistence."""

import json
from pathlib import Path
import tempfile
import unittest

from audit_core.research_snapshot_cache import ResearchSnapshotCache


class ResearchSnapshotCacheTests(unittest.TestCase):
    def test_round_trip_deduplicates_and_restores_reuse_mode(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "raw" / "google_ai_snapshot_cache.json"
            cache = ResearchSnapshotCache()
            cache.configure(path, only_reuse=False)
            cache.remember("prompt", "sd_abc123")
            cache.remember("prompt", "sd_abc123")
            self.assertEqual(cache.cached("prompt"), ["sd_abc123"])
            self.assertFalse(cache.only_reuse)

            resumed = ResearchSnapshotCache()
            resumed.configure(path, only_reuse=True)
            self.assertEqual(resumed.cached("prompt"), ["sd_abc123"])
            self.assertTrue(resumed.only_reuse)
            self.assertEqual(json.loads(path.read_text()), {
                ResearchSnapshotCache.key("prompt"): ["sd_abc123"],
            })

    def test_import_recovers_prompt_from_legacy_input_shape(self):
        with tempfile.TemporaryDirectory() as root:
            cache = ResearchSnapshotCache()
            cache.configure(Path(root) / "cache.json")
            downloaded = []
            recorded = []

            def download(snapshot_id):
                downloaded.append(snapshot_id)
                return [{"input": {"prompt": "recover me"}}]

            count = cache.import_ids(
                "noise sd_abc123 and sd_def456 sd_abc123",
                download_snapshot=download,
                record_recovered=lambda *args: recorded.append(args),
            )
            self.assertEqual(count, 2)
            self.assertEqual(downloaded, ["sd_abc123", "sd_def456"])
            self.assertEqual(cache.cached("recover me"), downloaded)
            self.assertEqual(recorded, [
                ("sd_abc123", 1), ("sd_def456", 1),
            ])

    def test_invalid_cache_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "cache.json"
            path.write_text("[]")
            cache = ResearchSnapshotCache()
            cache.configure(path)
            with self.assertRaisesRegex(ValueError, "cache is invalid"):
                cache.cached("prompt")


if __name__ == "__main__":
    unittest.main()
