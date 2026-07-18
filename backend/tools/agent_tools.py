"""Tools de agente no estilo Claude Code / Manus: validate_project, document_render, web_search alias."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config import settings
from services.project_files import sync_task_workspace_files
from tools.files import resolve_task_path


async def validate_project(task_id: str, bus: Any = None) -> dict[str, Any]:
    """Roda validação do workspace (Claude: rodar testes; Manus: verify step)."""
    from services.event_bus import EventBus
    from services.project_validation import validate_project_after_code_agent
    from services.registry import event_bus as default_bus

    project_dir = settings.WORKSPACE_PATH / task_id
    if not project_dir.is_dir():
        return {"success": False, "error": "Workspace da conversa vazio ou inexistente."}
    sync_task_workspace_files(task_id, project_dir)
    bus_obj: EventBus = bus or default_bus
    try:
        result = await validate_project_after_code_agent(
            task_id,
            "validate_project",
            bus_obj,
            agent_result={"success": True},
        )
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}
    if isinstance(result, dict):
        status = str(result.get("status") or "")
        result["success"] = status in {"passed", "ok"} or result.get("success") is True
        return result
    return {"success": True, "result": result}


async def document_render(task_id: str, markdown_path: str, pdf_path: str | None = None) -> dict[str, Any]:
    """Markdown → PDF explícito (Manus deploy-like delivery tool)."""
    from services.document_artifacts import render_markdown_to_pdf

    md = str(markdown_path or "").strip()
    if not md:
        return {"success": False, "error": "markdown_path obrigatorio"}
    try:
        resolve_task_path(task_id, md)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    out = pdf_path or (str(Path(md).with_suffix(".pdf")))
    try:
        result = await render_markdown_to_pdf(task_id, md, out)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}
    if isinstance(result, dict):
        result.setdefault("success", True)
        return result
    return {"success": True, "pdf_path": out, "result": result}
