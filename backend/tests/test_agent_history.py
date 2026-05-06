import unittest

from services.agent_runner import _latest_vertex_quality_gate, _latest_web_validation_gate, _message_history_from_events


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

    def test_web_validation_gate_blocks_latest_vertex_until_passed(self) -> None:
        events = [
            {
                "event_id": 1,
                "type": "tool_call",
                "payload": {"name": "shell_run", "params": {"command": "vertex 'crie um site'"}},
            },
            {"event_id": 2, "type": "web_validation_result", "payload": {"requires_validation": True, "status": "failed", "bugs": ["Texto cortado"]}},
        ]

        gate = _latest_web_validation_gate(events)

        self.assertTrue(gate["required"])
        self.assertEqual(gate["status"], "failed")
        self.assertEqual(gate["bugs"], ["Texto cortado"])

    def test_web_validation_gate_allows_passed_vertex_site(self) -> None:
        events = [
            {
                "event_id": 1,
                "type": "tool_call",
                "payload": {"name": "shell_run", "params": {"command": "vertex 'crie um site'"}},
            },
            {"event_id": 2, "type": "web_validation_result", "payload": {"requires_validation": True, "status": "passed"}},
        ]

        gate = _latest_web_validation_gate(events)

        self.assertTrue(gate["required"])
        self.assertEqual(gate["status"], "passed")

    def test_vertex_quality_gate_blocks_failed_python_project_validation(self) -> None:
        events = [
            {
                "event_id": 1,
                "type": "tool_call",
                "payload": {"name": "shell_run", "params": {"command": "vertex 'crie um script python'"}},
            },
            {"event_id": 2, "type": "web_validation_result", "payload": {"requires_validation": False, "status": "skipped"}},
            {
                "event_id": 3,
                "type": "project_validation_result",
                "payload": {"requires_validation": True, "status": "failed", "bugs": ["SyntaxError em main.py"]},
            },
        ]

        gate = _latest_vertex_quality_gate(events)

        self.assertTrue(gate["required"])
        self.assertEqual(gate["status"], "failed")
        self.assertEqual(gate["bugs"], ["SyntaxError em main.py"])

    def test_vertex_quality_gate_allows_non_web_project_after_validation(self) -> None:
        events = [
            {
                "event_id": 1,
                "type": "tool_call",
                "payload": {"name": "shell_run", "params": {"command": "vertex 'crie uma api python'"}},
            },
            {"event_id": 2, "type": "web_validation_result", "payload": {"requires_validation": False, "status": "skipped"}},
            {"event_id": 3, "type": "project_validation_result", "payload": {"requires_validation": True, "status": "passed"}},
        ]

        gate = _latest_vertex_quality_gate(events)

        self.assertTrue(gate["required"])
        self.assertEqual(gate["status"], "passed")

    def test_vertex_quality_gate_does_not_block_vertex_version_check(self) -> None:
        events = [
            {
                "event_id": 1,
                "type": "tool_call",
                "payload": {"name": "shell_run", "params": {"command": "vertex --version"}},
            },
        ]

        gate = _latest_vertex_quality_gate(events)

        self.assertFalse(gate["required"])
        self.assertEqual(gate["status"], "not_required")
