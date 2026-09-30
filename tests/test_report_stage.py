"""Parity and safety checks for the extracted deterministic report stage."""

import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from audit_core.report_content import DETERMINISTIC_REPORT_GENERATOR, build_report_content
from audit_core.report_stage import generate_report_stage_core


NOTEBOOK = Path(__file__).resolve().parents[1] / "competitive_visibility_audit_bd.ipynb"
BASELINE_SHA256 = "d3703f51152d21b928737cf62af71c0dabe7f07e72a6ec80870db2d920089cd3"


def notebook_definition(name):
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    matches = []
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue
        source = "".join(cell["source"])
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        matches.extend(
            ast.get_source_segment(source, node)
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        )
    return matches[-1]


def fixture():
    target = SimpleNamespace(
        brand_name="Apple", domain="apple.com", category="premium smartphones",
        positioning="premium", relevant_products=["iPhone"],
    )
    competitor = SimpleNamespace(
        brand_name="Samsung", domain="samsung.com", category="premium smartphones",
        positioning="Android", relevant_products=["Galaxy"],
    )
    keywords = ["best premium smartphone"]
    searches = [{"keyword": keywords[0], "success": True}]
    metrics = {
        "apple.com": {
            "appearances": 1, "best_rank": 1, "average_rank": 1,
            "total_keywords": 1, "coverage": 1, "details": [],
        },
        "samsung.com": {
            "appearances": 0, "best_rank": None, "average_rank": None,
            "total_keywords": 1, "coverage": 0, "details": [],
        },
    }
    visibility = {"engines": {}, "mentions": {}}
    return target, [competitor], keywords, searches, metrics, visibility


class ReportStageTests(unittest.TestCase):
    def test_content_matches_pre_extraction_notebook_byte_for_byte(self):
        target, competitors, keywords, searches, metrics, visibility = fixture()
        report = build_report_content(
            target, competitors, keywords, searches, metrics, visibility,
            country="US", search_engine="google", search_status="available",
            collect_sources=lambda *_args, **_kwargs: [],
        )
        self.assertEqual(hashlib.sha256(report.encode()).hexdigest(), BASELINE_SHA256)
        self.assertIn("Traditional search was measured on **Google**", report)

    def test_notebook_adapter_matches_imported_content(self):
        target, competitors, keywords, searches, metrics, visibility = fixture()
        collect = lambda *_args, **_kwargs: []
        namespace = {
            "_shared_build_report_content": build_report_content,
            "AUDIT_SETTINGS": {"country": "US"},
            "ACTIVE_SEARCH_ENGINE": "google",
            "ACTIVE_SEARCH_STATUS": "available",
            "collect_visibility_sources": collect,
        }
        exec(notebook_definition("build_deterministic_report"), namespace)
        notebook_report = namespace["build_deterministic_report"](
            target, competitors, keywords, searches, metrics, visibility,
        )
        imported_report = build_report_content(
            target, competitors, keywords, searches, metrics, visibility,
            country="US", search_engine="google", search_status="available",
            collect_sources=collect,
        )
        self.assertEqual(notebook_report, imported_report)

    def test_embedded_report_survives_late_legacy_name_override(self):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        source = "".join(notebook["cells"][6]["source"])
        embedded = source.split("# AUDIT-REPORT-CONTENT: start\n", 1)[1].split(
            "# AUDIT-REPORT-CONTENT: end", 1
        )[0]
        namespace = {
            "AUDIT_SETTINGS": {"country": "US"},
            "ACTIVE_SEARCH_ENGINE": "google",
            "ACTIVE_SEARCH_STATUS": "available",
            "collect_visibility_sources": lambda *_args, **_kwargs: [],
        }
        exec(embedded, namespace)
        namespace["_shared_build_report_content"] = namespace["build_report_content"]
        exec(notebook_definition("build_deterministic_report"), namespace)
        target, competitors, keywords, searches, metrics, visibility = fixture()
        report = namespace["build_report_content"](
            target, competitors, keywords, searches, metrics, visibility,
            country="US", search_engine="google", search_status="available",
            collect_sources=namespace["collect_visibility_sources"],
        )
        self.assertEqual(hashlib.sha256(report.encode()).hexdigest(), BASELINE_SHA256)

    def test_report_stage_does_not_claim_unavailable_search_as_zero(self):
        target, competitors, keywords, searches, metrics, visibility = fixture()
        result = generate_report_stage_core(
            target, competitors, keywords, searches, visibility,
            country="US", search_engine="google", search_status="unavailable",
            calculate_serp_metrics=lambda **_kwargs: metrics,
            collect_sources=lambda *_args, **_kwargs: [],
            build_evidence=lambda **_kwargs: "compact evidence",
            now_utc=datetime(2026, 9, 30, tzinfo=timezone.utc),
        )
        self.assertIn("Traditional search was not measured", result["report"])
        self.assertEqual(result["evidence"], "compact evidence")
        self.assertEqual(result["record"]["generated_at"], "2026-09-30T00:00:00+00:00")
        self.assertFalse(result["record"]["ai_generation"])
        self.assertIsNone(result["snapshot_id"])

    def test_notebook_stage_updates_legacy_result_state(self):
        target, competitors, keywords, searches, metrics, visibility = fixture()
        namespace = {
            "generate_report_stage_core": generate_report_stage_core,
            "DETERMINISTIC_REPORT_GENERATOR": DETERMINISTIC_REPORT_GENERATOR,
            "AUDIT_SETTINGS": {"country": "US"},
            "ACTIVE_SEARCH_ENGINE": "google",
            "ACTIVE_SEARCH_STATUS": "available",
            "calculate_all_serp_metrics": lambda **_kwargs: metrics,
            "collect_visibility_sources": lambda *_args, **_kwargs: [],
            "build_report_evidence": lambda **_kwargs: "compact evidence",
        }
        exec(notebook_definition("generate_report_stage"), namespace)
        result = namespace["generate_report_stage"](
            target, competitors, keywords, searches, visibility,
        )
        self.assertEqual(result["evidence"], "compact evidence")
        self.assertEqual(namespace["LAST_UTILITY_REPORT_RESULT"]["answer"], result["report"])
        self.assertEqual(namespace["LAST_UTILITY_REPORT_RESULT"]["record"], result["record"])

    def test_evidence_failure_preserves_report(self):
        target, competitors, keywords, searches, metrics, visibility = fixture()

        def broken_evidence(**_kwargs):
            raise ValueError("bad serialization")

        result = generate_report_stage_core(
            target, competitors, keywords, searches, visibility,
            country="US", search_engine="google", search_status="available",
            calculate_serp_metrics=lambda **_kwargs: metrics,
            collect_sources=lambda *_args, **_kwargs: [],
            build_evidence=broken_evidence,
        )
        self.assertIn("# Competitive Visibility Audit", result["report"])
        self.assertIn("ValueError: bad serialization", result["evidence"])


if __name__ == "__main__":
    unittest.main()
