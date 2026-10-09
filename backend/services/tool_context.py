"""Correlação entre uma chamada de ferramenta e os eventos que ela gera.

execute_tool define o call_id da chamada em andamento; o EventBus copia esse id para
os eventos derivados (saída do terminal, capturas, arquivos, validação). Cada tarefa
asyncio herda o contexto de quem a criou, então chamadas paralelas não se misturam.
O campo é opcional: eventos antigos e eventos fora de uma ferramenta não o têm.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

current_call_id: ContextVar[str | None] = ContextVar("vortax_current_call_id", default=None)

# Eventos publicados durante uma ferramenta que pertencem a ela.
DERIVED_EVENT_TYPES = frozenset(
    {
        "shell_stdout",
        "shell_stderr",
        "shell_interactive_prompt",
        "screen_frame",
        "screen_frame_blocked",
        "browser_view",
        "source_saved",
        "files_created",
        "vertex_progress",
        "agent_activity",
        "agent_progress",
        "ai_exchange",
        "web_validation_started",
        "web_validation_step",
        "web_validation_result",
        "project_validation_started",
        "project_validation_step",
        "project_validation_result",
        "dev_server_started",
        "error",
    }
)


def new_call_id() -> str:
    return f"tc_{uuid.uuid4().hex[:12]}"
