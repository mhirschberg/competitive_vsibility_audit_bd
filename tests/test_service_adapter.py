"""Offline parity for the transitional hosted provider adapter."""

import asyncio
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import tldextract

from hosted.service_adapter import build_runtime_ports, run_with_legacy_runtime
from runner_builder import _build_service_runner_script
from tests.test_audit_pipeline import AuditPipelineTests, Model


class SnapshotTimeoutError(TimeoutError):
    def __init__(self, snapshot_id):
        super().__init__(f'pending {snapshot_id}')
        self.snapshot_id = snapshot_id


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

        def profile_record(prompt, timeout_seconds):
            self.assertEqual(timeout_seconds, 600)
            fields = dict(
                line.split(': ', 1) for line in prompt.splitlines()
                if line.startswith(('Name: ', 'Website: ', 'Domain: '))
            )
            is_target = fields['Name'] == 'Apple'
            return {'answer_text': json.dumps({
                'brand_name': fields['Name'],
                'official_url': fields['Website'], 'domain': fields['Domain'],
                'category': 'premium smartphones',
                'positioning': 'premium devices' if is_target else 'Android devices',
                'differentiators': ['ecosystem' if is_target else 'choice'],
                'relevant_products': ['iPhone' if is_target else 'Galaxy'],
                'target_customers': ['smartphone buyers'], 'key_features': [],
                'pricing_model': 'premium',
                'competitor_reason': 'Target company' if is_target else 'Phones',
                'confidence': 0.9, 'evidence': ['fixture evidence'],
            })}

        client = Model(
            active_search_engine=None,
            google_ai_mode=profile_record,
            answer_text=lambda record: record['answer_text'],
            wait_for_snapshot=lambda *_args, **_kwargs: [],
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
            '_competitor_decision_ports': lambda: object(),
            'locked_scope_local_domain_bonus': lambda *_args: 0,
            'LOCKED_SCOPE_VALIDATION_WORKERS': 3,
            'LOCKED_SCOPE_VALIDATION_LIMIT': 12,
            'cached_research_snapshot_ids': lambda _prompt: [],
            'locked_scope_brand_family': lambda value: value,
            'SelectedCompetitor': Model,
            'BrightDataAPIError': RuntimeError,
            'start_reddit_discovery_prefetch': competitor.start_reddit_prefetch,
            'run_profile_stage': lambda *_args, **_kwargs: (
                (_ for _ in ()).throw(AssertionError(
                    'service profile must not call notebook wrapper'
                ))
            ),
            'BrandProfile': Model,
            'parse_ai_json': json.loads,
            'normalize_public_url': lambda value: value,
            'get_root_domain': lambda value: value.split('/', 1)[0],
            'SnapshotTimeoutError': SnapshotTimeoutError,
            'serialize_profile_task': lambda item: {
                key: value for key, value in item.items()
                if key not in ('profile', 'record')
            },
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
        original_analyze = runtime['analyze_company_stage']
        def analyze_and_lock(settings):
            scope = {
                'brand_name': 'Apple', 'domain': 'apple.com',
                'official_url': 'https://apple.com/', 'country': 'US',
                'category': 'premium smartphones', 'market_role': 'manufacturer',
                'business_model': 'hardware manufacturer',
                'primary_customers': ['smartphone buyers'],
                'core_offerings': ['premium smartphones'], 'audit_focus': '',
            }
            result = original_analyze(settings)
            # The analyzer returns scope explicitly. Notebook compatibility
            # may still publish it globally in its own wrapper.
            result['locked_target_scope'] = scope
            return result
        runtime['analyze_company_stage'] = analyze_and_lock
        return runtime

    def test_adapter_runs_same_fixture_with_and_without_social(self):
        for reddit in (False, True):
            with self.subTest(reddit=reddit), tempfile.TemporaryDirectory() as root:
                events = []
                runtime = self.runtime(events)
                fixture_selector = runtime.pop('select_competitors_stage')
                runtime['generate_report_stage'] = lambda *_args, **_kwargs: (
                    (_ for _ in ()).throw(AssertionError(
                        'service report must not call notebook wrapper'
                    ))
                )
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
                offline_tldextract = tldextract.TLDExtract(
                    cache_dir=None, suffix_list_urls=(),
                )
                def select_with_shared_adapter(target, candidates, keywords, **kwargs):
                    self.assertEqual(
                        kwargs['scope']['market_role'], 'manufacturer'
                    )
                    return fixture_selector(
                        target, candidates, keywords, kwargs['scope']
                    )
                with patch('tldextract.extract', offline_tldextract), patch(
                    'hosted.service_adapter.select_competitors_with_provider',
                    side_effect=select_with_shared_adapter,
                ):
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
                self.assertNotIn('LOCKED_TARGET_SCOPE', runtime)
                self.assertEqual(runtime['bd_client'].active_search_engine, 'google')
                self.assertEqual(events[0], 'resolve')
                output = runtime['CURRENT_AUDIT_OUTPUT_DIRECTORY']
                self.assertTrue((output / '00_run_settings.json').is_file())
                self.assertTrue((output / '20260930-apple-us.json').is_file())
                company_checkpoint = json.loads(
                    (output / '01_company_analysis.json').read_text()
                )
                self.assertEqual(
                    company_checkpoint['locked_target_scope']['market_role'],
                    'manufacturer',
                )
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

    def test_service_boundary_installs_explicit_chatgpt_gemini_research_race(self):
        events = []
        runtime = self.runtime(events)
        legacy_client = runtime['bd_client']
        legacy_client.token = 'test-token'
        legacy_client.serp_zone = 'test-zone'
        legacy_client.country = 'DE'
        legacy_client.debug = False
        measured_google = lambda *_args, **_kwargs: {
            'answer_text': 'measured Google AI Mode'
        }
        legacy_client.google_ai_mode_measured = measured_google
        fixture_path = Path(__file__).parent / 'fixtures' / 'research_provider_responses.json'
        fixture = json.loads(fixture_path.read_text(encoding='utf-8'))
        saved_by_snapshot = {}
        triggered = []
        saved_cache = {}

        def trigger(dataset, payload):
            snapshot_id = f'snapshot-{dataset}'
            triggered.append(dataset)
            saved_by_snapshot[snapshot_id] = fixture['snapshots'][dataset]
            return snapshot_id

        class FakeStandaloneProvider:
            def __init__(self, **options):
                self.__dict__.update(options)
                self.active_search_engine = None

            def _engine_payload(self, engine, prompt, request_index, web_search):
                return engine, {
                    'prompt': prompt, 'request_index': request_index,
                    'web_search': web_search,
                }

            def trigger_dataset(self, dataset, payload):
                return trigger(dataset, payload)

            def snapshot_status(self, _snapshot):
                return {'status': 'ready'}

            def download_snapshot(self, snapshot):
                return saved_by_snapshot[snapshot]

            def record_snapshot_results(self, *_args):
                pass

            @staticmethod
            def answer_text(record):
                return record.get('answer_text', '')

            @staticmethod
            def log(*_args):
                pass

            @staticmethod
            def configure_usage_checkpoint(*_args, **_kwargs):
                pass

            @staticmethod
            def refresh_usage_results():
                pass

            @staticmethod
            def usage_summary():
                return {}

        runtime.update({
            'BrightDataProviderClient': FakeStandaloneProvider,
            'parse_bing_markdown': lambda **kwargs: kwargs,
        })
        runtime.update({
            'RESEARCH_PROVIDERS': ('chatgpt', 'gemini'),
            'cached_google_ai_snapshot_ids': lambda key: saved_cache.get(key, []),
            'remember_google_ai_snapshot': lambda key, sid: saved_cache.setdefault(
                key, []
            ).append(sid),
            'localize_google_ai_prompt': lambda prompt: f'DE: {prompt}',
            'identify_google_ai_research_task': lambda _prompt: 'company_research',
            'validate_google_ai_research_answer': lambda answer, _prompt: {
                'valid': answer == 'usable research',
                'reason': 'no usable answer',
            },
            'google_ai_snapshot_is_materializing': lambda _records: False,
            'FAILED_STATUSES': {'failed', 'canceled'},
            '_GOOGLE_AI_ONLY_REUSE': False,
            '_RESEARCH_RACE_SEMAPHORE': threading.BoundedSemaphore(3),
            'RESEARCH_POLL_SECONDS': 0,
            'ResearchRaceTimeoutError': TimeoutError,
            'BrightDataAPIError': RuntimeError,
        })

        build_runtime_ports(runtime)
        client = runtime['bd_client']
        self.assertIsInstance(client, FakeStandaloneProvider)
        self.assertIsNot(client, legacy_client)
        runtime['_GOOGLE_AI_ONLY_REUSE'] = True
        with self.assertRaisesRegex(RuntimeError, 'No saved research snapshots'):
            client.google_ai_mode('research question', timeout_seconds=3)
        self.assertEqual(triggered, [])

        runtime['_GOOGLE_AI_ONLY_REUSE'] = False
        result = client.google_ai_mode('research question', timeout_seconds=3)

        self.assertCountEqual(triggered, ['chatgpt', 'gemini'])
        self.assertEqual(result['_research_race']['provider'], 'gemini')
        self.assertEqual(result['answer_text'], 'usable research')
        self.assertEqual(
            runtime['RESEARCH_PROVIDER_ADAPTER'].__class__.__name__,
            'ResearchProviderAdapter',
        )
        self.assertTrue(callable(client.google_ai_mode_measured))
        self.assertEqual(
            client.google_ai_mode_measured()['answer_text'],
            'measured Google AI Mode',
        )


if __name__ == '__main__':
    unittest.main()
