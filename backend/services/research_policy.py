import re
from urllib.parse import urlparse


STOPWORDS = {
    "a", "as", "ao", "aos", "com", "da", "das", "de", "do", "dos",
    "e", "em", "na", "nas", "no", "nos", "o", "os", "para", "por",
    "que", "qual", "quais", "um", "uma",
}

# Padroes para deteccao de pedidos que se beneficiariam de pesquisa previa
SUBJECTIVE_DESIGN_PATTERNS = (
    r"\b(modern[oa]|profissiona[l|is]|bonit[oa]|atrativ[oa]|elegante|"
    r"sofisticad[oa]|contemporane[oa]|estilos[oa]|luxuoso|minimalist[oa])\b"
)

TREND_PATTERNS = (
    r"\b(tendencias?|tendências?|atual|atualmente|lançamento|"
    r"novo|nova|novos|novas|últimos|ultimos|recém|recem)\b"
)

VAGUE_TECH_PATTERNS = (
    r"\b(react|vue|angular|next|nuxt|node|express|django|flask)\b(?!\s*(?:v?\d+|version|versão|com\s+typescript))"
)

QUALITY_AMBIGUITY_PATTERNS = (
    r"\b(responsivo|otimizad[oa]|performatic[oa]|escalável|escalavel|"
    r"acessível|acessivel|seguro|rápido|rapido|leve|robust[oa])\b"
)

SECTOR_PATTERNS = (
    r"\b(ecommerce|e-commerce|loja\s+virtual|saas|landing\s*page|"
    r"portfólio|portfolio|blog|sistema\s+web|plataforma|marketplace|"
    r"aplicativo|app|dashboard|painel|site\s+institucional)\b"
)

DEVELOPMENT_DESIGN_SOURCES = (
    "dribbble", "behance", "awwwards", "siteinspire", "referencia",
    "exemplo", "inspiração", "inspiracao", "ui design", "ux design",
)

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
    "pessoa": (
        r"\bnome\b",
        r"\bpessoa\b",
        r"\bperfil\b",
        r"\bquem [ée]\b",
        r"\blinkedin\b",
        r"\bcurriculo\b",
        r"\bcurrículo\b",
        r"\bbiografia\b",
        r"\bbio\b",
        r"\binformacoes sobre\b",
        r"\binformações sobre\b",
        r"\bdados de\b",
        r"\bquem sou\b",
        r"\bquem e\b",
        r"\bsobre\b.*\b(?:mim|voce|ele|ela|nome|pessoa)\b",
        r"\bconhecer\b",
        r"\bencontrar\b",
    ),
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

DEVELOPMENT_PATTERNS = (
    r"\b(crie|criar|gere|gerar|desenvolva|desenvolver|implemente|implementar|fa[cç]a|construa)\b",
    r"\b(site|pagina|p[aá]gina|app|aplicativo|calculadora|dashboard|landing|frontend|html|css|javascript|react|vite)\b",
)


def normalized_terms(text: str) -> set[str]:
    normalized = "".join(char.lower() if char.isalnum() else " " for char in text)
    return {part for part in normalized.split() if len(part) >= 3 and part not in STOPWORDS}


def research_profile(text: str) -> dict[str, object]:
    lowered = text.lower()
    development_intent = all(
        any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in group)
        for group in (
            DEVELOPMENT_PATTERNS[:1],
            DEVELOPMENT_PATTERNS[1:],
        )
    )
    categories = [
        category
        for category, patterns in SENSITIVE_PATTERNS.items()
        if any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in patterns)
    ]
    freshness_requested = any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in FRESHNESS_PATTERNS)
    search_intent = (not development_intent) and bool(
        re.search(
            r"\b(pesquis|busc|procure|encontre|fonte|fontes|web|internet|not[ií]ci[aa]|pre[cç]o|compar)",
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
        "development_intent": development_intent,
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


def _extract_project_type(text: str) -> str | None:
    """Extrai o tipo de projeto do texto (ex: 'site', 'dashboard', 'api')."""
    lowered = text.lower()
    types = re.findall(SECTOR_PATTERNS, lowered)
    if types:
        return types[0]
    for pattern in (r"\bsite\b", r"\bapi\b", r"\bscript\b", r"\bsistema\b", r"\bapp\b", r"\bcli\b"):
        match = re.search(pattern, lowered)
        if match:
            return match.group(0)
    return None


def _extract_research_keywords(text: str) -> list[str]:
    """Extrai termos-chave do pedido para montar queries de pesquisa."""
    lowered = text.lower()
    keywords: list[str] = []
    for match in re.finditer(
        r"\b(react|vue|angular|node|python|javascript|typescript|html|css|next|nuxt|vite|tailwind|bootstrap)\b",
        lowered,
    ):
        tech = match.group(0).strip()
        if tech not in keywords:
            keywords.append(tech)
    return keywords[:5]


def software_research_profile(text: str) -> dict:
    """Analisa se um pedido de criacao de software se beneficiaria de pesquisa previa.

    Retorna dict com:
    - is_software_request: bool
    - requires_pre_research: bool — True se pesquisa previa e altamente recomendada
    - reasons: list[str] — motivos para a recomendacao
    - research_queries: list[str] — queries sugeridas para pesquisa
    - keywords: list[str] — termos-chave extraidos
    - project_type: str | None
    """
    lowered = text.lower()

    is_software_request = all(
        any(re.search(pattern, lowered, re.IGNORECASE) for pattern in group)
        for group in (DEVELOPMENT_PATTERNS[:1], DEVELOPMENT_PATTERNS[1:])
    )
    if not is_software_request:
        return {
            "is_software_request": False,
            "requires_pre_research": False,
            "reasons": [],
            "research_queries": [],
            "keywords": [],
            "project_type": None,
        }

    reasons: list[str] = []
    if re.search(SUBJECTIVE_DESIGN_PATTERNS, lowered):
        reasons.append("pedido menciona atributos subjetivos de design")
    if re.search(TREND_PATTERNS, lowered):
        reasons.append("pedido menciona tendencias ou atualidade")
    if re.search(VAGUE_TECH_PATTERNS, lowered):
        reasons.append("pedido menciona framework sem especificar versao ou detalhes")
    if re.search(QUALITY_AMBIGUITY_PATTERNS, lowered):
        reasons.append("pedido usa termos de qualidade ambiguos que se beneficiam de contexto")

    project_type = _extract_project_type(text)
    keywords = _extract_research_keywords(text)

    research_queries: list[str] = []
    year = "2026"
    base = project_type or "site web"
    if reasons:
        research_queries.append(f"tendencias {base} {year}")
        research_queries.append(f"design {base} exemplos {year}")
        if any("design" in r for r in reasons):
            research_queries.append(f"melhores praticas {base} {year}")
    if keywords:
        tech_part = "+".join(keywords[:3])
        research_queries.append(f"{base} {tech_part} {year}")

    # Remove duplicatas mantendo ordem
    seen: set[str] = set()
    unique_queries: list[str] = []
    for q in research_queries:
        if q not in seen:
            seen.add(q)
            unique_queries.append(q)

    return {
        "is_software_request": True,
        "requires_pre_research": len(reasons) >= 1,
        "reasons": reasons,
        "research_queries": unique_queries[:3],
        "keywords": keywords,
        "project_type": project_type,
    }


# ─── Pesquisa de Pessoas ──────────────────────────────────────────────

PEOPLE_SEARCH_QUERIES = {
    "linkedin": "site:linkedin.com/in \"{nome}\"",
    "github": "site:github.com \"{nome}\"",
    "facebook": "site:facebook.com \"{nome}\"",
    "instagram": "site:instagram.com \"{nome}\"",
    "wikipedia": "site:wikipedia.org \"{nome}\"",
    "google_news": "\"{nome}\" noticias",
    "bing_news": "\"{nome}\"",
    "curriculo": "\"{nome}\" curriculo OR currículo OR CV OR lattes",
    "academico": "\"{nome}\" site:.edu.br OR site:.org",
    "profissional": "\"{nome}\" linkedin OR github OR portifolio OR portfolio",
}


def people_research_profile(text: str) -> dict:
    """Analisa se o pedido envolve pesquisa sobre uma pessoa e retorna
    estrategias de busca especializadas.

    Retorna dict com:
    - is_people_search: bool
    - person_name: str | None — nome extraido
    - required_sources: int — numero minimo de fontes (3+ para pessoas)
    - search_queries: list[str] — queries variadas para buscar a pessoa
    - categories: list[str] — plataformas sugeridas
    """
    lowered = text.lower()

    # Detecta se e uma busca por pessoa
    people_pattern = re.compile(
        r"(?:^|\s)(?:busque|pesquise|pesquisar|buscar|encontre|encontrar|"
        r"procure|procurar|quem [ée]|informa[cç][õo]es sobre|"
        r"dados de|biografia|perfil de|curriculo de|sobre\s+\w+\s+\w+)"
        r"(?:\s+[^.,!?]{3,60})",
        re.IGNORECASE,
    )

    # Nomes proprio (duas ou mais palavras com inicial maiuscula no pedido original)
    name_pattern = re.compile(
        r"[A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+){1,5}"
    )

    # Categoriza as plataformas mencionadas
    platform_keywords = {
        "linkedin": r"\blinkedin\b",
        "github": r"\bgithub\b",
        "facebook": r"\bfacebook\b",
        "instagram": r"\binstagram\b",
        "wikipedia": r"\bwikipedia\b",
        "curriculo": r"\bcurriculo\b|\bcurrículo\b|\blattes\b|\bcv\b",
        "noticias": r"\bnot[ií]cia\b|\bnews\b|\bartigo\b",
    }

    has_people_pattern = bool(people_pattern.search(text))
    has_name_mention = bool(name_pattern.search(text))

    # Se o research_profile ja detectou categoria "pessoa"
    profile = research_profile(text)
    is_people = has_people_pattern or has_name_mention or "pessoa" in profile.get("categories", [])

    if not is_people:
        return {
            "is_people_search": False,
            "person_name": None,
            "required_sources": 0,
            "search_queries": [],
            "categories": [],
        }

    # Extrai nome - pega o match mais longo de nome proprio
    names = name_pattern.findall(text)
    person_name = max(names, key=len) if names else None

    # Se nao achou nome via maiusculas, tenta extrair do padrao "sobre X"
    if not person_name:
        about_match = re.search(
            r"(?:sobre|de|para)\s+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+){1,5})",
            text,
        )
        if about_match:
            person_name = about_match.group(1).strip()

    suggested_platforms = []
    for platform, pattern in platform_keywords.items():
        if re.search(pattern, lowered):
            suggested_platforms.append(platform)

    # Se mencionou plataformas especificas, usa so elas; senao, algumas variadas
    if suggested_platforms:
        search_queries = [
            PEOPLE_SEARCH_QUERIES[p].format(nome=person_name)
            for p in suggested_platforms
            if p in PEOPLE_SEARCH_QUERIES
        ]
    else:
        # Query variada: nome entre aspas + variacoes
        quoted = f'"{person_name}"' if person_name else text
        search_queries = [
            PEOPLE_SEARCH_QUERIES["profissional"].format(nome=person_name),
            PEOPLE_SEARCH_QUERIES["google_news"].format(nome=person_name),
            PEOPLE_SEARCH_QUERIES["curriculo"].format(nome=person_name),
        ]

    # Sempre inclui busca generica com nome entre aspas
    if person_name:
        search_queries.insert(0, f'"{person_name}"')

    # Remove duplicatas
    seen: set[str] = set()
    unique_queries: list[str] = []
    for q in search_queries:
        if q not in seen:
            seen.add(q)
            unique_queries.append(q)

    return {
        "is_people_search": True,
        "person_name": person_name,
        "required_sources": max(3, len(suggested_platforms) if suggested_platforms else 3),
        "search_queries": unique_queries[:6],
        "categories": suggested_platforms or ["linkedin", "github", "profissional", "curriculo", "noticias"],
    }
