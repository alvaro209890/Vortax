import unittest

import tools.tool_executor as tool_executor
from services.event_bus import EventBus


class FakeDatabase:
    def list_sources(self, task_id: str) -> list[dict]:
        return [
            {
                "id": 1,
                "task_id": task_id,
                "url": "https://www.hyundai.com/br/pt/creta",
                "title": "Hyundai Creta 2026 oficial",
                "snippet": "Especificacoes do Creta 2026",
                "extracted_text": "Creta 2026 tem ficha tecnica e equipamentos.",
                "source_type": "official",
                "quality_score": 90,
            }
        ]


class FakeWeakEconomicDatabase:
    def list_sources(self, task_id: str) -> list[dict]:
        return [
            {
                "id": 1,
                "task_id": task_id,
                "url": "https://pt.wikipedia.org/wiki/Luiz_Inacio_Lula_da_Silva",
                "title": "Lula biografia",
                "snippet": "Presidente do Brasil de 2003 a 2010.",
                "extracted_text": "Biografia de Lula.",
                "source_type": "web",
                "quality_score": 82,
            },
            {
                "id": 2,
                "task_id": task_id,
                "url": "https://www.gov.br/planalto/pt-br/conheca-a-presidencia/ex-presidentes/jair-bolsonaro",
                "title": "Jair Bolsonaro",
                "snippet": "Presidente do Brasil de 2019 a 2022.",
                "extracted_text": "Biografia institucional de Jair Bolsonaro.",
                "source_type": "official",
                "quality_score": 86,
            },
        ]


class FakeBus(EventBus):
    def __init__(self) -> None:
        super().__init__()
        self.published: list[tuple[str, str, dict]] = []

    async def publish(self, task_id: str, event_type: str, payload: dict | None = None) -> None:
        self.published.append((task_id, event_type, payload or {}))


class FakeBrowserPool:
    def __init__(self, tool) -> None:
        self.tool = tool
        self.called = False
        self.method_name = ""
        self.task_id = ""

    async def get_tool_method(self, task_id: str, method_name: str):
        self.called = True
        self.task_id = task_id
        self.method_name = method_name
        return self.tool


class ToolExecutorResearchCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_google_search_uses_conversation_cache_before_browser(self) -> None:
        original_database = tool_executor.database
        original_pool = tool_executor.browser_pool

        async def fail_if_called(**kwargs):
            raise AssertionError("browser search should not be called on cache hit")

        fake_pool = FakeBrowserPool(fail_if_called)

        try:
            tool_executor.database = FakeDatabase()  # type: ignore[assignment]
            tool_executor.browser_pool = fake_pool  # type: ignore[assignment]

            result = await tool_executor.execute_tool(
                "browser_google_search",
                {"query": "Creta 2026 especificacoes"},
                task_id="task-1",
                bus=FakeBus(),
            )
        finally:
            tool_executor.database = original_database
            tool_executor.browser_pool = original_pool

        self.assertTrue(result["success"])
        self.assertTrue(result["data"]["from_conversation_cache"])
        self.assertFalse(fake_pool.called)

    async def test_google_search_skips_weak_cache_for_economic_comparison(self) -> None:
        original_database = tool_executor.database
        original_pool = tool_executor.browser_pool
        called = False

        async def fake_search(**kwargs):
            nonlocal called
            called = True
            return {
                "blocked": True,
                "error": "fake browser called",
                "query": kwargs.get("query"),
                "results": [],
                "result_count": 0,
            }

        fake_pool = FakeBrowserPool(fake_search)

        try:
            tool_executor.database = FakeWeakEconomicDatabase()  # type: ignore[assignment]
            tool_executor.browser_pool = fake_pool  # type: ignore[assignment]

            result = await tool_executor.execute_tool(
                "browser_google_search",
                {"query": "comparacao Lula Bolsonaro PIB inflacao desemprego 2003 2010 2019 2022"},
                task_id="task-1",
                bus=FakeBus(),
            )
        finally:
            tool_executor.database = original_database
            tool_executor.browser_pool = original_pool

        self.assertTrue(called)
        self.assertTrue(fake_pool.called)
        self.assertEqual(fake_pool.method_name, "google_search")
        self.assertFalse(result["success"])
        self.assertNotIn("from_conversation_cache", result["data"])


if __name__ == "__main__":
    unittest.main()
