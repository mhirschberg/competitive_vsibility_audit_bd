"""Stage 5 preserves measured answers and concurrent social work."""

import asyncio
import json
from pathlib import Path
import tempfile
import time
import unittest

from audit_core.visibility_checkpoint_stage import (
    VisibilityCheckpointPorts, run_visibility_checkpoint_stage_core,
)


class Model:
    def __init__(self, **values):
        self.__dict__.update(values)


class VisibilityCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.target = Model(brand_name="Apple")
        self.competitor = Model(brand_name="Samsung")

    def run_stage(self, root, ports, *, social=False, prefetch=None):
        return run_visibility_checkpoint_stage_core(
            self.target, [self.competitor], [self.target, self.competitor],
            ["premium smartphone"], [{"keyword": "premium smartphone"}],
            include_copilot=True, include_google_ai_mode=False,
            include_chatgpt=True, include_gemini=True,
            wait_longer_for_chatgpt=True, wait_longer_for_gemini=False,
            wait_longer_for_copilot=False,
            include_reddit_analysis=social, audit_focus="iPhone",
            reddit_prefetch_task=prefetch,
            output_directory=Path(root), started_at=time.monotonic(),
            ports=ports,
        )

    def test_one_failed_engine_keeps_other_measured_results(self):
        with tempfile.TemporaryDirectory() as root:
            calls, successes, warnings = [], [], []

            async def visibility(**kwargs):
                calls.append(kwargs)
                return {
                    "prompt": "Which premium smartphone?",
                    "engines": {
                        "chatgpt": {
                            "status": "success", "engine_name": "ChatGPT",
                            "duration_seconds": 3.5, "answer": "Apple and Samsung",
                        },
                        "gemini": {
                            "status": "failed", "engine_name": "Gemini",
                            "error": "provider unavailable",
                        },
                    },
                    "mentions": {"chatgpt": [{"brand_name": "Apple"}]},
                }

            async def unexpected_social(**kwargs):
                self.fail("Social provider called while disabled")

            result = asyncio.run(self.run_stage(root, VisibilityCheckpointPorts(
                run_visibility=visibility,
                run_reddit_social=unexpected_social,
                serialize_engine_result=lambda item: dict(item),
                write_json=lambda path, data: path.write_text(json.dumps(data)),
                stage_success=successes.append,
                stage_warning=warnings.append,
                format_duration=lambda seconds: f"{seconds}s",
            )))
            self.assertTrue(calls[0]["wait_longer_for_chatgpt"])
            self.assertFalse(calls[0]["include_google_ai_mode"])
            self.assertIsNone(result["reddit_task"])
            self.assertEqual(result["reddit_social_result"]["status"], "disabled")
            self.assertEqual(successes, ["ChatGPT completed in 3.5s"])
            self.assertEqual(warnings, [
                "Gemini visibility failed: provider unavailable"
            ])
            saved = json.loads((Path(root) / "05_ai_visibility.json").read_text())
            self.assertEqual(saved["engines"]["chatgpt"]["answer"],
                             "Apple and Samsung")
            self.assertEqual(saved["engines"]["gemini"]["status"], "failed")
            self.assertEqual(saved["mentions"]["chatgpt"][0]["brand_name"],
                             "Apple")

    def test_social_starts_in_parallel_and_is_not_awaited_by_stage_five(self):
        with tempfile.TemporaryDirectory() as root:
            social_started = asyncio.Event()
            release_social = asyncio.Event()
            events = []
            prefetch = object()

            async def visibility(**kwargs):
                await social_started.wait()
                events.append("visibility finished")
                return {"prompt": "Question", "engines": {}, "mentions": {}}

            async def social(**kwargs):
                self.assertIs(kwargs["discovery_prefetch_task"], prefetch)
                self.assertEqual(kwargs["audit_focus"], "iPhone")
                events.append("social started")
                social_started.set()
                await release_social.wait()
                return {"status": "success"}

            async def run():
                result = await self.run_stage(root, VisibilityCheckpointPorts(
                    run_visibility=visibility,
                    run_reddit_social=social,
                    serialize_engine_result=lambda item: item,
                    write_json=lambda path, data: path.write_text(json.dumps(data)),
                    stage_success=lambda message: None,
                    stage_warning=lambda message: None,
                    format_duration=str,
                ), social=True, prefetch=prefetch)
                self.assertEqual(events, ["social started", "visibility finished"])
                self.assertFalse(result["reddit_task"].done())
                self.assertIsNone(result["reddit_social_result"])
                self.assertTrue((Path(root) / "05_ai_visibility.json").is_file())
                release_social.set()
                self.assertEqual((await result["reddit_task"])["status"], "success")

            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
