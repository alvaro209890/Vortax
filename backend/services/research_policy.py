import re
from urllib.parse import urlparse


STOPWORDS = {
    "a",
    "as",
    "ao",
    "aos",
    "com",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "para",
    "por",
    "que",
    "qual",
    "quais",
    "um",
    "uma",
}

FRESHNESS_PATTERNS = (
    r"\batual(?:izado|izada|mente)?\b",
    r"\bhoje\b",
    r"\bagora\b",
    r"\brecent(?:e|es)\b",
    r"\bmais recente\b",
    r"\b[uú]ltim[oa]s?\b",
    r"\bnovo\b",
    r"\bnot[ií]ci[aa]s?\b",
    r"\blan[cç]amento\b",
)

SENSITIVE_PATTERNS = {
    "preco": (r"\bpre[cç]os?\b", r"\bvalor\b", r"\bcusta\b", r"\boferta\b", r"\bdisponibilidade\b"),
    "versao": (r"\bvers(?:[aã]o|oes|ões)\b", r"\brelease\b", r"\bchangelog\b", r"\bmodelo\b"),
    "documentacao": (r"\bdocumenta[cç][aã]o\b", r"\bdocs?\b", r"\bapi\b", r"\bsdk\b"),
    "noticia": (r"\bnot[ií]ci[aa]s?\b", r"\bhoje\b", r"\bagora\b", r"\brecent(?:e|es)\b"),
    "comparacao": (r"\bcompar(?:ar|e|acao|a[cç][aã]o)\b", r"\bversus\b", r"\bvs\b", r"\bmelhor\b"),
    "alto_risco": (
        r"\bmedic[oa]\b",
        r"\bsa[uú]de\b",
        r"\blegal\b",
        r"\bjur[ií]dic[oa]\b",
        r"\bfinanceir[oa]\b",
        r"\binvestimento\b",
        r"\bseguran[cç]a\b",
        r"\bsens[ií]ve(?:l|is)\b",
    ),
}

PRICE_RE = re.compile(r"(?:R\$\s*|\$\s*)\d[\d.,]*|\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})\b")
VERSION_RE = re.compile(r"\bv?\d+(?:\.\d+){1,3}\b", re.IGNORECASE)
DATE_RE = re.compile(r"\b(?:20\d{2}|\d{1,2}/\d{1,2}/20\d{2})\b")
NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?%?\b")


def normalized_terms(text: str) -> set[str]:
    normalized = "".join(char.lower() if char.isalnum() else " " for char in text)
    return {part for part in normalized.split() if len(part) >= 3 and part not in STOPWORDS}


def research_profile(text: str) -> dict[str, object]:
    lowered = text.lower()
    categories = [
        category
        for category, patterns in SENSITIVE_PATTERNS.items()
        if any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in patterns)
    ]
    freshness_requested = any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in FRESHNESS_PATTERNS)
    search_intent = bool(
        re.search(
            r"\b(pesquis|busc|procure|encontre|fonte|fontes|site|web|internet|not[ií]ci[aa]|pre[cç]o|compar)",
            lowered,
            flags=re.IGNORECASE,
        )
    )
    requires_cross_check = bool(categories)
    required_sources = 2 if requires_cross_check else (1 if search_intent else 0)
    return {
        "categories": categories,
        "freshness_requested": freshness_requested,
        "requires_cross_check": requires_cross_check,
        "required_sources": required_sources,
        "search_intent": search_intent,
    }


def _source_text(source: dict) -> str:
    return " ".join(
        str(source.get(key) or "")
        for key in ("title", "snippet", "extracted_text", "url", "source_type")
    )


def source_match_score(query: str, source: dict) -> int:
    query_terms = normalized_terms(query)
    if not query_terms:
        return 0
    source_terms = normalized_terms(_source_text(source))
    overlap = len(query_terms & source_terms)
    if overlap == 0:
        return 0
    ratio = overlap / max(len(query_terms), 1)
    quality = int(source.get("quality_score") or 0)
    return int(overlap * 12 + ratio * 35 + min(quality, 100) * 0.4)


def relevant_sources_for_query(query: str, sources: list[dict], *, limit: int = 8, min_quality: int = 55) -> list[dict]:
    ranked = []
    for source in sources:
        quality = int(source.get("quality_score") or 0)
        if quality < min_quality:
            continue
        score = source_match_score(query, source)
        if score < 24:
            continue
        ranked.append({**source, "match_score": score})
    ranked.sort(key=lambda item: (int(item.get("match_score") or 0), int(item.get("quality_score") or 0)), reverse=True)
    return ranked[:limit]


def cached_search_result(query: str, sources: list[dict], *, limit: int = 6) -> dict | None:
    profile = research_profile(query)
    if profile["freshness_requested"]:
        return None
    matches = relevant_sources_for_query(query, sources, limit=limit)
    if len(matches) < int(profile["required_sources"] or 1):
        return None
    results = []
    for index, source in enumerate(matches, start=1):
        text = str(source.get("extracted_text") or source.get("snippet") or "").strip()
        results.append(
            {
                "index": index,
                "title": source.get("title") or source.get("url"),
                "href": source.get("url"),
                "snippet": text[:700],
                "source_type": source.get("source_type") or "web",
                "quality_score": int(source.get("quality_score") or 0),
                "rank_score": int(source.get("match_score") or 0),
                "from_conversation_cache": True,
            }
        )
    return {
        "query": query,
        "from_conversation_cache": True,
        "cache_policy": "reused_saved_sources_for_same_conversation",
        "result_count": len(results),
        "results": results,
        "instruction": (
            "Estas fontes ja foram abertas e extraidas nesta conversa. "
            "Use os snippets/excertos salvos para responder ou use browser_navigate no href se precisar reler; "
            "nao use browser_click_link_by_index para estes resultados em cache."
        ),
    }


def _tokens_by_source(category: str, sources: list[dict]) -> list[dict[str, object]]:
    extractor = NUMBER_RE
    if category == "preco":
        extractor = PRICE_RE
    elif category in {"versao", "documentacao"}:
        extractor = VERSION_RE
    elif category == "noticia":
        extractor = DATE_RE

    extracted = []
    for source in sources:
        text = _source_text(source)
        tokens = sorted({match.group(0).strip().lower() for match in extractor.finditer(text) if match.group(0).strip()})
        if tokens:
            extracted.append(
                {
                    "url": source.get("url"),
                    "host": urlparse(str(source.get("url") or "")).netloc,
                    "tokens": tokens[:8],
                }
            )
    return extracted


def detect_source_divergence(query: str, sources: list[dict]) -> dict[str, object]:
    profile = research_profile(query)
    signals = []
    for category in profile["categories"]:
        token_sets = _tokens_by_source(str(category), sources)
        if len(token_sets) < 2:
            continue
        distinct = {token for item in token_sets for token in item["tokens"]}
        common = set(token_sets[0]["tokens"])
        for item in token_sets[1:]:
            common &= set(item["tokens"])
        if len(distinct) > 1 and not common:
            signals.append(
                {
                    "category": category,
                    "sources": token_sets[:4],
                }
            )
    return {"has_divergence": bool(signals), "signals": signals}


def cross_check_status(query: str, sources: list[dict]) -> dict[str, object]:
    profile = research_profile(query)
    relevant = relevant_sources_for_query(query, sources, limit=10, min_quality=45)
    required = int(profile["required_sources"] or 0)
    divergence = detect_source_divergence(query, relevant)
    return {
        "profile": profile,
        "required_sources": required,
        "source_count": len(relevant),
        "satisfied": len(relevant) >= required,
        "sources": relevant,
        "divergence": divergence,
    }
