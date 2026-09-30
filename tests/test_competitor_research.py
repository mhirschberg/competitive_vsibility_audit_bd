"""Replay provider answers through service and bundled-notebook research code."""

import ast
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from audit_core import competitor_research, competitor_scope
from notebook_builder import (
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


def notebook_adapters(namespace):
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    cell = next(
        item for item in notebook["cells"]
        if item.get("metadata", {}).get("id") == "runtime-utilities-merged"
    )
    source = "".join(cell["source"])
    names = {
        "_locked_scope_query_json",
        "discover_locked_scope_candidates",
        "validate_locked_scope_candidate",
        "validate_locked_scope_batch",
    }
    tree = ast.parse(source)
    definitions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    if {node.name for node in definitions} != names:
        raise AssertionError("Missing a notebook provider adapter")
    for node in definitions:
        exec(ast.get_source_segment(source, node), namespace)
    return namespace


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

        namespace = notebook_adapters({
            "bd_client": FakeClient(),
            "parse_ai_json": json.loads,
            "run_scope_discovery": competitor_research.run_scope_discovery,
            "run_scope_validation": competitor_research.run_scope_validation,
            "run_scope_validation_batch": competitor_research.run_scope_validation_batch,
            "build_locked_scope_discovery_prompt": lambda *_args: "discovery",
            "build_locked_scope_validation_prompt": (
                lambda _scope, candidate: "validate:" + candidate["brand_name"]
            ),
            "build_locked_scope_validation_retry_prompt": (
                lambda _scope, candidate, _initial: "retry:" + candidate["brand_name"]
            ),
            "normalize_locked_scope_validation": normalized,
            "discovery_supports_consistency_retry": (
                lambda candidate, _scope: candidate["brand_name"] == "Google"
            ),
            "locked_scope_local_domain_bonus": lambda *_args: 0,
            "LOCKED_SCOPE_VALIDATION_WORKERS": 3,
        })
        observed = [
            SimpleNamespace(domain=domain) for domain in FIXTURE["observed_domains"]
        ]
        discovery = namespace["discover_locked_scope_candidates"](
            FIXTURE["scope"], observed
        )
        validations = namespace["validate_locked_scope_batch"](
            FIXTURE["candidates"], FIXTURE["scope"]
        )
        expected_discovery, expected_validations, _, _ = run_fixture(
            competitor_research
        )
        self.assertEqual(stable(discovery), stable(expected_discovery))
        self.assertEqual(stable(validations), stable(expected_validations))


if __name__ == "__main__":
    unittest.main()
