"""Bridge existing provider functions to the importable audit coordinator.

This is a migration adapter, not the final lightweight provider implementation.
The caller supplies an already-initialized runtime namespace; this module
never reads or executes the notebook and never initiates a provider call.
"""

from pathlib import Path
import threading
from types import MethodType

import reddit_social
from audit_core.research_race import ResearchProviderAdapter
from audit_core.audit_finalize_stage import AuditFinalizePorts
from audit_core.audit_pipeline import (
    AuditPipelinePorts, AuditRunContext, run_audit_pipeline,
)
from audit_core.audit_preparation import (
    AuditPreparationPorts, prepare_audit_run_core,
)
from audit_core.artifact_writes import write_json_with_scope
from audit_core.company_stage import CompanyStagePorts
from audit_core.competitor_selection_stage import CompetitorSelectionStagePorts
from audit_core.competitor_pipeline import select_competitors_with_provider
from audit_core.profile_research import (
    ProfileResearchPorts, run_profile_research_core,
)
from audit_core.profile_provider import (
    fallback_profile_core, generate_profile_sync_core,
    normalize_brand_profile_core, recover_profile_sync_core,
)
from audit_core.profile_stage import ProfileStagePorts
from audit_core.primitives import ensure_string_list, normalize_confidence
from audit_core.report_content import DETERMINISTIC_REPORT_GENERATOR
from audit_core.report_evidence import build_report_evidence_core
from audit_core.report_render_stage import ReportRenderPorts
from audit_core.report_stage import generate_report_stage_core
from audit_core.serp_metrics import calculate_all_serp_metrics
from audit_core.search_stage import SearchStagePorts
from audit_core.social_completion_stage import SocialCompletionPorts
from audit_core.visibility_checkpoint_stage import VisibilityCheckpointPorts
from audit_core.visibility_prompt import build_visibility_prompt_core
from audit_core.visibility_stage import run_visibility_stage_core
from audit_core.visibility_sources import collect_visibility_sources_service
from audit_core.utility_ai_race import race_utility_ai_core
from audit_core.research_validation import (
    identify_research_task,
    snapshot_is_materializing,
    validate_research_answer,
)
from audit_core.brightdata_transport import (
    CHATGPT_DATASET_ID, GEMINI_DATASET_ID, FAILED_STATUSES,
    BrightDataAPIError,
)


_RESEARCH_BINDINGS = (
    'RESEARCH_PROVIDERS', 'cached_google_ai_snapshot_ids',
    'remember_google_ai_snapshot', 'localize_google_ai_prompt',
    'FAILED_STATUSES',
    '_GOOGLE_AI_ONLY_REUSE', 'ResearchRaceTimeoutError', 'BrightDataAPIError',
)


def _bind_research_provider_adapter(client, runtime):
    """Install the explicit ChatGPT/Gemini race at the legacy-client boundary.

    The generated notebook provides these callbacks today; the service runner
    captures them once here, so its coordinator invokes the standalone adapter
    rather than the notebook's monkey-patched ``google_ai_mode`` function.
    Measured Google AI Mode is intentionally untouched.
    """
    # BrightDataAPIError is also used by unrelated provider adapters, so it
    # must not by itself opt a small runtime into the complete research race.
    research_markers = tuple(
        name for name in _RESEARCH_BINDINGS if name != 'BrightDataAPIError'
    )
    present = [name for name in research_markers if name in runtime]
    if not present:
        # Small stage-fixture runtimes may not model any research provider.
        return None
    missing = [name for name in _RESEARCH_BINDINGS if name not in runtime]
    if missing:
        raise KeyError(f'Missing research provider bindings: {missing}')

    adapter = ResearchProviderAdapter(
        providers=runtime['RESEARCH_PROVIDERS'],
        cached_snapshot_ids=runtime['cached_google_ai_snapshot_ids'],
        remember_snapshot=runtime['remember_google_ai_snapshot'],
        localize_prompt=runtime['localize_google_ai_prompt'],
        identify_task=identify_research_task,
        validate_answer=lambda answer, prompt: validate_research_answer(
            answer,
            prompt,
            parse_json=runtime['parse_ai_json'],
            remove_boilerplate=runtime['remove_ai_boilerplate'],
        ),
        is_materializing=snapshot_is_materializing,
        failed_statuses=runtime['FAILED_STATUSES'],
        only_reuse=lambda: runtime['_GOOGLE_AI_ONLY_REUSE'],
        semaphore=runtime.get('_RESEARCH_RACE_SEMAPHORE')
        or threading.BoundedSemaphore(3),
        poll_seconds=runtime.get('RESEARCH_POLL_SECONDS', 5),
        error_type=runtime['BrightDataAPIError'],
        timeout_type=runtime['ResearchRaceTimeoutError'],
        legacy_snapshot_ids=runtime['cached_google_ai_snapshot_ids'],
    )

    def race(prompt, timeout_seconds=720):
        return adapter.race(client, prompt, timeout_seconds)

    client.google_ai_mode = race
    runtime['RESEARCH_PROVIDER_ADAPTER'] = adapter
    runtime['race_research_providers'] = race
    return adapter


def _standalone_brightdata_client(runtime):
    """Replace the initialized notebook client when its credentials exist."""
    legacy = runtime.get('bd_client')
    if legacy is None or not all(
        hasattr(legacy, name) for name in ('token', 'serp_zone', 'country')
    ):
        # Lightweight coordinator fixtures can continue to inject a fake port.
        return legacy

    if not callable(runtime.get('parse_bing_markdown')):
        raise KeyError('Missing standalone Bright Data binding: parse_bing_markdown')

    factory = runtime.get('BrightDataProviderClient')
    if factory is None:
        from hosted.brightdata_provider import BrightDataProviderClient
        factory = BrightDataProviderClient

    console = runtime.get('console')
    logger = (
        (lambda message, style='dim': console.print(
            f'[{style}]{message}[/{style}]'
        ))
        if console is not None else None
    )
    client = factory(
        token=legacy.token,
        serp_zone=legacy.serp_zone,
        country=legacy.country,
        debug=getattr(legacy, 'debug', False),
        logger=logger,
        parse_bing_markdown=runtime.get('parse_bing_markdown'),
    )

    measured_google = getattr(legacy, 'google_ai_mode_measured', None)
    measured_function = getattr(measured_google, '__func__', None)
    if measured_function is not None:
        client.google_ai_mode_measured = MethodType(measured_function, client)
    elif callable(measured_google):
        client.google_ai_mode_measured = (
            lambda *args, **kwargs: measured_google(*args, **kwargs)
        )

    runtime['bd_client'] = client
    return client


def _service_report_generator(runtime, client):
    """Generate the report through shared deterministic modules and explicit ports."""
    def collect_sources(visibility, max_per_engine=10):
        return collect_visibility_sources_service(
            visibility,
            max_per_engine,
            resolve_google_goto_url=runtime.get('resolve_google_goto_url'),
            is_google_goto_url=runtime.get('is_google_goto_url'),
        )

    def generate_report(
        target_profile, competitor_profiles, keywords,
        keyword_serp_results, visibility, locked_scope,
    ):
        settings = runtime.get('SERVICE_AUDIT_SETTINGS') or runtime.get(
            'AUDIT_SETTINGS', {}
        )

        def build_evidence(**kwargs):
            return build_report_evidence_core(
                **kwargs,
                search_engine=runtime.get('ACTIVE_SEARCH_ENGINE', ''),
                search_status=runtime.get('ACTIVE_SEARCH_STATUS', 'unavailable'),
                country=settings.get('country') or getattr(client, 'country', ''),
                locked_scope=locked_scope,
                collect_sources=collect_sources,
            )

        result = generate_report_stage_core(
            target_profile,
            competitor_profiles,
            keywords,
            keyword_serp_results,
            visibility,
            country=settings.get('country') or getattr(client, 'country', ''),
            search_engine=runtime.get('ACTIVE_SEARCH_ENGINE', ''),
            search_status=runtime.get('ACTIVE_SEARCH_STATUS', 'unavailable'),
            calculate_serp_metrics=calculate_all_serp_metrics,
            collect_sources=collect_sources,
            build_evidence=build_evidence,
        )
        runtime['LAST_UTILITY_REPORT_RESULT'] = {
            'engine': 'deterministic',
            'engine_name': DETERMINISTIC_REPORT_GENERATOR,
            'snapshot_id': None,
            'answer': result['report'],
            'record': result['record'],
        }
        return result

    return generate_report


def _service_profile_runner(runtime):
    """Bind profile orchestration and provider calls through shared modules."""
    def normalize_profile(data, job):
        return normalize_brand_profile_core(
            data,
            job,
            profile_factory=runtime['BrandProfile'],
            normalize_public_url=runtime['normalize_public_url'],
            get_root_domain=runtime['get_root_domain'],
            ensure_string_list=ensure_string_list,
            normalize_confidence=normalize_confidence,
        )

    def generate_profile(job, target_brand, audit_focus=''):
        return generate_profile_sync_core(
            job,
            target_brand,
            audit_focus,
            client=runtime['bd_client'],
            parse_ai_json=runtime['parse_ai_json'],
            normalize_profile=normalize_profile,
            snapshot_timeout_error=runtime['SnapshotTimeoutError'],
        )

    def recover_profile(task_result):
        return recover_profile_sync_core(
            task_result,
            client=runtime['bd_client'],
            parse_ai_json=runtime['parse_ai_json'],
            normalize_profile=normalize_profile,
            provider_error=RuntimeError,
        )

    def fallback_profile(job, target_brand):
        return fallback_profile_core(
            job, target_brand, profile_factory=runtime['BrandProfile'],
        )

    def pending_notice(count):
        console = runtime.get('console')
        if console is not None:
            console.print(f'      Waiting for {count} late profile snapshot(s)...')

    def run_profiles(target_brand, selected_competitors, audit_focus=''):
        return run_profile_research_core(
            target_brand,
            selected_competitors,
            audit_focus,
            ports=ProfileResearchPorts(
                generate_profile=generate_profile,
                recover_profile=recover_profile,
                fallback_profile=fallback_profile,
                root_domain=runtime['get_root_domain'],
                pending_notice=pending_notice,
            ),
        )

    return run_profiles


def _service_visibility_runner(runtime, client):
    """Bind the measured-visibility core to the standalone provider client."""
    async def run_visibility(
        *, target_profile, all_profiles, keywords, include_copilot,
        include_google_ai_mode, include_chatgpt, include_gemini,
        wait_longer_for_chatgpt, wait_longer_for_gemini,
        wait_longer_for_copilot,
    ):
        settings = runtime.get('SERVICE_AUDIT_SETTINGS') or runtime.get(
            'AUDIT_SETTINGS', {}
        )
        return await run_visibility_stage_core(
            target_profile,
            all_profiles,
            keywords,
            bd_client=client,
            prompt_builder=lambda target_profile, keywords: (
                build_visibility_prompt_core(
                    target_profile,
                    keywords,
                    audit_focus=settings.get('audit_focus', ''),
                )
            ),
            ai_mode_discovery=runtime.get('LAST_AI_MODE_DISCOVERY'),
            include_copilot=include_copilot,
            include_google_ai_mode=include_google_ai_mode,
            include_chatgpt=include_chatgpt,
            include_gemini=include_gemini,
            wait_longer_for_chatgpt=wait_longer_for_chatgpt,
            wait_longer_for_gemini=wait_longer_for_gemini,
            wait_longer_for_copilot=wait_longer_for_copilot,
        )

    return run_visibility


def _service_utility_ai_race(runtime, client):
    """Build Reddit's utility race from shared code and explicit providers."""
    def validate_json_object(answer):
        try:
            parsed = runtime['parse_ai_json'](answer)
            if not isinstance(parsed, dict):
                return {'valid': False, 'reason': 'Parsed result was not a JSON object.'}
            return {'valid': True, 'reason': 'Parseable JSON object', 'parsed': parsed}
        except Exception as exc:
            return {'valid': False, 'reason': f'{type(exc).__name__}: {exc}'}

    def race(prompt, validator=None, timeout_seconds=900, task_name='utility task'):
        result = race_utility_ai_core(
            client,
            prompt,
            validator=validator or validate_json_object,
            timeout_seconds=timeout_seconds,
            task_name=task_name,
            dataset_ids={
                'chatgpt': CHATGPT_DATASET_ID,
                'gemini': GEMINI_DATASET_ID,
            },
            failed_statuses=FAILED_STATUSES,
            error_type=BrightDataAPIError,
        )
        runtime['LAST_UTILITY_AI_RESULT'] = result
        return result

    return race


def _service_reddit_runners(
    runtime, client, utility_race=None, reddit_module=reddit_social,
):
    """Run the shared Reddit module with explicit service providers."""
    if utility_race is None:
        raise ValueError('The service Reddit utility race must be explicit.')

    def reddit_context():
        return reddit_module.bind_reddit_runtime(
            client,
            utility_race,
            parse_json=runtime['parse_ai_json'],
            is_google_goto_url=runtime.get('is_google_goto_url'),
            resolve_google_goto_url=runtime.get('resolve_google_goto_url'),
        )

    async def start_discovery(**kwargs):
        with reddit_context():
            return await reddit_module.start_reddit_discovery_prefetch(**kwargs)

    async def run_social_stage(**kwargs):
        with reddit_context():
            return await reddit_module.run_reddit_social_stage(**kwargs)

    return start_discovery, run_social_stage


def build_runtime_ports(runtime):
    """Bind explicit providers and legacy stage/artifact functions."""
    def need(name):
        return runtime[name]

    client = _standalone_brightdata_client(runtime)
    if client is None:
        raise KeyError('bd_client')
    runtime['bd_client'] = client
    _bind_research_provider_adapter(client, runtime)
    console = need('console')
    write_json = need('write_json')
    model_to_dict = need('model_to_dict')
    clean_record = need('clean_record_for_storage')
    success = need('print_stage_success')
    warning = need('print_stage_warning')
    format_duration = need('format_duration')
    company_scope = {'value': None}

    def write_company_json(path, data):
        return write_json_with_scope(
            path,
            data,
            locked_target_scope=company_scope['value'],
            write_json_fn=write_json,
        )

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

    def select_competitors(target_brand, candidates, keywords, scope):
        if not isinstance(scope, dict) or not scope:
            raise need('BrightDataAPIError')(
                'Target scope was not locked during Stage 1.'
            )
        return select_competitors_with_provider(
            target_brand,
            candidates,
            keywords,
            scope=scope,
            client=client,
            parse_ai_json=need('parse_ai_json'),
            decision_ports=need('_competitor_decision_ports')(),
            local_domain_bonus=need('locked_scope_local_domain_bonus'),
            validation_workers=need('LOCKED_SCOPE_VALIDATION_WORKERS'),
            validation_limit=need('LOCKED_SCOPE_VALIDATION_LIMIT'),
            only_reuse=runtime.get('_GOOGLE_AI_ONLY_REUSE', False),
            cached_snapshot_ids=need('cached_research_snapshot_ids'),
            brand_family=need('locked_scope_brand_family'),
            selected_factory=need('SelectedCompetitor'),
            error_type=need('BrightDataAPIError'),
            output_dir=runtime.get('CURRENT_AUDIT_OUTPUT_DIRECTORY'),
            write_json=write_json,
            clean_record=clean_record,
        )

    def preflight():
        # Missing bindings must fail before canonical-site resolution or paid work.
        for name in (
            'restore_locked_target_scope', 'CompanyIntake', 'BrandAnalysis',
            'BuyerIntentKeyword', 'analyze_company_stage', 'run_serp_stage',
            'CompetitorCandidate', '_competitor_decision_ports',
            'locked_scope_local_domain_bonus', 'LOCKED_SCOPE_VALIDATION_WORKERS',
            'LOCKED_SCOPE_VALIDATION_LIMIT', 'cached_research_snapshot_ids',
            'locked_scope_brand_family', 'SelectedCompetitor', 'BrightDataAPIError',
            'BrandProfile', 'is_google_goto_url', 'resolve_google_goto_url',
            'parse_ai_json', 'normalize_public_url', 'get_root_domain',
            'remove_ai_boilerplate',
            'SnapshotTimeoutError',
            'serialize_profile_task',
            'serialize_engine_result',
            'summarize_reddit_audit_warning',
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
    generate_report = _service_report_generator(runtime, client)
    run_profiles = _service_profile_runner(runtime)
    run_visibility = _service_visibility_runner(runtime, client)
    start_reddit_discovery, run_reddit_social = _service_reddit_runners(
        runtime,
        client,
        utility_race=_service_utility_ai_race(runtime, client),
        reddit_module=runtime.get('reddit_module', reddit_social),
    )

    return AuditPipelinePorts(
        company_stage=CompanyStagePorts(
            analyze=need('analyze_company_stage'),
            intake_factory=need('CompanyIntake'),
            brand_factory=need('BrandAnalysis'),
            keyword_factory=need('BuyerIntentKeyword'),
            get_locked_scope=lambda: None,
            set_locked_scope=lambda scope: company_scope.__setitem__(
                'value', dict(scope) if isinstance(scope, dict) else scope
            ),
            restore_locked_scope=need('restore_locked_target_scope'),
            model_to_dict=model_to_dict, write_json=write_company_json,
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
            select_competitors=select_competitors,
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
            start_reddit_prefetch=start_reddit_discovery,
        ),
        profile_stage=ProfileStagePorts(
            run_profiles=run_profiles,
            model_to_dict=model_to_dict,
            serialize_task=need('serialize_profile_task'),
            write_json=write_json, stage_success=success, stage_warning=warning,
        ),
        visibility_stage=VisibilityCheckpointPorts(
            run_visibility=run_visibility,
            run_reddit_social=run_reddit_social,
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
            generate_report=generate_report,
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
    prepared = await prepare_audit_run_core(
        settings, base_directory=Path(base_directory), ports=preparation_ports,
    )
    runtime['SERVICE_AUDIT_SETTINGS'] = prepared['settings']
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
