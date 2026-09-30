"""Stage 3 selects from saved provider results in service and notebook forms."""

import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from audit_core import competitor_scope, competitor_stage
from notebook_builder import COMPETITOR_STAGE_END, COMPETITOR_STAGE_START, NOTEBOOK
from tests.test_google_ai_timeout_safety import definition


def candidate(name, domain, rank):
    return {
        "brand_name": name,
        "representative_domain": domain,
        "discovery_rank": rank,
        "market_prominence": 0,
        "observed_score": 0,
    }


def result(item, *, direct=True, status="success", score=1.0):
    return {
        "candidate_record": item,
        "status": status,
        "selection_score": score,
        "validation": {
            "candidate_name": item["brand_name"],
            "candidate_domain": item["representative_domain"],
            "official_url": "https://" + item["representative_domain"],
            "candidate_role": "manufacturer" if direct else "unrelated",
            "is_direct_competitor": direct,
            "reason": "same category" if direct else "different category",
            "confidence": 0.9,
        },
    }


class CompetitorStageTests(unittest.TestCase):
    def setUp(self):
        self.scope = {"target_domain": "apple.com", "market_role": "manufacturer"}
        self.candidates = [
            candidate("Samsung", "samsung.com", 1),
            candidate("Google", "google.com", 2),
            candidate("Vertu", "vertu.com", 3),
        ]
        self.saved_results = [
            result(self.candidates[0], score=0.9),
            result(self.candidates[1], score=0.8),
            result(self.candidates[2], direct=False, score=0.7),
        ]
        self.persisted = []
        self.validated = []

    def ports(self, stage=competitor_stage, *, only_reuse=False, saved=None,
              results=None):
        available = set(saved or ())

        def validate(items, _scope):
            self.validated.extend(item["brand_name"] for item in items)
            by_name = {
                value["candidate_record"]["brand_name"]: value
                for value in (results if results is not None else self.saved_results)
            }
            return [by_name[item["brand_name"]] for item in items]

        return stage.CompetitorStagePorts(
            discover=lambda _scope, _candidates: {
                "competitors": [], "record": {"provider": "saved"},
                "prompt": "saved discovery",
            },
            build_universe=lambda **_kwargs: self.candidates,
            validate_batch=validate,
            mark_uncorroborated=lambda *_args: None,
            brand_family=lambda domain: domain,
            serialize_validation=lambda value: value,
            selected_factory=lambda **kwargs: SimpleNamespace(**kwargs),
            error_type=RuntimeError,
            validation_limit=12,
            only_reuse=only_reuse,
            cached_snapshot_ids=lambda prompt: [prompt] if prompt in available else [],
            validation_prompt=lambda _scope, item: item["brand_name"],
            persist_validation_records=self.persisted.append,
        )

    def test_selects_two_and_persists_all_verdicts(self):
        output = competitor_stage.select_competitors_core(
            self.scope, self.candidates, ["phone"], self.ports()
        )
        self.assertEqual(
            [item.brand_name for item in output["selected"]],
            ["Samsung", "Google"],
        )
        self.assertEqual(output["rejected"][0]["brand_name"], "Vertu")
        self.assertEqual(self.validated, ["Samsung", "Google", "Vertu"])
        self.assertEqual(len(self.persisted[0]["candidates"]), 3)
        self.assertEqual(output["unvalidated_on_resume"], 0)
        self.assertEqual(output["selection_method"],
                         "locked_scope_market_discovery_and_individual_validation")

    def test_resume_uses_only_existing_snapshots(self):
        output = competitor_stage.select_competitors_core(
            self.scope, self.candidates, [],
            self.ports(only_reuse=True, saved={"Samsung", "Google"}),
        )
        self.assertEqual(self.validated, ["Samsung", "Google"])
        self.assertEqual(output["unvalidated_on_resume"], 1)

    def test_resume_without_snapshots_refuses_new_requests(self):
        with self.assertRaisesRegex(RuntimeError, "will not launch new ones"):
            competitor_stage.select_competitors_core(
                self.scope, self.candidates, [], self.ports(only_reuse=True)
            )
        self.assertEqual(self.validated, [])

    def test_provider_failures_are_not_treated_as_absent_competitors(self):
        failed = [result(item, status="failed") for item in self.candidates]
        with self.assertRaisesRegex(RuntimeError, "providers were unavailable"):
            competitor_stage.select_competitors_core(
                self.scope, self.candidates, [], self.ports(results=failed)
            )

    def test_notebook_bundle_matches_service_stage(self):
        notebook = json.loads(Path(NOTEBOOK).read_text(encoding="utf-8"))
        cell = next(
            item for item in notebook["cells"]
            if item.get("metadata", {}).get("id") == "runtime-utilities-merged"
        )
        source = "".join(cell["source"])
        embedded = source.split(COMPETITOR_STAGE_START, 1)[1].split(
            COMPETITOR_STAGE_END, 1
        )[0]
        self.assertNotIn("from .competitor_scope", embedded)
        namespace = {"rank_valid_competitors": competitor_scope.rank_valid_competitors}
        exec(embedded, namespace)
        service = competitor_stage.select_competitors_core(
            self.scope, self.candidates, [], self.ports()
        )
        bundled = namespace["select_competitors_core"](
            self.scope, self.candidates, [],
            self.ports(stage=type("Bundle", (), namespace)),
        )
        self.assertEqual(service, bundled)

    def test_notebook_stage_wires_the_importable_pipeline(self):
        class FixturePipeline:
            def discover(self, _scope, _candidates):
                return {"competitors": [], "record": {}, "prompt": "fixture"}

            def build_universe(self, **_kwargs):
                return self_candidates

            def validate_batch(self, _candidates, _scope):
                return saved_results

            def mark_uncorroborated(self, *_args):
                pass

            def validation_prompt(self, _scope, item):
                return item["brand_name"]

        self_candidates = self.candidates
        saved_results = self.saved_results
        supplied = []
        fixture_pipeline = FixturePipeline()

        def make_pipeline(**kwargs):
            supplied.append(kwargs)
            return fixture_pipeline

        namespace = {
            "require_locked_target_scope": lambda _brand: self.scope,
            "CompetitorPipeline": make_pipeline,
            "query_google_ai_json": lambda *_args: None,
            "bd_client": object(),
            "parse_ai_json": json.loads,
            "_competitor_decision_ports": lambda: "decision ports",
            "locked_scope_local_domain_bonus": lambda *_args: 0,
            "LOCKED_SCOPE_VALIDATION_WORKERS": 3,
            "CompetitorStagePorts": competitor_stage.CompetitorStagePorts,
            "serialize_scope_validation": lambda value: value,
            "SelectedCompetitor": lambda **kwargs: SimpleNamespace(**kwargs),
            "BrightDataAPIError": RuntimeError,
            "LOCKED_SCOPE_VALIDATION_LIMIT": 12,
            "_GOOGLE_AI_ONLY_REUSE": False,
            "cached_research_snapshot_ids": lambda _prompt: [],
            "write_json": lambda *_args: None,
            "persist_validation_checkpoint": lambda *_args: None,
            "clean_record_for_storage": lambda value: value,
            "locked_scope_brand_family": lambda domain: domain,
            "select_competitors_core": competitor_stage.select_competitors_core,
        }
        exec(definition("select_competitors_stage", last=True), namespace)
        output = namespace["select_competitors_stage"](
            object(), self.candidates, ["phone"]
        )
        self.assertEqual(
            [item.brand_name for item in output["selected"]],
            ["Samsung", "Google"],
        )
        self.assertEqual(supplied[0]["decision_ports"], "decision ports")
        self.assertEqual(supplied[0]["validation_workers"], 3)


if __name__ == "__main__":
    unittest.main()
