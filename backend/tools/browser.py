import asyncio
import base64
import os
import random
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import httpx
from playwright.async_api import Browser, Page, Playwright, async_playwright

from config import settings
from services.process_registry import register_pid, unregister_pid
from services.source_quality import query_from_google_url, rank_search_results

_STEALTH_JS = """
// Mask webdriver flag
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// Fake plugins array
Object.defineProperty(navigator, 'plugins', {
  get: () => [1, 2, 3, 4, 5],
});

// Fake languages
Object.defineProperty(navigator, 'languages', {
  get: () => ['pt-BR', 'pt', 'en-US', 'en'],
});

// Remove chrome.runtime to look less like automation
if (window.chrome) {
  window.chrome.runtime = undefined;
}

// Fake permissions query
const originalQuery = window.navigator.permissions?.query;
if (originalQuery) {
  window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications'
      ? Promise.resolve({state: Notification.permission})
      : originalQuery(parameters)
  );
}
"""

_USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]


class BrowserToolError(RuntimeError):
    pass


class BrowserTool:
    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._chrome_process: subprocess.Popen | None = None
        self._launch_mode: str = "external"
        self._lock = asyncio.Lock()
        self._warmed_up: bool = False

    async def _ensure_page(self) -> Page:
        async with self._lock:
            if self._page and not self._page.is_closed():
                return self._page

            if self._playwright is None:
                self._playwright = await async_playwright().start()

            endpoint = f"http://127.0.0.1:{settings.CHROME_DEBUG_PORT}"
            if not await self._cdp_available(endpoint):
                await self._launch_chrome(headless=True)
                if not await self._wait_for_cdp(endpoint, timeout_s=12.0):
                    await self._terminate_launched_chrome()
                    await self._launch_chrome(headless=False)
                    if not await self._wait_for_cdp(endpoint, timeout_s=12.0):
                        raise BrowserToolError(f"Chrome CDP nao respondeu em {endpoint}")

            self._browser = await self._playwright.chromium.connect_over_cdp(endpoint)
            ua = random.choice(_USER_AGENTS)
            context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context(
                user_agent=ua,
                locale="pt-BR",
                viewport={"width": 1366, "height": 768},
            )
            self._page = context.pages[0] if context.pages else await context.new_page()
            await self._inject_stealth(self._page)
            if not self._warmed_up:
                await self._warmup_google(self._page)
                self._warmed_up = True
            return self._page

    async def _inject_stealth(self, page: Page) -> None:
        """Inject stealth JS to mask automation signals."""
        try:
            await page.add_init_script(_STEALTH_JS)
        except Exception:
            pass

    async def _warmup_google(self, page: Page) -> None:
        """Visit Google homepage to generate session cookies on first launch."""
        try:
            cookies = await page.context.cookies()
            has_google_cookies = any(
                c.get("domain", "").endswith(".google.com") for c in cookies
            )
            if has_google_cookies:
                return
            await page.goto("https://www.google.com/", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(random.uniform(1.0, 2.0))
            # Try to accept cookies consent if present
            try:
                accept_btn = page.locator('button:has-text("Aceitar"), button:has-text("Accept"), button:has-text("Concordo"), button[id="L2AGLb"]').first
                if await accept_btn.is_visible(timeout=2000):
                    await accept_btn.click()
                    await asyncio.sleep(0.5)
            except Exception:
                pass
            await page.goto("about:blank", wait_until="domcontentloaded", timeout=5000)
        except Exception:
            pass

    async def _cdp_available(self, endpoint: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                response = await client.get(f"{endpoint}/json/version")
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def _wait_for_cdp(self, endpoint: str, timeout_s: float) -> bool:
        deadline = asyncio.get_running_loop().time() + timeout_s
        while asyncio.get_running_loop().time() < deadline:
            if await self._cdp_available(endpoint):
                return True
            if self._chrome_process is not None and self._chrome_process.poll() is not None:
                return False
            await asyncio.sleep(0.25)
        return False

    async def _launch_chrome(self, *, headless: bool) -> None:
        chrome_binary = shutil.which(settings.CHROME_BINARY) or settings.CHROME_BINARY
        runtime_tmp = Path("/dev/shm/vortax-tmp") if Path("/dev/shm").exists() else settings.RUNTIME_PATH / "tmp"
        cache_dir = Path("/dev/shm/vortax-chrome-cache") if Path("/dev/shm").exists() else settings.RUNTIME_PATH / "chrome-cache"
        crash_dir = settings.RUNTIME_PATH / "chrome-crashes"
        runtime_tmp.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        crash_dir.mkdir(parents=True, exist_ok=True)
        # Only remove SingletonLock — preserve cookies and profile data
        if settings.CHROME_PROFILE_PATH.exists() and self._chrome_process is None:
            singleton = settings.CHROME_PROFILE_PATH / "SingletonLock"
            if singleton.exists() or singleton.is_symlink():
                try:
                    singleton.unlink(missing_ok=True)
                except Exception:
                    pass
        settings.CHROME_PROFILE_PATH.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.setdefault("DISPLAY", ":0")
        env.setdefault("XAUTHORITY", os.path.expanduser("~/.Xauthority"))
        env.setdefault("TMPDIR", str(runtime_tmp))
        env.setdefault("TEMP", str(runtime_tmp))
        env.setdefault("TMP", str(runtime_tmp))
        env.setdefault("XDG_CACHE_HOME", str(settings.RUNTIME_PATH / "cache"))

        args = [
            chrome_binary,
            f"--remote-debugging-port={settings.CHROME_DEBUG_PORT}",
            "--remote-debugging-address=127.0.0.1",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={settings.CHROME_PROFILE_PATH}",
            f"--disk-cache-dir={cache_dir}",
            f"--crash-dumps-dir={crash_dir}",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-crash-reporter",
            "--disable-breakpad",
            # Anti-detection: keep extensions enabled, use realistic window
            "--disable-blink-features=AutomationControlled",
            "--window-size=1366,768",
            "--lang=pt-BR",
            "--disable-infobars",
            "about:blank",
        ]
        if headless:
            args.insert(1, "--headless=new")
            self._launch_mode = "headless"
        else:
            self._launch_mode = "visible"

        self._chrome_process = subprocess.Popen(
            args,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        register_pid(self._chrome_process.pid)

    async def _terminate_launched_chrome(self) -> None:
        process = self._chrome_process
        if not process:
            return
        unregister_pid(process.pid)
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3.0)
        self._chrome_process = None

    async def navigate(self, url: str, task_id: str | None = None) -> dict[str, Any]:
        page = await self._ensure_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return {"url": page.url, "title": await page.title(), "launch_mode": self._launch_mode}

    async def get_state(self, task_id: str | None = None) -> dict[str, Any]:
        page = await self._ensure_page()
        return {"url": page.url, "title": await page.title(), "launch_mode": self._launch_mode}

    async def click_text(self, text: str, task_id: str | None = None) -> dict[str, Any]:
        page = await self._ensure_page()
        await page.get_by_text(text, exact=False).first.click(timeout=10000)
        return {"clicked_text": text, "url": page.url, "title": await page.title()}

    async def click_selector(self, selector: str, task_id: str | None = None) -> dict[str, Any]:
        page = await self._ensure_page()
        await page.locator(selector).first.click(timeout=10000)
        return {"clicked_selector": selector, "url": page.url, "title": await page.title()}

    async def click_link_by_index(self, index: int = 1, task_id: str | None = None) -> dict[str, Any]:
        page = await self._ensure_page()
        if "://www.google." in page.url and "/search" in page.url:
            query = query_from_google_url(page.url)
            links = rank_search_results(query, await self._google_results(page, limit=10), limit=max(int(index), 1))
        else:
            links = await self._visible_links(page, limit=max(int(index), 1))
        position = max(int(index), 1) - 1
        if position >= len(links):
            raise BrowserToolError(f"Link index fora do intervalo: {index}")
        link = links[position]
        if self._is_blocked_google_url(link["href"]):
            raise BrowserToolError("Link ignorado por apontar para login/conta do Google")
        await page.goto(link["href"], wait_until="domcontentloaded", timeout=30000)
        return {"opened": link, "url": page.url, "title": await page.title()}

    async def type_text(self, text: str, selector: str | None = None, task_id: str | None = None) -> dict[str, Any]:
        page = await self._ensure_page()
        if selector:
            await page.locator(selector).first.fill(text, timeout=10000)
        else:
            await page.keyboard.type(text)
        return {"typed_chars": len(text), "selector": selector}

    async def press_key(self, key: str, task_id: str | None = None) -> dict[str, Any]:
        page = await self._ensure_page()
        await page.keyboard.press(key)
        return {"pressed": key, "url": page.url, "title": await page.title()}

    async def wait_for_text(self, text: str, timeout_ms: int = 10000, task_id: str | None = None) -> dict[str, Any]:
        page = await self._ensure_page()
        await page.get_by_text(text, exact=False).first.wait_for(timeout=int(timeout_ms))
        return {"found_text": text, "url": page.url, "title": await page.title()}

    async def go_back(self, task_id: str | None = None) -> dict[str, Any]:
        page = await self._ensure_page()
        response = await page.go_back(wait_until="domcontentloaded", timeout=30000)
        return {
            "url": page.url,
            "title": await page.title(),
            "status": response.status if response else None,
        }

    async def google_search(self, query: str, hl: str = "pt-BR", task_id: str | None = None) -> dict[str, Any]:
        # Try pure HTTP search first - zero CAPTCHA risk
        http_result = await self._http_search_fallback(query, hl=hl, task_id=task_id)
        if http_result.get("result_count", 0) > 0:
            return http_result

        # HTTP found nothing - try Google browser as last resort
        page = await self._ensure_page()
        await asyncio.sleep(random.uniform(0.8, 2.5))
        search_url = f"https://www.google.com/search?q={quote_plus(query)}&hl={quote_plus(hl)}"
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

        body_text = ""
        try:
            body_text = await page.locator("body").inner_text(timeout=3000)
        except Exception:
            pass
        if any(m in body_text.lower() for m in ["captcha", "unusual traffic", "not a robot", "sorry", "blocked"]) or "/sorry/" in page.url:
            return http_result

        results = rank_search_results(query, await self._google_results(page, limit=20), limit=10)
        return {
            "query": query,
            "url": page.url,
            "title": await page.title(),
            "results": results,
            "result_count": len(results),
        }

    async def _http_search_fallback(self, query: str, hl: str = "pt-BR", task_id: str | None = None) -> dict[str, Any]:
        """Pure HTTP search — no browser, no fingerprint, no CAPTCHA."""
        ua = random.choice(_USER_AGENTS)
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
        }
        ddg_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&kl=br-pt"
        results: list[dict[str, Any]] = []
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
                resp = await client.get(ddg_url)
                if resp.status_code == 200:
                    results = self._parse_ddg_html(resp.text)
        except Exception:
            pass
        if not results:
            try:
                brave_url = f"https://search.brave.com/search?q={quote_plus(query)}&source=web"
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
                    resp = await client.get(brave_url)
                    if resp.status_code == 200:
                        results = self._parse_brave_html(resp.text)
            except Exception:
                pass
        if not results:
            return await self._duckduckgo_browser_search(query, hl=hl, task_id=task_id)
        ranked = rank_search_results(query, results, limit=10)
        return {"query": query, "url": ddg_url, "title": f"Search - {query}", "results": ranked, "result_count": len(ranked), "engine": "http_fallback"}

    @staticmethod
    def _parse_ddg_html(html: str) -> list[dict[str, Any]]:
        from urllib.parse import unquote
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
            href, title = m.group(1).strip(), re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if not title or not href or href in seen:
                continue
            um = re.search(r"uddg=([^&]+)", href)
            if um:
                href = unquote(um.group(1))
            if href in seen or "duckduckgo.com" in href:
                continue
            seen.add(href)
            results.append({"index": len(results)+1, "title": title[:180], "href": href, "snippet": ""})
            if len(results) >= 20:
                break
        for i, m in enumerate(re.finditer(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)):
            if i < len(results):
                results[i]["snippet"] = re.sub(r"<[^>]+>", "", m.group(1)).strip()[:320]
        return results

    @staticmethod
    def _parse_brave_html(html: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for m in re.finditer(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
            href, title = m.group(1).strip(), re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if not title or href in seen or "brave.com" in href or len(title) < 5:
                continue
            seen.add(href)
            results.append({"index": len(results)+1, "title": title[:180], "href": href, "snippet": ""})
            if len(results) >= 15:
                break
        return results

    async def _duckduckgo_browser_search(self, query: str, hl: str = "pt-BR", task_id: str | None = None) -> dict[str, Any]:
        """Last-resort browser-based DuckDuckGo search."""
        page = await self._ensure_page()
        await asyncio.sleep(random.uniform(0.5, 1.5))
        ddg_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&kl=br-pt"
        await page.goto(ddg_url, wait_until="domcontentloaded", timeout=30000)

        results = await page.evaluate(
            """
            (limit) => {
              const seen = new Set();
              return Array.from(document.querySelectorAll('.result'))
                .map((el) => {
                  const anchor = el.querySelector('.result__a');
                  const snippetEl = el.querySelector('.result__snippet');
                  if (!anchor || !anchor.href) return null;
                  const title = (anchor.innerText || '').replace(/\\s+/g, ' ').trim();
                  const href = anchor.href;
                  const snippet = (snippetEl?.innerText || '').replace(/\\s+/g, ' ').trim();
                  return {title, href, snippet};
                })
                .filter((item) => {
                  if (!item || !item.title || !item.href) return false;
                  if (seen.has(item.href)) return false;
                  seen.add(item.href);
                  return true;
                })
                .slice(0, limit)
                .map((item, i) => ({index: i + 1, title: item.title.slice(0, 180), href: item.href, snippet: item.snippet.slice(0, 320)}));
            }
            """,
            20,
        )

        # If DuckDuckGo HTML also blocked, try the lite version
        if not results:
            await asyncio.sleep(random.uniform(1.0, 2.0))
            lite_url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}&kl=br-pt"
            await page.goto(lite_url, wait_until="domcontentloaded", timeout=30000)
            results = await page.evaluate(
                """
                (limit) => {
                  const seen = new Set();
                  const links = Array.from(document.querySelectorAll('a.result-link, td a[href]'));
                  return links
                    .map((a) => {
                      const title = (a.innerText || '').replace(/\\s+/g, ' ').trim();
                      const href = a.href || '';
                      return {title, href, snippet: ''};
                    })
                    .filter((item) => {
                      if (!item.title || !item.href || item.href.startsWith('javascript:')) return false;
                      if (item.href.includes('duckduckgo.com')) return false;
                      if (seen.has(item.href)) return false;
                      seen.add(item.href);
                      return true;
                    })
                    .slice(0, limit)
                    .map((item, i) => ({index: i + 1, title: item.title.slice(0, 180), href: item.href, snippet: ''}));
                }
                """,
                20,
            )

        ranked = rank_search_results(query, results, limit=10)
        return {
            "query": query,
            "url": page.url,
            "title": await page.title(),
            "results": ranked,
            "result_count": len(ranked),
            "engine": "duckduckgo_browser",
        }

    async def extract_text(self, task_id: str | None = None) -> dict[str, Any]:
        page = await self._ensure_page()
        body_text = await page.locator("body").inner_text(timeout=10000)
        text = body_text[:6000]
        return {"url": page.url, "title": await page.title(), "text": text, "truncated": len(body_text) > len(text)}

    async def extract_article(self, task_id: str | None = None) -> dict[str, Any]:
        page = await self._ensure_page()
        data = await page.evaluate(
            """
            () => {
              const clone = document.body.cloneNode(true);
              clone.querySelectorAll('script, style, nav, footer, header, aside, form, noscript, svg, iframe, button').forEach((node) => node.remove());
              const candidates = Array.from(clone.querySelectorAll('article, main, [role="main"], section, div'));
              const scored = candidates
                .map((node) => {
                  const text = (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim();
                  const paragraphs = node.querySelectorAll ? node.querySelectorAll('p').length : 0;
                  return {node, text, score: text.length + paragraphs * 180};
                })
                .filter((item) => item.text.length > 200)
                .sort((a, b) => b.score - a.score);
              const best = scored[0];
              const title = document.querySelector('meta[property="og:title"]')?.content || document.title || '';
              const description = document.querySelector('meta[name="description"]')?.content || document.querySelector('meta[property="og:description"]')?.content || '';
              const author = document.querySelector('meta[name="author"]')?.content || '';
              const published = document.querySelector('time[datetime]')?.getAttribute('datetime') || document.querySelector('meta[property="article:published_time"]')?.content || '';
              const text = (best ? best.text : (clone.innerText || clone.textContent || '').replace(/\\s+/g, ' ').trim()).slice(0, 10000);
              return {title, description, author, published, text, length: text.length};
            }
            """
        )
        return {
            "url": page.url,
            "title": data.get("title") or await page.title(),
            "description": data.get("description") or "",
            "author": data.get("author") or "",
            "published": data.get("published") or "",
            "text": data.get("text") or "",
            "length": data.get("length") or 0,
        }

    async def extract_links(self, limit: int = 30, prefer_google_results: bool = True, task_id: str | None = None) -> dict[str, Any]:
        page = await self._ensure_page()
        page_url = page.url
        links = []
        if prefer_google_results and "://www.google." in page_url and "/search" in page_url:
            query = query_from_google_url(page_url)
            links = rank_search_results(query, await self._google_results(page, limit=max(int(limit) * 2, 10)), limit=int(limit))
        if not links:
            links = await self._visible_links(page, limit=int(limit))
        return {"url": page.url, "title": await page.title(), "links": links, "count": len(links)}

    async def screenshot(self, task_id: str | None = None) -> dict[str, Any]:
        page = await self._ensure_page()
        image = await page.screenshot(type="jpeg", quality=75, full_page=False)
        return {
            "url": page.url,
            "title": await page.title(),
            "image_base64": base64.b64encode(image).decode("ascii"),
        }

    async def scroll(self, direction: str = "down", amount: int = 700, task_id: str | None = None) -> dict[str, Any]:
        page = await self._ensure_page()
        delta = abs(int(amount))
        if direction == "up":
            delta = -delta
        await page.mouse.wheel(0, delta)
        return {"direction": direction, "amount": abs(int(amount)), "url": page.url}

    async def scroll_to_top(self, task_id: str | None = None) -> dict[str, Any]:
        page = await self._ensure_page()
        await page.evaluate("() => window.scrollTo(0, 0)")
        return await self.get_scroll_state(task_id=task_id)

    async def get_scroll_state(self, task_id: str | None = None) -> dict[str, Any]:
        page = await self._ensure_page()
        data = await page.evaluate(
            """
            () => ({
              scroll_y: Math.round(window.scrollY || document.documentElement.scrollTop || 0),
              viewport_height: Math.round(window.innerHeight || document.documentElement.clientHeight || 0),
              scroll_height: Math.round(document.documentElement.scrollHeight || document.body.scrollHeight || 0),
              url: window.location.href,
              title: document.title || ''
            })
            """
        )
        scroll_y = int(data.get("scroll_y") or 0)
        viewport_height = int(data.get("viewport_height") or 0)
        scroll_height = int(data.get("scroll_height") or 0)
        data["at_bottom"] = scroll_y + viewport_height >= max(scroll_height - 3, 0)
        return data

    async def frontend_smoke_test(self, max_actions: int = 8, task_id: str | None = None) -> dict[str, Any]:
        page = await self._ensure_page()
        errors: list[str] = []

        def _record_console(message) -> None:
            if message.type in {"error", "warning"}:
                errors.append(f"console.{message.type}: {message.text}"[:500])

        def _record_page_error(error) -> None:
            errors.append(f"pageerror: {error}"[:500])

        page.on("console", _record_console)
        page.on("pageerror", _record_page_error)

        actions: list[dict[str, Any]] = []
        try:
            controls = await page.evaluate(
                """
                () => {
                  const selector = 'button, a[href], input, select, textarea, [role="button"], [tabindex]';
                  return Array.from(document.querySelectorAll(selector))
                    .map((el, index) => {
                      const rect = el.getBoundingClientRect();
                      const style = window.getComputedStyle(el);
                      const text = (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('title') || el.placeholder || el.href || el.tagName || '')
                        .replace(/\\s+/g, ' ')
                        .trim();
                      return {
                        index,
                        tag: el.tagName.toLowerCase(),
                        type: el.getAttribute('type') || '',
                        text: text.slice(0, 120),
                        href: el.href || '',
                        visible: rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none',
                        disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true'),
                      };
                    })
                    .filter((item) => item.visible && !item.disabled)
                    .slice(0, 20);
                }
                """
            )

            origin = await page.evaluate("() => window.location.origin")
            start_url = page.url
            for item in controls[: max(int(max_actions), 0)]:
                result = await page.evaluate(
                    """
                    async ({ index, origin }) => {
                      const selector = 'button, a[href], input, select, textarea, [role="button"], [tabindex]';
                      const el = Array.from(document.querySelectorAll(selector))[index];
                      if (!el) return { ok: false, error: 'elemento nao encontrado' };
                      el.scrollIntoView({ block: 'center', inline: 'center' });
                      await new Promise((resolve) => setTimeout(resolve, 120));
                      const tag = el.tagName.toLowerCase();
                      const type = (el.getAttribute('type') || '').toLowerCase();
                      const href = el.href || '';
                      if (href && !href.startsWith(origin) && !href.startsWith('javascript:') && !href.startsWith('#')) {
                        return { ok: true, skipped: true, reason: 'link externo ignorado', href };
                      }
                      if (tag === 'input' || tag === 'textarea') {
                        if (!['checkbox', 'radio', 'button', 'submit', 'reset'].includes(type)) {
                          el.focus();
                          el.value = type === 'number' || type === 'range' ? '1' : 'teste';
                          el.dispatchEvent(new Event('input', { bubbles: true }));
                          el.dispatchEvent(new Event('change', { bubbles: true }));
                          return { ok: true, filled: true };
                        }
                      }
                      el.click();
                      return { ok: true, clicked: true };
                    }
                    """,
                    {"index": item["index"], "origin": origin},
                )
                await page.wait_for_timeout(300)
                if page.url != start_url and not page.url.startswith(origin):
                    await page.goto(start_url, wait_until="domcontentloaded", timeout=10000)
                actions.append({"target": item, "result": result, "url": page.url})

            body_text = await page.locator("body").inner_text(timeout=5000)
            visible_error = bool(re.search(r"\b(error|erro|failed|falhou|exception|cannot|undefined|not found)\b", body_text[:3000], re.IGNORECASE))
            return {
                "success": not errors and not visible_error,
                "actions": actions,
                "errors": errors[:20],
                "visible_error": visible_error,
                "url": page.url,
                "title": await page.title(),
            }
        finally:
            page.remove_listener("console", _record_console)
            page.remove_listener("pageerror", _record_page_error)

    async def _visible_links(self, page: Page, limit: int = 30) -> list[dict[str, Any]]:
        return await page.evaluate(
            """
            (limit) => {
              const seen = new Set();
              const blocked = /(accounts\\.google|ServiceLogin|signin|\\/preferences|\\/setprefs|\\/advanced_search|support\\.google|policies\\.google)/i;
              return Array.from(document.querySelectorAll('a[href]'))
                .map((anchor) => {
                  const rect = anchor.getBoundingClientRect();
                  const text = (anchor.innerText || anchor.textContent || '').replace(/\\s+/g, ' ').trim();
                  const href = anchor.href;
                  return {text, href, visible: rect.width > 0 && rect.height > 0};
                })
                .filter((item) => item.visible && item.text && item.href && !item.href.startsWith('javascript:') && !blocked.test(item.href))
                .filter((item) => {
                  const key = item.href + '|' + item.text;
                  if (seen.has(key)) return false;
                  seen.add(key);
                  return true;
                })
                .slice(0, limit)
                .map((item, index) => ({index: index + 1, title: item.text.slice(0, 180), text: item.text.slice(0, 240), href: item.href}));
            }
            """,
            max(int(limit), 1),
        )

    async def _google_results(self, page: Page, limit: int = 10) -> list[dict[str, Any]]:
        return await page.evaluate(
            """
            (limit) => {
              const seen = new Set();
              const blocked = /(accounts\\.google|ServiceLogin|signin|\\/preferences|\\/setprefs|\\/advanced_search|support\\.google|policies\\.google|google\\.com\\/intl|google\\.com\\/search\\?|google\\.com\\/url\\?sa=U)/i;
              const selectors = ['div.g', 'div[data-sokoban-container]', 'div.MjjYud'];
              const cards = selectors.flatMap((selector) => Array.from(document.querySelectorAll(selector)));
              const candidates = cards.length ? cards : Array.from(document.querySelectorAll('a[href]'));
              const results = [];

              for (const card of candidates) {
                const anchor = card.matches && card.matches('a[href]') ? card : card.querySelector('a[href]');
                if (!anchor || !anchor.href || blocked.test(anchor.href)) continue;

                const titleNode = card.querySelector('h3') || anchor;
                const title = (titleNode.innerText || titleNode.textContent || '').replace(/\\s+/g, ' ').trim();
                if (!title) continue;

                const text = (card.innerText || card.textContent || '').replace(/\\s+/g, ' ').trim();
                const snippet = text.replace(title, '').trim().slice(0, 320);
                const key = anchor.href;
                if (seen.has(key)) continue;
                seen.add(key);

                results.push({
                  index: results.length + 1,
                  title: title.slice(0, 180),
                  href: anchor.href,
                  snippet,
                });
                if (results.length >= limit) break;
              }
              return results;
            }
            """,
            max(int(limit), 1),
        )

    def _is_blocked_google_url(self, url: str) -> bool:
        blocked_fragments = (
            "accounts.google",
            "ServiceLogin",
            "signin",
            "/preferences",
            "/setprefs",
            "/advanced_search",
            "support.google",
            "policies.google",
        )
        return any(fragment.lower() in url.lower() for fragment in blocked_fragments)

    async def close(self) -> None:
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        await self._terminate_launched_chrome()
        self._page = None


browser_tool = BrowserTool()
