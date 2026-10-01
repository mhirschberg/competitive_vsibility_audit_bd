"""Offline checks for fresh and resumed audit preparation."""

import asyncio
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

from audit_core.audit_preparation import (
    AuditPreparationPorts, prepare_audit_run_core,
)


class AuditPreparationTests(unittest.TestCase):
    def make_ports(self, events, *, resumed_path=None, redirect=False):
        def resolve(url):
            events.append(('resolve', url))
            return {
                'submitted_url': url,
                'submitted_hostname': 'old.example.com',
                'canonical_url': 'https://new.example.com/' if redirect else url,
                'canonical_hostname': 'new.example.com' if redirect else 'old.example.com',
                'redirect_chain': ['https://new.example.com/'] if redirect else [],
            }

        def write_json(path, data):
            events.append(('settings', path))
            path.write_text(json.dumps(data), encoding='utf-8')

        return AuditPreparationPorts(
            resolve_official_site=resolve,
            get_root_domain=lambda host: host.removeprefix('www.'),
            find_latest_audit_to_continue=lambda settings: resumed_path,
            slugify=lambda name: name.lower().replace(' ', '-'),
            audit_export_prefix=lambda timestamp, name, focus, country: (
                f"{timestamp:%Y%m%d}-{name.lower()}-{country.lower()}"
            ),
            configure_usage_checkpoint=lambda path, restore: events.append(
                ('usage', path, restore)
            ),
            write_json=write_json,
            configure_google_ai_race_cache=lambda path, only_reuse: events.append(
                ('cache', path, only_reuse)
            ),
            import_google_ai_snapshot_ids=lambda ids: (
                events.append(('import', ids)) or len(ids)
            ),
            notice=lambda message: events.append(('notice', message)),
            set_output_directory=lambda path: events.append(('output', path)),
        )

    def settings(self, **changes):
        return {
            'company_name': 'Test Company',
            'company_url': 'https://old.example.com/',
            'company_domain': 'old.example.com',
            'country': 'US',
            'audit_focus': 'widgets',
            **changes,
        }

    def test_fresh_redirect_saves_canonical_settings_before_cache(self):
        with tempfile.TemporaryDirectory() as root:
            events = []
            original = self.settings()
            prepared = asyncio.run(prepare_audit_run_core(
                original, base_directory=Path(root),
                ports=self.make_ports(events, redirect=True),
            ))
            settings = prepared['settings']
            saved = json.loads((
                prepared['output_directory'] / '00_run_settings.json'
            ).read_text(encoding='utf-8'))
            self.assertFalse(prepared['continuing'])
            self.assertEqual(original['company_domain'], 'old.example.com')
            self.assertEqual(settings['company_domain'], 'new.example.com')
            self.assertEqual(saved['submitted_company_domain'], 'old.example.com')
            self.assertEqual(saved['company_url'], 'https://new.example.com/')
            self.assertEqual(settings['audit_as_of_date'], prepared['run_timestamp'].date().isoformat())
            self.assertTrue(prepared['raw_directory'].is_dir())
            self.assertEqual([entry[0] for entry in events],
                             ['resolve', 'notice', 'output', 'usage', 'settings', 'cache'])
            self.assertFalse(next(e for e in events if e[0] == 'usage')[2])
            self.assertFalse(next(e for e in events if e[0] == 'cache')[2])

    def test_resume_restores_original_timestamp_and_imports_snapshot_ids(self):
        with tempfile.TemporaryDirectory() as root:
            resumed = Path(root) / 'competitive-visibility-test-20260915-123000'
            resumed.mkdir()
            (resumed / '01_company_analysis.json').write_text(
                json.dumps({'created_at': '2026-09-15T12:30:00+00:00'}),
                encoding='utf-8',
            )
            events = []
            prepared = asyncio.run(prepare_audit_run_core(
                self.settings(continue_last_audit=True, recovery_snapshot_ids=['snap-1']),
                base_directory=Path(root),
                ports=self.make_ports(events, resumed_path=resumed),
            ))
            self.assertTrue(prepared['continuing'])
            self.assertEqual(prepared['output_directory'], resumed)
            self.assertEqual(prepared['run_id'], 'test-20260915-123000')
            self.assertEqual(prepared['run_timestamp'], datetime.fromisoformat(
                '2026-09-15T12:30:00+00:00'
            ))
            self.assertEqual(prepared['settings']['audit_as_of_date'], '2026-09-15')
            self.assertEqual([entry[0] for entry in events],
                             ['resolve', 'notice', 'notice', 'output', 'usage',
                              'cache', 'import', 'notice'])
            self.assertTrue(next(e for e in events if e[0] == 'usage')[2])
            self.assertTrue(next(e for e in events if e[0] == 'cache')[2])
            self.assertFalse((resumed / '00_run_settings.json').exists())
            self.assertIn('Legacy checkpoint', events[2][1])

    def test_site_resolution_failure_does_not_create_run_or_checkpoint(self):
        with tempfile.TemporaryDirectory() as root:
            events = []
            ports = self.make_ports(events)
            def fail(url):
                raise ValueError('unreachable')
            ports.resolve_official_site = fail
            with self.assertRaisesRegex(ValueError, 'unreachable'):
                asyncio.run(prepare_audit_run_core(
                    self.settings(), base_directory=Path(root), ports=ports,
                ))
            self.assertEqual(events, [])
            self.assertEqual(list(Path(root).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
