"""Prepare a new or resumed audit without depending on notebook globals."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time


RUN_SETTINGS_KEYS = (
    'company_name', 'company_domain', 'audit_focus',
    'company_url', 'submitted_company_url',
    'submitted_company_domain', 'official_site_resolution',
    'country', 'search_engine', 'serp_zone',
    'include_reddit_analysis', 'reddit_comment_posts_per_cohort',
    'include_google_ai_mode', 'include_chatgpt_visibility',
    'include_gemini_visibility', 'include_copilot_visibility',
    'wait_longer_for_chatgpt', 'wait_longer_for_gemini',
    'wait_longer_for_copilot', 'wait_longer_for_google_ai_mode',
)


@dataclass
class AuditPreparationPorts:
    resolve_official_site: object
    get_root_domain: object
    find_latest_audit_to_continue: object
    slugify: object
    audit_export_prefix: object
    configure_usage_checkpoint: object
    write_json: object
    configure_google_ai_race_cache: object
    import_google_ai_snapshot_ids: object
    notice: object
    set_output_directory: object


async def prepare_audit_run_core(settings, *, base_directory, ports):
    """Resolve the official site, then prepare checkpoints before paid work."""
    settings = dict(settings)
    site_resolution = await asyncio.to_thread(
        ports.resolve_official_site, settings['company_url']
    )
    settings['submitted_company_url'] = site_resolution['submitted_url']
    settings['submitted_company_domain'] = settings['company_domain']
    settings['company_url'] = site_resolution['canonical_url']
    settings['company_domain'] = ports.get_root_domain(
        site_resolution['canonical_hostname']
    )
    site_resolution['submitted_domain'] = ports.get_root_domain(
        site_resolution['submitted_hostname']
    )
    site_resolution['canonical_domain'] = settings['company_domain']
    settings['official_site_resolution'] = site_resolution
    if site_resolution['redirect_chain']:
        ports.notice(
            f"[cyan]Official website redirects to {settings['company_url']}; "
            f"using {settings['company_domain']} for scoring.[/cyan]"
        )

    continuing = bool(settings.get('continue_last_audit'))
    audit_started_at = time.monotonic()
    if continuing:
        output_directory = ports.find_latest_audit_to_continue(settings)
        previous = json.loads((
            output_directory / '01_company_analysis.json'
        ).read_text(encoding='utf-8'))
        run_timestamp = datetime.fromisoformat(previous['created_at'])
        run_id = output_directory.name.removeprefix('competitive-visibility-')
        ports.notice(f'[cyan]Continuing {output_directory}[/cyan]')
        if not (output_directory / '00_run_settings.json').exists():
            ports.notice(
                '[yellow]Legacy checkpoint: only the company domain '
                'could be verified. Confirm that focus, country and '
                'Reddit setting match the interrupted run.[/yellow]'
            )
    else:
        run_timestamp = datetime.now(timezone.utc)
        run_id = (
            f"{ports.slugify(settings['company_name'])}"
            f"-{run_timestamp.strftime('%Y%m%d-%H%M%S')}"
        )
        output_directory = (
            Path(base_directory) / f'competitive-visibility-{run_id}'
        )

    export_prefix = ports.audit_export_prefix(
        run_timestamp, settings['company_name'],
        settings.get('audit_focus', ''), settings['country'],
    )
    settings['audit_as_of_date'] = run_timestamp.date().isoformat()
    raw_directory = output_directory / 'raw'
    output_directory.mkdir(parents=True, exist_ok=True)
    raw_directory.mkdir(parents=True, exist_ok=True)
    ports.set_output_directory(output_directory)
    ports.configure_usage_checkpoint(
        raw_directory / 'bright_data_usage_events.json', restore=continuing,
    )
    if not continuing:
        ports.write_json(
            output_directory / '00_run_settings.json',
            {key: settings.get(key) for key in RUN_SETTINGS_KEYS},
        )
    ports.configure_google_ai_race_cache(
        raw_directory / 'google_ai_snapshot_cache.json',
        only_reuse=continuing,
    )
    if continuing and settings.get('recovery_snapshot_ids'):
        imported = await asyncio.to_thread(
            ports.import_google_ai_snapshot_ids,
            settings['recovery_snapshot_ids'],
        )
        ports.notice(
            f'[cyan]Imported {imported} existing snapshot ID(s).[/cyan]'
        )
    return {
        'settings': settings,
        'site_resolution': site_resolution,
        'continuing': continuing,
        'run_timestamp': run_timestamp,
        'run_id': run_id,
        'output_directory': output_directory,
        'raw_directory': raw_directory,
        'export_prefix': export_prefix,
        'audit_started_at': audit_started_at,
    }
