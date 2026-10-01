"""Build the final narrative and export its Markdown/PDF artifacts."""

import asyncio
import time


class ReportRenderPorts:
    def __init__(
        self, *, generate_report, finalize_report, insert_reddit_section,
        refresh_usage, usage_summary, build_usage_section, write_json,
        write_text, report_filename, create_pdf, clean_record,
        stage_success, stage_warning, format_duration,
    ):
        self.generate_report = generate_report
        self.finalize_report = finalize_report
        self.insert_reddit_section = insert_reddit_section
        self.refresh_usage = refresh_usage
        self.usage_summary = usage_summary
        self.build_usage_section = build_usage_section
        self.write_json = write_json
        self.write_text = write_text
        self.report_filename = report_filename
        self.create_pdf = create_pdf
        self.clean_record = clean_record
        self.stage_success = stage_success
        self.stage_warning = stage_warning
        self.format_duration = format_duration


async def run_report_render_stage_core(
    target_profile, competitor_profiles, keywords, keyword_serp_results,
    visibility_result, reddit_social_result, *, locked_scope=None,
    site_resolution, country,
    run_timestamp, export_prefix, output_directory, raw_directory,
    started_at, price_per_1000, ports,
):
    report_result = await asyncio.to_thread(
        ports.generate_report, target_profile, competitor_profiles, keywords,
        keyword_serp_results, visibility_result, locked_scope,
    )
    finalized = ports.finalize_report(
        report=report_result["report"], visibility=visibility_result,
    )
    final_report = ports.insert_reddit_section(
        finalized["report"], reddit_social_result,
    )
    ports.refresh_usage()
    bright_data_usage = ports.usage_summary(price_per_1000=price_per_1000)
    final_report = (
        final_report.rstrip()
        + ports.build_usage_section(bright_data_usage)
    )
    if site_resolution["submitted_domain"] != site_resolution["canonical_domain"]:
        domain_note = (
            "> **Official-domain correction:** The submitted address "
            f"`{site_resolution['submitted_domain']}` redirects to "
            f"`{site_resolution['canonical_domain']}`. Search coverage "
            "and source ownership are measured against the canonical domain.\n\n"
        )
        final_report = final_report.replace(
            "# Competitive Visibility Audit\n\n",
            "# Competitive Visibility Audit\n\n" + domain_note, 1,
        )
    ports.write_json(
        output_directory / "06_bright_data_usage.json", bright_data_usage,
    )
    final_sources = finalized["sources"]
    duration_seconds = time.monotonic() - started_at
    markdown_path = output_directory / ports.report_filename(export_prefix, "md")
    ports.write_text(markdown_path, final_report)

    pdf_path = output_directory / ports.report_filename(export_prefix, "pdf")
    warnings = []
    try:
        ports.create_pdf(
            markdown_text=final_report,
            output_path=pdf_path,
            company_name=target_profile.brand_name,
            company_url=target_profile.official_url,
            country=country,
            generated_at=run_timestamp,
        )
        ports.stage_success("Styled PDF report generated")
    except Exception as exc:
        pdf_path = None
        warning = f"PDF generation failed: {type(exc).__name__}: {exc}"
        warnings.append(warning)
        ports.stage_warning(warning)

    ports.write_json(
        raw_directory / "06_final_report_record.json",
        ports.clean_record(report_result["record"]),
    )
    ports.stage_success(
        f"Report generated in {ports.format_duration(duration_seconds)}"
    )
    return {
        "report_result": report_result,
        "final_report": final_report,
        "final_sources": final_sources,
        "bright_data_usage": bright_data_usage,
        "markdown_path": markdown_path,
        "pdf_path": pdf_path,
        "duration_seconds": duration_seconds,
        "warnings": warnings,
    }
