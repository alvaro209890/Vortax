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


class FakeBus(EventBus):
    def __init__(self) -> None:
        super().__init__()
        self.published: list[tuple[str, str, dict]] = []

    async def publish(self, task_id: str, event_type: str, payload: dict | None = None) -> None:
        self.published.append((task_id, event_type, payload or {}))


class ToolExecutorResearchCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_google_search_uses_conversation_cache_before_browser(self) -> None:
        original_database = tool_executor.database
        original_tool = tool_executor.TOOLS["browser_google_search"]

        async def fail_if_called(**kwargs):
            raise AssertionError("browser search should not be called on cache hit")

        try:
            tool_executor.database = FakeDatabase()  # type: ignore[assignment]
            tool_executor.TOOLS["browser_google_search"] = fail_if_called

            result = await tool_executor.execute_tool(
                "browser_google_search",
                {"query": "Creta 2026 especificacoes"},
                task_id="task-1",
                bus=FakeBus(),
            )
        finally:
            tool_executor.database = original_database
            tool_executor.TOOLS["browser_google_search"] = original_tool

        self.assertTrue(result["success"])
        self.assertTrue(result["data"]["from_conversation_cache"])


if __name__ == "__main__":
    unittest.main()
