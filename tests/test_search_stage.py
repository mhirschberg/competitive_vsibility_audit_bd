"""Stage 2 preserves partial search evidence and AI discovery on resume."""

import asyncio
import json
from pathlib import Path
import tempfile
import time
import unittest

from audit_core.artifact_writes import write_json
from audit_core.search_stage import SearchStagePorts, run_search_stage_core


class Candidate:
    def __init__(self, **values):
        self.__dict__.update(values)


class SearchStageTests(unittest.TestCase):
    def ports(self, run_search, successes, warnings):
        return SearchStagePorts(
            run_search=run_search,
            candidate_factory=Candidate,
            model_to_dict=lambda item: vars(item).copy(),
            write_json=write_json,
            stage_success=successes.append,
            stage_warning=warnings.append,
            format_duration=lambda seconds: f"{seconds:.1f}s",
        )

    def test_partial_search_and_ai_discovery_are_checkpointed(self):
        discovery = {
            "questions": ["find a home", "rent an apartment"],
            "results": [
                {"success": True, "answer": "Example", "citations": []},
                {"success": False, "answer": "", "citations": []},
            ],
            "successful": 1, "failed": 1, "source_candidates": [],
        }
        calls = []

        async def run_search(**kwargs):
            calls.append(kwargs)
            return {
                "keyword_results": [
                    {"keyword": "find a home", "success": True, "results": []},
                    {"keyword": "rent an apartment", "success": False, "results": []},
                ],
                "candidates": [Candidate(brand_name="Portal", domain="portal.es")],
                "successful": 1, "failed": 1, "ai_mode_failed": 1,
                "search_engine": "google", "search_status": "partial",
                "ai_mode_discovery": discovery,
            }

        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            successes, warnings = [], []
            result = asyncio.run(run_search_stage_core(
                ["find a home", "rent an apartment"], "example.com",
                continuing=False, output_directory=output,
                started_at=time.monotonic(),
                ports=self.ports(run_search, successes, warnings),
            ))
            self.assertEqual(calls[0]["target_domain"], "example.com")
            self.assertEqual(result["search_status"], "partial")
            self.assertEqual(result["ai_mode_discovery"], discovery)
            self.assertEqual(len(result["warnings"]), 2)
            self.assertEqual(warnings, result["warnings"])
            saved = json.loads((output / "02_serp_results.json").read_text())
            self.assertEqual(saved["ai_mode_discovery"], discovery)
            self.assertEqual(saved["competitor_candidates"][0]["domain"], "portal.es")
            self.assertIn("1/2 searches completed", successes[0])

    def test_resume_reuses_search_and_restores_ai_mode_results(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            discovery = {"results": [{"success": True, "answer": "saved"}]}
            checkpoint = {
                "keyword_results": [{"keyword": "phone", "success": True}],
                "competitor_candidates": [{"brand_name": "Samsung", "domain": "samsung.com"}],
                "successful": 1, "failed": 0, "ai_mode_failed": 0,
                "search_engine": "bing", "search_status": "available",
                "ai_mode_discovery": discovery, "duration_seconds": 47.5,
            }
            (output / "02_serp_results.json").write_text(json.dumps(checkpoint))

            async def should_not_search(**_kwargs):
                self.fail("A resumed Stage 2 must not call the provider")

            result = asyncio.run(run_search_stage_core(
                ["phone"], "apple.com", continuing=True,
                output_directory=output, started_at=0.0,
                ports=self.ports(should_not_search, [], []),
            ))
            self.assertEqual(result["search_engine"], "bing")
            self.assertEqual(result["duration_seconds"], 47.5)
            self.assertEqual(result["ai_mode_discovery"], discovery)
            self.assertEqual(result["candidates"][0].domain, "samsung.com")

    def test_old_checkpoint_without_ai_discovery_remains_resumable(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            checkpoint = {
                "keyword_results": [], "competitor_candidates": [],
                "successful": 0, "failed": 1,
                "search_engine": None, "search_status": "unavailable",
            }
            (output / "02_serp_results.json").write_text(json.dumps(checkpoint))

            async def should_not_search(**_kwargs):
                self.fail("A resumed Stage 2 must not call the provider")

            result = asyncio.run(run_search_stage_core(
                ["phone"], "apple.com", continuing=True,
                output_directory=output, started_at=0.0,
                ports=self.ports(should_not_search, [], []),
            ))
            self.assertIsNone(result["ai_mode_discovery"])
            self.assertEqual(result["warnings"], ["1 SERP request(s) failed"])


if __name__ == "__main__":
    unittest.main()
