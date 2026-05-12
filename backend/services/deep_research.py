"""Modo de Pesquisa Profunda do Vortax.

Executa N iteracoes de busca + leitura de paginas + sintese,
entregando um relatorio estruturado ao final.
"""

from __future__ import annotations

import json
from typing import Any

from config import settings
from services.activity_events import publish_agent_activity
from services.event_bus import EventBus
from services.research_policy import query_complexity
from tools.browser_pool import browser_pool
from tools.browser import BrowserTool

# Pular links que sao login, ads ou tracking
_SKIP_URL_PATTERNS = [
    "accounts.google.com",
    "ServiceLogin",
    "google.com/preferences",
    "google.com/settings",
    "ad.doubleclick.net",
    "facebook.com/login",
    "twitter.com/login",
    "instagram.com/accounts",
    "linkedin.com/login",
    "apple.com/sign-in",
    "signin",
    "sign-up",
    "register",
    "paywall",
    "/preferences",
    "/settings/account",
]

# Maximo de caracteres extraidos por fonte
MAX_EXTRACTED_CHARS = 5000


def _skip_url(url: str) -> bool:
    url_lower = url.lower()
    return any(pattern.lower() in url_lower for pattern in _SKIP_URL_PATTERNS)


def _select_top_results(
    results: list[dict[str, Any]],
    max_results: int = 2,
    already_visited: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Seleciona os melhores resultados, pulando login/ads/duplicados."""
    visited = already_visited or set()
    selected: list[dict[str, Any]] = []
    for r in results:
        if len(selected) >= max_results:
            break
        url = str(r.get("url") or r.get("href") or "")
        if not url or url in visited or _skip_url(url):
            continue
        title = str(r.get("title") or "").strip()
        if not title or len(title) < 3:
            continue
        selected.append(r)
        visited.add(url)
    return selected


async def _extract_text_from_page(browser: BrowserTool, url: str) -> str:
    """Navega ate a URL e extrai conteudo textual."""
    try:
        article = await browser.extract_article()
        text = str(article.get("text") or article.get("content") or "")
        if len(text) >= 100:
            return text[:MAX_EXTRACTED_CHARS]
    except Exception:
        pass

    try:
        result = await browser.extract_text()
        text = str(result.get("text") or "")
        if len(text) >= 50:
            return text[:MAX_EXTRACTED_CHARS]
    except Exception:
        pass

    return ""


async def _analyze_page_content(
    content: str,
    current_query: str,
    iteration: int,
) -> dict[str, Any]:
    """Analisa o conteudo extraido e gera insights + query refinada."""
    # Analise local (sem chamada extra de API para manter rapido)
    facts: list[str] = []
    import re

    # Extrai sentencas com dados factuais (datas, numeros, nomes proprios)
    sentences = re.split(r'(?<=[.!?])\s+', content)
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 30 or len(sent) > 300:
            continue
        # Detecta frases com dados concretos
        has_number = bool(re.search(r'\d+', sent))
        has_name = bool(re.search(r'[A-Z][a-z]+ [A-Z][a-z]+', sent))
        if has_number or has_name:
            facts.append(sent)

    # Refina a query: adiciona termos mais especificos encontrados
    refined = current_query
    words = re.findall(r'[A-Za-zÀ-ÿ]+', content.lower())
    from collections import Counter
    common = [w for w, c in Counter(words).most_common(15) if c >= 2 and len(w) > 3]
    # Filtra stopwords
    stopwords = {"para", "como", "mais", "tambem", "foram", "pelo", "sobre", "outros", "entre", "cada", "anos", "parte", "ser", "foi", "ainda", "muito", "essa", "esse"}
    keywords = [w for w in common if w not in stopwords]
    if keywords:
        refined = f"{current_query} {' '.join(keywords[:5])}"

    return {
        "facts_extracted": len(facts),
        "sample_facts": facts[:5],
        "refined_query": refined,
        "content_length": len(content),
        "iteration": iteration,
    }


async def execute_deep_research(
    task_id: str,
    initial_query: str,
    bus: EventBus,
    depth: int = 3,
) -> dict[str, Any]:
    """Executa pesquisa iterativa com profundidade configurada.

    Cada iteracao: pesquisa google -> abre top resultado -> extrai conteudo ->
    analisa e refina query -> proxima iteracao.
    Ao final, produz relatorio estruturado.

    Retorna dicionario com:
      - executive_summary: str
      - sources: list[dict]
      - findings: list[dict]
      - conclusions: str
      - queries_used: list[str]
    """
    complexity = query_complexity(initial_query)
    # Ajusta profundidade baseado na complexidade
    if complexity == "SIMPLE":
        depth = min(depth, 2)
    elif complexity == "COMPLEX":
        depth = max(depth, 3)

    await publish_agent_activity(
        bus,
        task_id,
        kind="search",
        title="Iniciando pesquisa profunda",
        detail=f"Pesquisa iterativa com {depth} rodadas",
        status="running",
        metadata={"depth": depth, "initial_query": initial_query},
    )

    browser = await browser_pool.acquire(task_id)
    try:
        current_query = initial_query
        all_sources: list[dict[str, Any]] = []
        all_findings: list[dict[str, Any]] = []
        queries_used: list[str] = []
        visited_urls: set[str] = set()

        for iteration in range(1, depth + 1):
            await bus.publish(
                task_id,
                "agent_progress",
                {
                    "label": f"Pesquisa profunda {iteration}/{depth}",
                    "detail": f"Buscando: {current_query[:150]}",
                },
            )
            await publish_agent_activity(
                bus,
                task_id,
                kind="search",
                title=f"Rodada {iteration}/{depth}",
                detail=f"Pesquisando: {current_query[:150]}",
                status="running",
                metadata={"iteration": iteration, "depth": depth},
            )

            # Google search
            try:
                search_result = await browser.google_search(current_query, hl="pt-BR")
                results = search_result.get("results") if isinstance(search_result, dict) else []
                if not isinstance(results, list) or not results:
                    await bus.publish(
                        task_id,
                        "agent_progress",
                        {"label": f"Rodada {iteration}/{depth}", "detail": "Sem resultados nesta query. Tentando abordagem diferente."},
                    )
                    # Refina query para tentar de novo
                    current_query = f"{initial_query} {'informacoes' if iteration % 2 else 'dados'} {'completos' if iteration > 2 else 'atualizados'}"
                    continue
            except Exception:
                await bus.publish(
                    task_id,
                    "agent_progress",
                    {"label": f"Rodada {iteration}/{depth}", "detail": "Erro na busca; continuando com fontes ja coletadas."},
                )
                continue

            queries_used.append(current_query)

            # Seleciona top resultados
            selected = _select_top_results(results, max_results=2, already_visited=visited_urls)
            if not selected:
                continue

            for result in selected:
                url = str(result.get("url") or result.get("href") or "")
                title = str(result.get("title") or result.get("snippet") or "")[:200]

                await bus.publish(
                    task_id,
                    "agent_progress",
                    {"label": f"Lendo fonte {iteration}/{depth}", "detail": title[:120]},
                )

                # Navega e extrai
                try:
                    await browser.navigate(url)
                except Exception:
                    continue

                text = await _extract_text_from_page(browser, url)
                if not text:
                    continue

                visited_urls.add(url)

                # Analisa conteudo
                analysis = await _analyze_page_content(text, current_query, iteration)

                # Salva fonte
                source_entry = {
                    "url": url,
                    "title": title,
                    "snippet": text[:300],
                    "extracted_length": len(text),
                    "iteration": iteration,
                }
                all_sources.append(source_entry)

                finding_entry = {
                    "topic": title,
                    "detail": analysis.get("sample_facts", [text[:200]])[0] if analysis.get("sample_facts") else text[:200],
                    "source_urls": [url],
                    "iteration": iteration,
                    "facts_count": analysis.get("facts_extracted", 0),
                }
                all_findings.append(finding_entry)

                # Refina query para proxima iteracao
                refined = analysis.get("refined_query", current_query)
                if refined != current_query:
                    current_query = refined

                # Atualiza fontes no BD (reusa logica de salvar fonte)
                try:
                    from database import database as db
                    from services.stream_contract import utc_now
                    from services.source_quality import source_quality_score, source_type_for_url
                    db.upsert_source(
                        task_id,
                        {
                            "url": url,
                            "title": title,
                            "snippet": text[:300],
                            "extracted_text": text[:2000],
                            "source_type": source_type_for_url(url),
                            "quality_score": source_quality_score(url, title, text[:300]),
                            "used": True,
                            "created_at": utc_now(),
                        },
                    )
                except Exception:
                    pass

            await publish_agent_activity(
                bus,
                task_id,
                kind="source",
                title=f"Rodada {iteration}/{depth} concluida",
                detail=f"{len(selected)} fontes lidas nesta rodada. Total: {len(all_sources)} fontes.",
                status="done",
                metadata={"iteration": iteration, "sources_this_round": len(selected), "total_sources": len(all_sources)},
            )

        # Gerar relatorio estruturado
        executive_summary = _generate_executive_summary(initial_query, all_sources, all_findings, depth)
        conclusions = _generate_conclusions(all_findings, all_sources)

        report = {
            "executive_summary": executive_summary,
            "sources": all_sources,
            "findings": all_findings,
            "conclusions": conclusions,
            "queries_used": queries_used,
            "total_sources": len(all_sources),
            "depth": depth,
        }

        await publish_agent_activity(
            bus,
            task_id,
            kind="search",
            title="Pesquisa profunda concluida",
            detail=f"{len(all_sources)} fontes analisadas em {depth} rodadas.",
            status="done",
            metadata={"total_sources": len(all_sources), "depth": depth},
        )

        return report

    finally:
        await browser_pool.release(task_id)


def _generate_executive_summary(
    query: str,
    sources: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    depth: int,
) -> str:
    """Gera um resumo executivo a partir dos achados."""
    if not findings:
        return f"Pesquisa profunda sobre '{query}' com {depth} rodadas nao encontrou fontes relevantes."

    num_sources = len(sources)
    num_findings = len(findings)

    topics = list({f.get("topic", "") for f in findings if f.get("topic")})
    topic_list = "; ".join(topics[:5])

    return (
        f"Pesquisa profunda sobre '{query}' realizada em {depth} rodadas. "
        f"Foram analisadas {num_sources} fontes, resultando em {num_findings} achados. "
        f"Principais topicos: {topic_list}."
    )


def _generate_conclusions(
    findings: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> str:
    """Sintetiza conclusoes a partir dos achados."""
    if not findings:
        return "Nao foi possivel gerar conclusoes por falta de fontes."

    lines: list[str] = []
    for i, f in enumerate(findings[:8]):
        topic = f.get("topic", f"Topico {i+1}")
        detail = f.get("detail", "")[:200]
        urls = f.get("source_urls", [])
        url_str = urls[0] if urls else ""
        lines.append(f"- **{topic}**: {detail} {'[fonte](' + url_str + ')' if url_str else ''}")

    unique_hosts = len({s.get("url", "").split("/")[2] for s in sources if s.get("url")})
    lines.append(f"\nTotal: {len(sources)} fontes de {unique_hosts} dominios diferentes.")

    return "\n".join(lines)


def format_deep_research_for_agent(report: dict[str, Any]) -> str:
    """Formata o relatorio de pesquisa profunda para injecao no historico do agente."""
    parts = [
        "RELATORIO DE PESQUISA PROFUNDA:",
        "",
        f"Resumo: {report.get('executive_summary', '')}",
        "",
        "Fontes consultadas:",
    ]
    for src in report.get("sources", []):
        parts.append(f"- {src.get('title', 'Sem titulo')}: {src.get('url', '')}")
    parts.append("")
    parts.append("Conclusoes:")
    parts.append(report.get("conclusions", ""))
    parts.append("")
    parts.append(f"Queries usadas: {', '.join(report.get('queries_used', []))}")
    parts.append(f"Profundidade: {report.get('depth', 0)} rodadas | {report.get('total_sources', 0)} fontes lidas")
    return "\n".join(parts)
