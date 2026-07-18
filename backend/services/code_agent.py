"""Detecção unificada do agente de código (Vertex / legado openclaude).

Consolida as implementações triplicadas em agent_runner / tool_executor / shell.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from config import settings

CODE_AGENT_COMMAND = str(getattr(settings, "CODE_AGENT_COMMAND", "vertex") or "vertex").strip()
CODE_AGENT_LABEL = str(getattr(settings, "CODE_AGENT_LABEL", "Vertex") or "Vertex").strip()
LEGACY_CODE_AGENT_COMMANDS = frozenset({"openclaude"})


def code_agent_names() -> set[str]:
    names = {Path(CODE_AGENT_COMMAND).name.lower(), CODE_AGENT_COMMAND.lower()}
    names |= {n.lower() for n in LEGACY_CODE_AGENT_COMMANDS}
    return names


def is_code_agent_name(value: str) -> bool:
    name = Path(str(value or "").strip()).name.lower()
    return name in code_agent_names()


def is_code_agent_token(token: str) -> bool:
    raw = str(token or "").strip().lower()
    if not raw:
        return False
    if is_code_agent_name(raw):
        return True
    # `vertex "..."` sem espaço entre comando e aspas
    for name in code_agent_names():
        if raw.startswith(name + '"') or raw.startswith(name + "'"):
            return True
    return False


def is_code_agent_command(command: str) -> bool:
    text = str(command or "").strip()
    if not text:
        return False
    try:
        tokens = shlex.split(text)
    except ValueError:
        tokens = text.split()
    for token in tokens:
        if is_code_agent_token(token):
            return True
        # padrão `cd X && vertex "..."`
        if "&&" in token:
            for part in token.split("&&"):
                if is_code_agent_token(part.strip()):
                    return True
    # fallback textual
    lowered = text.lower()
    for name in code_agent_names():
        if re.search(rf"(^|[\s;&|]){re.escape(name)}([\s\"']|$)", lowered):
            return True
    return False


def normalize_invocation(command: str) -> str:
    """Normaliza openclaude → CODE_AGENT_COMMAND quando for legacy."""
    text = str(command or "")
    for legacy in LEGACY_CODE_AGENT_COMMANDS:
        text = re.sub(
            rf"(^|[\s;&|]){re.escape(legacy)}\b",
            rf"\1{CODE_AGENT_COMMAND}",
            text,
            flags=re.IGNORECASE,
        )
    return text
