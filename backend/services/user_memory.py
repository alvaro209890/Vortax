"""Servico de memorias do usuario entre conversas no Vortax.

Permite persistir preferencias, fatos, contexto e feedback do usuario no SQLite
e injeta-los no system prompt do DeepSeek para personalizacao cross-session.
"""

from __future__ import annotations

from typing import Any

from database import database


MEMORY_TYPES = ("preference", "fact", "context", "feedback")

PREFERENCE_PATTERNS = [
    "eu prefiro",
    "eu gosto de",
    "eu gosto quando",
    "sempre uso",
    "sempre prefiro",
    "me chamo",
    "meu nome",
    "sou ",
    "trabalho como",
    "trabalho com",
    "minha profissao",
    "minha area",
    "eu uso",
    "nao gosto de",
    "nao gosto quando",
    "detesto",
    "odeio",
]


def add_memory(
    user_id: str,
    memory_type: str,
    key: str,
    content: str,
    priority: int = 5,
) -> int:
    """Adiciona uma memoria para o usuario. Retorna o ID da memoria."""
    if memory_type not in MEMORY_TYPES:
        raise ValueError(f"Tipo invalido: {memory_type}. Use: {', '.join(MEMORY_TYPES)}")
    return database.add_user_memory(user_id, memory_type, key[:200], content, priority)


def update_memory(memory_id: int, user_id: str, content: str, priority: int | None = None) -> bool:
    """Atualiza o conteudo e opcionalmente a prioridade de uma memoria."""
    return database.update_user_memory(memory_id, user_id, content, priority)


def delete_memory(memory_id: int, user_id: str) -> bool:
    """Remove uma memoria."""
    return database.delete_user_memory(memory_id, user_id)


def list_memories(user_id: str, memory_type: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Lista memorias do usuario, opcionalmente filtradas por tipo."""
    return database.list_user_memories(user_id, memory_type, limit=limit)


def search_memories(user_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Busca memorias por relevancia com os termos da query."""
    terms = query.lower().split()
    return database.search_user_memories(user_id, terms, limit=limit)


def format_for_system_prompt(user_id: str, max_tokens: int = 600) -> str:
    """Formata memorias do usuario para injecao no system prompt.

    Retorna string vazia se nao houver memorias relevantes.
    A saida e limitada a ~max_tokens tokens estimados (4 chars/token).
    """
    memories = database.list_user_memories(user_id, limit=20)
    if not memories:
        return ""

    # Ordena: preference > fact > feedback > context, depois por priority desc
    type_order = {"preference": 0, "fact": 1, "feedback": 2, "context": 3}
    memories.sort(key=lambda m: (type_order.get(m.get("memory_type", "context"), 3), -m.get("priority", 0)))

    max_chars = max_tokens * 4
    lines: list[str] = []
    chars_used = 0

    header = "MEMORIAS DO USUARIO (preferencias e contexto salvos de conversas anteriores):"
    lines.append(header)
    chars_used += len(header)

    for mem in memories:
        mtype = mem.get("memory_type", "context")
        key = str(mem.get("key") or "")
        content = str(mem.get("content") or "")
        line = f"- [{mtype}] {key}: {content}"
        if chars_used + len(line) > max_chars:
            break
        lines.append(line)
        chars_used += len(line)

    if len(lines) <= 1:
        return ""

    lines.append(
        "Considere essas informacoes ao decidir acoes e ao formular respostas. "
        "Elas tem precedencia sobre comportamentos default do agente."
    )
    return "\n".join(lines)


def auto_save_from_message(user_id: str, content: str) -> bool:
    """Detecta automaticamente preferencias em mensagens do usuario e salva como memorias.

    Retorna True se alguma memoria foi salva.
    """
    text = content.strip().lower()
    saved = False

    for pattern in PREFERENCE_PATTERNS:
        idx = text.find(pattern)
        if idx < 0:
            continue
        # Extrai o resto da frase apos o padrao
        snippet = content[idx:].strip()
        if len(snippet) < 5:
            continue
        # Limita a 200 caracteres para a chave
        key = snippet[:80].replace("\n", " ").strip()
        if len(snippet) > 200:
            snippet = snippet[:200].rsplit(".", 1)[0].strip() + "."

        # Determina o tipo baseado no padrao
        if any(p in pattern for p in ["sou ", "trabalho", "profissao", "area", "me chamo", "meu nome"]):
            mtype = "fact"
        elif any(p in pattern for p in ["prefiro", "gosto", "uso", "detesto", "odeio"]):
            mtype = "preference"
        else:
            mtype = "context"

        try:
            database.add_user_memory(user_id, mtype, key, snippet, priority=6)
            saved = True
        except Exception:
            continue

    return saved


def handle_remember_command(user_id: str, content: str) -> str | None:
    """Processa o comando /remember. Retorna mensagem de confirmacao ou None se nao for comando.

    Formatos suportados:
    - /remember [tipo:preference|fact|context|feedback] chave: valor
    - /remember chave: valor  (tipo default: context)
    - /remember esqueca <id>  (deletar)
    - /remember listar  (listar memorias)
    """
    text = content.strip()
    if not text.startswith("/remember"):
        return None

    command = text[len("/remember"):].strip()

    # Listar memorias
    if command.lower() in {"listar", "list", "ver", "show"}:
        memories = list_memories(user_id, limit=20)
        if not memories:
            return "Voce ainda nao tem memorias salvas. Use `/remember chave: valor` para salvar."
        lines = ["**Memorias salvas:**"]
        for mem in memories:
            mtype = mem.get("memory_type", "context")
            mid = mem.get("id")
            key = mem.get("key", "")
            lines.append(f"- `[{mtype}]` {key} (id: {mid})")
        return "\n".join(lines)

    # Esquecer/deletar memoria
    if command.lower().startswith(("esqueca ", "esquecer ", "deletar ", "remover ", "delete ", "remove ")):
        parts = command.split(None, 1)
        if len(parts) < 2:
            return "Uso: `/remember esqueca <id>` — use `/remember listar` para ver os IDs."
        try:
            memory_id = int(parts[1].strip())
        except ValueError:
            return f"ID invalido: '{parts[1]}'. Use um numero inteiro (ex: `/remember esqueca 3`)."
        deleted = delete_memory(memory_id, user_id)
        return (
            f"Memoria {memory_id} removida."
            if deleted
            else f"Memoria {memory_id} nao encontrada ou nao pertence a voce."
        )

    # Salvar: detectar tipo opcional
    mtype = "context"
    remaining = command
    if command.startswith("[") and "]" in command:
        bracket_end = command.index("]")
        type_candidate = command[1:bracket_end].strip().lower()
        if type_candidate in MEMORY_TYPES:
            mtype = type_candidate
            remaining = command[bracket_end + 1:].strip()

    # Parse chave: valor
    if ":" not in remaining:
        return (
            "Uso: `/remember [tipo:] chave: valor`\n"
            "Tipos: preference, fact, context, feedback\n"
            "Exemplos:\n"
            "  `/remember prefiro respostas em portugues brasileiro`\n"
            "  `/remember [fact] profissao: desenvolvedor fullstack`\n"
            "  `/remember listar`\n"
            "  `/remember esqueca 1`"
        )

    parts = remaining.split(":", 1)
    key = parts[0].strip()[:200]
    value = parts[1].strip()

    if not key or not value:
        return "Forneca chave e valor. Ex: `/remember profissao: desenvolvedor`"

    memory_id = add_memory(user_id, mtype, key, value)
    return f"Memoria salva: `[{mtype}]` {key} (id: {memory_id})"
