import unittest

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


if __name__ == "__main__":
    unittest.main()
