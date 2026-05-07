import unittest

from tools.browser import BrowserTool


class FakeResponse:
    status = 200


class FakePage:
    def __init__(self) -> None:
        self.url = "about:blank"
        self.goto_calls: list[str] = []
        self.evaluate_calls: list[tuple[str, int]] = []

    async def title(self) -> str:
        return "Fake Title"

    async def goto(self, url: str, wait_until: str, timeout: int) -> FakeResponse:
        self.url = url
        self.goto_calls.append(url)
        return FakeResponse()

    async def evaluate(self, script: str, limit: int) -> list[dict]:
        self.evaluate_calls.append((script, limit))
        if "_google_results" in script:
            return []
        return [
            {"index": 1, "title": "Primeiro", "text": "Primeiro link", "href": "https://example.com/one"},
            {"index": 2, "title": "Segundo", "text": "Segundo link", "href": "https://example.com/two"},
        ][:limit]


class BrowserSearchToolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.page = FakePage()
        self.tool = BrowserTool()

        async def ensure_page():
            return self.page

        self.tool._ensure_page = ensure_page  # type: ignore[method-assign]

        # Mock _http_search_fallback to return empty so test reaches browser google
        async def empty_fallback(*args, **kwargs):
            return {"result_count": 0, "results": []}

        self.tool._http_search_fallback = empty_fallback  # type: ignore[method-assign]

    async def test_google_search_opens_encoded_google_url(self) -> None:
        result = await self.tool.google_search("deepseek v4 flash", hl="pt-BR")

        self.assertIn("https://www.google.com/search?q=deepseek+v4+flash", self.page.goto_calls[0])
        self.assertEqual(result["query"], "deepseek v4 flash")
        self.assertEqual(result["result_count"], 2)

    async def test_extract_links_returns_visible_links(self) -> None:
        result = await self.tool.extract_links(limit=2, prefer_google_results=False)

        self.assertEqual(result["count"], 2)
        self.assertEqual(result["links"][0]["href"], "https://example.com/one")

    async def test_click_link_by_index_opens_selected_link(self) -> None:
        result = await self.tool.click_link_by_index(index=2)

        self.assertEqual(self.page.goto_calls[-1], "https://example.com/two")
        self.assertEqual(result["opened"]["title"], "Segundo")

    async def test_google_login_urls_are_blocked(self) -> None:
        self.assertTrue(self.tool._is_blocked_google_url("https://accounts.google.com/ServiceLogin"))
        self.assertTrue(self.tool._is_blocked_google_url("https://www.google.com/preferences"))
        self.assertFalse(self.tool._is_blocked_google_url("https://www.hyundai.com.br/"))


if __name__ == "__main__":
    unittest.main()
