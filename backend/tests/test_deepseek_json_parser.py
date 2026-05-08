import unittest

import services.deepseek_client as deepseek_module
from services.deepseek_client import DeepSeekError, _extract_json_object


class DeepSeekJsonParserTests(unittest.TestCase):
    def test_parses_plain_json_object(self) -> None:
        self.assertEqual(_extract_json_object('{"action":"finish","result":"ok"}'), {"action": "finish", "result": "ok"})

    def test_extracts_json_object_without_greedy_extra_braces(self) -> None:
        content = '```json\n{"action":"finish","result":"ok"}\n```\ntexto extra com {chaves fora do JSON}'

        self.assertEqual(_extract_json_object(content), {"action": "finish", "result": "ok"})

    def test_preserves_braces_inside_strings(self) -> None:
        content = r'Antes {"action":"finish","result":"Use dict literal: {\"a\": 1}"} depois {nao-json}'

        self.assertEqual(
            _extract_json_object(content),
            {"action": "finish", "result": 'Use dict literal: {"a": 1}'},
        )

    def test_rejects_truncated_json_instead_of_masking_error(self) -> None:
        with self.assertRaises(DeepSeekError):
            _extract_json_object('{"action":"finish","result":"texto sem fechar"')

    def test_rejects_missing_json(self) -> None:
        with self.assertRaises(DeepSeekError):
            _extract_json_object('sem nenhum objeto json')


class GroqTaskPlannerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.original_groq_key = deepseek_module.settings.GROQ_API_KEY
        self.original_deepseek_key = deepseek_module.settings.DEEPSEEK_API_KEY
        self.original_model = deepseek_module.settings.GROQ_TASK_PLANNER_MODEL
        self.original_post_groq = deepseek_module._post_groq

    async def asyncTearDown(self) -> None:
        deepseek_module.settings.GROQ_API_KEY = self.original_groq_key
        deepseek_module.settings.DEEPSEEK_API_KEY = self.original_deepseek_key
        deepseek_module.settings.GROQ_TASK_PLANNER_MODEL = self.original_model
        deepseek_module._post_groq = self.original_post_groq

    async def test_request_task_plan_uses_groq_json_mode(self) -> None:
        calls = []
        deepseek_module.settings.GROQ_API_KEY = "test-groq-key"
        deepseek_module.settings.DEEPSEEK_API_KEY = ""
        deepseek_module.settings.GROQ_TASK_PLANNER_MODEL = "llama-3.3-70b-versatile"

        async def fake_post_groq(payload):
            calls.append(payload)
            return {
                "model": payload["model"],
                "usage": {"total_tokens": 123},
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"plan":[{"label":"Pesquisar jogos","detail":"Buscar agenda atual.",'
                                '"tool_hint":"research","acceptance_criteria":["Agenda encontrada"]},'
                                '{"label":"Entregar resumo","detail":"Responder com fontes.",'
                                '"tool_hint":"deliver","acceptance_criteria":["Resposta entregue"]}],'
                                '"vertex_steps":[]}'
                            )
                        }
                    }
                ],
            }

        deepseek_module._post_groq = fake_post_groq

        result = await deepseek_module.request_task_plan("pesquise os jogos do Corinthians de hoje")

        self.assertEqual(calls[0]["model"], "llama-3.3-70b-versatile")
        self.assertEqual(calls[0]["response_format"], {"type": "json_object"})
        self.assertEqual(result["planner_provider"], "groq")
        self.assertEqual(result["planner_model"], "llama-3.3-70b-versatile")
        self.assertEqual(result["usage"]["total_tokens"], 123)
        self.assertEqual(result["plan"][0]["tool_hint"], "research")

    async def test_request_task_plan_keeps_simple_prompts_direct(self) -> None:
        calls = []
        deepseek_module.settings.GROQ_API_KEY = "test-groq-key"

        async def fake_post_groq(payload):
            calls.append(payload)
            return {}

        deepseek_module._post_groq = fake_post_groq

        result = await deepseek_module.request_task_plan("qual seu nome")

        self.assertEqual(calls, [])
        self.assertEqual(result["planner_provider"], "direct")
        self.assertEqual(result["plan"], [])


if __name__ == "__main__":
    unittest.main()
