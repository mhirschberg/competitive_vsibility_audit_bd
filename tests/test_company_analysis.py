"""Offline tests for company research and structuring orchestration."""

import ast
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from audit_core.company_analysis import (
    CompanyAnalysisPorts,
    build_company_research_prompt,
    build_company_structuring_prompt,
    normalize_keyword_records,
    normalize_company_intake_core,
    prepare_company_intake_payload,
    run_company_analysis_core,
)
from audit_core.company_models import (
    BrandAnalysis,
    BuyerIntentKeyword,
    CompanyIntake,
)
from pydantic import ValidationError
from audit_core.company_models import (
    BrandAnalysis,
    BuyerIntentKeyword,
    CompanyIntake,
)
from pydantic import ValidationError
from notebook_builder import (
    COMPANY_ANALYSIS_PROVIDER_END,
    COMPANY_ANALYSIS_PROVIDER_START,
    COMPANY_ANALYSIS_SOURCE,
    COMPANY_MODELS_END,
    COMPANY_MODELS_START,
    _without_service_imports,
)


class Model:
    def __init__(self, **values):
        self.__dict__.update(values)


class FakeClient:
    def __init__(self, answer="research evidence"):
        self.answer = answer
        self.events = []

    def log(self, message, *_args):
        self.events.append(message)

    def google_ai_mode(self, prompt, timeout_seconds):
        self.events.append(("research", prompt, timeout_seconds))
        return {"answer_text": self.answer}

    @staticmethod
    def answer_text(record):
        return record.get("answer_text", "")


class CompanyAnalysisTests(unittest.TestCase):
    settings = {
        "company_name": "Example",
        "company_url": "https://example.com/",
        "company_domain": "example.com",
        "country": "DE",
        "audit_focus": "premium appliances",
    }

    def make_ports(self, *, initial_keyword_count=8, fail_first=True):
        client = FakeClient("A concise research brief about Example and its market.")
        utility_prompts = []
        completions = []
        proofreads = []
        attempts = {"count": 0}

        def run_utility(prompt):
            utility_prompts.append(prompt)
            attempts["count"] += 1
            if fail_first and attempts["count"] == 1:
                return {"answer": "not JSON", "record": {}, "snapshot_id": "bad"}
            items = [
                {"keyword": f"appliance buyer query {i}", "intent": "commercial"}
                for i in range(initial_keyword_count)
            ]
            parsed = {
                "brand": {
                    "brand_name": "Example", "category": "premium appliances",
                    "description": "Home appliances", "positioning": "Premium",
                    "target_customers": ["homeowners"], "products": ["ovens"],
                    "key_features": ["efficient"], "differentiators": ["design"],
                    "confidence": 0.9, "evidence": ["website"],
                },
                "buyer_intent_keywords": items,
            }
            return {
                "answer": json.dumps(parsed), "record": {"answer_text": "structured"},
                "snapshot_id": "structured-snapshot",
            }

        def normalize_intake(*, data, company_name, company_url):
            return Model(
                brand=Model(**{
                    **data["brand"],
                    "brand_name": company_name,
                    "official_url": company_url,
                    "domain": "example.com",
                }),
                buyer_intent_keywords=[Model(**item) for item in data["buyer_intent_keywords"]],
            )

        def complete_keywords(**kwargs):
            completions.append(kwargs)
            current = list(kwargs["current_keywords"])
            return {
                "keywords": current + [
                    Model(keyword=f"completed query {i}", intent="commercial")
                    for i in range(8 - len(current))
                ],
                "record": {"answer_text": "completion"},
                "snapshot_id": "completion-snapshot",
            }

        def proofread_keywords(**kwargs):
            proofreads.append(kwargs)
            return {
                "keywords": kwargs["current_keywords"],
                "status": "skipped",
                "reason": "fixture preserves source queries",
                "record": None,
                "snapshot_id": None,
            }

        ports = CompanyAnalysisPorts(
            client=client,
            run_utility=run_utility,
            parse_json=json.loads,
            normalize_intake=normalize_intake,
            select_relevant_research=lambda **kwargs: kwargs["research_text"],
            complete_keywords=complete_keywords,
            proofread_keywords=proofread_keywords,
            build_locked_scope=lambda brand, settings: {
                "brand_name": brand.brand_name,
                "domain": settings["company_domain"],
                "market_role": "manufacturer",
            },
            error_type=RuntimeError,
        )
        return ports, client, utility_prompts, completions, proofreads

    def test_company_prompts_preserve_neutral_eight_keyword_brief(self):
        research = build_company_research_prompt(self.settings)
        self.assertIn("Country: DE", research)
        self.assertIn("Specific audit focus: premium appliances", research)
        self.assertIn("Exactly eight non-branded buyer-intent searches", research)
        self.assertNotIn("Example", research.split("Do not include", 1)[1])

        structuring = build_company_structuring_prompt(
            self.settings,
            "Evidence block",
            select_relevant_research=lambda **kwargs: kwargs["research_text"],
            strict_retry=True,
        )
        self.assertIn("Evidence block", structuring)
        self.assertIn("A previous formatting attempt failed", structuring)
        self.assertIn('"buyer_intent_keywords"', structuring)

    def test_keyword_record_normalization_preserves_existing_input_rules(self):
        self.assertEqual(
            normalize_keyword_records("  query one, query two ,, QUERY ONE "),
            [
                {"keyword": "query one", "intent": "commercial", "rationale": ""},
                {"keyword": "query two", "intent": "commercial", "rationale": ""},
            ],
        )
        self.assertEqual(
            normalize_keyword_records([
                {"query": "  Query A ", "intent": "  informational ", "reason": "  why "},
                {"term": "Query B", "rationale": " evidence "},
                {"keyword": "query a", "intent": "ignored duplicate"},
                {"keyword": ""},
                7,
            ]),
            [
                {"keyword": "Query A", "intent": "informational", "rationale": "why"},
                {"keyword": "Query B", "intent": "commercial", "rationale": "evidence"},
            ],
        )
        self.assertEqual(normalize_keyword_records({"keyword": "not a list"}), [])

    def test_company_payload_is_normalized_before_the_pydantic_boundary(self):
        from audit_core.domains import normalize_public_url

        def ensure_string_list(value):
            if value is None:
                return []
            if isinstance(value, str):
                value = value.strip()
                return [value] if value else []
            if isinstance(value, list):
                return [str(item).strip() for item in value if item is not None and str(item).strip()]
            return [str(value).strip()]

        def normalize_confidence(value):
            try:
                number = float(value)
                if 1 < number <= 100:
                    number /= 100
                return max(0.0, min(1.0, number))
            except (TypeError, ValueError):
                return 0.0

        original = {
            "brand_name": "  Example Co  ",
            "official_url": " example.com/about ",
            "category": "  appliances ",
            "target_customers": [" homeowners ", None, "retailers"],
            "evidence": list(range(10)),
            "confidence": 85,
            "keywords": ["buy an oven"],
        }
        payload = prepare_company_intake_payload(
            original,
            "Fallback name",
            "fallback.example",
            normalize_public_url=normalize_public_url,
            get_root_domain=lambda _value: "example.com",
            ensure_string_list=ensure_string_list,
            normalize_confidence=normalize_confidence,
        )

        self.assertEqual(payload["brand"]["brand_name"], "Example Co")
        self.assertEqual(payload["brand"]["official_url"], "https://example.com/about")
        self.assertEqual(payload["brand"]["domain"], "example.com")
        self.assertEqual(payload["brand"]["category"], "appliances")
        self.assertEqual(payload["brand"]["target_customers"], ["homeowners", "retailers"])
        self.assertEqual(payload["brand"]["evidence"], [str(value) for value in range(8)])
        self.assertEqual(payload["brand"]["confidence"], 0.85)
        self.assertEqual(payload["buyer_intent_keywords"][0]["keyword"], "buy an oven")
        self.assertIn("brand", original)  # Preserve the notebook's prior mutation.

    def test_company_payload_rejects_non_object_before_schema_validation(self):
        with self.assertRaisesRegex(ValueError, "must be a JSON object"):
            prepare_company_intake_payload(
                [], "Example", "example.com",
                normalize_public_url=lambda value: value,
                get_root_domain=lambda value: value,
                ensure_string_list=lambda value: value,
                normalize_confidence=lambda value: value,
            )

    def test_shared_company_normalizer_returns_the_shared_pydantic_model(self):
        with patch("audit_core.company_analysis.get_root_domain", return_value="example.com"):
            intake = normalize_company_intake_core(
                {
                    "brand": {
                        "brand_name": " Example ",
                        "official_url": "example.com",
                        "confidence": 0.8,
                    },
                    "buyer_intent_keywords": [" buy an oven "],
                },
                "Fallback",
                "example.com",
            )

        self.assertIsInstance(intake, CompanyIntake)
        self.assertIsInstance(intake.brand, BrandAnalysis)
        self.assertIsInstance(intake.buyer_intent_keywords[0], BuyerIntentKeyword)
        self.assertEqual(intake.brand.brand_name, "Example")
        self.assertEqual(intake.brand.domain, "example.com")
        self.assertEqual(intake.buyer_intent_keywords[0].keyword, "buy an oven")

    def test_generated_notebook_has_one_shared_keyword_normalizer(self):
        notebook_path = Path(__file__).resolve().parents[1] / "competitive_visibility_audit_bd.ipynb"
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        definitions = []
        for notebook_cell in notebook["cells"]:
            try:
                tree = ast.parse("".join(notebook_cell.get("source", [])))
            except SyntaxError:
                continue
            definitions.extend(
                node.name for node in tree.body
                if isinstance(node, ast.FunctionDef)
                and node.name == "normalize_keyword_records"
            )
        self.assertEqual(definitions, ["normalize_keyword_records"])

    def test_company_intake_notebook_adapter_keeps_schema_validation_explicit(self):
        notebook_path = Path(__file__).resolve().parents[1] / "competitive_visibility_audit_bd.ipynb"
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        analysis_cell = next(
            item for item in notebook["cells"]
            if item.get("metadata", {}).get("id") == "final-analysis"
        )
        tree = ast.parse("".join(analysis_cell["source"]))
        adapters = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "normalize_company_intake"
        ]
        self.assertEqual(len(adapters), 2)  # Base adapter plus placeholder filter.
        calls = {
            node.func.id
            for node in ast.walk(adapters[0])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertIn("normalize_company_intake_core", calls)

    def test_shared_company_models_preserve_nested_defaults_and_validation(self):
        brand = BrandAnalysis(
            brand_name="Example", official_url="https://example.com/",
            domain="example.com",
        )
        intake = CompanyIntake(
            brand=brand,
            buyer_intent_keywords=[BuyerIntentKeyword(keyword="buy an oven")],
        )
        self.assertEqual(intake.brand.primary_market_role, "other")
        self.assertEqual(intake.brand.target_customers, [])
        self.assertEqual(intake.buyer_intent_keywords[0].intent, "commercial")
        self.assertEqual(intake.buyer_intent_keywords[0].rationale, "")
        with self.assertRaises(ValidationError):
            validate = getattr(CompanyIntake, "model_validate", CompanyIntake.parse_obj)
            validate({"brand": {"brand_name": "Missing fields"}})

    def test_generated_notebook_embeds_the_shared_company_models(self):
        root = Path(__file__).resolve().parents[1]
        notebook = json.loads((root / "competitive_visibility_audit_bd.ipynb").read_text(encoding="utf-8"))
        core_cell = next(
            item for item in notebook["cells"]
            if item.get("metadata", {}).get("id") == "final-core"
        )
        source = "".join(core_cell["source"])
        embedded = source.split(COMPANY_MODELS_START, 1)[1].split(
            COMPANY_MODELS_END, 1
        )[0].strip()
        self.assertEqual(
            embedded,
            (root / "audit_core" / "company_models.py").read_text(encoding="utf-8").strip(),
        )
        names = []
        for cell in notebook["cells"]:
            try:
                tree = ast.parse("".join(cell.get("source", [])))
            except SyntaxError:
                continue
            names.extend(
                node.name for node in tree.body
                if isinstance(node, ast.ClassDef)
                and node.name in {"BuyerIntentKeyword", "BrandAnalysis", "CompanyIntake"}
            )
        self.assertEqual(names, ["BuyerIntentKeyword", "BrandAnalysis", "CompanyIntake"])

    def test_research_structuring_retry_and_scope_are_shared(self):
        ports, client, prompts, completions, proofreads = self.make_ports()
        result = run_company_analysis_core(self.settings, ports=ports)

        self.assertEqual(len(prompts), 2)
        self.assertIn("A previous formatting attempt failed", prompts[1])
        research_call = next(event for event in client.events if isinstance(event, tuple))
        self.assertEqual(research_call[0], "research")
        self.assertEqual(research_call[2], 720)
        self.assertEqual(len(result["intake"].buyer_intent_keywords), 8)
        self.assertEqual(result["locked_target_scope"]["domain"], "example.com")
        self.assertEqual(result["structuring_snapshot_id"], "structured-snapshot")
        self.assertEqual(result["workflow"], "google_ai_research_chatgpt_structuring")
        self.assertEqual(completions, [])
        self.assertEqual(len(proofreads), 1)

    def test_keyword_completion_and_proofreading_records_are_preserved(self):
        ports, _client, _prompts, completions, _proofreads = self.make_ports(
            initial_keyword_count=6, fail_first=False,
        )
        result = run_company_analysis_core(self.settings, ports=ports)
        self.assertEqual(len(completions), 1)
        self.assertEqual(len(result["intake"].buyer_intent_keywords), 8)
        self.assertEqual(
            result["keyword_completion"]["snapshot_id"], "completion-snapshot"
        )

    def test_empty_research_fails_before_structuring(self):
        ports, _client, prompts, _completions, _proofreads = self.make_ports()
        ports.client.answer = ""
        with self.assertRaisesRegex(RuntimeError, "returned no company research"):
            run_company_analysis_core(self.settings, ports=ports)
        self.assertEqual(prompts, [])

    def test_generated_notebook_embeds_the_shared_company_provider(self):
        notebook_path = Path(__file__).resolve().parents[1] / "competitive_visibility_audit_bd.ipynb"
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        cell = next(
            item for item in notebook["cells"]
            if item.get("metadata", {}).get("id") == "final-orchestration"
        )
        source = "".join(cell["source"])
        embedded = source.split(COMPANY_ANALYSIS_PROVIDER_START, 1)[1].split(
            COMPANY_ANALYSIS_PROVIDER_END, 1
        )[0].strip()
        self.assertEqual(
            embedded,
            _without_service_imports(
                COMPANY_ANALYSIS_SOURCE.read_text(encoding="utf-8")
            ).strip(),
        )
        definitions = []
        for notebook_cell in notebook["cells"]:
            try:
                tree = ast.parse("".join(notebook_cell.get("source", [])))
            except SyntaxError:
                continue
            definitions.extend(
                node.name for node in tree.body
                if isinstance(node, ast.FunctionDef)
                and node.name == "select_relevant_company_research"
            )
        self.assertEqual(definitions, ["select_relevant_company_research"])


if __name__ == "__main__":
    unittest.main()
