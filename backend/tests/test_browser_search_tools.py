import unittest
from pathlib import Path

from tools.browser import BrowserTool


class FakeResponse:
    status = 200


class FakePage:
    def __init__(self) -> None:
        self.url = "about:blank"
        self.body_text = "conteudo normal"
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

    def locator(self, selector: str):
        page = self

        class FakeLocator:
            async def inner_text(self, timeout: int):
                return page.body_text

        return FakeLocator()


class BrowserSearchToolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.page = FakePage()
        self.tool = BrowserTool(cdp_port=9999, profile_dir=Path("/tmp/vortax-browser-test"))

        async def ensure_page():
            return self.page

        self.tool._ensure_page = ensure_page  # type: ignore[method-assign]

        # Mock _http_search_fallback to return empty so test reaches browser google
        async def empty_fallback(*args, **kwargs):
            return {"result_count": 0, "results": []}

        self.tool._http_search_fallback = empty_fallback  # type: ignore[method-assign]

    async def test_google_search_uses_non_google_browser_fallback(self) -> None:
        result = await self.tool.google_search("deepseek v4 flash", hl="pt-BR")

        self.assertIn("https://html.duckduckgo.com/html/?q=deepseek+v4+flash", self.page.goto_calls[0])
        self.assertNotIn("google.com/search", self.page.goto_calls[0])
        self.assertEqual(result["query"], "deepseek v4 flash")
        self.assertEqual(result["result_count"], 2)
        self.assertEqual(result["engine"], "duckduckgo_browser")

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

    async def test_navigate_reports_captcha_without_screenshot_flow(self) -> None:
        self.page.body_text = "Confirme que nao sou um robo"

        result = await self.tool.navigate("https://example.com/captcha")

        self.assertTrue(result["blocked"])
        self.assertFalse(result["success"])

    async def test_extract_text_uses_http_fallback_when_browser_is_blocked(self) -> None:
        self.page.url = "https://example.com/noticia"
        self.page.body_text = "captcha not a robot"

        async def fake_http_extract(url):
            return {"url": url, "title": "Noticia", "text": "conteudo por http", "length": 17}

        self.tool._http_extract_url = fake_http_extract  # type: ignore[method-assign]
        result = await self.tool.extract_text()

        self.assertEqual(result["text"], "conteudo por http")
        self.assertIn("blocked_browser", result)


if __name__ == "__main__":
    unittest.main()
