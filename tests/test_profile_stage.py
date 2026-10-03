"""Profile research and Stage 4 persistence outside the notebook."""

import asyncio
import json
from pathlib import Path
import tempfile
import time
import unittest

from audit_core.profile_research import ProfileResearchPorts, run_profile_research_core
from audit_core.profile_stage import ProfileStagePorts, run_profile_stage_core


class Model:
    def __init__(self, **values):
        self.__dict__.update(values)


def make_profile(job, *, domain=None):
    return Model(
        brand_name=job["brand_name"],
        domain=domain or job["domain"],
        official_url=job["official_url"],
        direct_competitor=job["role"] == "competitor",
    )


class ProfileStageTests(unittest.TestCase):
    def setUp(self):
        self.target = Model(
            brand_name="Apple", domain="apple.com",
            official_url="https://apple.com/",
        )
        self.competitors = [
            Model(brand_name="Samsung", domain="samsung.com",
                  official_url="https://samsung.com/", reason="Phones"),
            Model(brand_name="Galaxy", domain="www.samsung.com",
                  official_url="https://www.samsung.com/", reason="Phones"),
        ]

    def test_pending_profile_recovery_and_fallback_preserve_metrics(self):
        calls, notices = [], []

        def generate(job, target, focus):
            calls.append((job["domain"], target.brand_name, focus))
            if job["brand_name"] == "Samsung":
                return {"job": job, "status": "pending", "profile": None}
            if job["brand_name"] == "Galaxy":
                return {"job": job, "status": "failed", "profile": None}
            return {"job": job, "status": "success", "profile": make_profile(job)}

        def recover(result):
            calls.append(("recover", result["job"]["domain"]))
            return {
                "job": result["job"], "status": "success",
                "profile": make_profile(result["job"]),
            }

        result = asyncio.run(run_profile_research_core(
            self.target, self.competitors, "premium smartphone",
            ports=ProfileResearchPorts(
                generate_profile=generate,
                recover_profile=recover,
                fallback_profile=lambda job, target: make_profile(job),
                root_domain=lambda domain: domain.removeprefix("www."),
                pending_notice=notices.append,
            ),
        ))
        self.assertEqual(notices, [1])
        self.assertIn(("recover", "samsung.com"), calls)
        self.assertEqual(result["successful"], 2)
        self.assertEqual(result["fallbacks"], 1)
        self.assertEqual(len(result["competitor_profiles"]), 1)
        self.assertEqual(len(result["all_profiles"]), 2)
        self.assertEqual(result["task_results"][2]["used_fallback"], True)

    def test_stage_restores_official_target_and_writes_tasks(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            target_profile = make_profile({
                "role": "target", "brand_name": "Apple",
                "domain": "wrong.example", "official_url": "https://wrong.example/",
            })
            competitor_profile = make_profile({
                "role": "competitor", "brand_name": "Samsung",
                "domain": "samsung.com", "official_url": "https://samsung.com/",
            })
            messages, warnings = [], []

            async def run_profiles(**kwargs):
                self.assertEqual(kwargs["audit_focus"], "premium smartphone")
                return {
                    "target_profile": target_profile,
                    "competitor_profiles": [competitor_profile],
                    "all_profiles": [target_profile, competitor_profile],
                    "task_results": [{"status": "success"}, {"status": "failed"}],
                    "successful": 1, "fallbacks": 1,
                }

            def write(path, data):
                path.write_text(json.dumps(data), encoding="utf-8")

            result = asyncio.run(run_profile_stage_core(
                self.target, self.competitors,
                audit_focus="premium smartphone",
                company_domain="apple.com", company_url="https://apple.com/",
                output_directory=output, started_at=time.monotonic(),
                ports=ProfileStagePorts(
                    run_profiles=run_profiles,
                    model_to_dict=lambda item: vars(item).copy(),
                    serialize_task=lambda item: dict(item),
                    write_json=write,
                    stage_success=messages.append,
                    stage_warning=warnings.append,
                ),
            ))
            self.assertIs(result["all_profiles"][0], result["target_profile"])
            self.assertEqual(result["target_profile"].domain, "apple.com")
            self.assertEqual(result["target_profile"].official_url,
                             "https://apple.com/")
            self.assertEqual(messages, ["2/3 profiles available"])
            self.assertEqual(warnings, ["1 profile fallback(s) used"])
            saved = json.loads((output / "04_brand_profiles.json").read_text())
            self.assertEqual(saved["target_profile"]["domain"], "apple.com")
            self.assertEqual(saved["successful_profiles"], 1)
            self.assertEqual(saved["fallback_profiles"], 1)
            self.assertEqual(len(saved["tasks"]), 2)


if __name__ == "__main__":
    unittest.main()
