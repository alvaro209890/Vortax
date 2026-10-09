import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from services.software_delivery import archive_requested, build_project_zip, delivery_payload

PROMPT = 'Desenvolva uma API REST completa em Python com FastAPI para gerenciar tarefas'


class SoftwareDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root/'app').mkdir()
        (self.root/'app/main.py').write_text('print("ok")')
        (self.root/'README.md').write_text('Como usar')
        (self.root/'requirements.txt').write_text('fastapi')
        for path in ['.env', '.pytest_cache/cache.txt', 'node_modules/lib/index.js', '__pycache__/main.pyc']:
            target = self.root/path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('excluir')
        self.events = [{'type': 'user_message', 'payload': {'content': PROMPT}}, {'type': 'project_validation_result', 'payload': {'status': 'passed'}}]

    def tearDown(self):
        self.tmp.cleanup()

    def test_actual_files_short_delivery_without_archive_by_default(self):
        payload = delivery_payload('task', PROMPT, self.events, self.root)
        self.assertEqual(payload['delivery']['file_count'], 3)
        self.assertEqual(payload['delivery']['validation_status'], 'passed')
        self.assertNotIn('archive', payload)
        self.assertNotIn('```', payload['content'])
        self.assertLess(len(payload['content']), 1000)

    def test_zip_followup_uses_existing_files_and_latest_validation(self):
        events = self.events + [{'type': 'user_message', 'payload': {'content': 'manda o zip'}}]
        payload = delivery_payload('task', 'manda o zip', events, self.root)
        self.assertEqual(payload['archive']['file_count'], 3)
        self.assertEqual(payload['delivery']['validation_status'], 'passed')
        with zipfile.ZipFile(build_project_zip(self.root)) as archive:
            self.assertEqual(set(archive.namelist()), {'app/main.py', 'README.md', 'requirements.txt'})
            self.assertEqual(archive.read('app/main.py'), b'print("ok")')

    def test_new_edit_cannot_reuse_old_validation(self):
        events = self.events + [{'type': 'user_message', 'payload': {'content': 'Corrija a API Python'}}]
        payload = delivery_payload('task', 'Corrija a API Python', events, self.root)
        self.assertEqual(payload['delivery']['validation_status'], 'unknown')

    def test_explicit_code_explanation_and_research_are_preserved(self):
        for prompt in ['Mostre um trecho de código Python', 'Crie um exemplo de código Python no chat', 'Pesquise notícias de IA']:
            self.assertIsNone(delivery_payload('task', prompt, self.events, self.root))

    def test_archive_requires_request_not_just_word(self):
        for prompt in ['O que é um ZIP?', 'Crie uma API sem ZIP', 'Crie um script Python que usa zipfile']:
            self.assertFalse(archive_requested(prompt))
        for prompt in ['zip', 'mande os arquivos compactados', 'gere o zip com os arquivos', 'Crie uma API e mande o ZIP']:
            self.assertTrue(archive_requested(prompt))

    def test_empty_workspace_does_not_claim_delivery(self):
        with tempfile.TemporaryDirectory() as empty:
            payload = delivery_payload('task', 'manda o zip', [], Path(empty))
        self.assertEqual(payload['delivery']['file_count'], 0)
        self.assertNotIn('archive', payload)

    def test_links_outside_project_are_not_included(self):
        try:
            (self.root/'leak.py').symlink_to(__file__)
        except OSError:
            self.skipTest('Symlinks unavailable')
        with zipfile.ZipFile(build_project_zip(self.root)) as archive:
            self.assertNotIn('leak.py', archive.namelist())

    def test_application_versions_directory_is_preserved(self):
        (self.root/'app/versions').mkdir()
        (self.root/'app/versions/v1.py').write_text('VERSION = 1')
        with zipfile.ZipFile(build_project_zip(self.root)) as archive:
            self.assertIn('app/versions/v1.py', archive.namelist())

    def test_native_software_does_not_stream_raw_code(self):
        from test_native_loop_exits import run_loop, _turn
        with mock.patch('services.agent_runner._finish_text_response', new=mock.AsyncMock()) as finish:
            events, calls = run_loop(PROMPT, [_turn('```python\nprint("raw")\n```')], streaming=True)
        self.assertFalse(calls[0]['stream'])
        self.assertFalse(any(kind == 'assistant_message_delta' for kind, _ in events))
        finish.assert_awaited_once()

    def test_native_zip_does_not_call_model(self):
        from test_native_loop_exits import run_loop
        with mock.patch('services.agent_runner._finish_text_response', new=mock.AsyncMock()) as finish:
            _, calls = run_loop('manda o zip', [])
        self.assertEqual(calls, [])
        finish.assert_awaited_once()

    def test_zip_entrypoint_works_without_provider_and_skips_context_model(self):
        import asyncio
        from services import agent_runner
        store = mock.Mock()
        bus = mock.Mock()
        with mock.patch.object(agent_runner, 'deepseek_configured', return_value=False), mock.patch.object(agent_runner, '_finish_text_response', new=mock.AsyncMock()) as finish, mock.patch.object(agent_runner.browser_pool, 'release', new=mock.AsyncMock()):
            asyncio.run(agent_runner.run_agent_task('task', 'manda o zip', store, bus))
        finish.assert_awaited_once_with('task', 'manda o zip', '', store, bus, refresh_context=False)

    def test_zip_plan_is_local_and_creation_still_uses_planner(self):
        import asyncio
        from api import tasks
        with mock.patch.object(tasks, 'task_plan_store') as plans, mock.patch.object(tasks, 'event_bus') as bus, mock.patch.object(tasks, 'request_task_plan', new=mock.AsyncMock(return_value={'plan': []})) as planner, mock.patch.object(tasks, 'task_planner_configured', return_value=True):
            plans.replace_plan.return_value = []
            bus.publish = mock.AsyncMock()
            asyncio.run(tasks._create_live_plan('task', 'manda o zip'))
            planner.assert_not_awaited()
            asyncio.run(tasks._create_live_plan('task', PROMPT + ' e mande o ZIP'))
            planner.assert_awaited_once()

