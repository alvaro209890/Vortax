from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse, urlunparse


DATA_HINTS = (
    "ibge.gov.br",
    "sidra.ibge.gov.br",
    "ipea.gov.br",
    "ipeadata.gov.br",
    "bcb.gov.br",
    "sgs.bcb.gov.br",
    "dados.gov.br",
    "data.worldbank.org",
    "worldbank.org",
    "oecd.org",
    "imf.org",
    "cepal.org",
)
OFFICIAL_HINTS = ("gov.", ".gov", "edu.", ".edu", "hyundai.com", "openai.com", "deepseek.com")
NEWS_HINTS = ("g1.globo.com", "uol.com.br", "estadao.com.br", "folha.uol.com.br", "autoesporte.globo.com", "motor1.com")
LOW_VALUE_HINTS = (
    "accounts.google",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "pinterest.",
    "youtube.com/shorts",
    "google.com/preferences",
    "google.com/search",
    "google.com/url",
)
MAX_RESULTS_PER_HOST = 2


def source_type_for_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if any(hint in host for hint in DATA_HINTS):
        return "data"
    if any(hint in host for hint in OFFICIAL_HINTS):
        return "official"
    if any(hint in host for hint in NEWS_HINTS):
        return "news"
    if "youtube.com" in host or "youtu.be" in host:
        return "video"
    if "reddit.com" in host or "forum" in host:
        return "forum"
    if any(hint in host for hint in ("mercadolivre", "amazon.", "shop", "loja")):
        return "marketplace"
    return "web"


def source_quality_score(url: str, title: str = "", text: str = "") -> int:
    host = urlparse(url).netloc.lower()
    score = 50
    if any(hint in host for hint in DATA_HINTS):
        score += 35
    if any(hint in host for hint in OFFICIAL_HINTS):
        score += 30
    if any(hint in host for hint in NEWS_HINTS):
        score += 18
    if any(hint in host for hint in LOW_VALUE_HINTS):
        score -= 35
    if len(text) >= 1500:
        score += 12
    elif len(text) < 400:
        score -= 10
    if title:
        score += 4
    if url.lower().endswith(".pdf"):
        score += 8
    return max(0, min(score, 100))


def _canonical_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", "", ""))


def _terms(text: str) -> set[str]:
    return {part for part in "".join(char.lower() if char.isalnum() else " " for char in text).split() if len(part) >= 3}


def _result_text(result: dict) -> str:
    return " ".join(
        str(result.get(key) or "")
        for key in ("title", "text", "snippet", "href", "url")
    )


def _recency_score(text: str) -> int:
    year = datetime.now(timezone.utc).year
    lowered = text.lower()
    if "hoje" in lowered or "atualizado" in lowered or "updated" in lowered:
        return 8
    for candidate in range(year, year - 4, -1):
        if str(candidate) in lowered:
            return max(2, 8 - (year - candidate) * 2)
    return 0


def rank_search_results(query: str, results: list[dict], *, limit: int = 10) -> list[dict]:
    """Deduplicate and rank search results before the planner opens links."""
    query_terms = _terms(query)
    by_url: dict[str, dict] = {}

    for result in results:
        href = str(result.get("href") or result.get("url") or "").strip()
        if not href:
            continue
        host = urlparse(href).netloc.lower()
        if not host or any(hint in href.lower() for hint in LOW_VALUE_HINTS):
            continue

        canonical = _canonical_url(href)
        text = _result_text(result)
        result_terms = _terms(text)
        overlap = len(query_terms & result_terms)
        quality = source_quality_score(href, str(result.get("title") or ""), text)
        score = quality + overlap * 8 + _recency_score(text)
        if host.startswith("www."):
            host_key = host[4:]
        else:
            host_key = host

        ranked = {
            **result,
            "href": href,
            "source_type": source_type_for_url(href),
            "quality_score": quality,
            "rank_score": max(0, min(score, 150)),
            "_host_key": host_key,
        }
        existing = by_url.get(canonical)
        if not existing or ranked["rank_score"] > existing["rank_score"]:
            by_url[canonical] = ranked

    host_counts: dict[str, int] = {}
    ranked_results = []
    for result in sorted(by_url.values(), key=lambda item: item["rank_score"], reverse=True):
        host_key = result.pop("_host_key", "")
        if host_counts.get(host_key, 0) >= MAX_RESULTS_PER_HOST:
            continue
        host_counts[host_key] = host_counts.get(host_key, 0) + 1
        result["index"] = len(ranked_results) + 1
        ranked_results.append(result)
        if len(ranked_results) >= limit:
            break
    return ranked_results


def query_from_google_url(url: str) -> str:
    parsed = urlparse(url)
    values = parse_qs(parsed.query).get("q") or []
    return values[0] if values else ""
