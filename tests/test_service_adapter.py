"""Offline parity for the transitional hosted provider adapter."""

import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from hosted.service_adapter import run_with_legacy_runtime
from runner_builder import _build_service_runner_script
from tests.test_audit_pipeline import AuditPipelineTests, Model


class ServiceAdapterTests(unittest.TestCase):
    def test_opt_in_runner_calls_shared_coordinator_once(self):
        source = _build_service_runner_script(
            'Apple', 'apple.com', 'premium smartphone', 'US',
            'auto', False, False,
        )
        compile(source, 'service-adapter-runner', 'exec')
        self.assertEqual(source.count('run_with_legacy_runtime(AUDIT_SETTINGS'), 1)
        self.assertNotIn(
            'asyncio.run(run_competitive_visibility_audit(AUDIT_SETTINGS))',
            source,
        )

    def runtime(self, events):
        fixture = AuditPipelineTests().make_ports(events)
        company = fixture.company_stage
        search = fixture.search_stage
        competitor = fixture.competitor_stage
        profile = fixture.profile_stage
        visibility = fixture.visibility_stage
        social = fixture.social_stage
        report = fixture.report_stage
        final = fixture.finalize_stage_factory()
        client = Model(
            active_search_engine=None,
            configure_usage_checkpoint=lambda path, restore: events.append(
                ('usage', restore)
            ),
            refresh_usage_results=report.refresh_usage,
            usage_summary=report.usage_summary,
        )
        runtime = {
            'bd_client': client,
            'console': Model(print=lambda message: None),
            'write_json': company.write_json,
            'model_to_dict': company.model_to_dict,
            'clean_record_for_storage': company.clean_record,
            'print_stage_success': company.stage_success,
            'print_stage_warning': search.stage_warning,
            'format_duration': search.format_duration,
            'restore_locked_target_scope': company.restore_locked_scope,
            'CompanyIntake': company.intake_factory,
            'BrandAnalysis': company.brand_factory,
            'BuyerIntentKeyword': company.keyword_factory,
            'analyze_company_stage': company.analyze,
            'run_serp_stage': search.run_search,
            'CompetitorCandidate': search.candidate_factory,
            'select_competitors_stage': competitor.select_competitors,
            'start_reddit_discovery_prefetch': competitor.start_reddit_prefetch,
            'run_profile_stage': profile.run_profiles,
            'serialize_profile_task': profile.serialize_task,
            'run_visibility_stage': visibility.run_visibility,
            'run_reddit_social_stage': visibility.run_reddit_social,
            'serialize_engine_result': visibility.serialize_engine_result,
            'summarize_reddit_audit_warning': social.summarize_warning,
            'generate_report_stage': report.generate_report,
            'finalize_report': report.finalize_report,
            'insert_reddit_report_section': report.insert_reddit_section,
            'build_bright_data_usage_section': report.build_usage_section,
            'write_text': report.write_text,
            'report_filename': report.report_filename,
            'create_styled_pdf_report': report.create_pdf,
            'build_audit_record': final.build_record,
            'create_audit_zip': final.create_zip,
            'BRIGHT_DATA_PRICE_PER_1000_RESULTS_USD': 1.5,
            'configure_google_ai_race_cache': lambda path, only_reuse: None,
            'print_stage': fixture.stage_banner,
            'resolve_official_site': lambda url: (
                events.append('resolve') or {
                    'submitted_url': url, 'submitted_hostname': 'apple.com',
                    'canonical_url': url, 'canonical_hostname': 'apple.com',
                    'redirect_chain': [],
                }
            ),
            'get_root_domain': lambda host: host,
            'find_latest_audit_to_continue': lambda settings: None,
            'slugify': lambda name: name.lower(),
            'audit_export_prefix': lambda *args: '20260930-apple-us',
            'import_google_ai_snapshot_ids': lambda ids: len(ids),
            'LAST_UTILITY_REPORT_RESULT': {'engine_name': 'ChatGPT'},
        }
        return runtime

    def test_adapter_runs_same_fixture_with_and_without_social(self):
        for reddit in (False, True):
            with self.subTest(reddit=reddit), tempfile.TemporaryDirectory() as root:
                events = []
                runtime = self.runtime(events)
                original_visibility = runtime['run_visibility_stage']
                async def checked_visibility(**kwargs):
                    self.assertEqual(runtime['ACTIVE_SEARCH_ENGINE'], 'google')
                    self.assertEqual(runtime['ACTIVE_SEARCH_STATUS'], 'available')
                    self.assertEqual(runtime['bd_client'].active_search_engine, 'google')
                    return await original_visibility(**kwargs)
                runtime['run_visibility_stage'] = checked_visibility
                settings = {
                    'company_name': 'Apple', 'company_domain': 'apple.com',
                    'company_url': 'https://apple.com/', 'country': 'US',
                    'audit_focus': 'premium smartphone',
                    'include_reddit_analysis': reddit,
                    'include_google_ai_mode': False,
                    'include_chatgpt_visibility': True,
                    'include_gemini_visibility': False,
                    'include_copilot_visibility': False,
                }
                result = asyncio.run(run_with_legacy_runtime(
                    settings, runtime, base_directory=Path(root),
                ))
                _, direct, _ = AuditPipelineTests().run_fixture(
                    Path(root) / 'direct', reddit=reddit,
                )
                for field in (
                    'selected', 'selection_record', 'search_results',
                    'visibility', 'social_status', 'usage', 'warnings',
                    'stage_names',
                ):
                    self.assertEqual(result[field], direct[field], field)
                self.assertEqual(result['selected'], ['Samsung'])
                self.assertEqual(result['social_status'],
                                 'success' if reddit else 'disabled')
                self.assertEqual(result['usage']['estimated_cost_usd'], 0.03)
                self.assertEqual(runtime['ACTIVE_SEARCH_ENGINE'], 'google')
                self.assertEqual(runtime['ACTIVE_SEARCH_STATUS'], 'available')
                self.assertIsNone(runtime['LAST_AI_MODE_DISCOVERY'])
                self.assertEqual(runtime['bd_client'].active_search_engine, 'google')
                self.assertEqual(events[0], 'resolve')
                output = runtime['CURRENT_AUDIT_OUTPUT_DIRECTORY']
                self.assertTrue((output / '00_run_settings.json').is_file())
                self.assertTrue((output / '20260930-apple-us.json').is_file())
                saved = json.loads((output / '00_run_settings.json').read_text())
                self.assertEqual(saved['company_domain'], 'apple.com')

    def test_missing_binding_fails_before_site_or_provider_work(self):
        events = []
        runtime = self.runtime(events)
        del runtime['run_serp_stage']
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(KeyError):
                asyncio.run(run_with_legacy_runtime(
                    {'company_url': 'https://apple.com/'}, runtime,
                    base_directory=Path(root),
                ))
            self.assertEqual(events, [])
            self.assertEqual(list(Path(root).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
