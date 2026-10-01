"""Finish the structured audit and its JSON/ZIP exports."""

from datetime import datetime, timezone
import time


class AuditFinalizePorts:
    def __init__(
        self, *, build_record, model_to_dict, serialize_engine_result,
        generator_name, report_filename, write_json, create_zip,
        stage_success, completion_notice, format_duration,
    ):
        self.build_record = build_record
        self.model_to_dict = model_to_dict
        self.serialize_engine_result = serialize_engine_result
        self.generator_name = generator_name
        self.report_filename = report_filename
        self.write_json = write_json
        self.create_zip = create_zip
        self.stage_success = stage_success
        self.completion_notice = completion_notice
        self.format_duration = format_duration


def run_audit_finalize_stage_core(
    record_inputs, *, audit_started_at, site_resolution, output_directory,
    export_prefix, markdown_path, pdf_path, ports,
):
    completed_at = datetime.now(timezone.utc)
    total_duration = time.monotonic() - audit_started_at
    audit_data = ports.build_record(
        completed_at=completed_at,
        total_duration=total_duration,
        generator_name=ports.generator_name,
        model_to_dict=ports.model_to_dict,
        serialize_engine_result=ports.serialize_engine_result,
        **record_inputs,
    )
    audit_data["official_site_resolution"] = site_resolution
    audit_json_path = output_directory / ports.report_filename(export_prefix, "json")
    audit_data["files"] = {
        "output_directory": str(output_directory),
        "markdown_report": str(markdown_path),
        "pdf_report": str(pdf_path) if pdf_path is not None else None,
        "json_report": str(audit_json_path),
    }
    ports.write_json(audit_json_path, audit_data)
    zip_path = ports.create_zip(
        output_directory, ports.report_filename(export_prefix, "zip"),
    )
    audit_data["files"]["zip_archive"] = str(zip_path)
    # Rewrite JSON so its file manifest includes the newly created ZIP path.
    ports.write_json(audit_json_path, audit_data)
    ports.stage_success(
        "Markdown, PDF, JSON and ZIP saved" if pdf_path is not None
        else "Markdown, JSON and ZIP saved"
    )
    ports.completion_notice(
        f"✓ Audit complete in {ports.format_duration(total_duration)}"
    )
    return audit_data
