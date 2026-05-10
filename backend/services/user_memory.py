"""
Memória de longo prazo do usuário — extrai fatos úteis das conversas,
armazena no SQLite e injeta no contexto quando relevante.

Inspirado no sistema MEMORY.md do Claw.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from config import settings
from database import database

logger = logging.getLogger(__name__)

# Tipos de fatos que o sistema reconhece
FACT_TYPES = [
    "personal",       # nome, idade, localização, idioma
    "professional",   # trabalho, cargo, empresa, skills
    "project",        # projetos ativos, stack, repositórios
    "preference",     # preferências, gostos, estilo de comunicação
    "context",        # decisões, estado atual, planos
]

# Palavras-chave inúteis — fatos que NÃO devem ser guardados
USELESS_PATTERNS = [
    "obrigado", "valeu", "tchau", "oi", "olá", "bom dia", "boa tarde", "boa noite",
    "tudo bem", "como vai", "até mais", "falou",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def extract_facts_from_conversation(
    user_id: str,
    task_id: str,
    messages: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """
    Analisa a conversa e extrai fatos novos ou atualizados sobre o usuário.
    Retorna lista de fatos extraídos.
    """
    if not messages or not user_id:
        return []

    # Pega fatos existentes para evitar duplicação
    existing = database.get_user_facts(user_id)
    existing_context = ""
    if existing:
        lines = []
        for f in existing:
            lines.append(f"- [{f['fact_type']}] {f['fact_key']}: {f['fact_value']} (confiança: {f['confidence']})")
        existing_context = "Fatos já conhecidos:\n" + "\n".join(lines) + "\n\n"

    # Últimas 10 mensagens (user + assistant)
    recent = messages[-20:] if len(messages) > 20 else messages
    conversation_text = "\n".join(
        f"{'Usuário' if m['role'] == 'user' else 'Vortax'}: {m['content'][:500]}"
        for m in recent
        if m.get("content", "").strip()
    )

    if len(conversation_text) < 50:
        return []

    prompt = """Analise a conversa abaixo e extraia fatos NOVOS ou ATUALIZADOS sobre o USUÁRIO.
"""
    if existing_context:
        prompt += existing_context + "\n"
    prompt += """Apenas fatos ÚTEIS e RELEVANTES. Ignore saudações, agradecimentos, conversa fiada.
Classifique cada fato em um tipo: personal, professional, project, preference, context.

Retorne APENAS um JSON array. Cada item:
- fact_key: identificador curto (ex: "nome", "trabalho", "stack_dev")
- fact_value: valor do fato (ex: "desenvolvedor full stack", "React, Node.js")
- fact_type: tipo do fato
- confidence: 0.0 a 1.0 (quao certo voce esta sobre o fato)

Se nao houver fatos novos, retorne [].

Conversa:
""" + conversation_text

    try:
        from services.deepseek_client import _post_deepseek
        result_text = await _post_deepseek({
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 1000,
            "response_format": {"type": "json_object"},
        })
        result = json.loads(result_text.get("choices", [{}])[0].get("message", {}).get("content", "{}"))
        facts = result.get("facts", result if isinstance(result, list) else [])
        if not isinstance(facts, list):
            return []

        validated = []
        for fact in facts:
            if not isinstance(fact, dict):
                continue
            key = str(fact.get("fact_key", "")).strip().lower().replace(" ", "_")
            value = str(fact.get("fact_value", "")).strip()
            ftype = str(fact.get("fact_type", "general")).strip().lower()
            conf = float(fact.get("confidence", 0.5))

            # Validações
            if not key or not value or len(value) < 2:
                continue
            if key in USELESS_PATTERNS or value.lower() in USELESS_PATTERNS:
                continue
            if ftype not in FACT_TYPES:
                ftype = "general"
            if conf < 0.3:
                continue

            validated.append({
                "user_id": user_id,
                "fact_key": key,
                "fact_value": value,
                "fact_type": ftype,
                "confidence": round(conf, 2),
                "source_task_id": task_id,
            })

        return validated

    except Exception as e:
        logger.warning(f"extract_facts_from_conversation: {e}")
        return []


def save_facts(facts: list[dict[str, Any]]) -> int:
    """Salva ou atualiza fatos no banco. Retorna quantos foram salvos."""
    count = 0
    for fact in facts:
        database.upsert_user_fact(
            user_id=fact["user_id"],
            fact_key=fact["fact_key"],
            fact_value=fact["fact_value"],
            fact_type=fact["fact_type"],
            confidence=fact["confidence"],
            source_task_id=fact.get("source_task_id"),
        )
        count += 1
    if count:
        logger.info(f"user_memory: {count} fatos salvos para user_id={fact['user_id']}")
    return count


def format_memory_context(user_id: str | None) -> str:
    """
    Formata os fatos do usuário para injeção no sistema prompt.
    Retorna string vazia se não houver fatos.
    """
    if not user_id:
        return ""

    facts = database.get_user_facts(user_id)
    if not facts:
        return ""

    by_type: dict[str, list[str]] = {}
    for f in facts:
        t = f.get("fact_type", "general")
        by_type.setdefault(t, []).append(f"- {f['fact_key']}: {f['fact_value']}")

    lines = ["## Memória do Usuário (Vortax)", ""]
    type_labels = {
        "personal": "👤 Pessoal",
        "professional": "💼 Profissional",
        "project": "🚀 Projetos",
        "preference": "🎯 Preferências",
        "context": "📋 Contexto Atual",
        "general": "📌 Geral",
    }

    for ftype, items in by_type.items():
        lines.append(f"### {type_labels.get(ftype, ftype)}")
        lines.extend(items)
        lines.append("")

    return "\n".join(lines)


def recall_facts(user_id: str, query: str, limit: int = 8) -> str:
    """
    Busca fatos relevantes para uma consulta.
    Retorna string formatada para injeção no contexto.
    """
    if not user_id or not query:
        return ""

    facts = database.search_user_facts(user_id, query, limit)
    if not facts:
        return ""

    lines = ["[Memória do usuário relevante para esta consulta:]"]
    for f in facts:
        lines.append(f"- {f['fact_key']}: {f['fact_value']}")
    return "\n".join(lines)
