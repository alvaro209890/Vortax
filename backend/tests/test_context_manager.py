import unittest

from services.context_manager import chat_messages_from_events, context_status, estimate_messages_tokens


class ContextManagerTests(unittest.TestCase):
    def test_extracts_chat_messages_with_event_ids_and_images(self) -> None:
        events = [
            {"event_id": 1, "type": "agent_progress", "payload": {"label": "Ignorar"}},
            {"event_id": 2, "type": "user_message", "payload": {"content": "Analise", "images": [{"filename": "a.png"}]}},
            {"event_id": 3, "type": "assistant_message_done", "payload": {"content": "Pronto"}},
        ]

        messages = chat_messages_from_events(events)

        self.assertEqual(messages[0]["event_id"], 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(len(messages[0]["images"]), 1)
        self.assertEqual(messages[1]["role"], "assistant")

    def test_estimates_summary_and_message_tokens(self) -> None:
        messages = [{"role": "user", "content": "x" * 400, "images": []}]

        estimated = estimate_messages_tokens(messages, summary="y" * 200)

        self.assertGreaterEqual(estimated, 150)

    def test_context_status_thresholds(self) -> None:
        self.assertEqual(context_status(0), "empty")
        self.assertEqual(context_status(100), "ok")


if __name__ == "__main__":
    unittest.main()
