"""Presentation of actual HTTP results, independent of the Chrome session."""
from typing import Any


def browser_reading_view(name: str, result: dict[str, Any]) -> dict[str, Any] | None:
    if result.get("blocked") or result.get("success") is False:
        return None
    if name == "browser_google_search":
        if "browser" in str(result.get("engine", "")):
            return None
        return {
            "kind": "search", "url": result.get("url", ""),
            "title": result.get("title") or "Resultados da pesquisa",
            "query": result.get("query", ""),
            "results": [
                {key: str(item.get(key) or "")[:1500] for key in ("title", "href", "snippet")}
                for item in result.get("results", [])[:10]
            ],
            "via": "cache" if result.get("from_conversation_cache") else "http",
        }
    if name == "web_fetch" or result.get("blocked_browser"):
        return {
            "kind": "article", "url": result.get("url", ""),
            "title": result.get("title") or "Leitura da página",
            "text": str(result.get("text") or "")[:12000], "via": "http",
        }
    return None
