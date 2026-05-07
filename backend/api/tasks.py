import asyncio
import base64
import contextlib
import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import settings
from database import database
from services.agent_runner import run_agent_task
from services.context_manager import get_context_payload, prepare_context_history
from services.deepseek_client import DeepSeekError, deepseek_configured, request_direct_chat_response
from services.exact_solver import format_exact_answer, is_exact_prompt, solve_exact_problem
from services.registry import event_bus, runner_tasks, task_store
from services.stream_contract import utc_now
from api.files import list_task_workspace_files, list_task_workspace_projects
from tools.vision import VisionError, vision_tool

router = APIRouter()


class TaskCreate(BaseModel):
    description: str = Field(min_length=1, max_length=4000)


class TaskMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 6 * 1024 * 1024


def _normalize_question(question: str | None) -> str:
    value = (question or "").strip()
    return value or "Analise esta imagem."


def _vision_question_for_chat(question: str) -> str:
    return (
        f"{question.strip() or 'Analise esta imagem.'}\n\n"
        "Se houver exercicio de matematica, fisica, quimica, estatistica ou outra area de exatas, "
        "transcreva fielmente o enunciado, numeros, formulas, unidades e alternativas em visible_text."
    )


def _analysis_text(analyses: list[dict]) -> str:
    parts: list[str] = []
    for index, analysis in enumerate(analyses, start=1):
        summary = str(analysis.get("summary") or "").strip()
        visible_text = str(analysis.get("visible_text") or "").strip()
        suggested = str(analysis.get("suggested_action") or "").strip()
        parts.append(
            "\n".join(
                item
                for item in (
                    f"Imagem {index}:",
                    f"Resumo: {summary}" if summary else "",
                    f"Texto visivel: {visible_text}" if visible_text else "",
                    f"Observacao: {suggested}" if suggested else "",
                )
                if item
            )
        )
    return "\n\n".join(part for part in parts if part)


async def _read_image_upload(file: UploadFile) -> dict:
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"Tipo de imagem nao suportado: {content_type or 'desconhecido'}")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Imagem vazia")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Imagem maior que 6 MB")
    return {
        "filename": file.filename or "imagem",
        "content_type": content_type,
        "image_base64": base64.b64encode(data).decode("ascii"),
        "size": len(data),
    }


async def _publish_and_analyze_images(task_id: str, question: str, files: list[UploadFile]) -> dict:
    images = [await _read_image_upload(file) for file in files]
    chat_images = [
        {
            "filename": image["filename"],
            "content_type": image["content_type"],
            "image_base64": image["image_base64"],
            "size": image["size"],
        }
        for image in images
    ]
    user_event = await event_bus.publish(
        task_id,
        "user_message",
        {"content": question, "images": chat_images},
    )
    _, context_payload, compacted = await prepare_context_history(task_id, event_bus.history(task_id), question)
    if compacted:
        await event_bus.publish(task_id, "context_compacted", context_payload)
    await event_bus.publish(task_id, "context_status", context_payload)

    analyses = []
    saved_images = []
    await event_bus.publish(
        task_id,
        "agent_status",
        {"status": "thinking", "label": "Analisando imagem"},
    )
    for index, image in enumerate(images, start=1):
        saved = database.insert_chat_image(
            {
                "task_id": task_id,
                "event_id": user_event.get("event_id"),
                "created_at": utc_now(),
                "filename": image["filename"],
                "content_type": image["content_type"],
                "question": question,
                "image_base64": image["image_base64"],
            }
        )
        saved_images.append(saved)
        await event_bus.publish(
            task_id,
            "image_saved",
            {
                "id": saved["id"],
                "filename": saved.get("filename"),
                "content_type": saved["content_type"],
                "question": question,
            },
        )
        await event_bus.publish(
            task_id,
            "agent_progress",
            {"label": "Enviando imagem para Groq", "detail": image["filename"], "step": index},
        )
        analysis = await vision_tool.analyze(
            image["image_base64"],
            question=_vision_question_for_chat(question),
            content_type=image["content_type"],
            task_id=task_id,
        )
        analyses.append(analysis)
        updated_saved = database.update_chat_image_analysis(saved["id"], analysis.get("summary") or "")
        if updated_saved:
            saved_images[-1] = updated_saved

    analysis_context = _analysis_text(analyses)
    if is_exact_prompt(f"{question}\n{analysis_context}"):
        await event_bus.publish(
            task_id,
            "agent_progress",
            {"label": "Resolvendo enunciado da imagem", "detail": "Usando tool de exatas com a transcricao visual.", "tool": "exact_solve"},
        )
        await event_bus.publish(
            task_id,
            "tool_call",
            {
                "name": "exact_solve",
                "description": "Resolver pergunta de exatas extraida de imagem",
                "params": {"problem": question, "context": analysis_context},
            },
        )
        exact_result = solve_exact_problem(question, context=analysis_context)
        await event_bus.publish(task_id, "tool_result", {"name": "exact_solve", "result": exact_result})
        if exact_result.get("status") == "solved":
            answer = format_exact_answer(exact_result)
        elif deepseek_configured():
            direct = await request_direct_chat_response(
                [{"role": "user", "content": f"{question}\n\nAnalise da imagem:\n{analysis_context}"}],
                mode="exact",
                tool_context={"vision_analysis": analyses, "exact_solve": exact_result},
            )
            answer = direct["content"]
        else:
            answer = _format_vision_answer(analyses[0]) if len(analyses) == 1 else "\n\n".join(
                f"Imagem {index}: {_format_vision_answer(analysis)}" for index, analysis in enumerate(analyses, start=1)
            )
    elif len(analyses) == 1:
        answer = _format_vision_answer(analyses[0])
    else:
        answer = "\n\n".join(
            f"Imagem {index}: {_format_vision_answer(analysis)}" for index, analysis in enumerate(analyses, start=1)
        )

    task_store.update_status(task_id, "done", result=answer)
    await event_bus.publish(task_id, "assistant_message_done", {"content": answer})
    _, context_payload, compacted = await prepare_context_history(task_id, event_bus.history(task_id), question)
    if compacted:
        await event_bus.publish(task_id, "context_compacted", context_payload)
    await event_bus.publish(task_id, "context_status", context_payload)
    await event_bus.publish(task_id, "agent_status", {"status": "done", "label": "Concluído"})
    return {"ok": True, "task_id": task_id, "images": saved_images, "analysis": analyses, "answer": answer}


def _format_vision_answer(analysis: dict) -> str:
    parts = []
    summary = str(analysis.get("summary") or "").strip()
    if summary:
        parts.append(summary)
    visible_text = analysis.get("visible_text")
    if visible_text:
        parts.append(f"Texto visivel: {visible_text}")
    suggested_action = str(analysis.get("suggested_action") or "").strip()
    if suggested_action:
        parts.append(f"Acao sugerida: {suggested_action}")
    confidence = analysis.get("confidence")
    if confidence:
        parts.append(f"Confianca: {confidence}")
    return "\n".join(parts) if parts else "Analise concluida."


@router.post("/")
async def create_task(payload: TaskCreate) -> dict:
    task = task_store.create(payload.description)
    await event_bus.publish(task["id"], "task_created", {"task": task})
    await event_bus.publish(task["id"], "user_message", {"content": task["description"]})
    runner_tasks[task["id"]] = asyncio.create_task(
        run_agent_task(task["id"], task["description"], task_store, event_bus)
    )
    return {"task_id": task["id"], "task": task}


@router.post("/{task_id}/messages")
async def create_task_message(task_id: str, payload: TaskMessageCreate) -> dict:
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task nao encontrada")

    runner = runner_tasks.get(task_id)
    if runner and not runner.done():
        raise HTTPException(status_code=409, detail="A tarefa ainda esta em execucao")

    content = payload.content.strip()
    await event_bus.publish(task_id, "user_message", {"content": content})
    task_store.update_status(task_id, "queued")
    runner_tasks[task_id] = asyncio.create_task(run_agent_task(task_id, content, task_store, event_bus))
    return {"ok": True, "task_id": task_id}


@router.post("/images")
async def create_image_task(question: str = Form(""), files: list[UploadFile] = File(...)) -> dict:
    normalized_question = _normalize_question(question)
    task = task_store.create(normalized_question)
    await event_bus.publish(task["id"], "task_created", {"task": task})
    try:
        result = await _publish_and_analyze_images(task["id"], normalized_question, files)
    except (VisionError, DeepSeekError) as exc:
        task_store.update_status(task["id"], "error", result=str(exc))
        await event_bus.publish(task["id"], "error", {"message": str(exc)})
        await event_bus.publish(task["id"], "agent_status", {"status": "error", "label": "Erro na visão"})
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"task": task_store.get(task["id"]) or task, **result}


@router.post("/{task_id}/images")
async def create_task_images(task_id: str, question: str = Form(""), files: list[UploadFile] = File(...)) -> dict:
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task nao encontrada")

    runner = runner_tasks.get(task_id)
    if runner and not runner.done():
        raise HTTPException(status_code=409, detail="A tarefa ainda esta em execucao")

    normalized_question = _normalize_question(question)
    task_store.update_status(task_id, "running")
    try:
        return await _publish_and_analyze_images(task_id, normalized_question, files)
    except (VisionError, DeepSeekError) as exc:
        task_store.update_status(task_id, "error", result=str(exc))
        await event_bus.publish(task_id, "error", {"message": str(exc)})
        await event_bus.publish(task_id, "agent_status", {"status": "error", "label": "Erro na visão"})
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/")
async def list_tasks() -> dict:
    return {"tasks": task_store.list()}


@router.get("/{task_id}")
async def get_task(task_id: str) -> dict:
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task nao encontrada")
    return {
        "task": task,
        "events": event_bus.history(task_id),
        "sources": database.list_sources(task_id),
        "images": database.list_chat_images(task_id),
        "files": list_task_workspace_files(task_id),
        "projects": list_task_workspace_projects(task_id),
        "context": get_context_payload(task_id, event_bus.history(task_id)),
    }


@router.get("/{task_id}/download")
async def download_task_zip(task_id: str) -> StreamingResponse:
    """Gera e retorna um ZIP com todos os arquivos criados na conversa."""
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task nao encontrada")

    project_dir = settings.WORKSPACE_PATH / task_id
    if not project_dir.exists() or not project_dir.is_dir():
        raise HTTPException(status_code=404, detail="Nenhum arquivo encontrado para esta conversa")

    # Coleta todos os arquivos recursivamente
    file_paths: list[Path] = []
    for entry in project_dir.rglob("*"):
        if entry.is_file() and entry.name != ".gitkeep":
            file_paths.append(entry)

    if not file_paths:
        raise HTTPException(status_code=404, detail="Nenhum arquivo encontrado para esta conversa")

    # Gera ZIP em memória
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in file_paths:
            arcname = str(file_path.relative_to(project_dir))
            zf.write(file_path, arcname)

    zip_buffer.seek(0)

    task_id_short = task_id[:8]
    filename = f"vortax-{task_id_short}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{task_id}")
async def delete_task(task_id: str) -> dict:
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task nao encontrada")

    task_store.stop(task_id)

    runner = runner_tasks.pop(task_id, None)
    if runner and not runner.done():
        runner.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await runner

    # Mata dev server se estiver rodando
    from tools.shell import _dev_servers
    dev_server = _dev_servers.pop(task_id, None)
    if dev_server:
        import os as _os
        import signal as _signal
        proc = dev_server["process"]
        try:
            _os.killpg(_os.getpgid(proc.pid), _signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass

    await event_bus.close_task_connections(task_id)
    deleted = task_store.delete(task_id)
    return {"ok": deleted}
