"""Offline checks for service-only redirect and PDF support."""

from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from hosted.google_redirects import GoogleRedirectResolver
from hosted import service_runner
from hosted.service_pdf import create_styled_pdf_report


class FakeResponse:
    def __init__(self, url):
        self.url = url
        self.closed = False

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, *, head_result=None, get_result=None, head_error=None):
        self.head_result = head_result
        self.get_result = get_result
        self.head_error = head_error
        self.calls = []
        self.max_redirects = 0
        self.closed = False

    def head(self, url, **kwargs):
        self.calls.append(('head', url, kwargs))
        if self.head_error:
            raise self.head_error
        return self.head_result

    def get(self, url, **kwargs):
        self.calls.append(('get', url, kwargs))
        return self.get_result

    def close(self):
        self.closed = True


class ServiceRuntimeSupportTests(unittest.TestCase):
    def test_native_service_bootstrap_uses_explicit_provider_secrets(self):
        client = object()
        with patch.dict(
            'os.environ',
            {'BRIGHTDATA_API_TOKEN': 'fixture-token', 'SERP_ZONE': 'fixture-zone'},
        ), patch(
            'hosted.service_runner.build_brightdata_provider',
            return_value=client,
        ) as provider, patch(
            'hosted.service_runner.GoogleRedirectResolver',
            return_value='resolver',
        ):
            runtime = service_runner.build_runtime({
                'country': 'ES', 'debug_mode': True,
            })
        provider.assert_called_once()
        kwargs = provider.call_args.kwargs
        self.assertEqual(kwargs['token'], 'fixture-token')
        self.assertEqual(kwargs['serp_zone'], 'fixture-zone')
        self.assertEqual(kwargs['country'], 'ES')
        self.assertTrue(kwargs['debug'])
        self.assertIs(runtime['bd_client'], client)
        self.assertEqual(runtime['resolve_google_goto_url'], 'resolver')
        self.assertTrue(callable(runtime['create_styled_pdf_report']))

    def test_run_service_audit_uses_the_native_coordinator(self):
        runtime = {'service': True}
        settings = {'company_name': 'Rayner'}
        with tempfile.TemporaryDirectory() as root, patch(
            'hosted.service_runner.build_runtime', return_value=runtime,
        ), patch(
            'hosted.service_runner.run_with_legacy_runtime',
            return_value={'ok': True},
        ) as run:
            result = service_runner.run_service_audit(
                settings, output_directory=root,
            )
        self.assertEqual(result, {'ok': True})
        passed_settings, passed_runtime = run.call_args.args
        self.assertEqual(passed_settings, settings)
        self.assertIs(passed_runtime, runtime)
        self.assertEqual(run.call_args.kwargs['base_directory'], Path(root))

    def test_google_redirect_is_resolved_once_and_cached(self):
        sessions = []

        def session_factory():
            session = FakeSession(head_result=FakeResponse('https://source.example/a'))
            sessions.append(session)
            return session

        resolver = GoogleRedirectResolver(session_factory=session_factory)
        url = 'https://www.google.com/goto?url=https%3A%2F%2Fsource.example'
        self.assertEqual(resolver(url), 'https://source.example/a')
        self.assertEqual(resolver(url), 'https://source.example/a')
        self.assertEqual(len(sessions), 1)
        self.assertTrue(sessions[0].closed)
        self.assertEqual(sessions[0].max_redirects, 8)

    def test_google_redirect_falls_back_to_streaming_get(self):
        session = FakeSession(
            get_result=FakeResponse('https://source.example/page'),
            head_error=TimeoutError('fixture timeout'),
        )
        resolver = GoogleRedirectResolver(session_factory=lambda: session)
        self.assertEqual(
            resolver('https://google.com/goto?x=1'),
            'https://source.example/page',
        )
        self.assertEqual([call[0] for call in session.calls], ['head', 'get'])
        self.assertTrue(session.calls[1][2]['stream'])
        self.assertTrue(session.closed)

    def test_non_google_url_is_returned_without_network(self):
        resolver = GoogleRedirectResolver(
            session_factory=lambda: self.fail('unexpected HTTP session'),
        )
        self.assertEqual(resolver('https://source.example/page'), 'https://source.example/page')

    def test_pdf_renderer_escapes_cover_fields_and_blocks_remote_fetch(self):
        rendered = {}

        class FakeHTML:
            def __init__(self, *, string, url_fetcher):
                rendered['html'] = string
                rendered['url_fetcher'] = url_fetcher

            def write_pdf(self, *, target):
                Path(target).write_bytes(b'%PDF-' + b'x' * 1200)

        markdown_module = types.SimpleNamespace(
            markdown=lambda text, **kwargs: '<h2>Report body</h2>' + text,
        )
        weasyprint_module = types.SimpleNamespace(HTML=FakeHTML)
        with tempfile.TemporaryDirectory() as root, patch.dict(
            sys.modules,
            {'markdown': markdown_module, 'weasyprint': weasyprint_module},
        ):
            output = Path(root) / 'report.pdf'
            result = create_styled_pdf_report(
                markdown_text='# Competitive Visibility Audit\n\nBody',
                output_path=output,
                company_name='<Acme & Co>',
                company_url='https://acme.example/',
                country='us',
                generated_at=datetime(2026, 10, 2, tzinfo=timezone.utc),
                audit_focus='premium devices',
            )
            self.assertEqual(result, output)
            self.assertTrue(output.is_file())
        self.assertIn('&lt;Acme &amp; Co&gt;', rendered['html'])
        self.assertIn('Competitive Visibility Report for', rendered['html'])
        self.assertIn('Audit focus', rendered['html'])
        self.assertEqual(
            rendered['url_fetcher']('https://outside.example/image.png'),
            {
                'string': b'', 'mime_type': 'text/plain',
                'redirected_url': 'https://outside.example/image.png',
            },
        )


if __name__ == '__main__':
    unittest.main()
