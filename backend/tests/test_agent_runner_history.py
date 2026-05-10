import unittest

from services.agent_runner import _message_history_from_events


class AgentRunnerHistoryTests(unittest.TestCase):
    def test_ignores_non_chat_file_lists_with_string_entries(self) -> None:
        history = _message_history_from_events(
            [
                {
                    "type": "user_message",
                    "payload": {
                        "content": "corrija esse worl",
                        "files": [
                            {
                                "path": "uploads/Especies.docx",
                                "summary": "DOCX com 10 paragrafo(s).",
                            }
                        ],
                    },
                },
                {
                    "type": "vertex_progress",
                    "payload": {
                        "status": "done",
                        "message": "Entrega pronta.",
                        "files": ["Especies_Corrigido.docx"],
                    },
                },
            ],
            "fallback",
        )

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["role"], "user")
        self.assertIn("uploads/Especies.docx", history[0]["content"])


if __name__ == "__main__":
    unittest.main()
