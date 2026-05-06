import unittest

from services.agent_runner import _message_history_from_events


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
