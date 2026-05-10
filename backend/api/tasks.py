import asyncio
import base64
import contextlib
import io
import re
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, SecretStr

from auth import AuthUser, ensure_task_owner, require_auth
from config import settings
from database import database
from services.activity_events import publish_agent_activity
from services.agent_runner import run_agent_task
from services.context_manager import get_context_payload, prepare_context_history
from services.credential_store import CredentialStoreError, credential_store, normalize_origin
from services.deepseek_client import (
    DeepSeekError,
    deepseek_configured,
    request_direct_chat_response,
    request_task_plan,
    task_planner_configured,
)
from services.exact_solver import format_exact_answer, is_exact_prompt, should_answer_directly, solve_exact_problem
from services.file_ingestion import (
    FileIngestionError,
    build_file_agent_prompt,
    public_uploaded_file_payloads,
    save_and_analyze_uploads,
)
from services.registry import event_bus, runner_tasks, task_plan_store, task_store
from services.stream_contract import utc_now
from services.task_plan_store import direct_response_steps
from api.files import list_task_workspace_files, list_task_workspace_projects
from tools.vision import VisionError, vision_tool

router = APIRouter()


class TaskCreate(BaseModel):
    description: str = Field(min_length=1, max_length=4000)
    client_message_id: str | None = Field(default=None, max_length=120)


class TaskMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    client_message_id: str | None = Field(default=None, max_length=120)


class AuthorizedTaskCreate(BaseModel):
    description: str = Field(min_length=1, max_length=4000)
    url: str = Field(min_length=1, max_length=2000)
    username: SecretStr = Field(min_length=1, max_length=500)
    password: SecretStr = Field(min_length=1, max_length=2000)
    allowed_origins: list[str] = Field(default_factory=list, max_length=8)
    username_selector: str | None = Field(default=None, max_length=300)
    password_selector: str | None = Field(default=None, max_length=300)
    submit_selector: str | None = Field(default=None, max_length=300)


class TaskAuthorizationCreate(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    username: SecretStr = Field(min_length=1, max_length=500)
    password: SecretStr = Field(min_length=1, max_length=2000)
    allowed_origins: list[str] = Field(default_factory=list, max_length=8)
    username_selector: str | None = Field(default=None, max_length=300)
    password_selector: str | None = Field(default=None, max_length=300)
    submit_selector: str | None = Field(default=None, max_length=300)


class TaskPlanRequest(BaseModel):
    description: str = Field(min_length=1, max_length=4000)


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
IMAGE_TYPE_BY_EXTENSION = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
MAX_IMAGE_BYTES = 6 * 1024 * 1024
INLINE_CREDENTIAL_RE = re.compile(
    r"\b(password|passwd|pwd|senha|token|secret|otp|mfa|2fa)\s*[:=]",
    re.IGNORECASE,
)


def _reject_inline_credentials(text: str) -> None:
    if INLINE_CREDENTIAL_RE.search(str(text or "")):
        raise HTTPException(
            status_code=400,
            detail="Use o fluxo seguro de login para enviar credenciais; nao envie senhas no chat.",
        )


def _message_payload(content: str, client_message_id: str | None = None) -> dict:
    payload = {"content": content}
    value = str(client_message_id or "").strip()
    if value:
        payload["client_message_id"] = value[:120]
    return payload


async def _publish_preparing_environment(task_id: str, description: str) -> None:
    await event_bus.publish(task_id, "agent_status", {"status": "queued", "label": "Preparando"})
    if should_answer_directly(description):
        return
    await event_bus.publish(
        task_id,
        "agent_progress",
        {
            "label": "Iniciando ambiente",
            "detail": "Criando plano de tarefas",
            "tool": "planning",
        },
    )
    await publish_agent_activity(
        event_bus,
        task_id,
        kind="analysis",
        title="Iniciando ambiente",
        detail="Criando plano de tarefas",
        status="running",
        tool="planning",
    )


def _safe_authorized_description(description: str, origin: str) -> str:
    return f"Automacao autorizada para {origin}. Credenciais enviadas por fluxo seguro. Pedido: {description.strip()}"


def _store_authorization(task_id: str, user_id: str, payload: AuthorizedTaskCreate | TaskAuthorizationCreate) -> dict:
    try:
        return credential_store.create_authorization(
            task_id=task_id,
            user_id=user_id,
            login_url=payload.url,
            username=payload.username.get_secret_value(),
            password=payload.password.get_secret_value(),
            allowed_origins=payload.allowed_origins,
            username_selector=payload.username_selector,
            password_selector=payload.password_selector,
            submit_selector=payload.submit_selector,
        )
    except CredentialStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

async def _create_live_plan(task_id: str, description: str, *, replan: bool = False) -> list[dict]:
    if should_answer_directly(description):
        steps = task_plan_store.replace_plan(task_id, direct_response_steps(description), description)
        event_type = "task_plan_replanned" if replan else "task_plan_created"
        await event_bus.publish(task_id, event_type, {"steps": steps, "direct": True, "fallback": True})
        return steps

    raw_steps: list[dict] = []
    plan_error = ""
    plan_result: dict = {}
    if task_planner_configured():
        try:
            plan_result = await request_task_plan(description)
            raw_steps = plan_result.get("plan", [])
        except DeepSeekError as exc:
            plan_error = str(exc)

    steps = task_plan_store.replace_plan(task_id, raw_steps, description)
    event_type = "task_plan_replanned" if replan else "task_plan_created"
    payload = {"steps": steps, "fallback": not bool(raw_steps)}
    if plan_result.get("planner_provider"):
        payload["planner"] = {
            "provider": plan_result.get("planner_provider"),
            "model": plan_result.get("planner_model"),
        }
    if plan_result.get("planner_warning"):
        payload["warning"] = plan_result["planner_warning"]
    if plan_error:
        payload["warning"] = plan_error
    await event_bus.publish(task_id, event_type, payload)
    return steps


async def _start_live_step(task_id: str, hint: str) -> None:
    before = task_plan_store.find_for_hint(task_id, hint)
    if before and before.get("status") == "running":
        return
    step = task_plan_store.start_step(task_id, hint=hint)
    if step:
        await event_bus.publish(task_id, "task_step_started", {"step": step})


async def _complete_live_step(task_id: str, hint: str, summary: str, *, status: str = "passed") -> None:
    step = task_plan_store.complete_step(
        task_id,
        hint=hint,
        status=status,
        evidence={"status": status, "summary": summary[:360]},
    )
    if step:
        event_type = "task_step_failed" if status == "failed" else "task_step_completed"
        await event_bus.publish(task_id, event_type, {"step": step})


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
    if not content_type or content_type == "application/octet-stream":
        content_type = IMAGE_TYPE_BY_EXTENSION.get(Path(file.filename or "").suffix.lower(), content_type)
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
    await _start_live_step(task_id, "understand")
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
    await _complete_live_step(task_id, "understand", "Imagem e pergunta registradas na conversa.")

    analyses = []
    saved_images = []
    await _start_live_step(task_id, "execute")
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
    await _complete_live_step(task_id, "execute", f"{len(analyses)} imagem(ns) analisada(s).")

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
    await _start_live_step(task_id, "deliver")
    await event_bus.publish(task_id, "assistant_message_done", {"content": answer})
    await _complete_live_step(task_id, "deliver", "Resposta final da analise de imagem entregue.")
    _, context_payload, compacted = await prepare_context_history(task_id, event_bus.history(task_id), question)
    if compacted:
        await event_bus.publish(task_id, "context_compacted", context_payload)
    await event_bus.publish(task_id, "context_status", context_payload)
    await event_bus.publish(task_id, "agent_status", {"status": "done", "label": "Entrega pronta"})
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


def _is_image_upload(file: UploadFile) -> bool:
    content_type = (file.content_type or "").lower()
    suffix = Path(file.filename or "").suffix.lower()
    return content_type in ALLOWED_IMAGE_TYPES or suffix in IMAGE_TYPE_BY_EXTENSION


def _split_attachment_uploads(files: list[UploadFile]) -> tuple[list[UploadFile], list[UploadFile]]:
    if not files:
        raise FileIngestionError("Nenhum arquivo enviado.")
    if len(files) > 8:
        raise FileIngestionError("Envie no maximo 8 arquivos por vez.")
    document_uploads: list[UploadFile] = []
    image_uploads: list[UploadFile] = []
    for file in files:
        if _is_image_upload(file):
            image_uploads.append(file)
        else:
            document_uploads.append(file)
    return document_uploads, image_uploads


def _build_attachment_agent_prompt(question: str, file_analyses: list[dict], image_analyses: list[dict]) -> str:
    prompt = build_file_agent_prompt(question, file_analyses) if file_analyses else question.strip()
    if image_analyses:
        image_context = _analysis_text(image_analyses)
        image_block = [
            "IMAGENS_ENVIADAS_PELO_USUARIO_VORTAX:",
            image_context or "Imagens recebidas; use a analise visual como contexto.",
            "",
            "INSTRUCOES_DE_IMAGEM_VORTAX:",
            "- Use as imagens enviadas como fonte visual para responder junto com os arquivos anexados.",
            "- Quando houver divergencia entre arquivo e imagem, destaque a incerteza em vez de assumir.",
        ]
        prompt = "\n\n".join(part for part in (prompt, "\n".join(image_block).strip()) if part)
    return prompt or "Analise os anexos enviados pelo usuario."


async def _save_and_analyze_images_for_agent(task_id: str, question: str, raw_images: list[dict], user_event_id: str | None) -> dict:
    saved_images = []
    analyses = []
    if not raw_images:
        return {"images": saved_images, "analysis": analyses}

    await event_bus.publish(
        task_id,
        "agent_status",
        {"status": "thinking", "label": "Analisando anexos"},
    )
    for index, image in enumerate(raw_images, start=1):
        saved = database.insert_chat_image(
            {
                "task_id": task_id,
                "event_id": user_event_id,
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
            {"label": "Analisando imagem anexada", "detail": image["filename"], "step": index},
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
    return {"images": saved_images, "analysis": analyses}


def _normalize_file_question(question: str | None) -> str:
    value = (question or "").strip()
    return value or "Analise estes arquivos."


async def _publish_and_register_files(
    task_id: str,
    question: str,
    files: list[UploadFile],
    client_message_id: str | None = None,
) -> dict:
    await _start_live_step(task_id, "understand")
    document_uploads, image_uploads = _split_attachment_uploads(files)
    analyses = await save_and_analyze_uploads(task_id, document_uploads) if document_uploads else []
    uploaded_files = public_uploaded_file_payloads(analyses)
    raw_images = [await _read_image_upload(file) for file in image_uploads]
    chat_images = [
        {
            "filename": image["filename"],
            "content_type": image["content_type"],
            "image_base64": image["image_base64"],
            "size": image["size"],
        }
        for image in raw_images
    ]
    user_event = await event_bus.publish(
        task_id,
        "user_message",
        {
            **_message_payload(question, client_message_id),
            "files": uploaded_files,
            "images": chat_images,
        },
    )
    if uploaded_files:
        await event_bus.publish(task_id, "files_uploaded", {"files": uploaded_files})
        await publish_agent_activity(
            event_bus,
            task_id,
            kind="file",
            title="Arquivos recebidos",
            detail=f"{len(uploaded_files)} arquivo(s) prontos para analise.",
            status="done",
            metadata={"file_count": len(uploaded_files)},
        )
    analysis_payload = [
        {
            "path": item.get("path"),
            "name": item.get("name"),
            "extension": item.get("extension"),
            "kind": item.get("kind"),
            "summary": item.get("summary"),
            "archive_contents": item.get("archive_contents", []),
            "geospatial_layers": item.get("geospatial_layers", []),
        }
        for item in analyses
    ]
    if analysis_payload:
        await event_bus.publish(task_id, "file_analysis_done", {"files": analysis_payload})
    image_result = await _save_and_analyze_images_for_agent(
        task_id,
        question,
        raw_images,
        user_event.get("event_id"),
    )
    _, context_payload, compacted = await prepare_context_history(task_id, event_bus.history(task_id), question)
    if compacted:
        await event_bus.publish(task_id, "context_compacted", context_payload)
    await event_bus.publish(task_id, "context_status", context_payload)
    summary_parts = []
    if uploaded_files:
        summary_parts.append(f"{len(uploaded_files)} arquivo(s)")
    if image_result["images"]:
        summary_parts.append(f"{len(image_result['images'])} imagem(ns)")
    await _complete_live_step(
        task_id,
        "understand",
        f"{' e '.join(summary_parts) or 'Anexos'} registrados para analise.",
    )
    return {
        "files": uploaded_files,
        "images": image_result["images"],
        "analysis": analysis_payload,
        "image_analysis": image_result["analysis"],
        "agent_prompt": _build_attachment_agent_prompt(question, analyses, image_result["analysis"]),
    }


@router.post("/")
async def create_task(payload: TaskCreate, current_user: AuthUser = Depends(require_auth)) -> dict:
    _reject_inline_credentials(payload.description)
    task = task_store.create(payload.description, current_user.uid)
    await event_bus.publish(task["id"], "task_created", {"task": task})
    await event_bus.publish(task["id"], "user_message", _message_payload(task["description"], payload.client_message_id))
    await _publish_preparing_environment(task["id"], task["description"])
    runner_tasks[task["id"]] = asyncio.create_task(
        run_agent_task(task["id"], task["description"], task_store, event_bus)
    )
    return {"task_id": task["id"], "task": task, "plan": {"steps": []}}


@router.post("/authorized")
async def create_authorized_task(payload: AuthorizedTaskCreate, current_user: AuthUser = Depends(require_auth)) -> dict:
    origin = normalize_origin(payload.url)
    safe_description = _safe_authorized_description(payload.description, origin)
    task = task_store.create(safe_description, current_user.uid)
    auth_metadata = _store_authorization(task["id"], current_user.uid, payload)
    await event_bus.publish(task["id"], "task_created", {"task": task})
    await event_bus.publish(
        task["id"],
        "agent_progress",
        {
            "label": "Login seguro autorizado",
            "detail": f"Credenciais recebidas por fluxo seguro para {origin}.",
            "origin": origin,
        },
    )
    steps = await _create_live_plan(task["id"], task["description"])
    await event_bus.publish(task["id"], "user_message", _message_payload(safe_description))
    runner_tasks[task["id"]] = asyncio.create_task(
        run_agent_task(task["id"], task["description"], task_store, event_bus)
    )
    return {"task_id": task["id"], "task": task, "authorization": auth_metadata, "plan": {"steps": steps}}


@router.post("/{task_id}/authorization")
async def authorize_task(
    task_id: str,
    payload: TaskAuthorizationCreate,
    current_user: AuthUser = Depends(require_auth),
) -> dict:
    ensure_task_owner(task_store.get(task_id), current_user)
    origin = normalize_origin(payload.url)
    auth_metadata = _store_authorization(task_id, current_user.uid, payload)
    await event_bus.publish(
        task_id,
        "agent_progress",
        {
            "label": "Login seguro autorizado",
            "detail": f"Credenciais recebidas por fluxo seguro para {origin}.",
            "origin": origin,
        },
    )
    return {"ok": True, "authorization": auth_metadata}


@router.post("/plan")
async def create_task_plan(
    payload: TaskPlanRequest,
    current_user: AuthUser = Depends(require_auth),
) -> dict:
    _ = current_user
    try:
        result = await request_task_plan(payload.description)
    except DeepSeekError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return result


@router.post("/{task_id}/messages")
async def create_task_message(
    task_id: str,
    payload: TaskMessageCreate,
    current_user: AuthUser = Depends(require_auth),
) -> dict:
    ensure_task_owner(task_store.get(task_id), current_user)

    runner = runner_tasks.get(task_id)
    if runner and not runner.done():
        raise HTTPException(status_code=409, detail="A tarefa ainda esta em execucao")

    content = payload.content.strip()
    _reject_inline_credentials(content)
    await event_bus.publish(task_id, "user_message", _message_payload(content, payload.client_message_id))
    await _publish_preparing_environment(task_id, content)
    await _create_live_plan(task_id, content, replan=True)
    task_store.update_status(task_id, "queued")
    runner_tasks[task_id] = asyncio.create_task(run_agent_task(task_id, content, task_store, event_bus))
    return {"ok": True, "task_id": task_id}


@router.post("/files")
async def create_file_task(
    question: str = Form(""),
    client_message_id: str = Form(""),
    files: list[UploadFile] = File(...),
    current_user: AuthUser = Depends(require_auth),
) -> dict:
    normalized_question = _normalize_file_question(question)
    _reject_inline_credentials(normalized_question)
    task = task_store.create(normalized_question, current_user.uid)
    await event_bus.publish(task["id"], "task_created", {"task": task})
    try:
        upload_result = await _publish_and_register_files(task["id"], normalized_question, files, client_message_id)
    except FileIngestionError as exc:
        task_store.update_status(task["id"], "error", result=str(exc))
        await _complete_live_step(task["id"], "understand", str(exc), status="failed")
        await event_bus.publish(task["id"], "error", {"message": str(exc)})
        await event_bus.publish(task["id"], "agent_status", {"status": "error", "label": "Erro no arquivo"})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (VisionError, DeepSeekError) as exc:
        task_store.update_status(task["id"], "error", result=str(exc))
        await _complete_live_step(task["id"], "understand", str(exc), status="failed")
        await event_bus.publish(task["id"], "error", {"message": str(exc)})
        await event_bus.publish(task["id"], "agent_status", {"status": "error", "label": "Erro na visão"})
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await _publish_preparing_environment(task["id"], normalized_question)
    steps = await _create_live_plan(task["id"], normalized_question)
    task_store.update_status(task["id"], "queued")
    runner_tasks[task["id"]] = asyncio.create_task(
        run_agent_task(task["id"], upload_result["agent_prompt"], task_store, event_bus)
    )
    return {
        "ok": True,
        "task_id": task["id"],
        "task": task_store.get(task["id"]) or task,
        "files": upload_result["files"],
        "images": upload_result["images"],
        "analysis": upload_result["analysis"],
        "image_analysis": upload_result["image_analysis"],
        "plan": {"steps": steps},
    }


@router.post("/{task_id}/files")
async def create_task_files(
    task_id: str,
    question: str = Form(""),
    client_message_id: str = Form(""),
    files: list[UploadFile] = File(...),
    current_user: AuthUser = Depends(require_auth),
) -> dict:
    ensure_task_owner(task_store.get(task_id), current_user)

    runner = runner_tasks.get(task_id)
    if runner and not runner.done():
        raise HTTPException(status_code=409, detail="A tarefa ainda esta em execucao")

    normalized_question = _normalize_file_question(question)
    _reject_inline_credentials(normalized_question)
    try:
        upload_result = await _publish_and_register_files(task_id, normalized_question, files, client_message_id)
    except FileIngestionError as exc:
        task_store.update_status(task_id, "error", result=str(exc))
        await _complete_live_step(task_id, "understand", str(exc), status="failed")
        await event_bus.publish(task_id, "error", {"message": str(exc)})
        await event_bus.publish(task_id, "agent_status", {"status": "error", "label": "Erro no arquivo"})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (VisionError, DeepSeekError) as exc:
        task_store.update_status(task_id, "error", result=str(exc))
        await _complete_live_step(task_id, "understand", str(exc), status="failed")
        await event_bus.publish(task_id, "error", {"message": str(exc)})
        await event_bus.publish(task_id, "agent_status", {"status": "error", "label": "Erro na visão"})
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await _publish_preparing_environment(task_id, normalized_question)
    await _create_live_plan(task_id, normalized_question, replan=True)
    task_store.update_status(task_id, "queued")
    runner_tasks[task_id] = asyncio.create_task(
        run_agent_task(task_id, upload_result["agent_prompt"], task_store, event_bus)
    )
    return {
        "ok": True,
        "task_id": task_id,
        "files": upload_result["files"],
        "images": upload_result["images"],
        "analysis": upload_result["analysis"],
        "image_analysis": upload_result["image_analysis"],
    }


@router.post("/images")
async def create_image_task(
    question: str = Form(""),
    files: list[UploadFile] = File(...),
    current_user: AuthUser = Depends(require_auth),
) -> dict:
    normalized_question = _normalize_question(question)
    task = task_store.create(normalized_question, current_user.uid)
    await event_bus.publish(task["id"], "task_created", {"task": task})
    steps = await _create_live_plan(task["id"], normalized_question)
    try:
        result = await _publish_and_analyze_images(task["id"], normalized_question, files)
    except (VisionError, DeepSeekError) as exc:
        task_store.update_status(task["id"], "error", result=str(exc))
        await _complete_live_step(task["id"], "execute", str(exc), status="failed")
        await event_bus.publish(task["id"], "error", {"message": str(exc)})
        await event_bus.publish(task["id"], "agent_status", {"status": "error", "label": "Erro na visão"})
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"task": task_store.get(task["id"]) or task, "plan": {"steps": steps}, **result}


@router.post("/{task_id}/images")
async def create_task_images(
    task_id: str,
    question: str = Form(""),
    files: list[UploadFile] = File(...),
    current_user: AuthUser = Depends(require_auth),
) -> dict:
    ensure_task_owner(task_store.get(task_id), current_user)

    runner = runner_tasks.get(task_id)
    if runner and not runner.done():
        raise HTTPException(status_code=409, detail="A tarefa ainda esta em execucao")

    normalized_question = _normalize_question(question)
    task_store.update_status(task_id, "running")
    try:
        return await _publish_and_analyze_images(task_id, normalized_question, files)
    except (VisionError, DeepSeekError) as exc:
        task_store.update_status(task_id, "error", result=str(exc))
        await _complete_live_step(task_id, "execute", str(exc), status="failed")
        await event_bus.publish(task_id, "error", {"message": str(exc)})
        await event_bus.publish(task_id, "agent_status", {"status": "error", "label": "Erro na visão"})
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/")
async def list_tasks(current_user: AuthUser = Depends(require_auth)) -> dict:
    return {"tasks": task_store.list(current_user.uid)}


@router.get("/{task_id}")
async def get_task(task_id: str, current_user: AuthUser = Depends(require_auth)) -> dict:
    task = ensure_task_owner(task_store.get(task_id), current_user)
    return {
        "task": task,
        "events": event_bus.history(task_id),
        "sources": database.list_sources(task_id),
        "images": database.list_chat_images(task_id),
        "files": list_task_workspace_files(task_id),
        "projects": list_task_workspace_projects(task_id),
        "plan": {"steps": task_plan_store.list_steps(task_id)},
        "context": get_context_payload(task_id, event_bus.history(task_id)),
    }


@router.get("/{task_id}/download")
async def download_task_zip(
    task_id: str,
    current_user: AuthUser = Depends(require_auth),
) -> StreamingResponse:
    """Gera e retorna um ZIP com todos os arquivos criados na conversa."""
    task = ensure_task_owner(task_store.get(task_id), current_user)

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
async def delete_task(task_id: str, current_user: AuthUser = Depends(require_auth)) -> dict:
    ensure_task_owner(task_store.get(task_id), current_user)

    task_store.stop(task_id)

    runner = runner_tasks.pop(task_id, None)
    if runner and not runner.done():
        runner.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await runner

    # Fecha runtimes temporarios do projeto, inclusive possiveis processos orfaos.
    from tools.shell import stop_dev_server

    await stop_dev_server(task_id)
    from tools.browser_pool import browser_pool

    await browser_pool.release(task_id)
    credential_store.revoke_task(task_id)

    await event_bus.close_task_connections(task_id)
    deleted = task_store.delete(task_id)
    return {"ok": deleted}
