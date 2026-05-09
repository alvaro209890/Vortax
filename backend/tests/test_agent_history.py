import asyncio
import tempfile
import unittest
from pathlib import Path

import database as database_module
import services.agent_runner as agent_runner_module
import services.event_bus as event_bus_module
import services.task_plan_store as task_plan_store_module
from config import settings
from database import Database
from services.agent_runner import (
    _complete_supported_steps_before_delivery,
    _generated_file_response_payload,
    _latest_code_agent_quality_gate,
    _latest_web_validation_gate,
    _message_history_from_events,
)
from services.event_bus import EventBus
from services.task_plan_store import TaskPlanStore
from services.task_store import utc_now


class AgentHistoryTests(unittest.TestCase):
    def test_builds_model_history_from_persisted_chat_events(self) -> None:
        events = [
            {"type": "task_created", "payload": {"task": {}}},
            {"type": "user_message", "payload": {"content": "Pesquise o Creta 2026"}},
            {"type": "agent_progress", "payload": {"label": "Pesquisando"}},
            {"type": "assistant_message_done", "payload": {"content": "Resumo do Creta."}},
            {"type": "user_message", "payload": {"content": "Compare com o Tracker"}},
        ]

        history = _message_history_from_events(events, "fallback")

        self.assertEqual(
            history,
            [
                {"role": "user", "content": "Pesquise o Creta 2026"},
                {"role": "assistant", "content": "Resumo do Creta."},
                {"role": "user", "content": "Compare com o Tracker"},
            ],
        )

    def test_falls_back_when_no_chat_events_exist(self) -> None:
        history = _message_history_from_events([], "tarefa inicial")

        self.assertEqual(history, [{"role": "user", "content": "tarefa inicial"}])

    def test_limits_long_history_to_recent_turns(self) -> None:
        events = [
            {"type": "user_message", "payload": {"content": f"mensagem {index}"}}
            for index in range(20)
        ]

        history = _message_history_from_events(events, "fallback")

        self.assertEqual(len(history), 12)
        self.assertEqual(history[0]["content"], "mensagem 8")
        self.assertEqual(history[-1]["content"], "mensagem 19")

    def test_web_validation_gate_blocks_latest_openclaude_until_passed(self) -> None:
        events = [
            {
                "event_id": 1,
                "type": "tool_call",
                "payload": {"name": "shell_run", "params": {"command": "openclaude 'crie um site'"}},
            },
            {"event_id": 2, "type": "web_validation_result", "payload": {"requires_validation": True, "status": "failed", "bugs": ["Texto cortado"]}},
        ]

        gate = _latest_web_validation_gate(events)

        self.assertTrue(gate["required"])
        self.assertEqual(gate["status"], "failed")
        self.assertEqual(gate["bugs"], ["Texto cortado"])

    def test_web_validation_gate_allows_passed_openclaude_site(self) -> None:
        events = [
            {
                "event_id": 1,
                "type": "tool_call",
                "payload": {"name": "shell_run", "params": {"command": "openclaude 'crie um site'"}},
            },
            {"event_id": 2, "type": "web_validation_result", "payload": {"requires_validation": True, "status": "passed"}},
        ]

        gate = _latest_web_validation_gate(events)

        self.assertTrue(gate["required"])
        self.assertEqual(gate["status"], "passed")

    def test_code_agent_quality_gate_blocks_failed_python_project_validation(self) -> None:
        events = [
            {
                "event_id": 1,
                "type": "tool_call",
                "payload": {"name": "shell_run", "params": {"command": "openclaude 'crie um script python'"}},
            },
            {"event_id": 2, "type": "web_validation_result", "payload": {"requires_validation": False, "status": "skipped"}},
            {
                "event_id": 3,
                "type": "project_validation_result",
                "payload": {"requires_validation": True, "status": "failed", "bugs": ["SyntaxError em main.py"]},
            },
        ]

        gate = _latest_code_agent_quality_gate(events)

        self.assertTrue(gate["required"])
        self.assertEqual(gate["status"], "failed")
        self.assertEqual(gate["bugs"], ["SyntaxError em main.py"])

    def test_code_agent_quality_gate_allows_non_web_project_after_validation(self) -> None:
        events = [
            {
                "event_id": 1,
                "type": "tool_call",
                "payload": {"name": "shell_run", "params": {"command": "openclaude 'crie uma api python'"}},
            },
            {"event_id": 2, "type": "web_validation_result", "payload": {"requires_validation": False, "status": "skipped"}},
            {"event_id": 3, "type": "project_validation_result", "payload": {"requires_validation": True, "status": "passed"}},
        ]

        gate = _latest_code_agent_quality_gate(events)

        self.assertTrue(gate["required"])
        self.assertEqual(gate["status"], "passed")

    def test_code_agent_quality_gate_does_not_block_openclaude_version_check(self) -> None:
        events = [
            {
                "event_id": 1,
                "type": "tool_call",
                "payload": {"name": "shell_run", "params": {"command": "openclaude --version"}},
            },
        ]

        gate = _latest_code_agent_quality_gate(events)

        self.assertFalse(gate["required"])
        self.assertEqual(gate["status"], "not_required")


class GeneratedFilePayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.original_base = database_module.settings.DATABASE_BASE_PATH
        self.original_workspace = settings.WORKSPACE_PATH
        database_module.settings.DATABASE_BASE_PATH = Path(self.tmp.name) / "db"
        settings.WORKSPACE_PATH = Path(self.tmp.name) / "workspace"
        settings.WORKSPACE_PATH.mkdir(parents=True, exist_ok=True)
        self.db = Database()
        self.original_database = database_module.database
        self.original_runner_database = agent_runner_module.database
        database_module.database = self.db
        agent_runner_module.database = self.db
        self.task_id = "task-documents"
        now = utc_now()
        self.db.create_task(
            {
                "id": self.task_id,
                "description": "crie um site",
                "status": "running",
                "created_at": now,
                "updated_at": now,
            }
        )

    def tearDown(self) -> None:
        database_module.database = self.original_database
        agent_runner_module.database = self.original_runner_database
        database_module.settings.DATABASE_BASE_PATH = self.original_base
        settings.WORKSPACE_PATH = self.original_workspace
        self.db.close()
        self.tmp.cleanup()

    def _sync_files(self, files: list[dict]) -> None:
        now = utc_now()
        project = {
            "id": f"{self.task_id}:__root__",
            "task_id": self.task_id,
            "root_path": "",
            "name": "Projeto principal",
            "project_type": "static_web",
            "main_file": "index.html",
            "file_count": len(files),
            "total_size": sum(int(file.get("size_bytes", 0)) for file in files),
            "created_at": now,
            "updated_at": now,
        }
        indexed = [
            {
                **file,
                "task_id": self.task_id,
                "project_id": project["id"],
                "created_at": now,
                "updated_at": now,
            }
            for file in files
        ]
        self.db.sync_generated_projects(self.task_id, [project], indexed)

    def test_payload_attaches_markdown_document_card_for_site(self) -> None:
        task_dir = settings.WORKSPACE_PATH / self.task_id
        task_dir.mkdir(parents=True)
        (task_dir / "DOCUMENTACAO.md").write_text("# Guia do Site\n\n" + "Conteudo da documentacao. " * 8, encoding="utf-8")
        self._sync_files(
            [
                {"path": "index.html", "size_bytes": 20, "extension": ".html", "modified_at": 1},
                {"path": "DOCUMENTACAO.md", "size_bytes": 220, "extension": ".md", "modified_at": 1},
            ]
        )
        events = [
            {
                "event_id": 1,
                "type": "tool_call",
                "payload": {"name": "shell_run", "params": {"command": "openclaude 'crie um site html'"}},
            }
        ]

        payload = _generated_file_response_payload(self.task_id, "ok", events)

        self.assertEqual(payload["documents"][0]["path"], "DOCUMENTACAO.md")
        self.assertEqual(payload["documents"][0]["title"], "Guia do Site")
        self.assertTrue(payload["documents"][0]["previewable"])
        self.assertEqual(payload["documents"][0]["kind"], "markdown")
        self.assertEqual(payload["documentation"]["path"], "DOCUMENTACAO.md")

    def test_payload_attaches_pdf_as_primary_and_markdown_as_secondary(self) -> None:
        task_dir = settings.WORKSPACE_PATH / self.task_id
        task_dir.mkdir(parents=True)
        (task_dir / "relatorio.pdf").write_bytes(b"%PDF-1.4\n" + b"x" * 300)
        (task_dir / "relatorio.md").write_text("# Fonte do Relatorio\n\n" + "Conteudo pesquisado. " * 8, encoding="utf-8")
        self._sync_files(
            [
                {"path": "relatorio.pdf", "size_bytes": 309, "extension": ".pdf", "modified_at": 1},
                {"path": "relatorio.md", "size_bytes": 190, "extension": ".md", "modified_at": 1},
            ]
        )
        events = [
            {
                "event_id": 1,
                "type": "tool_call",
                "payload": {"name": "shell_run", "params": {"command": "openclaude 'gere um relatorio em PDF'"}},
            }
        ]

        payload = _generated_file_response_payload(self.task_id, "ok", events)

        self.assertEqual([item["path"] for item in payload["documents"]], ["relatorio.pdf", "relatorio.md"])
        self.assertTrue(payload["documents"][0]["primary"])
        self.assertEqual(payload["documents"][0]["kind"], "pdf")

    def test_payload_attaches_requested_office_document_cards(self) -> None:
        task_dir = settings.WORKSPACE_PATH / self.task_id
        task_dir.mkdir(parents=True)
        (task_dir / "relatorio.docx").write_bytes(b"docx-bytes")
        (task_dir / "slides.pptx").write_bytes(b"pptx-bytes")
        self._sync_files(
            [
                {"path": "relatorio.docx", "size_bytes": 1024, "extension": ".docx", "modified_at": 1},
                {"path": "slides.pptx", "size_bytes": 2048, "extension": ".pptx", "modified_at": 1},
            ]
        )
        events = [
            {
                "event_id": 1,
                "type": "tool_call",
                "payload": {"name": "shell_run", "params": {"command": "openclaude 'gere um arquivo docx e slides pptx'"}},
            }
        ]

        payload = _generated_file_response_payload(self.task_id, "ok", events)

        self.assertEqual([item["path"] for item in payload["documents"]], ["relatorio.docx", "slides.pptx"])
        self.assertEqual([item["kind"] for item in payload["documents"]], ["word", "presentation"])
        self.assertTrue(all(item["previewable"] for item in payload["documents"]))
        self.assertEqual([item["path"] for item in payload["downloads"]], ["relatorio.docx", "slides.pptx"])


class SupportedStepCompletionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.original_base = database_module.settings.DATABASE_BASE_PATH
        database_module.settings.DATABASE_BASE_PATH = Path(self.tmp.name)
        self.db = Database()
        self.original_database = database_module.database
        self.original_runner_database = agent_runner_module.database
        self.original_event_bus_database = event_bus_module.database
        self.original_plan_database = task_plan_store_module.database
        database_module.database = self.db
        agent_runner_module.database = self.db
        event_bus_module.database = self.db
        task_plan_store_module.database = self.db
        self.store = TaskPlanStore()
        self.original_runner_plan_store = agent_runner_module.task_plan_store
        agent_runner_module.task_plan_store = self.store
        self.task_id = "task-supported-steps"
        now = utc_now()
        self.db.create_task(
            {
                "id": self.task_id,
                "description": "pesquise sobre o Corinthians agora",
                "status": "running",
                "created_at": now,
                "updated_at": now,
            }
        )

    def tearDown(self) -> None:
        agent_runner_module.task_plan_store = self.original_runner_plan_store
        database_module.database = self.original_database
        agent_runner_module.database = self.original_runner_database
        event_bus_module.database = self.original_event_bus_database
        task_plan_store_module.database = self.original_plan_database
        database_module.settings.DATABASE_BASE_PATH = self.original_base
        self.db.close()
        self.tmp.cleanup()

    def _replace_plan(self) -> None:
        self.store.replace_plan(
            self.task_id,
            [
                {"label": "Entender", "tool_hint": "understand"},
                {"label": "Pesquisar", "tool_hint": "research"},
                {"label": "Compilar", "tool_hint": "execute"},
                {"label": "Validar", "tool_hint": "validate"},
                {"label": "Entregar", "tool_hint": "deliver"},
            ],
            "pesquise sobre o Corinthians agora",
        )

    def test_completes_only_steps_supported_by_real_events(self) -> None:
        self._replace_plan()
        now = utc_now()
        self.db.insert_event(self.task_id, "user_message", now, {"content": "pesquise sobre o Corinthians agora"})
        self.db.upsert_source(
            self.task_id,
            {
                "url": "https://ge.globo.com/futebol/times/corinthians/",
                "title": "Corinthians noticias recentes",
                "source_type": "web",
                "quality_score": 80,
                "snippet": "Corinthians noticias recentes agora futebol",
                "extracted_text": "Corinthians noticias recentes agora futebol",
                "created_at": now,
            }
        )
        self.db.upsert_source(
            self.task_id,
            {
                "url": "https://www.corinthians.com.br/",
                "title": "Corinthians site oficial noticias",
                "source_type": "web",
                "quality_score": 78,
                "snippet": "Corinthians noticias recentes agora clube oficial",
                "extracted_text": "Corinthians noticias recentes agora clube oficial",
                "created_at": now,
            }
        )
        self.db.insert_event(self.task_id, "tool_result", now, {"name": "browser_google_search", "result": {"query": "Corinthians noticias", "results": [1, 2]}})

        asyncio.run(_complete_supported_steps_before_delivery(self.task_id, EventBus(), "pesquise sobre o Corinthians agora", "Resumo final."))

        statuses = {step["tool_hint"]: step["status"] for step in self.store.list_steps(self.task_id)}
        self.assertEqual(statuses["understand"], "passed")
        self.assertEqual(statuses["research"], "passed")
        self.assertEqual(statuses["execute"], "passed")
        self.assertEqual(statuses["validate"], "passed")
        self.assertEqual(statuses["deliver"], "pending")

    def test_keeps_validation_pending_without_required_evidence(self) -> None:
        self._replace_plan()

        asyncio.run(_complete_supported_steps_before_delivery(self.task_id, EventBus(), "preco atual do Corolla", "Resumo final."))

        statuses = {step["tool_hint"]: step["status"] for step in self.store.list_steps(self.task_id)}
        self.assertEqual(statuses["understand"], "passed")
        self.assertEqual(statuses["execute"], "passed")
        self.assertEqual(statuses["research"], "pending")
        self.assertEqual(statuses["validate"], "pending")
        self.assertEqual(statuses["deliver"], "pending")
