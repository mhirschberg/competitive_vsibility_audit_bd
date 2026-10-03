"""Final report rendering and JSON/ZIP assembly outside the notebook."""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import time
import unittest

from audit_core.report_render_stage import ReportRenderPorts, run_report_render_stage_core
from audit_core.audit_finalize_stage import AuditFinalizePorts, run_audit_finalize_stage_core


class Model:
    def __init__(self, **values):
        self.__dict__.update(values)


class ReportCompletionTests(unittest.TestCase):
    def setUp(self):
        self.target = Model(
            brand_name="Apple", domain="apple.com",
            official_url="https://apple.com/",
        )
        self.timestamp = datetime(2026, 9, 30, tzinfo=timezone.utc)
        self.resolution = {
            "submitted_domain": "apple.com",
            "canonical_domain": "apple.com",
        }

    def render_ports(self, events, *, pdf_fails=False):
        def write_json(path, data):
            events.append(("json", path.name))
            path.write_text(json.dumps(data), encoding="utf-8")

        def create_pdf(**kwargs):
            events.append(("pdf", kwargs["output_path"].name))
            if pdf_fails:
                raise RuntimeError("renderer unavailable")
            kwargs["output_path"].write_bytes(b"%PDF-test")

        return ReportRenderPorts(
            generate_report=lambda *args: {
                "report": "# Competitive Visibility Audit\n\nBase report\n",
                "record": {"provider": "saved"},
            },
            finalize_report=lambda **kwargs: {
                "report": kwargs["report"], "sources": [{"url": "https://example.com"}],
            },
            insert_reddit_section=lambda report, social: report + "Reddit: disabled\n",
            refresh_usage=lambda: events.append(("refresh",)),
            usage_summary=lambda **kwargs: {
                "estimated_cost_usd": 0.06,
                "price_per_1000": kwargs["price_per_1000"],
            },
            build_usage_section=lambda usage: "\nUsage: $0.06\n",
            write_json=write_json,
            write_text=lambda path, value: path.write_text(value, encoding="utf-8"),
            report_filename=lambda prefix, ext: f"{prefix}.{ext}",
            create_pdf=create_pdf,
            clean_record=lambda record: dict(record),
            stage_success=lambda message: events.append(("success", message)),
            stage_warning=lambda message: events.append(("warning", message)),
            format_duration=lambda seconds: f"{seconds:.1f}s",
        )

    def run_render(self, output, raw, ports, *, resolution=None):
        return run_report_render_stage_core(
            self.target, [], ["premium smartphone"], [],
            {"engines": {}}, {"status": "disabled"},
            site_resolution=resolution or self.resolution,
            country="US", run_timestamp=self.timestamp,
            export_prefix="20260930-apple-us", output_directory=output,
            raw_directory=raw, started_at=time.monotonic(),
            price_per_1000=1.5, ports=ports,
        )

    def test_report_renders_usage_and_official_domain_note(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            raw = output / "raw"
            raw.mkdir()
            events = []
            result = asyncio.run(self.run_render(
                output, raw, self.render_ports(events),
                resolution={
                    "submitted_domain": "old.example",
                    "canonical_domain": "apple.com",
                },
            ))
            self.assertEqual(result["warnings"], [])
            self.assertTrue(result["pdf_path"].is_file())
            self.assertEqual(result["bright_data_usage"]["price_per_1000"], 1.5)
            self.assertEqual(result["final_sources"], [{"url": "https://example.com"}])
            markdown = result["markdown_path"].read_text()
            self.assertIn("Official-domain correction", markdown)
            self.assertIn("Reddit: disabled", markdown)
            self.assertIn("Usage: $0.06", markdown)
            self.assertLess(events.index(("refresh",)),
                            events.index(("json", "06_bright_data_usage.json")))
            self.assertEqual(json.loads((
                raw / "06_final_report_record.json"
            ).read_text()), {"provider": "saved"})

    def test_pdf_failure_keeps_markdown_usage_and_raw_record(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            raw = output / "raw"
            raw.mkdir()
            events = []
            result = asyncio.run(self.run_render(
                output, raw, self.render_ports(events, pdf_fails=True),
            ))
            self.assertIsNone(result["pdf_path"])
            self.assertEqual(result["warnings"], [
                "PDF generation failed: RuntimeError: renderer unavailable"
            ])
            self.assertTrue(result["markdown_path"].is_file())
            self.assertTrue((output / "06_bright_data_usage.json").is_file())
            self.assertTrue((raw / "06_final_report_record.json").is_file())

    def test_finalizer_includes_selection_result_and_zip_in_json(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            writes, notices = [], []

            def write_json(path, data):
                writes.append((path.name, "zip_archive" in data.get("files", {})))
                path.write_text(json.dumps(data), encoding="utf-8")

            def create_zip(directory, name):
                path = directory / name
                path.write_bytes(b"zip-test")
                return path

            captured = {}

            def build_record(**kwargs):
                captured.update(kwargs)
                return {"selection": kwargs["selection_result"]}

            result = run_audit_finalize_stage_core(
                {"selection_result": {"selected": ["Samsung"]}},
                audit_started_at=time.monotonic(),
                site_resolution=self.resolution,
                output_directory=output, export_prefix="20260930-apple-us",
                markdown_path=output / "20260930-apple-us.md",
                pdf_path=None,
                ports=AuditFinalizePorts(
                    build_record=build_record,
                    model_to_dict=dict,
                    serialize_engine_result=dict,
                    generator_name="ChatGPT",
                    report_filename=lambda prefix, ext: f"{prefix}.{ext}",
                    write_json=write_json,
                    create_zip=create_zip,
                    stage_success=notices.append,
                    completion_notice=notices.append,
                    format_duration=lambda seconds: f"{seconds:.1f}s",
                ),
            )
            self.assertEqual(captured["selection_result"],
                             {"selected": ["Samsung"]})
            self.assertEqual(captured["generator_name"], "ChatGPT")
            self.assertEqual(writes, [
                ("20260930-apple-us.json", False),
                ("20260930-apple-us.json", True),
            ])
            self.assertIsNone(result["files"]["pdf_report"])
            self.assertTrue(Path(result["files"]["zip_archive"]).is_file())
            saved = json.loads((output / "20260930-apple-us.json").read_text())
            self.assertEqual(saved["files"]["zip_archive"],
                             result["files"]["zip_archive"])
            self.assertIn("Markdown, JSON and ZIP saved", notices)


if __name__ == "__main__":
    unittest.main()
