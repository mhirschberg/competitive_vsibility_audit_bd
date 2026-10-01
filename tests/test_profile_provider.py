"""Shared profile provider behavior for hosted and notebook runners."""

import json
from pathlib import Path
import unittest

from audit_core.primitives import ensure_string_list, normalize_confidence
from audit_core.profile_provider import (
    build_profile_prompt_core,
    fallback_profile_core,
    generate_profile_sync_core,
    normalize_brand_profile_core,
    recover_profile_sync_core,
)
from notebook_builder import NOTEBOOK, build_notebook


class Model:
    def __init__(self, **values):
        self.__dict__.update(values)


class SnapshotTimeoutError(TimeoutError):
    def __init__(self, snapshot_id):
        super().__init__(f"snapshot {snapshot_id} is pending")
        self.snapshot_id = snapshot_id


class ProviderError(RuntimeError):
    pass


class ProfileProviderTests(unittest.TestCase):
    def setUp(self):
        self.target = Model(brand_name="Rayner")
        self.target_brand = Model(
            brand_name="Rayner", official_url="https://rayner.com/",
            domain="rayner.com", category="IOLs", positioning="Lens maker",
            target_customers=["surgeons"], products=["RayOne"],
            key_features=["optics"], differentiators=["choice"],
            confidence=0.8, evidence=["public product page"],
        )
        self.job = {
            "role": "competitor", "brand_name": "Acme Lenses",
            "official_url": "https://acme.example/", "domain": "acme.example",
            "reason": "Alternative IOL portfolio",
        }

    def normalize(self, data, job):
        return normalize_brand_profile_core(
            data, job, profile_factory=Model,
            normalize_public_url=lambda value: value,
            get_root_domain=lambda value: value.split("/", 1)[0].removeprefix("www."),
            ensure_string_list=ensure_string_list,
            normalize_confidence=normalize_confidence,
        )

    def test_prompt_is_category_focused_and_distinguishes_target_from_competitor(self):
        target_prompt = build_profile_prompt_core(
            {**self.job, "role": "target"}, self.target, "RayOne Galaxy",
        )
        competitor_prompt = build_profile_prompt_core(
            self.job, self.target, "RayOne Galaxy",
        )
        self.assertIn("AUDIT SCOPE — STRICT REQUIREMENT", target_prompt)
        self.assertIn("This is the audited target", target_prompt)
        self.assertIn('"direct_competitor": false', target_prompt)
        self.assertIn("alternative to Rayner", competitor_prompt)
        self.assertIn('"direct_competitor": true', competitor_prompt)

    def test_normalization_cleans_fields_bounds_lists_and_uses_job_role(self):
        profile = self.normalize({
            "brand_name": "[Acme](https://acme.example/)",
            "official_url": "https://www.acme.example/products?utm_source=x",
            "domain": "www.acme.example/path",
            "category": " IOLs ",
            "target_customers": [" surgeons ", "clinics", "buyers", "patients", "researchers", "extra"],
            "relevant_products": ["[Acme lens](https://acme.example/lens)", "Lens 2"],
            "confidence": 85,
            "direct_competitor": False,
        }, self.job)
        self.assertEqual(profile.brand_name, "Acme Lenses")
        self.assertEqual(profile.domain, "acme.example")
        self.assertEqual(profile.category, "IOLs")
        self.assertEqual(len(profile.target_customers), 5)
        self.assertEqual(profile.relevant_products[0], "Acme lens")
        self.assertEqual(profile.confidence, 0.85)
        self.assertTrue(profile.direct_competitor)
        self.assertEqual(profile.competitor_reason, self.job["reason"])

    def test_generation_handles_success_timeout_and_provider_error(self):
        class Client:
            def __init__(self, result=None, error=None):
                self.result = result
                self.error = error

            def google_ai_mode(self, _prompt, timeout_seconds):
                self.assert_timeout = timeout_seconds
                if self.error:
                    raise self.error
                return self.result

            @staticmethod
            def answer_text(record):
                return record["answer_text"]

        record = {"answer_text": json.dumps({"brand_name": "Acme Lenses"})}
        success_client = Client(result=record)
        success = generate_profile_sync_core(
            self.job, self.target, "IOLs", client=success_client,
            parse_ai_json=json.loads, normalize_profile=self.normalize,
            snapshot_timeout_error=SnapshotTimeoutError,
        )
        self.assertEqual(success["status"], "success")
        self.assertEqual(success["profile"].brand_name, "Acme Lenses")
        self.assertEqual(success_client.assert_timeout, 600)
        self.assertIn("IOLs", success["prompt"])

        pending = generate_profile_sync_core(
            self.job, self.target, client=Client(error=SnapshotTimeoutError("s1")),
            parse_ai_json=json.loads, normalize_profile=self.normalize,
            snapshot_timeout_error=SnapshotTimeoutError,
        )
        self.assertEqual((pending["status"], pending["snapshot_id"]), ("pending", "s1"))

        failed = generate_profile_sync_core(
            self.job, self.target, client=Client(error=ProviderError("offline")),
            parse_ai_json=json.loads, normalize_profile=self.normalize,
            snapshot_timeout_error=SnapshotTimeoutError,
        )
        self.assertEqual((failed["status"], failed["error"]), ("failed", "offline"))

    def test_recovery_and_fallback_keep_the_existing_result_shapes(self):
        class Client:
            def wait_for_snapshot(self, snapshot_id, timeout_seconds):
                self.assert_snapshot = (snapshot_id, timeout_seconds)
                return [{"answer_text": ""}, {"answer_text": '{"category":"IOLs"}'}]

            @staticmethod
            def answer_text(record):
                return record["answer_text"]

        pending = {
            "status": "pending", "job": self.job,
            "snapshot_id": "s2", "prompt": "saved prompt",
        }
        client = Client()
        recovered = recover_profile_sync_core(
            pending, client=client, parse_ai_json=json.loads,
            normalize_profile=self.normalize, provider_error=ProviderError,
        )
        self.assertEqual(recovered["status"], "success")
        self.assertEqual(recovered["record"]["answer_text"], '{"category":"IOLs"}')
        self.assertEqual(client.assert_snapshot, ("s2", 600))

        target_fallback = fallback_profile_core(
            {**self.job, "role": "target"}, self.target_brand,
            profile_factory=Model,
        )
        competitor_fallback = fallback_profile_core(
            self.job, self.target_brand, profile_factory=Model,
        )
        self.assertEqual(target_fallback.relevant_products, ["RayOne"])
        self.assertFalse(target_fallback.direct_competitor)
        self.assertTrue(competitor_fallback.direct_competitor)
        self.assertEqual(competitor_fallback.competitor_reason, self.job["reason"])

    def test_notebook_embeds_the_shared_provider_source(self):
        generated = json.loads(build_notebook())
        checked_in = json.loads(Path(NOTEBOOK).read_text(encoding="utf-8"))
        self.assertEqual(generated, checked_in)
        cell = next(
            item for item in generated["cells"]
            if item.get("metadata", {}).get("id") == "final-analysis"
        )
        source = "".join(cell["source"])
        self.assertIn("# AUDIT-PROFILE-PROVIDER: start", source)
        self.assertIn("def generate_profile_sync_core(", source)
        self.assertIn("def generate_profile_sync(job, target_brand", source)
        self.assertIn("return generate_profile_sync_core(", source)


if __name__ == "__main__":
    unittest.main()
