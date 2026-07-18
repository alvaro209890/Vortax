import asyncio
import unittest
from unittest import mock

from services.deepseek_client import request_agent_turn


class NativeTurnTests(unittest.TestCase):
    def test_parses_tool_calls(self):
        fake = {
            "model": "deepseek-v4-pro",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "browser_google_search",
                                    "arguments": '{"query":"teste"}',
                                },
                            }
                        ],
                    },
                }
            ],
        }

        async def _run():
            with mock.patch("services.deepseek_client.deepseek_configured", return_value=True), mock.patch(
                "services.deepseek_client._post_deepseek", new=mock.AsyncMock(return_value=fake)
            ), mock.patch("services.deepseek_client.settings") as st:
                st.DEEPSEEK_STREAMING = False
                st.DEEPSEEK_TEMPERATURE = 0.0
                st.DEEPSEEK_MAX_OUTPUT_TOKENS = 1024
                st.DEEPSEEK_MODEL_BRAIN = "deepseek-v4-pro"
                st.DEEPSEEK_MODEL = "deepseek-v4-pro"
                st.DEEPSEEK_MODEL_FAST = "deepseek-v4-flash"
                return await request_agent_turn(
                    [{"role": "user", "content": "oi"}],
                    tools=[{"type": "function", "function": {"name": "browser_google_search", "parameters": {}}}],
                    stream=False,
                )

        result = asyncio.run(_run())
        self.assertEqual(len(result["tool_calls"]), 1)
        self.assertEqual(result["tool_calls"][0]["name"], "browser_google_search")
        self.assertEqual(result["tool_calls"][0]["arguments"]["query"], "teste")


if __name__ == "__main__":
    unittest.main()
