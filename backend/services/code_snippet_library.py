import logging
from typing import Any

from database import database

logger = logging.getLogger(__name__)


class CodeSnippetLibrary:
    """Biblioteca persistente de snippets de código reutilizáveis gerados pelo agente de codigo.

    Evita que o agente de código regenere do zero soluções técnicas recorrentes
    (auth JWT, CRUD FastAPI, hooks React, configurações padrão, etc.).
    """

    def search(self, query: str, language: str | None = None, limit: int = 3) -> list[dict[str, Any]]:
        """Busca snippets por keywords em tags e descrição. Retorna top-N por relevância + uso."""
        results = database.search_snippets(query, language=language, limit=limit)
        if results:
            logger.debug("[snippet_library] %d resultado(s) — query=%s", len(results), query[:60])
        return results

    def add(self, tags: list[str], language: str, description: str, content: str) -> int:
        """Adiciona snippet; ignora duplicatas por SHA256 do conteúdo. Retorna ID."""
        snippet_id = database.add_snippet(tags, language, description, content)
        logger.debug("[snippet_library] snippet id=%d lang=%s desc=%s", snippet_id, language, description[:60])
        return snippet_id

    def increment_use(self, snippet_id: int) -> None:
        database.increment_snippet_use(snippet_id)

    def format_for_prompt(self, snippets: list[dict[str, Any]]) -> str:
        """Formata snippets para inclusão no ExecutionPackage como seção Markdown."""
        if not snippets:
            return ""
        parts = ["## Padrões Disponíveis (reutilize quando aplicável)"]
        for s in snippets:
            lang = str(s.get("language") or "")
            desc = str(s.get("description") or "")
            content = str(s.get("content") or "")
            fence = f"```{lang}" if lang else "```"
            parts.append(f"### {desc}\n{fence}\n{content}\n```")
        return "\n\n".join(parts)


snippet_library = CodeSnippetLibrary()
