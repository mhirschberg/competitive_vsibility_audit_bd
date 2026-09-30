"""Replay provider answers through service and bundled-notebook research code."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from audit_core import (
    competitor_decisions, competitor_pipeline, competitor_research,
    competitor_scope,
)
from notebook_builder import (
    COMPETITOR_PIPELINE_END,
    COMPETITOR_PIPELINE_START,
    COMPETITOR_RESEARCH_END,
    COMPETITOR_RESEARCH_START,
    NOTEBOOK,
)


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "competitor_research.json")
    .read_text(encoding="utf-8")
)


def bundled_research():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    cell = next(
        item for item in notebook["cells"]
        if item.get("metadata", {}).get("id") == "runtime-utilities-merged"
    )
    source = "".join(cell["source"])
    embedded = source.split(COMPETITOR_RESEARCH_START, 1)[1].split(
        COMPETITOR_RESEARCH_END, 1
    )[0]
    namespace = {}
    exec(embedded, namespace)
    return SimpleNamespace(**namespace)


def bundled_pipeline():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    cell = next(
        item for item in notebook["cells"]
        if item.get("metadata", {}).get("id") == "runtime-utilities-merged"
    )
    source = "".join(cell["source"])
    embedded = source.split(COMPETITOR_PIPELINE_START, 1)[1].split(
        COMPETITOR_PIPELINE_END, 1
    )[0]
    namespace = {
        name: getattr(competitor_research, name)
        for name in ("run_scope_discovery", "run_scope_validation",
                     "run_scope_validation_batch")
    }
    namespace.update({
        name: getattr(competitor_decisions, name)
        for name in (
            "core_build_locked_candidate_universe",
            "core_build_locked_scope_discovery_prompt",
            "core_build_locked_scope_validation_prompt",
            "core_build_locked_scope_validation_retry_prompt",
            "core_discovery_supports_consistency_retry",
            "core_normalize_locked_scope_validation",
        )
    })
    exec(embedded, namespace)
    return SimpleNamespace(**namespace)


class FixtureProvider:
    def __init__(self, answers=None):
        self.answers = answers or FIXTURE["answers"]
        self.calls = []

    def query_json(self, prompt):
        self.calls.append(prompt)
        parsed = self.answers[prompt]
        record = {
            "snapshot_id": f"fixture-{prompt}",
            "answer_text": json.dumps(parsed),
        }
        return record, json.loads(record["answer_text"])


def normalized(data, candidate, scope):
    return {
        "candidate_name": candidate["brand_name"],
        "candidate_domain": candidate["representative_domain"],
        "official_url": candidate["official_url"],
        "candidate_role": data["candidate_role"],
        "locked_target_role": scope["market_role"],
        "is_direct_competitor": data["is_direct_competitor"],
        "confidence": data["confidence"],
        "market_prominence": data["market_prominence"],
        "reason": data["reason"],
    }


def fixture_pipeline(pipeline_class, provider):
    pipeline = pipeline_class(
        query_json=provider.query_json,
        decision_ports=None,
        local_domain_bonus=lambda *_args: 0,
        validation_workers=3,
    )
    pipeline.discovery_prompt = lambda *_args: "discovery"
    pipeline.validation_prompt = (
        lambda _scope, candidate: "validate:" + candidate["brand_name"]
    )
    pipeline.retry_prompt = (
        lambda _scope, candidate, _initial: "retry:" + candidate["brand_name"]
    )
    pipeline.normalize = normalized
    pipeline.supports_retry = (
        lambda candidate, _scope: candidate["brand_name"] == "Google"
    )
    return pipeline


def run_fixture(research):
    provider = FixtureProvider()
    scope = FIXTURE["scope"]
    observed = [SimpleNamespace(domain=domain) for domain in FIXTURE["observed_domains"]]
    discovery = research.run_scope_discovery(
        scope, observed, lambda _scope, _domains: "discovery", provider.query_json
    )
    candidates = FIXTURE["candidates"]

    def validate_one(candidate, current_scope):
        return research.run_scope_validation(
            candidate,
            current_scope,
            lambda _scope, item: "validate:" + item["brand_name"],
            lambda _scope, item, _initial: "retry:" + item["brand_name"],
            normalized,
            lambda item, _scope: item["brand_name"] == "Google",
            provider.query_json,
            lambda _domain, _country: 0,
        )

    validations = research.run_scope_validation_batch(candidates, scope, validate_one, 3)
    ranked = competitor_scope.rank_valid_competitors(validations)
    return discovery, validations, ranked, provider.calls


def stable(value):
    if isinstance(value, list):
        return [stable(item) for item in value]
    if isinstance(value, dict):
        return {
            key: stable(item) for key, item in value.items()
            if key != "duration_seconds"
        }
    return value


class CompetitorResearchTests(unittest.TestCase):
    def test_validation_checkpoint_path_and_serialization(self):
        writes = []
        write_json = lambda path, payload: writes.append((path, payload))
        competitor_pipeline.persist_validation_checkpoint(
            None, write_json, {"candidates": []}
        )
        self.assertEqual(writes, [])
        competitor_pipeline.persist_validation_checkpoint(
            Path("audit"), write_json, {"candidates": []}
        )
        self.assertEqual(
            writes[0][0], Path("audit/raw/03_candidate_validation_records.json")
        )

        value = {
            "candidate_record": {
                **FIXTURE["candidates"][0],
                "domains": ["samsung.com"], "observed_frequency": 3,
            },
            "status": "success", "validation": {"is_direct_competitor": True},
            "selection_score": 1600.0,
        }
        self.assertEqual(
            competitor_pipeline.serialize_scope_validation(value),
            bundled_pipeline().serialize_scope_validation(value),
        )

    def test_service_and_notebook_replay_same_answers(self):
        service = run_fixture(competitor_research)
        notebook = run_fixture(bundled_research())
        self.assertEqual(stable(service[:3]), stable(notebook[:3]))
        discovery, validations, ranked, calls = service
        self.assertEqual(len(discovery["competitors"]), 2)
        self.assertEqual(
            [item["candidate_record"]["brand_name"] for item in ranked],
            ["Samsung", "Google"],
        )
        self.assertEqual(ranked[0]["selection_score"], 1600.0)
        self.assertEqual(ranked[1]["selection_score"], 1475.0)
        self.assertTrue(validations[1]["consistency_retry_used"])
        self.assertFalse(validations[2]["validation"]["is_direct_competitor"])
        self.assertCountEqual(
            calls,
            ["discovery", "validate:Samsung", "validate:Google",
             "retry:Google", "validate:Vertu"],
        )

    def test_provider_failure_is_recorded_without_aborting_batch(self):
        answers = dict(FIXTURE["answers"])
        answers.pop("validate:Samsung")
        provider = FixtureProvider(answers)
        candidate = FIXTURE["candidates"][0]
        result = competitor_research.run_scope_validation(
            candidate,
            FIXTURE["scope"],
            lambda _scope, _candidate: "validate:Samsung",
            lambda *_args: "retry:Samsung",
            normalized,
            lambda *_args: False,
            provider.query_json,
            lambda *_args: 0,
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["validation"]["candidate_role"], "validation_error")
        self.assertEqual(result["selection_score"], 0.0)

    def test_batch_keeps_input_order_even_when_one_worker_raises(self):
        candidates = FIXTURE["candidates"]

        def validate_one(candidate, scope):
            if candidate["brand_name"] == "Google":
                raise RuntimeError("provider unavailable")
            return {"status": "success", "candidate_record": candidate}

        results = competitor_research.run_scope_validation_batch(
            candidates, FIXTURE["scope"], validate_one, 3
        )
        self.assertEqual(
            [item["candidate_record"]["brand_name"] for item in results],
            ["Samsung", "Google", "Vertu"],
        )
        self.assertEqual(results[1]["status"], "failed")

    def test_notebook_adapter_uses_the_same_port_contract(self):
        provider = FixtureProvider()

        class FakeClient:
            @staticmethod
            def google_ai_mode(prompt, timeout_seconds):
                self.assertEqual(timeout_seconds, 720)
                return provider.query_json(prompt)[0]

            @staticmethod
            def answer_text(record):
                return record["answer_text"]

        bundle = bundled_pipeline()
        self.assertEqual(
            bundle.query_google_ai_json(FakeClient(), json.loads, "discovery"),
            competitor_pipeline.query_google_ai_json(
                FakeClient(), json.loads, "discovery"
            ),
        )
        pipeline = fixture_pipeline(bundle.CompetitorPipeline, provider)
        observed = [
            SimpleNamespace(domain=domain) for domain in FIXTURE["observed_domains"]
        ]
        discovery = pipeline.discover(FIXTURE["scope"], observed)
        validations = pipeline.validate_batch(
            FIXTURE["candidates"], FIXTURE["scope"]
        )
        expected_discovery, expected_validations, _, _ = run_fixture(
            competitor_research
        )
        self.assertEqual(stable(discovery), stable(expected_discovery))
        self.assertEqual(stable(validations), stable(expected_validations))
        service = fixture_pipeline(
            competitor_pipeline.CompetitorPipeline, FixtureProvider()
        )
        self.assertEqual(
            stable(discovery), stable(service.discover(FIXTURE["scope"], observed))
        )
        self.assertEqual(
            stable(validations),
            stable(service.validate_batch(FIXTURE["candidates"], FIXTURE["scope"])),
        )


if __name__ == "__main__":
    unittest.main()
