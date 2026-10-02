"""Offline parity for the transitional hosted provider adapter."""

import asyncio
import json
from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import tldextract
import reddit_social

from hosted.service_adapter import (
    _service_company_analyzer, _service_reddit_runners, _service_utility_ai_race,
    _service_search_runner, build_runtime_ports, run_with_legacy_runtime,
)
from hosted.brightdata_provider import BrightDataProviderClient
from audit_core.brightdata_transport import CHATGPT_DATASET_ID, GEMINI_DATASET_ID
from audit_core.competitor_scope import build_locked_target_scope
from audit_core.json_parsing import parse_ai_json as shared_parse_ai_json
from runner_builder import _build_service_runner_script
from tests.test_audit_pipeline import AuditPipelineTests, Model


class SnapshotTimeoutError(TimeoutError):
    def __init__(self, snapshot_id):
        super().__init__(f'pending {snapshot_id}')
        self.snapshot_id = snapshot_id


class ServiceAdapterTests(unittest.TestCase):
    def test_reddit_runners_bind_provider_context_for_each_call(self):
        client = object()
        utility_race = lambda **_kwargs: "answer"

        async def check_context(**kwargs):
            self.assertIs(reddit_social._reddit_client(), client)
            self.assertIs(reddit_social._reddit_utility_race(), utility_race)
            return kwargs

        runtime = {
        }
        with patch.object(
            reddit_social, 'start_reddit_discovery_prefetch', check_context
        ), patch.object(reddit_social, 'run_reddit_social_stage', check_context):
            start_discovery, run_social = _service_reddit_runners(
                runtime, client, utility_race=utility_race,
            )
            self.assertEqual(
                asyncio.run(start_discovery(brand='Acme')),
                {'brand': 'Acme'},
            )
            self.assertEqual(
                asyncio.run(run_social(brand='Acme')),
                {'brand': 'Acme'},
            )

    def test_service_utility_race_uses_shared_core_and_country_free_payloads(self):
        class Client:
            def __init__(self):
                self.triggers = []

            def log(self, *_args):
                pass

            def trigger_dataset(self, dataset_id, payload):
                self.triggers.append((dataset_id, payload))
                return f'snapshot-{dataset_id}'

            def snapshot_status(self, _snapshot_id):
                return {'status': 'ready'}

            def download_snapshot(self, _snapshot_id):
                return [{'answer_text': '{"ok": true}'}]

            def record_snapshot_results(self, *_args):
                pass

            @staticmethod
            def answer_text(record):
                return record['answer_text']

        client = Client()
        runtime = {}
        race = _service_utility_ai_race(runtime, client)
        result = race('Return JSON')
        self.assertEqual(result['status'], 'success')
        self.assertEqual(runtime['LAST_UTILITY_AI_RESULT'], result)
        self.assertCountEqual(
            [dataset for dataset, _ in client.triggers],
            [CHATGPT_DATASET_ID, GEMINI_DATASET_ID],
        )
        self.assertTrue(all(
            'country' not in str(payload).lower()
            for _, payload in client.triggers
        ))

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
            'bind_reddit_runtime': reddit_social.bind_reddit_runtime,
            'is_google_goto_url': lambda _url: False,
            'resolve_google_goto_url': lambda url: url,
            'run_profile_stage': lambda *_args, **_kwargs: (
                (_ for _ in ()).throw(AssertionError(
                    'service profile must not call notebook wrapper'
                ))
            ),
            'BrandProfile': Model,
            'remove_ai_boilerplate': lambda value: value,
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
        runtime['reddit_module'] = SimpleNamespace(
            bind_reddit_runtime=runtime['bind_reddit_runtime'],
            start_reddit_discovery_prefetch=runtime['start_reddit_discovery_prefetch'],
            run_reddit_social_stage=runtime['run_reddit_social_stage'],
        )
        original_analyze = company.analyze
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
        runtime['company_analysis_runner'] = analyze_and_lock
        return runtime

    def test_service_company_analyzer_uses_shared_provider_core(self):
        runtime = {
            'run_chatgpt_without_web': lambda *_args, **_kwargs: None,
            'normalize_company_intake': lambda **kwargs: kwargs,
            'complete_company_keywords': lambda **kwargs: kwargs,
            'proofread_buyer_keywords': lambda **kwargs: kwargs,
            'BrightDataAPIError': RuntimeError,
        }
        client = object()
        expected = {'workflow': 'shared-company-core'}
        with patch(
            'hosted.service_adapter.run_company_analysis_core',
            return_value=expected,
        ) as run_core:
            result = _service_company_analyzer(runtime, client)({'company_name': 'Acme'})
        self.assertIs(result, expected)
        ports = run_core.call_args.kwargs['ports']
        self.assertIs(ports.client, client)
        self.assertIs(ports.parse_json, shared_parse_ai_json)
        self.assertEqual(ports.error_type, RuntimeError)
        self.assertIs(ports.build_locked_scope, build_locked_target_scope)
        from audit_core.company_analysis import select_relevant_company_research
        self.assertIs(ports.select_relevant_research, select_relevant_company_research)

    def test_adapter_runs_same_fixture_with_and_without_social(self):
        for reddit in (False, True):
            with self.subTest(reddit=reddit), tempfile.TemporaryDirectory() as root:
                events = []
                runtime = self.runtime(events)
                # Artifact names, JSON/text/ZIP writes, and report-record
                # assembly are shared engine code, not notebook callbacks.
                for name in (
                    'write_json', 'write_text', 'create_audit_zip',
                    'report_filename', 'clean_record_for_storage',
                    'build_audit_record', 'build_bright_data_usage_section',
                    'format_duration', 'serialize_profile_task',
                    'serialize_engine_result',
                    'summarize_reddit_audit_warning', 'finalize_report',
                    'insert_reddit_report_section',
                    'restore_locked_target_scope',
                    'find_latest_audit_to_continue', 'slugify',
                    'audit_export_prefix',
                    'get_root_domain',
                    'normalize_public_url',
                ):
                    runtime.pop(name)
                fixture_selector = runtime.pop('select_competitors_stage')
                runtime['generate_report_stage'] = lambda *_args, **_kwargs: (
                    (_ for _ in ()).throw(AssertionError(
                        'service report must not call notebook wrapper'
                    ))
                )
                original_visibility = runtime['run_visibility_stage']
                async def forbidden_notebook_visibility(**_kwargs):
                    raise AssertionError(
                        'service visibility must not call notebook wrapper'
                    )

                async def checked_visibility_core(
                    target_profile, all_profiles, keywords, **kwargs
                ):
                    self.assertEqual(runtime['ACTIVE_SEARCH_ENGINE'], 'google')
                    self.assertEqual(runtime['ACTIVE_SEARCH_STATUS'], 'available')
                    self.assertEqual(runtime['bd_client'].active_search_engine, 'google')
                    self.assertIs(kwargs['bd_client'], runtime['bd_client'])
                    self.assertFalse(kwargs['include_google_ai_mode'])
                    self.assertTrue(kwargs['include_chatgpt'])
                    self.assertEqual(
                        kwargs['ai_mode_discovery'],
                        runtime['LAST_AI_MODE_DISCOVERY'],
                    )
                    self.assertIn(
                        'premium smartphone',
                        kwargs['prompt_builder'](
                            target_profile, keywords
                        ),
                    )
                    return await original_visibility(
                        target_profile=target_profile,
                        all_profiles=all_profiles,
                        keywords=keywords,
                        **{
                            name: kwargs[name]
                            for name in (
                                'include_copilot', 'include_google_ai_mode',
                                'include_chatgpt', 'include_gemini',
                                'wait_longer_for_chatgpt',
                                'wait_longer_for_gemini',
                                'wait_longer_for_copilot',
                            )
                        },
                    )

                runtime['run_visibility_stage'] = forbidden_notebook_visibility
                settings = {
                    'company_name': 'Apple', 'company_domain': 'apple.com',
                    'company_url': 'https://apple.com/', 'country': 'US',
                    'serp_zone': 'fixture-zone',
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
                ), patch(
                    'hosted.service_adapter.run_visibility_stage_core',
                    side_effect=checked_visibility_core,
                ):
                    result = asyncio.run(run_with_legacy_runtime(
                        settings, runtime, base_directory=Path(root),
                    ))
                self.assertEqual(
                    [item['brand_name'] for item in
                     result['competitor_selection']['selected']],
                    ['Samsung'],
                )
                self.assertEqual(
                    result['configuration']['include_reddit_analysis'], reddit,
                )
                self.assertEqual(
                    result['bright_data_usage']['estimated_cost_usd'], 0.03,
                )
                self.assertEqual(runtime['ACTIVE_SEARCH_ENGINE'], 'google')
                self.assertEqual(runtime['ACTIVE_SEARCH_STATUS'], 'available')
                self.assertIsNone(runtime['LAST_AI_MODE_DISCOVERY'])
                self.assertNotIn('LOCKED_TARGET_SCOPE', runtime)
                self.assertEqual(runtime['bd_client'].active_search_engine, 'google')
                self.assertEqual(events[0], 'resolve')
                output = runtime['CURRENT_AUDIT_OUTPUT_DIRECTORY']
                self.assertTrue((output / '00_run_settings.json').is_file())
                self.assertTrue(Path(result['files']['json_report']).is_file())
                self.assertTrue(Path(result['files']['json_report']).name.endswith(
                    '_competitive_visibility_audit.json'
                ))
                self.assertTrue(Path(result['files']['zip_archive']).is_file())
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

    def test_service_adapter_does_not_require_notebook_reddit_wrappers(self):
        runtime = self.runtime([])
        for name in (
            'bind_reddit_runtime',
            'start_reddit_discovery_prefetch',
            'run_reddit_social_stage',
        ):
            runtime.pop(name)
        ports = build_runtime_ports(runtime)
        self.assertTrue(callable(ports.visibility_stage.run_reddit_social))
        self.assertTrue(callable(ports.competitor_stage.start_reddit_prefetch))

    def test_service_search_runner_uses_shared_core_and_explicit_settings(self):
        client = BrightDataProviderClient('token', 'zone', 'US')
        client.choose_search_engine = lambda _query, requested: (
            setattr(client, 'requested_engine', requested) or 'google'
        )
        search_calls = []

        def search_serp(keyword, engine, language, num_results):
            search_calls.append((keyword, engine, language, num_results))
            return {
                'results': [
                    {'domain': f'site-{index}.example', 'rank': index}
                    for index in range(1, 6)
                ],
            }

        client.search_serp = search_serp

        runtime = {
            'SERVICE_AUDIT_SETTINGS': {
                'search_engine': 'auto',
                'include_google_ai_mode': False,
                'wait_longer_for_google_ai_mode': True,
            },
            '_GOOGLE_AI_ONLY_REUSE': True,
            'CompetitorCandidate': lambda **kwargs: SimpleNamespace(**kwargs),
            'model_to_dict': lambda item: item,
            'run_serp_stage': lambda *_args, **_kwargs: (
                (_ for _ in ()).throw(AssertionError(
                    'shared search core must bypass the notebook stage wrapper'
                ))
            ),
        }

        with patch(
            'audit_core.search_discovery.get_root_domain',
            side_effect=lambda domain: str(domain).removeprefix('www.'),
        ):
            result = asyncio.run(_service_search_runner(runtime, client)(
                ['first keyword', 'second keyword'], 'example.com',
            ))

        self.assertEqual(client.requested_engine, 'auto')
        self.assertEqual(result['search_status'], 'available')
        self.assertEqual(result['ai_mode_discovery']['results'], [])
        self.assertEqual(len(search_calls), 2)
        self.assertTrue(all(call[1] == 'google' for call in search_calls))

    def test_service_search_runner_uses_shared_google_ai_question_core(self):
        client = BrightDataProviderClient('token', 'zone', 'DE')
        client.choose_search_engine = lambda _query, _requested: 'google'
        measured_prompts = []

        def measured_google(prompt, timeout_seconds=720):
            measured_prompts.append((prompt, timeout_seconds))
            return {
                'answer_text': 'For the Germany market, buyers compare several options.',
                'citations': [],
            }

        async def keyword_task(**kwargs):
            return {
                'keyword': kwargs['keyword'], 'success': True, 'results': [],
            }

        client.google_ai_mode_measured = measured_google
        client.run_keyword_serp_task = keyword_task
        runtime = {
            'SERVICE_AUDIT_SETTINGS': {
                'country': 'DE', 'search_engine': 'google',
                'include_google_ai_mode': True,
                'wait_longer_for_google_ai_mode': False,
            },
            'CompetitorCandidate': lambda **kwargs: SimpleNamespace(**kwargs),
            'model_to_dict': lambda item: item,
            'SnapshotTimeoutError': SnapshotTimeoutError,
            'is_google_goto_url': lambda _url: False,
            'resolve_google_goto_url': lambda url: url,
            'get_root_domain': lambda url: str(url).split('/')[0],
        }

        with patch(
            'audit_core.search_discovery.get_root_domain',
            side_effect=lambda domain: str(domain).removeprefix('www.'),
        ):
            result = asyncio.run(_service_search_runner(runtime, client)(
                ['query one', 'query two', 'query three'], 'target.example',
            ))

        self.assertEqual(len(measured_prompts), 3)
        self.assertTrue(all('Germany' in prompt for prompt, _ in measured_prompts))
        self.assertTrue(all(timeout == 120 for _, timeout in measured_prompts[:1]))
        self.assertEqual(result['ai_mode_successful'], 3)
        self.assertEqual(result['ai_mode_failed'], 0)

    def test_runtime_ports_do_not_require_notebook_search_stage_wrapper(self):
        runtime = self.runtime([])
        runtime.pop('run_serp_stage')
        runtime['bd_client'].run_keyword_serp_task = lambda **_kwargs: None

        ports = build_runtime_ports(runtime)

        self.assertTrue(callable(ports.search_stage.run_search))

    def test_worker_images_copy_the_importable_reddit_module(self):
        root = Path(__file__).resolve().parents[1]
        for name in ('Dockerfile.worker', 'Dockerfile.worker.overlay'):
            dockerfile = (root / 'hosted' / name).read_text(encoding='utf-8')
            self.assertIn('COPY reddit_social.py /app/reddit_social.py', dockerfile)

    def test_service_boundary_installs_explicit_chatgpt_gemini_research_race(self):
        events = []
        runtime = self.runtime(events)
        legacy_client = runtime['bd_client']
        legacy_client.token = 'test-token'
        legacy_client.serp_zone = 'test-zone'
        legacy_client.country = 'DE'
        legacy_client.debug = False
        legacy_measurement_calls = []
        measured_google = lambda *_args, **_kwargs: legacy_measurement_calls.append(
            'legacy'
        ) or {'answer_text': 'legacy measurement'}
        legacy_client.google_ai_mode_measured = measured_google
        fixture_path = Path(__file__).parent / 'fixtures' / 'research_provider_responses.json'
        fixture = json.loads(fixture_path.read_text(encoding='utf-8'))
        saved_by_snapshot = {}
        triggered = []
        triggered_payloads = []
        saved_cache = {}

        def trigger(dataset, payload):
            snapshot_id = f'snapshot-{dataset}'
            triggered.append(dataset)
            triggered_payloads.append(payload)
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

            @staticmethod
            def google_ai_mode_measured(*_args, **_kwargs):
                return {'answer_text': 'standalone measured Google AI Mode'}

            def trigger_dataset(self, dataset, payload):
                return trigger(dataset, payload)

            def snapshot_status(self, _snapshot):
                return {'status': 'ready'}

            def download_snapshot(self, snapshot):
                if snapshot.endswith('chatgpt'):
                    return [{'answer_text': 'short'}]
                return [{
                    'answer_text': (
                        'A substantive market research answer with useful details. '
                        * 4
                    )
                }]

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
        self.assertTrue(all(
            'STRICT TARGET MARKET: Germany (DE).' in payload['prompt']
            for payload in triggered_payloads
        ))
        self.assertEqual(result['_research_race']['provider'], 'gemini')
        self.assertIn('substantive market research', result['answer_text'].lower())
        self.assertEqual(
            runtime['RESEARCH_PROVIDER_ADAPTER'].__class__.__name__,
            'ResearchProviderAdapter',
        )
        self.assertTrue(callable(client.google_ai_mode_measured))
        self.assertEqual(
            client.google_ai_mode_measured()['answer_text'],
            'standalone measured Google AI Mode',
        )
        self.assertEqual(legacy_measurement_calls, [])

    def test_research_provider_preflight_no_longer_requires_notebook_policy_helpers(self):
        events = []
        runtime = self.runtime(events)
        runtime.pop('is_google_goto_url', None)
        runtime.pop('remove_ai_boilerplate', None)
        runtime.pop('model_to_dict', None)
        runtime.pop('select_relevant_company_research', None)
        runtime.pop('_competitor_decision_ports', None)
        runtime.pop('locked_scope_local_domain_bonus', None)
        runtime.pop('locked_scope_brand_family', None)
        runtime.update({
            'RESEARCH_PROVIDERS': ('chatgpt', 'gemini'),
            'cached_google_ai_snapshot_ids': lambda _key: [],
            'remember_google_ai_snapshot': lambda *_args: None,
            'FAILED_STATUSES': {'failed', 'canceled'},
            '_GOOGLE_AI_ONLY_REUSE': False,
            'ResearchRaceTimeoutError': TimeoutError,
            'BrightDataAPIError': RuntimeError,
        })
        ports = build_runtime_ports(runtime)
        self.assertTrue(callable(ports.search_stage.run_search))
        self.assertNotIn('identify_google_ai_research_task', runtime)
        self.assertNotIn('validate_google_ai_research_answer', runtime)
        self.assertNotIn('google_ai_snapshot_is_materializing', runtime)
        self.assertNotIn('localize_google_ai_prompt', runtime)


if __name__ == '__main__':
    unittest.main()
