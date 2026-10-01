"""Bridge existing provider functions to the importable audit coordinator.

This is a migration adapter, not the final lightweight provider implementation.
The caller supplies an already-initialized runtime namespace; this module
never reads or executes the notebook and never initiates a provider call.
"""

from pathlib import Path

from audit_core.audit_finalize_stage import AuditFinalizePorts
from audit_core.audit_pipeline import (
    AuditPipelinePorts, AuditRunContext, run_audit_pipeline,
)
from audit_core.audit_preparation import (
    AuditPreparationPorts, prepare_audit_run_core,
)
from audit_core.company_stage import CompanyStagePorts
from audit_core.competitor_selection_stage import CompetitorSelectionStagePorts
from audit_core.profile_stage import ProfileStagePorts
from audit_core.report_render_stage import ReportRenderPorts
from audit_core.search_stage import SearchStagePorts
from audit_core.social_completion_stage import SocialCompletionPorts
from audit_core.visibility_checkpoint_stage import VisibilityCheckpointPorts


def build_runtime_ports(runtime):
    """Bind legacy provider/artifact functions before any audit work starts."""
    def need(name):
        return runtime[name]

    client = need('bd_client')
    console = need('console')
    write_json = need('write_json')
    model_to_dict = need('model_to_dict')
    clean_record = need('clean_record_for_storage')
    success = need('print_stage_success')
    warning = need('print_stage_warning')
    format_duration = need('format_duration')

    def after_search(search):
        runtime['ACTIVE_SEARCH_ENGINE'] = search['search_engine']
        runtime['ACTIVE_SEARCH_STATUS'] = search['search_status']
        runtime['LAST_AI_MODE_DISCOVERY'] = search['ai_mode_discovery']
        client.active_search_engine = search['search_engine']

    def finalize_ports():
        utility = runtime.get('LAST_UTILITY_REPORT_RESULT') or {}
        return AuditFinalizePorts(
            build_record=need('build_audit_record'),
            model_to_dict=model_to_dict,
            serialize_engine_result=need('serialize_engine_result'),
            generator_name=utility.get('engine_name', 'Unknown'),
            report_filename=need('report_filename'),
            write_json=write_json,
            create_zip=need('create_audit_zip'),
            stage_success=success,
            completion_notice=lambda message: console.print(
                f'\n[bold green]{message}[/bold green]'
            ),
            format_duration=format_duration,
        )

    def preflight():
        # Missing bindings must fail before canonical-site resolution or paid work.
        for name in (
            'restore_locked_target_scope', 'CompanyIntake', 'BrandAnalysis',
            'BuyerIntentKeyword', 'analyze_company_stage', 'run_serp_stage',
            'CompetitorCandidate', 'select_competitors_stage',
            'start_reddit_discovery_prefetch', 'run_profile_stage',
            'serialize_profile_task', 'run_visibility_stage',
            'run_reddit_social_stage', 'serialize_engine_result',
            'summarize_reddit_audit_warning', 'generate_report_stage',
            'finalize_report', 'insert_reddit_report_section',
            'build_bright_data_usage_section', 'write_text',
            'report_filename', 'create_styled_pdf_report',
            'build_audit_record', 'create_audit_zip',
            'BRIGHT_DATA_PRICE_PER_1000_RESULTS_USD',
        ):
            need(name)
        for name in ('refresh_usage_results', 'usage_summary'):
            getattr(client, name)
    preflight()

    return AuditPipelinePorts(
        company_stage=CompanyStagePorts(
            analyze=need('analyze_company_stage'),
            intake_factory=need('CompanyIntake'),
            brand_factory=need('BrandAnalysis'),
            keyword_factory=need('BuyerIntentKeyword'),
            get_locked_scope=lambda: runtime.get('LOCKED_TARGET_SCOPE'),
            set_locked_scope=lambda scope: runtime.__setitem__('LOCKED_TARGET_SCOPE', scope),
            restore_locked_scope=need('restore_locked_target_scope'),
            model_to_dict=model_to_dict, write_json=write_json,
            clean_record=clean_record, stage_success=success,
        ),
        search_stage=SearchStagePorts(
            run_search=need('run_serp_stage'),
            candidate_factory=need('CompetitorCandidate'),
            model_to_dict=model_to_dict, write_json=write_json,
            stage_success=success, stage_warning=warning,
            format_duration=format_duration,
        ),
        competitor_stage=CompetitorSelectionStagePorts(
            select_competitors=need('select_competitors_stage'),
            configure_race_cache=need('configure_google_ai_race_cache'),
            write_json=write_json, model_to_dict=model_to_dict,
            clean_record=clean_record, stage_warning=warning,
            print_selected=lambda competitor: console.print(
                f'      ✓ {competitor.brand_name}'
            ),
            social_notice=lambda: console.print(
                '      [cyan]↗ Social discovery started in parallel; '
                'snapshots are labelled [Social · …].[/cyan]'
            ),
            start_reddit_prefetch=need('start_reddit_discovery_prefetch'),
        ),
        profile_stage=ProfileStagePorts(
            run_profiles=need('run_profile_stage'),
            model_to_dict=model_to_dict,
            serialize_task=need('serialize_profile_task'),
            write_json=write_json, stage_success=success, stage_warning=warning,
        ),
        visibility_stage=VisibilityCheckpointPorts(
            run_visibility=need('run_visibility_stage'),
            run_reddit_social=need('run_reddit_social_stage'),
            serialize_engine_result=need('serialize_engine_result'),
            write_json=write_json, stage_success=success,
            stage_warning=warning, format_duration=format_duration,
        ),
        social_stage=SocialCompletionPorts(
            print_stage=need('print_stage'), stage_success=success,
            stage_warning=warning, format_duration=format_duration,
            summarize_warning=need('summarize_reddit_audit_warning'),
            write_json=write_json,
        ),
        report_stage=ReportRenderPorts(
            generate_report=need('generate_report_stage'),
            finalize_report=need('finalize_report'),
            insert_reddit_section=need('insert_reddit_report_section'),
            refresh_usage=client.refresh_usage_results,
            usage_summary=client.usage_summary,
            build_usage_section=need('build_bright_data_usage_section'),
            write_json=write_json, write_text=need('write_text'),
            report_filename=need('report_filename'),
            create_pdf=need('create_styled_pdf_report'),
            clean_record=clean_record, stage_success=success,
            stage_warning=warning, format_duration=format_duration,
        ),
        finalize_stage_factory=finalize_ports,
        stage_banner=need('print_stage'),
        price_per_1000=need('BRIGHT_DATA_PRICE_PER_1000_RESULTS_USD'),
        after_search=after_search,
    )


def build_preparation_ports(runtime):
    """Bind official-site and checkpoint operations from the same runtime."""
    def need(name):
        return runtime[name]

    return AuditPreparationPorts(
        resolve_official_site=need('resolve_official_site'),
        get_root_domain=need('get_root_domain'),
        find_latest_audit_to_continue=need('find_latest_audit_to_continue'),
        slugify=need('slugify'),
        audit_export_prefix=need('audit_export_prefix'),
        configure_usage_checkpoint=need('bd_client').configure_usage_checkpoint,
        write_json=need('write_json'),
        configure_google_ai_race_cache=need('configure_google_ai_race_cache'),
        import_google_ai_snapshot_ids=need('import_google_ai_snapshot_ids'),
        notice=need('console').print,
        set_output_directory=lambda path: runtime.__setitem__(
            'CURRENT_AUDIT_OUTPUT_DIRECTORY', path
        ),
    )


async def run_with_legacy_runtime(settings, runtime, *, base_directory):
    """Run the shared coordinator with existing, already-loaded providers."""
    pipeline_ports = build_runtime_ports(runtime)
    preparation_ports = build_preparation_ports(runtime)
    runtime['CURRENT_AUDIT_OUTPUT_DIRECTORY'] = None
    runtime['LOCKED_TARGET_SCOPE'] = None
    prepared = await prepare_audit_run_core(
        settings, base_directory=Path(base_directory), ports=preparation_ports,
    )
    context = AuditRunContext(
        run_id=prepared['run_id'],
        run_timestamp=prepared['run_timestamp'],
        export_prefix=prepared['export_prefix'],
        output_directory=prepared['output_directory'],
        raw_directory=prepared['raw_directory'],
        site_resolution=prepared['site_resolution'],
        continuing=prepared['continuing'],
        audit_started_at=prepared['audit_started_at'],
    )
    return await run_audit_pipeline(
        prepared['settings'], context, ports=pipeline_ports,
    )
