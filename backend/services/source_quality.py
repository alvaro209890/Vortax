from urllib.parse import urlparse


OFFICIAL_HINTS = ("gov.", ".gov", "edu.", ".edu", "hyundai.com", "openai.com", "deepseek.com")
NEWS_HINTS = ("g1.globo.com", "uol.com.br", "estadao.com.br", "folha.uol.com.br", "autoesporte.globo.com", "motor1.com")
LOW_VALUE_HINTS = ("accounts.google", "facebook.com", "instagram.com", "tiktok.com", "pinterest.", "youtube.com/shorts")


def source_type_for_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
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
