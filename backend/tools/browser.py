import asyncio
import base64
import os
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
            context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()
            self._page = context.pages[0] if context.pages else await context.new_page()
            return self._page

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
        if settings.CHROME_PROFILE_PATH.exists() and self._chrome_process is None:
            singleton = settings.CHROME_PROFILE_PATH / "SingletonLock"
            if singleton.exists() or singleton.is_symlink():
                shutil.rmtree(settings.CHROME_PROFILE_PATH, ignore_errors=True)
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
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-extensions",
            "--disable-crash-reporter",
            "--disable-breakpad",
            "--disable-background-networking",
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
        page = await self._ensure_page()
        search_url = f"https://www.google.com/search?q={quote_plus(query)}&hl={quote_plus(hl)}"
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        results = rank_search_results(query, await self._google_results(page, limit=20), limit=10)
        return {
            "query": query,
            "url": page.url,
            "title": await page.title(),
            "results": results,
            "result_count": len(results),
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
