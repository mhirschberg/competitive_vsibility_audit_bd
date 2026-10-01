"""Stage 6 social completion persists both measured and disabled states."""

import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from audit_core.social_completion_stage import (
    SocialCompletionPorts, run_social_completion_stage_core,
)
from notebook_builder import SOCIAL_COMPLETION_STAGE_CALL_SOURCE


class SocialCompletionTests(unittest.TestCase):
    def make_ports(self, events, *, warning=""):
        def write(path, data):
            events.append(("write", path.name))
            path.write_text(json.dumps(data), encoding="utf-8")

        return SocialCompletionPorts(
            print_stage=lambda *args: events.append(("stage", *args)),
            stage_success=lambda message: events.append(("success", message)),
            stage_warning=lambda message: events.append(("warning", message)),
            format_duration=lambda seconds: f"{seconds}s",
            summarize_warning=lambda result: warning,
            write_json=write,
        )

    def test_disabled_reddit_keeps_empty_artifacts_without_stage_banner(self):
        with tempfile.TemporaryDirectory() as root:
            events = []
            disabled = {
                "status": "disabled", "mode": "disabled", "sample": [],
                "duration_seconds": 0.0,
            }
            result = asyncio.run(run_social_completion_stage_core(
                None, disabled, include_reddit_analysis=False,
                total_stages=6, output_directory=Path(root),
                ports=self.make_ports(events),
            ))
            self.assertEqual(result["duration_seconds"], 0.0)
            self.assertEqual(result["warnings"], [])
            self.assertFalse(any(item[0] == "stage" for item in events))
            self.assertFalse(any(item[0] == "success" for item in events))
            saved = json.loads((Path(root) / "05_reddit_social.json").read_text())
            self.assertEqual(saved["status"], "disabled")
            manifest = json.loads((
                Path(root) / "05_reddit_snapshot_manifest.json"
            ).read_text())
            self.assertEqual(manifest["snapshots"], [])

    def test_competitive_sample_waits_for_task_and_preserves_warning(self):
        with tempfile.TemporaryDirectory() as root:
            events = []
            sample = {
                "status": "partial", "mode": "competitive",
                "duration_seconds": 8.5, "unique_thread_count": 3,
                "comparison": [{
                    "brand": "Apple", "relevant_posts": 2,
                    "classified_posts": 1, "sample_size": 3,
                }],
                "snapshot_manifest": [{"snapshot_id": "snap-1"}],
                "warnings": ["one cohort unmeasured"],
            }

            async def run():
                async def social():
                    events.append(("task",))
                    return sample

                task = asyncio.create_task(social())
                return await run_social_completion_stage_core(
                    task, None, include_reddit_analysis=True,
                    total_stages=7, output_directory=Path(root),
                    ports=self.make_ports(events, warning="Reddit coverage partial"),
                )

            result = asyncio.run(run())
            self.assertEqual(events[0], ("stage", 6, "Reddit conversation analysis", 7))
            self.assertEqual(events[1], ("task",))
            self.assertEqual(result["duration_seconds"], 8.5)
            self.assertEqual(result["warnings"], ["Reddit coverage partial"])
            success = next(item[1] for item in events if item[0] == "success")
            self.assertIn("Apple: 2 relevant / 1 classified / 3 sampled", success)
            self.assertIn("3 unique thread(s) in 8.5s", success)
            self.assertEqual(json.loads((
                Path(root) / "05_reddit_social.json"
            ).read_text())["warnings"], ["one cohort unmeasured"])
            self.assertEqual(json.loads((
                Path(root) / "05_reddit_snapshot_manifest.json"
            ).read_text())["snapshots"], [{"snapshot_id": "snap-1"}])

    def test_generated_notebook_adapter_propagates_result_and_duration(self):
        with tempfile.TemporaryDirectory() as root:
            events = []
            namespace = {
                "run_social_completion_stage_core": run_social_completion_stage_core,
                "SocialCompletionPorts": SocialCompletionPorts,
                "print_stage": lambda *args: events.append(("stage", *args)),
                "print_stage_success": lambda message: events.append(("success", message)),
                "print_stage_warning": lambda message: events.append(("warning", message)),
                "format_duration": str,
                "summarize_reddit_audit_warning": lambda result: "",
                "write_json": lambda path, data: path.write_text(json.dumps(data)),
            }
            script = (
                "async def adapter(reddit_task, reddit_social_result, "
                "include_reddit_analysis, total_stages, output_directory, "
                "stage_durations, warnings):\n"
                + SOCIAL_COMPLETION_STAGE_CALL_SOURCE
                + "\n    return reddit_social_result\n"
            )
            exec(compile(script, "notebook-social-adapter", "exec"), namespace)

            async def run():
                async def social():
                    return {
                        "status": "success", "mode": "legacy", "sample": [{}],
                        "duration_seconds": 2.0,
                    }

                durations, warnings = {}, []
                result = await namespace["adapter"](
                    asyncio.create_task(social()), None, True, 7,
                    Path(root), durations, warnings,
                )
                return result, durations, warnings

            result, durations, warnings = asyncio.run(run())
            self.assertEqual(result["status"], "success")
            self.assertEqual(durations["reddit_social"], 2.0)
            self.assertEqual(warnings, [])
            self.assertTrue((Path(root) / "05_reddit_social.json").is_file())
            self.assertTrue(any(item[0] == "success" for item in events))


if __name__ == "__main__":
    unittest.main()
