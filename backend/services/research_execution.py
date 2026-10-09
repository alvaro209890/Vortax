"""Bounded research mode; creation and computer operations keep the full agent."""
import re

RESEARCH_TOOLS = {
    "web_search", "web_fetch", "browser_google_search", "browser_navigate",
    "browser_extract_article", "browser_extract_text", "browser_extract_links",
    "browser_get_state", "browser_screenshot", "browser_scroll",
    "message_notify_user", "message_ask_user", "todo_write",
}


def is_research_task(prompt: str) -> bool:
    text = str(prompt or "").lower()
    if re.search(r"\b(crie|criar|gere|gerar|desenvolva|implemente|edite|instale|publique|envie|arquivo|pdf|docx|script|código|codigo)\b", text):
        return False
    return bool(re.search(r"pesquis|busqu|notícias|noticias|cotação|cotacao|compare|preços atuais|precos atuais", text))


def evidence_fallback(sources: list[dict]) -> str:
    lines = ["A pesquisa atingiu o limite de tempo. Não consegui concluir a síntese; seguem as fontes obtidas:"]
    for source in sources[:6]:
        url = str(source.get("url") or "")
        if not url.startswith(("https://", "http://")):
            continue
        title = str(source.get("title") or url).replace("[", "").replace("]", "")
        lines.append(f"- [{title}]({url})")
    if len(lines) == 1:
        return "A pesquisa atingiu o limite de tempo sem fontes verificadas. Não tenho dados suficientes para confirmar a resposta."
    return "\n\n".join(lines)
