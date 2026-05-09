import asyncio
import json
import re
import shlex
from typing import Any
from pathlib import Path

from config import settings
from services.activity_events import publish_agent_activity
from database import database
from services.context_manager import prepare_context_history
from services.credential_store import credential_store
from services.deepseek_client import (
    DeepSeekError,
    deepseek_configured,
    request_deepseek_action,
    request_direct_chat_response,
    request_task_plan,
    task_planner_configured,
)
from services.document_artifacts import (
    artifact_profile as document_artifact_profile,
    document_context_for_code_agent,
    is_document_edit_request,
    resolve_document_target,
    valid_markdown_files,
    valid_pdf_files,
)
from services.document_intent import (
    document_extensions_from_text,
    downloadable_document_files,
    is_markdown_document,
    is_previewable_document,
    markdown_documentation_files,
    report_artifact_profile,
)
from services.event_bus import EventBus
from services.exact_solver import format_exact_answer, is_exact_prompt, should_answer_directly, solve_exact_problem
from services.mock_runner import run_mock_task
from services.research_policy import cross_check_status, document_research_profile, query_complexity, relevant_sources_for_query
from services.ephemeral_cache import ephemeral_cache
from services.code_snippet_library import snippet_library
from services.execution_package import enrich_code_agent_command
from services.source_quality import source_quality_score, source_type_for_url
from services.stream_contract import utc_now
from services.task_store import TaskStore
from services.task_plan_store import direct_response_steps, fallback_steps, task_plan_store
from tools.tool_executor import CODE_AGENT_COMMAND, CODE_AGENT_LABEL, compact_tool_result, execute_tool
from tools.browser_pool import browser_pool
from services.web_validation import web_intent_from_command


LOCAL_PREVIEW_RE = re.compile(
    r"(?:LINK_LOCAL_DO_SITE:\s*)?https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0):\d{2,5}(?:/[^\s\"'<>)]*)?",
    re.IGNORECASE,
)
LOCAL_PREVIEW_LINE_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:LINK_LOCAL_DO_SITE\s*:\s*)?https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0):\d{2,5}.*(?:\n|$)",
    re.IGNORECASE | re.MULTILINE,
)


def _message_history_from_events(events: list[dict[str, Any]], fallback_description: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for event in events:
        event_type = event.get("type")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        content = str(payload.get("content") or "").strip()
        if not content:
            continue
        if event_type == "user_message":
            messages.append({"role": "user", "content": content})
        elif event_type == "assistant_message_done":
            messages.append({"role": "assistant", "content": content})

    if not messages:
        messages.append({"role": "user", "content": fallback_description})

    return messages[-12:]


def _progress_label(action_name: str, description: str) -> str:
    if action_name == "browser_google_search":
        return "Pesquisando na web"
    if action_name == "browser_click_link_by_index":
        return "Abrindo resultado"
    if action_name in {"browser_extract_text", "browser_extract_links"}:
        return "Lendo conteudo da pagina"
    if action_name in {"browser_go_back", "browser_navigate"}:
        return "Navegando"
    if action_name.startswith("browser_"):
        return "Operando o navegador"
    return description or action_name


def _action_plan_hint(action_name: str, params: dict[str, Any] | None = None) -> str:
    if action_name.startswith("browser_"):
        return "research"
    if action_name == "shell_run":
        return "execute"
    if action_name in {"vision_analyze", "exact_solve"}:
        return "execute"
    return "execute"


def _tool_evidence(action_name: str, result: dict[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = {"tool": action_name}
    if result.get("success") is False or result.get("error"):
        evidence["status"] = "failed"
        evidence["summary"] = str(result.get("error") or "Ferramenta retornou erro.")[:360]
        return evidence
    evidence["status"] = "ok"
    if result.get("query") and isinstance(result.get("results"), list):
        evidence["summary"] = f"{len(result['results'])} resultado(s) encontrados para {result['query']}."
    elif result.get("file_summary"):
        summary = result["file_summary"]
        evidence["summary"] = f"{summary.get('file_count', 0)} arquivo(s) gerados; tipo {summary.get('project_type', 'generico')}."
    elif result.get("title") and result.get("url"):
        evidence["summary"] = f"{result['title']} - {result['url']}"
    elif result.get("stdout"):
        evidence["summary"] = str(result.get("stdout"))[:360]
    elif result.get("text"):
        evidence["summary"] = str(result.get("text"))[:360]
    else:
        evidence["summary"] = "Ferramenta executada."
    return evidence


async def _ensure_plan(task_id: str, description: str, bus: EventBus) -> None:
    if should_answer_directly(description):
        if not task_plan_store.list_steps(task_id):
            steps = task_plan_store.replace_plan(task_id, direct_response_steps(description), description)
            await bus.publish(task_id, "task_plan_created", {"steps": steps, "direct": True, "fallback": True})
        return
    if task_plan_store.list_steps(task_id):
        return
    raw_steps: list[dict[str, Any]] = []
    plan_result: dict[str, Any] = {}
    warning = ""
    if task_planner_configured():
        try:
            plan_result = await request_task_plan(description)
            raw_steps = plan_result.get("plan", [])
        except DeepSeekError as exc:
            warning = str(exc)
    steps = task_plan_store.replace_plan(task_id, raw_steps or fallback_steps(description), description)
    payload: dict[str, Any] = {"steps": steps, "fallback": not bool(raw_steps)}
    if plan_result.get("planner_provider"):
        payload["planner"] = {
            "provider": plan_result.get("planner_provider"),
            "model": plan_result.get("planner_model"),
        }
    if plan_result.get("planner_warning"):
        payload["warning"] = plan_result["planner_warning"]
    if warning:
        payload["warning"] = warning
    await bus.publish(task_id, "task_plan_created", payload)


async def _start_plan_step(task_id: str, hint: str, bus: EventBus) -> dict[str, Any] | None:
    before = task_plan_store.find_for_hint(task_id, hint)
    if before and before.get("status") == "running":
        return before
    step = task_plan_store.start_step(task_id, hint=hint)
    if step:
        await bus.publish(task_id, "task_step_started", {"step": step})
    return step


def _activity_for_action(action_name: str, action_params: dict[str, Any] | None = None) -> tuple[str, str, dict[str, Any]]:
    params = action_params or {}
    if action_name == "browser_google_search":
        query = str(params.get("query") or "").strip()
        return "search", "Pesquisando na web", {"query": query}
    if action_name in {"browser_extract_article", "browser_extract_text", "browser_extract_links"}:
        return "source", "Lendo fonte", {}
    if action_name.startswith("browser_"):
        return "browser", "Usando navegador", {}
    if action_name == "shell_run":
        command = str(params.get("command") or "")
        if _is_code_agent_shell_call_from_params(params):
            return "code", f"Delegando ao {CODE_AGENT_LABEL}", {"command": command[:220]}
        return "code", "Executando comando", {"command": command[:220]}
    if action_name == "exact_solve":
        return "analysis", "Resolvendo cálculo", {}
    return "analysis", "Executando etapa", {}


async def _publish_action_activity(
    task_id: str,
    bus: EventBus,
    action_name: str,
    action_params: dict[str, Any] | None,
    detail: str,
    *,
    status: str = "running",
) -> None:
    kind, title, metadata = _activity_for_action(action_name, action_params)
    await publish_agent_activity(
        bus,
        task_id,
        kind=kind,
        title=title,
        detail=detail or action_name,
        status=status,
        tool=action_name,
        metadata=metadata,
    )


async def _complete_plan_step(
    task_id: str,
    hint: str,
    bus: EventBus,
    *,
    status: str = "passed",
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    step = task_plan_store.complete_step(task_id, hint=hint, status=status, evidence=evidence)
    if step:
        event_type = "task_step_failed" if status == "failed" else "task_step_completed"
        await bus.publish(task_id, event_type, {"step": step})
    return step


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _tool_result_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = _event_payload(event)
    result = payload.get("result")
    return result if isinstance(result, dict) else payload


def _result_succeeded(result: dict[str, Any]) -> bool:
    status = str(result.get("status") or "").lower()
    return result.get("success") is not False and not result.get("error") and status not in {"failed", "error", "blocked"}


def _has_successful_tool(events: list[dict[str, Any]], predicate) -> bool:
    for event in events:
        if event.get("type") != "tool_result":
            continue
        payload = _event_payload(event)
        name = str(payload.get("name") or "")
        result = _tool_result_payload(event)
        if predicate(name, result) and _result_succeeded(result):
            return True
    return False


def _latest_research_prompt(events: list[dict[str, Any]], fallback: str) -> str:
    return _latest_user_prompt(_message_history_from_events(events, fallback)) or fallback


def _real_completion_evidence(
    task_id: str,
    step: dict[str, Any],
    events: list[dict[str, Any]],
    description: str,
    final_content: str,
) -> dict[str, Any] | None:
    hint = str(step.get("tool_hint") or "")
    if hint == "understand":
        return {"status": "ok", "summary": "Pedido analisado e contexto preparado."}

    if hint == "research":
        prompt = _latest_research_prompt(events, description)
        research_status = cross_check_status(prompt, database.list_sources(task_id))
        if research_status.get("satisfied"):
            count = int(research_status.get("source_count") or 0)
            return {"status": "ok", "summary": f"Checagem de pesquisa satisfeita com {count} fonte(s) relevante(s)."}
        if _has_successful_tool(events, lambda name, _result: name.startswith("browser_")):
            return {"status": "ok", "summary": "Pesquisa ou navegacao registrada por ferramenta."}
        return None

    if hint == "execute":
        document_profile = document_artifact_profile(description)
        report_profile = report_artifact_profile(description)
        if document_profile.get("requires_artifact") and not _has_requested_document_artifact(task_id, document_profile):
            return None
        if report_profile.get("requires_markdown") and not _has_markdown_artifact(task_id):
            return None
        if _has_successful_tool(events, lambda name, _result: not name.startswith("browser_")):
            return {"status": "ok", "summary": "Ferramenta de execucao concluiu sem erro."}
        if final_content.strip():
            return {"status": "ok", "summary": "Informacoes processadas na resposta final."}
        return None

    if hint == "validate":
        validation_events = [
            _event_payload(event)
            for event in events
            if event.get("type") in {"web_validation_result", "project_validation_result"}
        ]
        required = [item for item in validation_events if item.get("requires_validation")]
        if required:
            if all(item.get("status") == "passed" for item in required):
                return {"status": "ok", "summary": "Validacao automatica obrigatoria aprovada."}
            return None

        prompt = _latest_research_prompt(events, description)
        research_status = cross_check_status(prompt, database.list_sources(task_id))
        profile = research_status.get("profile") if isinstance(research_status.get("profile"), dict) else {}
        if profile.get("requires_cross_check"):
            if research_status.get("satisfied"):
                return {"status": "ok", "summary": "Fontes suficientes para a checagem cruzada exigida."}
            return None

        if validation_events:
            return {"status": "ok", "summary": "Validacao automatica registrada como nao obrigatoria."}
        if final_content.strip():
            return {"status": "ok", "summary": "Resultado revisado sem validacao automatica obrigatoria."}
        return None

    return None


async def _complete_supported_steps_before_delivery(
    task_id: str,
    bus: EventBus,
    description: str,
    final_content: str,
) -> None:
    events = bus.history(task_id)
    steps = task_plan_store.list_steps(task_id)
    deliver_positions = [
        int(step.get("position") or 0)
        for step in steps
        if step.get("tool_hint") == "deliver"
    ]
    deliver_position = min(deliver_positions) if deliver_positions else None
    for step in steps:
        status = step.get("status")
        if status in {"passed", "skipped", "failed"} or step.get("tool_hint") == "deliver":
            continue
        if deliver_position is not None and int(step.get("position") or 0) > deliver_position:
            continue
        evidence = _real_completion_evidence(task_id, step, events, description, final_content)
        if not evidence:
            continue
        completed = task_plan_store.complete_step_by_id(
            step["id"],
            evidence=evidence,
        )
        if completed:
            await bus.publish(task_id, "task_step_completed", {"step": completed})


async def _append_plan_evidence(
    task_id: str,
    hint: str,
    bus: EventBus,
    evidence: dict[str, Any],
) -> dict[str, Any] | None:
    step = task_plan_store.append_evidence(task_id, evidence, hint=hint)
    if step:
        await bus.publish(task_id, "task_step_updated", {"step": step})
    return step


async def _fail_running_plan_step(task_id: str, bus: EventBus, message: str) -> None:
    running = next((step for step in task_plan_store.list_steps(task_id) if step.get("status") == "running"), None)
    if not running:
        return
    step = task_plan_store.complete_step(
        task_id,
        hint=str(running.get("tool_hint") or ""),
        status="failed",
        evidence={"status": "failed", "summary": message[:360]},
    )
    if step:
        await bus.publish(task_id, "task_step_failed", {"step": step})


async def _sync_validation_plan(task_id: str, bus: EventBus, result: dict[str, Any]) -> None:
    validations = [
        item
        for item in (result.get("web_validation"), result.get("project_validation"))
        if isinstance(item, dict) and item.get("requires_validation")
    ]
    if not validations:
        return
    await _start_plan_step(task_id, "validate", bus)
    await publish_agent_activity(
        bus,
        task_id,
        kind="validation",
        title="Validando entrega",
        detail="Conferindo o resultado antes de finalizar.",
        status="running",
    )
    failed = [item for item in validations if item.get("status") == "failed"]
    blocked = [item for item in validations if item.get("status") == "blocked"]
    passed = [item for item in validations if item.get("status") == "passed"]
    if failed or blocked:
        issues: list[str] = []
        for item in [*failed, *blocked]:
            bugs = item.get("bugs") if isinstance(item.get("bugs"), list) else []
            issues.extend(str(bug) for bug in bugs[:5])
            if not bugs and item.get("reason"):
                issues.append(str(item["reason"]))
        await _append_plan_evidence(
            task_id,
            "validate",
            bus,
            {"status": "failed", "summary": "; ".join(issues)[:500] or "Validacao encontrou problemas."},
        )
        await publish_agent_activity(
            bus,
            task_id,
            kind="validation",
            title="Validação encontrou ajustes",
            detail="; ".join(issues)[:220] or "A revisão encontrou algo para corrigir.",
            status="failed",
        )
        return
    if passed and len(passed) == len(validations):
        await _complete_plan_step(
            task_id,
            "validate",
            bus,
            evidence={"status": "ok", "summary": "Validacao automatica aprovada."},
        )
        await publish_agent_activity(
            bus,
            task_id,
            kind="validation",
            title="Validação aprovada",
            detail="A revisão automática passou.",
            status="done",
        )


def _latest_user_prompt(history: list[dict[str, str]]) -> str:
    for message in reversed(history):
        if message.get("role") == "user":
            content = str(message.get("content") or "").strip()
            if (
                content
                and not content.startswith("Resultado da ferramenta:")
                and not content.startswith("Controle automatico de pesquisa:")
                and not content.startswith("Controle automatico de documento:")
                and not content.startswith("Controle automatico de relatorio:")
                and not content.startswith("Controle automatico de revisao")
                and not content.startswith("Controle automatico de validacao")
            ):
                return content
    return ""


def _is_code_agent_shell_call_from_params(params: dict[str, Any]) -> bool:
    """Detecta se os params de uma acao shell_run contem chamada ao agente de codigo."""
    command = str(params.get("command") or "").strip()
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()
    for part in parts:
        if part == CODE_AGENT_COMMAND or Path(part).name == Path(CODE_AGENT_COMMAND).name:
            return True
    return False


def _is_code_agent_shell_call(event: dict[str, Any]) -> bool:
    return _code_agent_shell_command(event) is not None


def _code_agent_shell_command(event: dict[str, Any]) -> str | None:
    if event.get("type") != "tool_call":
        return None
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    if payload.get("name") != "shell_run":
        return None
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    command = str(params.get("command") or "").strip()
    try:
        parts = shlex.split(command)
    except ValueError:
        return None
    if len(parts) >= 4 and parts[0] == "cd" and parts[2] == "&&":
        cd_path = Path(parts[1])
        if cd_path.is_absolute() or ".." in cd_path.parts:
            return None
        parts = parts[3:]
    return command if bool(parts) and (parts[0] == CODE_AGENT_COMMAND or Path(parts[0]).name == Path(CODE_AGENT_COMMAND).name) else None


def _looks_like_creation_code_agent_command(command: str) -> bool:
    try:
        parts = shlex.split(str(command or ""))
    except ValueError:
        return False
    if len(parts) >= 4 and parts[0] == "cd" and parts[2] == "&&":
        parts = parts[3:]
    if not parts or (parts[0] != CODE_AGENT_COMMAND and Path(parts[0]).name != Path(CODE_AGENT_COMMAND).name):
        return False
    if any(part in {"--version", "-v", "--help", "help"} for part in parts[1:]):
        return False
    text = " ".join(parts[1:]).lower()
    return bool(
        text
        and any(
            keyword in text
            for keyword in (
                "api",
                "app",
                "arquivo",
                "automacao",
                "automação",
                "backend",
                "bug",
                "codigo",
                "código",
                "corrija",
                "crie",
                "criar",
                "dashboard",
                "desenvolva",
                "documento",
                "edite",
                "editar",
                "erro",
                "faça",
                "faca",
                "frontend",
                "gere",
                "html",
                "implemente",
                "interface",
                "markdown",
                "melhore",
                "atualize",
                "altere",
                "node",
                "pdf",
                "python",
                "react",
                "script",
                "site",
                "software",
                "sistema",
            )
        )
    )


def _latest_code_agent_call(events: list[dict[str, Any]]) -> tuple[int, str] | None:
    latest: tuple[int, str] | None = None
    for event in events:
        command = _code_agent_shell_command(event)
        if command is not None:
            latest = (int(event.get("event_id") or 0), command)
    return latest


def _latest_validation_payload(events: list[dict[str, Any]], latest_code_agent_id: int, event_type: str) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    for event in events:
        event_id = int(event.get("event_id") or 0)
        if event_id <= latest_code_agent_id or event.get("type") != event_type:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        latest = payload
    return latest


def _latest_web_validation_gate(events: list[dict[str, Any]]) -> dict[str, Any]:
    latest_call = _latest_code_agent_call(events)
    if latest_call is None:
        return {"required": False, "status": "not_required"}
    latest_code_agent_id, command = latest_call
    latest_result = _latest_validation_payload(events, latest_code_agent_id, "web_validation_result")

    if latest_result is None:
        if not _looks_like_creation_code_agent_command(command):
            return {"required": False, "status": "not_required"}
        return {"required": True, "status": "pending", "reason": f"Site criado pelo {CODE_AGENT_LABEL} ainda nao passou pela revisao visual."}

    if not latest_result.get("requires_validation"):
        return {"required": False, "status": str(latest_result.get("status") or "skipped"), "result": latest_result}

    return {
        "required": True,
        "status": str(latest_result.get("status") or "pending"),
        "result": latest_result,
        "reason": latest_result.get("reason") or "",
        "bugs": latest_result.get("bugs") if isinstance(latest_result.get("bugs"), list) else [],
    }


def _latest_code_agent_quality_gate(events: list[dict[str, Any]]) -> dict[str, Any]:
    latest_call = _latest_code_agent_call(events)
    if latest_call is None:
        return {"required": False, "status": "not_required"}

    latest_code_agent_id, command = latest_call
    web_result = _latest_validation_payload(events, latest_code_agent_id, "web_validation_result")
    project_result = _latest_validation_payload(events, latest_code_agent_id, "project_validation_result")
    creation_command = _looks_like_creation_code_agent_command(command)

    pending_reasons: list[str] = []
    failed_bugs: list[str] = []
    blocked_reasons: list[str] = []
    passed_required = False

    for label, result in (("web_validation", web_result), ("project_validation", project_result)):
        if result is None:
            if label == "project_validation" and creation_command:
                pending_reasons.append(f"Projeto criado pelo {CODE_AGENT_LABEL} ainda nao passou pela revisao automatica.")
            elif label == "web_validation" and creation_command:
                pending_reasons.append(f"Projeto criado pelo {CODE_AGENT_LABEL} ainda nao passou pela revisao visual.")
            continue

        requires_validation = bool(result.get("requires_validation"))
        status = str(result.get("status") or "pending")
        if status == "blocked":
            blocked_reasons.append(str(result.get("reason") or "Revisao bloqueada."))
            continue
        if not requires_validation:
            continue
        if status == "passed":
            passed_required = True
            continue
        if status == "failed":
            bugs = result.get("bugs") if isinstance(result.get("bugs"), list) else []
            failed_bugs.extend(str(item) for item in bugs)
            if not bugs and result.get("reason"):
                failed_bugs.append(str(result["reason"]))
            continue
        pending_reasons.append(str(result.get("reason") or f"{label} ainda esta pendente."))

    if blocked_reasons:
        return {
            "required": True,
            "status": "blocked",
            "reason": " ".join(blocked_reasons),
            "bugs": [],
            "web_validation": web_result,
            "project_validation": project_result,
        }
    if failed_bugs:
        return {
            "required": True,
            "status": "failed",
            "reason": "Revisao automatica encontrou bugs.",
            "bugs": failed_bugs[:12],
            "web_validation": web_result,
            "project_validation": project_result,
        }
    if pending_reasons:
        return {
            "required": True,
            "status": "pending",
            "reason": " ".join(pending_reasons),
            "bugs": [],
            "web_validation": web_result,
            "project_validation": project_result,
        }
    if passed_required:
        return {
            "required": True,
            "status": "passed",
            "reason": "Revisao automatica aprovada.",
            "bugs": [],
            "web_validation": web_result,
            "project_validation": project_result,
        }
    return {
        "required": False,
        "status": "not_required",
        "reason": "",
        "bugs": [],
        "web_validation": web_result,
        "project_validation": project_result,
    }


def _format_research_note(status: dict[str, Any]) -> str:
    required = int(status.get("required_sources") or 0)
    if required <= 1:
        return ""
    source_count = int(status.get("source_count") or 0)
    topic_coverage = status.get("topic_coverage") if isinstance(status.get("topic_coverage"), dict) else {}
    covered_topics = [str(topic) for topic, count in topic_coverage.items() if int(count or 0) > 0]
    data_source_count = int(status.get("data_source_count") or 0)
    divergence = status.get("divergence") if isinstance(status.get("divergence"), dict) else {}
    details = []
    if covered_topics:
        details.append(f"indicadores cobertos: {', '.join(covered_topics)}")
    if data_source_count:
        details.append(f"{data_source_count} fonte(s) de dados/oficiais")
    detail_text = f" ({'; '.join(details)})" if details else ""
    if divergence.get("has_divergence"):
        categories = ", ".join(str(item.get("category")) for item in divergence.get("signals", []) if isinstance(item, dict))
        return f"\n\nVerificacao cruzada: {source_count} fontes relevantes consultadas{detail_text}. Possivel divergencia detectada em: {categories or 'dados extraidos'}."
    return f"\n\nVerificacao cruzada: {source_count} fontes relevantes consultadas{detail_text}; nenhuma divergencia automatica evidente foi detectada."


def _format_research_gate_instruction(status: dict[str, Any], required: int, found: int) -> str:
    pieces = [
        "Controle automatico de pesquisa: nao finalize ainda.",
        f"A pergunta exige pelo menos {required} fonte(s) relevante(s) e ha {found}.",
    ]
    missing_topics = [str(item) for item in status.get("missing_topics") or []]
    if missing_topics:
        pieces.append("Faltam fontes que cubram: " + ", ".join(missing_topics) + ".")
    if status.get("requires_data_source") and int(status.get("data_source_count") or 0) <= 0:
        pieces.append("Inclua pelo menos uma fonte de dados/oficial, como IBGE, Ipea, Banco Central, World Bank, OECD ou IMF.")
    unique_host_count = int(status.get("unique_host_count") or 0)
    min_unique_hosts = int(status.get("min_unique_hosts") or 0)
    if min_unique_hosts and unique_host_count < min_unique_hosts:
        pieces.append(f"Use fontes de pelo menos {min_unique_hosts} dominios diferentes; ha {unique_host_count}.")
    suggested = [str(item) for item in status.get("suggested_queries") or [] if str(item).strip()]
    if suggested:
        pieces.append("Tente consultas especificas: " + " | ".join(suggested[:4]) + ".")
    pieces.append("Abra as paginas encontradas e use browser_extract_article ou browser_extract_text para salvar evidencias antes de finalizar.")
    pieces.append("Para preco, versao, documentacao, noticia, dado sensivel ou comparacao, faca verificacao cruzada e marque divergencias na resposta final.")
    return " ".join(pieces)


def _sanitize_chat_content(content: str) -> str:
    text = str(content or "")
    had_local_preview = bool(LOCAL_PREVIEW_RE.search(text) or "LINK_LOCAL_DO_SITE" in text)
    text = LOCAL_PREVIEW_LINE_RE.sub("", text)
    text = LOCAL_PREVIEW_RE.sub("preview interno do Vortax", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if had_local_preview:
        note = "O preview foi usado apenas para revisao interna e foi encerrado apos a entrega."
        if note not in text:
            text = f"{text}\n\n{note}".strip() if text else note
    return text or "Pronto. A entrega foi gerada e revisada pelo Vortax."


async def _cleanup_project_runtime(task_id: str, bus: EventBus, reason: str) -> None:
    try:
        from tools.shell import stop_dev_server

        stopped = await stop_dev_server(task_id)
    except Exception as exc:
        await bus.publish(task_id, "error", {"message": f"Falha ao encerrar preview interno: {type(exc).__name__}: {exc}"})
        return
    if stopped:
        await bus.publish(
            task_id,
            "agent_progress",
            {
                "label": "Preview interno encerrado",
                "detail": reason,
            },
        )
        await bus.publish(task_id, "dev_server_stopped", {"task_id": task_id, "reason": reason})


def _file_payload(file: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": file.get("path"),
        "name": Path(str(file.get("path") or "arquivo")).name,
        "extension": file.get("extension") or Path(str(file.get("path") or "")).suffix.lower(),
        "size_bytes": int(file.get("size_bytes") or file.get("size") or 0),
        "project_name": file.get("project_name"),
    }


def _document_kind(path: str) -> str:
    extension = Path(str(path or "")).suffix.lower()
    if extension in {".md", ".markdown"}:
        return "markdown"
    if extension == ".pdf":
        return "pdf"
    return "document"


def _title_from_filename(path: str) -> str:
    stem = Path(str(path or "documento")).stem
    title = stem.replace("_", " ").replace("-", " ").strip()
    if not title:
        return "Documento"
    return " ".join(word.capitalize() for word in title.split())


def _document_title(task_id: str, file: dict[str, Any]) -> str:
    path = str(file.get("path") or "")
    if is_markdown_document(path):
        target = (settings.WORKSPACE_PATH / task_id / path).resolve()
        base = (settings.WORKSPACE_PATH / task_id).resolve()
        try:
            if target.is_file() and (target == base or base in target.parents):
                for line in target.read_text(encoding="utf-8", errors="replace").splitlines()[:40]:
                    match = re.match(r"^\s{0,3}#{1,3}\s+(.+?)\s*$", line)
                    if match:
                        return match.group(1).strip()[:120]
        except OSError:
            pass
    return _title_from_filename(path)


def _document_payload(task_id: str, file: dict[str, Any], *, primary: bool = False, source: str = "generated") -> dict[str, Any]:
    payload = _file_payload(file)
    path = str(payload.get("path") or "")
    payload.update(
        {
            "title": _document_title(task_id, file),
            "kind": _document_kind(path),
            "primary": primary,
            "previewable": is_previewable_document(path),
            "source": source,
        }
    )
    return payload


def _append_unique_file(files: list[dict[str, Any]], file: dict[str, Any]) -> None:
    path = str(file.get("path") or "")
    if path and all(str(existing.get("path") or "") != path for existing in files):
        files.append(file)


def _has_markdown_artifact(task_id: str) -> bool:
    return bool(markdown_documentation_files(database.list_generated_files(task_id)))


def _has_requested_document_artifact(task_id: str, profile: dict[str, Any]) -> bool:
    project_dir = settings.WORKSPACE_PATH / task_id
    if profile.get("wants_pdf"):
        return bool(valid_pdf_files(project_dir) and valid_markdown_files(project_dir))
    if profile.get("wants_markdown") and not valid_markdown_files(project_dir):
        return False
    return bool(profile.get("wants_pdf") or profile.get("wants_markdown"))


def _format_report_gate_instruction(description: str, profile: dict[str, Any]) -> str:
    filename = str(profile.get("preferred_filename") or "RELATORIO_TECNICO.md")
    return (
        "Controle automatico de relatorio: nao finalize ainda. "
        "Este pedido tecnico deve anexar um Markdown bonito e legivel no chat. "
        f"Use shell_run com {CODE_AGENT_COMMAND} para criar {filename} no diretorio atual. "
        "O arquivo deve conter titulo claro, resumo executivo, contexto do pedido, achados/decisoes principais, "
        "estrutura tecnica ou arquivos relevantes, como executar/testar quando houver software, validacao feita, limites e proximos passos. "
        "Depois observe a validacao e so finalize quando o Markdown existir e estiver nao vazio. "
        f"Pedido original: {description}"
    )


def _format_document_gate_instruction(description: str, profile: dict[str, Any]) -> str:
    parts = [
        "Controle automatico de documento: nao finalize ainda.",
        "O usuario pediu um arquivo final no chat e o artefato valido ainda nao existe.",
        f"Use shell_run com {CODE_AGENT_COMMAND} para criar ou atualizar o documento no diretorio atual.",
    ]
    if profile.get("wants_pdf"):
        parts.append(
            f"Crie primeiro o Markdown fonte {profile.get('preferred_markdown')} com H1, secoes completas e fontes; "
            f"o Vortax convertera para {profile.get('preferred_pdf')} se necessario."
        )
    if profile.get("wants_markdown"):
        parts.append(
            f"Crie o Markdown final {profile.get('preferred_markdown')} com H1, resumo, secoes bem estruturadas, validacao e fontes quando houver pesquisa."
        )
    parts.append("A resposta final deve explicar o que foi entregue e deixar o card de documento no chat.")
    parts.append(f"Pedido original: {description}")
    return " ".join(str(part) for part in parts if part)


def _format_document_research_gate_instruction(description: str, status: dict[str, Any]) -> str:
    queries = [str(query) for query in status.get("research_queries") or [] if str(query).strip()]
    required = int(status.get("required_sources") or 3)
    found = int(status.get("found_sources") or 0)
    pieces = [
        "Controle automatico de documento: nao finalize ainda.",
        f"Este documento factual precisa de pelo menos {required} fontes relevantes antes de gerar o arquivo; ha {found}.",
    ]
    if queries:
        pieces.append("Pesquise e abra fontes com estas consultas: " + " | ".join(queries[:5]) + ".")
    pieces.append("Use browser_google_search, abra resultados relevantes e salve evidencias com browser_extract_article ou browser_extract_text.")
    pieces.append(f"Depois chame {CODE_AGENT_LABEL} com as fontes pesquisadas para criar o Markdown/PDF e so finalize quando o arquivo aparecer no card.")
    pieces.append(f"Pedido original: {description}")
    return " ".join(pieces)


def _generated_file_response_payload(task_id: str, result: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    latest_call = _latest_code_agent_call(events)
    command = latest_call[1] if latest_call else ""
    files = [
        file
        for file in database.list_generated_files(task_id)
        if not str(file.get("path") or "").startswith("versions/")
    ]
    if not files:
        return {"content": result}
    requested_extensions = document_extensions_from_text(command)
    docs = markdown_documentation_files(files)
    requested_downloads = downloadable_document_files(files, requested_extensions)
    is_web_project = web_intent_from_command(command)
    report_profile = report_artifact_profile(command)

    download_files: list[dict[str, Any]] = []
    for file in [*requested_downloads, *docs]:
        _append_unique_file(download_files, file)

    document_files: list[tuple[dict[str, Any], str]] = []
    pdf_requested = ".pdf" in requested_extensions
    if pdf_requested:
        for file in requested_downloads:
            if Path(str(file.get("path") or "")).suffix.lower() == ".pdf":
                document_files.append((file, "requested"))
    include_markdown = bool(docs) and (
        is_web_project
        or bool(report_profile.get("requires_markdown"))
        or _looks_like_creation_code_agent_command(command)
        or ".md" in requested_extensions
        or pdf_requested
        or not requested_extensions
    )
    if include_markdown:
        document_files.extend((file, "documentation") for file in docs)
    if not pdf_requested:
        for file in requested_downloads:
            if is_previewable_document(str(file.get("path") or "")):
                document_files.append((file, "requested"))

    documents: list[dict[str, Any]] = []
    seen_documents: set[str] = set()
    for file, source in document_files:
        path = str(file.get("path") or "")
        if not path or path in seen_documents:
            continue
        seen_documents.add(path)
        documents.append(_document_payload(task_id, file, primary=len(documents) == 0, source=source))

    downloads = [_file_payload(file) for file in download_files]
    if not downloads and not documents:
        return {"content": result}

    payload: dict[str, Any] = {"content": result, "downloads": downloads[:8]}
    if documents:
        payload["documents"] = documents[:8]
    if docs:
        payload["documentation"] = _file_payload(docs[0])

    # Se o resultado ja tem um bloco de codigo ou e longo, nao sobrescrevemos com a mensagem padrao
    # Isso permite que o codigo apareça no chat com o botao de copiar
    has_code = "```" in result
    is_short = len(result.strip()) < 50

    if is_web_project and docs and (is_short or not has_code):
        payload["content"] = (
            "Pronto. Criei o site solicitado, revisei o projeto e anexei a documentacao em Markdown. "
            "Abra o card no chat para ler ou baixar."
        )
    elif requested_downloads and (is_short or not has_code):
        payload["content"] = "Pronto. Gerei o arquivo solicitado e anexei no chat para leitura ou download."

    return payload


def _history_with_research_context(task_id: str, history: list[dict[str, str]]) -> list[dict[str, str]]:
    all_sources = database.list_sources(task_id)
    # Filtra fontes de baixa qualidade: score < 30 e texto extraído curto são ruído no contexto
    good = [
        s for s in all_sources
        if int(s.get("quality_score") or 0) >= 30 and len(str(s.get("extracted_text") or "").strip()) >= 80
    ]
    # Fallback: se filtro remover tudo, usa as originais para não perder contexto
    sources = (good if good else all_sources)[:8]
    files = database.list_generated_files(task_id)
    document_context = document_context_for_code_agent(task_id, _latest_user_prompt(history), files, sources)
    if not sources and not document_context:
        return history
    lines = []
    for source in sources:
        title = source.get("title") or source.get("url")
        score = source.get("quality_score", 0)
        source_type = source.get("source_type") or "web"
        snippet = str(source.get("snippet") or "").strip()
        excerpt = str(source.get("extracted_text") or "").strip()
        detail = snippet or excerpt
        lines.append(f"- [{source_type} {score}/100] {title}: {source.get('url')}" + (f" — {detail[:520]}" if detail else ""))
    source_context = (
        f"Fontes ja abertas e salvas nesta conversa. IMPORTANTE: Se voce for criar software com {CODE_AGENT_LABEL}, "
        "USE estas fontes para enriquecer o prompt. Extraia destas fontes: tendencias de design, exemplos "
        "de layout, paleta de cores, estrutura de navegacao, tecnologias recomendadas e boas praticas. "
        "Se houver resultado de vision_analyze no historico, ELE contem analise visual com cores exatas, "
        f"estrutura de layout, estilo visual, tipografia e elementos de UI — incorpore TUDO no prompt do {CODE_AGENT_LABEL}. "
        f"Monte um prompt detalhado para o {CODE_AGENT_LABEL} que inclua referencias concretas extraidas das fontes "
        "(ex: 'crie um site inspirado nas referencias de [URL], usando paleta de cores similar, layout com "
        "hero section, navegacao superior, secao de depoimentos e rodape com contato'). "
        "Reutilize antes de pesquisar de novo quando responder ao mesmo tema; "
        "se precisar de informacao atual, controversa ou insuficiente, busque fontes adicionais. "
        "Quando browser_google_search retornar from_conversation_cache=true, nao use browser_click_link_by_index; use as evidencias salvas ou navegue direto pela URL se precisar reler.\n"
        + "\n".join(lines)
    )
    if document_context:
        source_context += (
            "\n\nContexto de documentos/arquivos da conversa para edicao e geracao:\n"
            + document_context
        )
    return [{"role": "system", "content": source_context}, *history]


async def _finish_text_response(
    task_id: str,
    description: str,
    result: str,
    store: TaskStore,
    bus: EventBus,
    *,
    emit_activity: bool = True,
) -> None:
    signup = credential_store.signup_summary(task_id)
    if signup:
        result = (
            f"{result}\n\n"
            "Credenciais criadas para o cadastro autorizado:\n"
            f"- Origem: {signup.get('origin')}\n"
            f"- Usuário: {signup.get('username')}\n"
            f"- E-mail: {signup.get('email')}\n"
            f"- Senha: {signup.get('password')}\n"
            f"- Status: {signup.get('status')}"
        )
    if emit_activity:
        await publish_agent_activity(
            bus,
            task_id,
            kind="finalizing",
            title="Preparando resposta final",
            detail="Organizando a entrega para aparecer no chat.",
            status="running",
        )
    await _complete_supported_steps_before_delivery(task_id, bus, description, result)
    await _start_plan_step(task_id, "deliver", bus)
    payload = _generated_file_response_payload(task_id, result, bus.history(task_id))
    final_content = _sanitize_chat_content(str(payload.get("content") or result))
    payload["content"] = final_content
    store.update_status(task_id, "done", result=final_content)
    await bus.publish(task_id, "assistant_message_done", payload)
    if emit_activity:
        await publish_agent_activity(
            bus,
            task_id,
            kind="finalizing",
            title="Resposta entregue",
            detail="A resposta final foi enviada ao chat.",
            status="done",
        )
    await _complete_plan_step(
        task_id,
        "deliver",
        bus,
        evidence={"status": "ok", "summary": "Resposta final entregue ao usuario."},
    )
    await _cleanup_project_runtime(task_id, bus, "Servidor temporario do projeto fechado apos a resposta no chat.")
    _, final_context, final_compacted = await prepare_context_history(task_id, bus.history(task_id), description)
    if final_compacted:
        await bus.publish(task_id, "context_compacted", final_context)
    await bus.publish(task_id, "context_status", final_context)
    await bus.publish(task_id, "agent_status", {"status": "done", "label": "Entrega pronta"})


async def _answer_exact_prompt(
    task_id: str,
    description: str,
    history: list[dict[str, str]],
    store: TaskStore,
    bus: EventBus,
) -> None:
    await bus.publish(task_id, "agent_status", {"status": "thinking", "label": "Calculando"})
    await bus.publish(task_id, "agent_progress", {"label": "Resolvendo com tool de exatas", "detail": description, "tool": "exact_solve"})
    await publish_agent_activity(
        bus,
        task_id,
        kind="analysis",
        title="Resolvendo cálculo",
        detail=description,
        status="running",
        tool="exact_solve",
    )
    await bus.publish(task_id, "tool_call", {"name": "exact_solve", "description": "Resolver pergunta de matematica/exatas", "params": {"problem": description}})
    exact_result = solve_exact_problem(description)
    await bus.publish(task_id, "tool_result", {"name": "exact_solve", "result": exact_result})
    await publish_agent_activity(
        bus,
        task_id,
        kind="analysis",
        title="Cálculo processado",
        detail=str(exact_result.get("answer") or exact_result.get("status") or ""),
        status="done" if exact_result.get("status") == "solved" else "running",
        tool="exact_solve",
    )

    if exact_result.get("status") == "solved":
        await _finish_text_response(task_id, description, format_exact_answer(exact_result), store, bus)
        return

    direct = await request_direct_chat_response(
        history,
        mode="exact",
        tool_context={"exact_solve": exact_result},
    )
    await _finish_text_response(task_id, description, direct["content"], store, bus, emit_activity=False)


async def _answer_simple_prompt(
    task_id: str,
    description: str,
    history: list[dict[str, str]],
    store: TaskStore,
    bus: EventBus,
) -> None:
    await bus.publish(task_id, "agent_status", {"status": "thinking", "label": "Respondendo"})
    await bus.publish(task_id, "agent_progress", {"label": "Resposta rapida", "detail": f"Sem planner e sem {CODE_AGENT_LABEL} para pergunta simples."})
    direct = await request_direct_chat_response(history, mode="direct")
    await _finish_text_response(task_id, description, direct["content"], store, bus)


async def _wait_if_paused_or_stopped(task_id: str, store: TaskStore, bus: EventBus) -> bool:
    while store.is_paused(task_id):
        if store.is_stopped(task_id):
            await bus.publish(task_id, "agent_status", {"status": "stopped", "label": "Tarefa parada"})
            return False
        await bus.publish(task_id, "agent_status", {"status": "paused", "label": "Pausado"})
        import asyncio

        await asyncio.sleep(0.5)
    if store.is_stopped(task_id):
        await bus.publish(task_id, "agent_status", {"status": "stopped", "label": "Tarefa parada"})
        return False
    return True


async def _inject_pre_research_if_needed(
    task_id: str,
    description: str,
    history: list[dict[str, str]],
    bus: EventBus,
) -> list[dict[str, str]]:
    """Analisa o pedido e, se for criacao de software viavel para pesquisa, executa
    pesquisa web automatica e alimenta o historico para o DeepSeek usar ao planejar.
    IMPORTANTE: Nao usa execute_tool para nao poluir o historico do DeepSeek com
    tool_results indesejados. Usa o navegador isolado da task diretamente."""
    from services.research_policy import relevant_sources_for_query, software_research_profile

    profile = software_research_profile(description)
    if not profile.get("is_software_request") or not profile.get("requires_pre_research"):
        return history

    research_queries = profile.get("research_queries", [])
    if not research_queries:
        return history

    # Verifica se ja ha fontes relevantes salvas para esta task
    existing_sources = database.list_sources(task_id)
    if existing_sources:
        relevant = relevant_sources_for_query(description, existing_sources, limit=3)
        if len(relevant) >= 2:
            return _history_with_research_context(task_id, history)

    # Consulta cache efêmero cross-task antes de abrir o navegador
    primary_query = research_queries[0]
    cached_sources = await ephemeral_cache.get(primary_query)
    if cached_sources:
        for src in cached_sources:
            database.upsert_source(task_id, {**src, "used": True})
        history = history + [
            {
                "role": "user",
                "content": (
                    f"[CACHE_HIT] Fontes pré-carregadas do cache (query: {primary_query!r}). "
                    "Consulte 'Fontes já abertas e salvas nesta conversa' para usá-las ao chamar o OpenClaude."
                ),
            }
        ]
        return _history_with_research_context(task_id, history)

    import logging
    from datetime import datetime, timezone

    logger = logging.getLogger("vortax.preresearch")
    _now = lambda: datetime.now(timezone.utc).isoformat()

    await bus.publish(
        task_id,
        "agent_status",
        {"status": "thinking", "label": "Pesquisando referencias antes de criar"},
    )

    pesquisa_feita = False
    bt = await browser_pool.acquire(task_id)
    for query in research_queries[:1]:  # So 1 consulta — 1 e suficiente
        await bus.publish(
            task_id,
            "agent_progress",
            {
                "label": "Pesquisando referencias e tendencias",
                "detail": f"Buscando: {query}",
                "tool": "browser_google_search",
            },
        )
        await publish_agent_activity(
            bus,
            task_id,
            kind="search",
            title="Pesquisando referências",
            detail=f"Buscando: {query}",
            status="running",
            tool="browser_google_search",
            metadata={"query": query},
        )
        try:
            search_result = await bt.google_search(query, hl="pt-BR")
            results = search_result.get("results", [])
            if not results:
                continue
            pesquisa_feita = True
            best = results[0]
            await bus.publish(
                task_id,
                "agent_progress",
                {
                    "label": "Abrindo referencia",
                    "detail": f"Abrindo: {best.get('title') or best.get('href', 'resultado')}",
                    "tool": "browser_navigate",
                },
            )
            await publish_agent_activity(
                bus,
                task_id,
                kind="browser",
                title="Abrindo referência",
                detail=str(best.get("title") or best.get("href") or "resultado")[:220],
                status="running",
                tool="browser_navigate",
                metadata={"url": best.get("href"), "source_title": best.get("title")},
            )
            await bt.navigate(best.get("href"), task_id=task_id)
            await bus.publish(
                task_id,
                "agent_progress",
                {
                    "label": "Extraindo referencia",
                    "detail": "Extraindo conteudo da pagina de referencia",
                    "tool": "browser_extract_article",
                },
            )
            await publish_agent_activity(
                bus,
                task_id,
                kind="source",
                title="Lendo referência",
                detail=str(best.get("title") or "Extraindo conteúdo da página")[:220],
                status="running",
                tool="browser_extract_article",
                metadata={"url": best.get("href"), "source_title": best.get("title")},
            )
            article = await bt.extract_article()
            # Salva fonte diretamente no banco
            if article.get("url") and article.get("text"):
                database.upsert_source(
                    task_id,
                    {
                        "url": article.get("url"),
                        "title": article.get("title") or best.get("title"),
                        "snippet": (article.get("description") or article.get("text", ""))[:280],
                        "extracted_text": article.get("text", "")[:10000],
                        "source_type": "web",
                        "quality_score": 80,
                        "used": True,
                        "created_at": _now(),
                    },
                )
        except Exception as exc:
            logger.warning("Pre-research failed for query %s: %s: %s", query, type(exc).__name__, exc)

    if pesquisa_feita:
        await bus.publish(
            task_id,
            "agent_progress",
            {
                "label": "Pesquisa de referencias concluida",
                "detail": f"Dados coletados. O DeepSeek usara as referencias ao planejar a criacao com {CODE_AGENT_LABEL}.",
            },
        )
        await publish_agent_activity(
            bus,
            task_id,
            kind="source",
            title="Referências coletadas",
            detail=f"Dados prontos para orientar a criação com {CODE_AGENT_LABEL}.",
            status="done",
        )
        # Salva no cache efêmero cross-task para reutilização em tasks futuras com mesma query
        fresh_sources = database.list_sources(task_id)
        if fresh_sources and primary_query:
            complexity = str(query_complexity(description).get("complexity", "MODERATE"))
            await ephemeral_cache.set(primary_query, fresh_sources, complexity)
    return _history_with_research_context(task_id, history)


async def _save_extracted_source(task_id: str, bus: EventBus, article: dict[str, Any], fallback_title: str = "") -> bool:
    url = str(article.get("url") or "").strip()
    text = str(article.get("text") or "").strip()
    if not url or not text:
        return False
    title = str(article.get("title") or fallback_title or url).strip()
    source = database.upsert_source(
        task_id,
        {
            "url": url,
            "title": title,
            "snippet": str(article.get("description") or text[:280]),
            "extracted_text": text[:10000],
            "source_type": source_type_for_url(url),
            "quality_score": source_quality_score(url, title, text),
            "used": True,
            "created_at": utc_now(),
        },
    )
    await bus.publish(
        task_id,
        "source_saved",
        {
            "id": source["id"],
            "url": source["url"],
            "title": source.get("title"),
            "source_type": source.get("source_type"),
            "quality_score": source.get("quality_score"),
        },
    )
    await publish_agent_activity(
        bus,
        task_id,
        kind="source",
        title="Fonte salva",
        detail=title,
        status="done",
        metadata={"url": source["url"], "source_title": title},
    )
    return True


async def _inject_document_research_if_needed(
    task_id: str,
    description: str,
    history: list[dict[str, str]],
    bus: EventBus,
) -> list[dict[str, str]]:
    """Pesquisa automaticamente quando o usuario pediu PDF/MD factual."""
    profile = document_research_profile(description)
    if not profile.get("requires_research"):
        return history

    required = int(profile.get("required_sources") or 3)
    subject = str(profile.get("subject") or description)
    existing = relevant_sources_for_query(subject, database.list_sources(task_id), limit=required, min_quality=50)
    if len(existing) >= required:
        return _history_with_research_context(task_id, history)

    await bus.publish(
        task_id,
        "agent_status",
        {"status": "thinking", "label": "Pesquisando fontes do documento"},
    )
    queries = [str(query) for query in profile.get("research_queries") or [] if str(query).strip()]
    seen_urls: set[str] = set()
    bt = await browser_pool.acquire(task_id)

    for query in queries[:5]:
        current = relevant_sources_for_query(subject, database.list_sources(task_id), limit=required, min_quality=50)
        if len(current) >= required:
            break
        await bus.publish(
            task_id,
            "agent_progress",
            {
                "label": "Pesquisando fontes do documento",
                "detail": f"Buscando: {query}",
                "tool": "browser_google_search",
            },
        )
        await publish_agent_activity(
            bus,
            task_id,
            kind="search",
            title="Pesquisando fontes",
            detail=f"Buscando: {query}",
            status="running",
            tool="browser_google_search",
            metadata={"query": query},
        )
        try:
            search = await bt.google_search(query, hl="pt-BR", task_id=task_id)
        except Exception:
            continue
        for result in list(search.get("results") or [])[:4]:
            current = relevant_sources_for_query(subject, database.list_sources(task_id), limit=required, min_quality=50)
            if len(current) >= required:
                break
            href = str(result.get("href") or result.get("url") or "").strip()
            if not href or href in seen_urls:
                continue
            seen_urls.add(href)
            await bus.publish(
                task_id,
                "agent_progress",
                {
                    "label": "Lendo fonte do documento",
                    "detail": str(result.get("title") or href)[:180],
                    "tool": "browser_extract_article",
                },
            )
            await publish_agent_activity(
                bus,
                task_id,
                kind="source",
                title="Lendo fonte",
                detail=str(result.get("title") or href)[:180],
                status="running",
                tool="browser_extract_article",
                metadata={"url": href, "source_title": result.get("title")},
            )
            try:
                navigate_result = await bt.navigate(href, task_id=task_id)
                if isinstance(navigate_result, dict) and navigate_result.get("blocked"):
                    article = await bt.extract_article(task_id=task_id)
                else:
                    article = await bt.extract_article(task_id=task_id)
            except Exception:
                continue
            await _save_extracted_source(task_id, bus, article, str(result.get("title") or ""))

    found = len(relevant_sources_for_query(subject, database.list_sources(task_id), limit=required, min_quality=50))
    await bus.publish(
        task_id,
        "agent_progress",
        {
            "label": "Pesquisa do documento concluida",
            "detail": f"{found} fonte(s) relevante(s) prontas para gerar o arquivo.",
        },
    )
    await publish_agent_activity(
        bus,
        task_id,
        kind="source",
        title="Pesquisa concluída",
        detail=f"{found} fonte(s) relevante(s) prontas para gerar o arquivo.",
        status="done",
        metadata={"found_sources": found},
    )
    return _history_with_research_context(task_id, history)


async def _inject_people_research_if_needed(
    task_id: str,
    description: str,
    history: list[dict[str, str]],
    bus: EventBus,
) -> list[dict[str, str]]:
    """Analisa se o pedido e sobre uma pessoa. Se for, pesquisa diretamente com
    navegador isolado da task (sem execute_tool) para evitar poluir o historico do DeepSeek.
    Maximo 2 consultas, com fallback silencioso."""
    from services.research_policy import people_research_profile, relevant_sources_for_query

    profile = people_research_profile(description)
    if not profile.get("is_people_search"):
        return history

    person_name = profile.get("person_name")
    search_queries = profile.get("search_queries", [])
    if not person_name or not search_queries:
        return history

    # Verifica se ja tem fontes
    existing_sources = database.list_sources(task_id)
    if existing_sources:
        relevant = relevant_sources_for_query(person_name, existing_sources, limit=3, min_quality=50)
        if len(relevant) >= profile.get("required_sources", 3):
            return _history_with_research_context(task_id, history)

    import logging
    from datetime import datetime, timezone

    logger = logging.getLogger("vortax.people")
    _now = lambda: datetime.now(timezone.utc).isoformat()

    await bus.publish(
        task_id,
        "agent_status",
        {"status": "thinking", "label": "Pesquisando informacoes da pessoa"},
    )
    await bus.publish(
        task_id,
        "agent_progress",
        {
            "label": "Pesquisando informacoes",
            "detail": f"Buscando dados sobre: {person_name}",
        },
    )
    await publish_agent_activity(
        bus,
        task_id,
        kind="search",
        title="Pesquisando informações",
        detail=f"Buscando dados sobre: {person_name}",
        status="running",
        metadata={"query": person_name},
    )

    pesquisa_feita = False
    categories = profile.get("categories", [])
    bt = await browser_pool.acquire(task_id)

    # Usa so 2 consultas principais (max 3)
    for query in search_queries[:2]:
        try:
            await publish_agent_activity(
                bus,
                task_id,
                kind="search",
                title="Consultando fontes",
                detail=query,
                status="running",
                tool="browser_google_search",
                metadata={"query": query},
            )
            search_result = await bt.google_search(query, hl="pt-BR")
            results = search_result.get("results", [])
            if not results:
                continue
            pesquisa_feita = True
            # Pula login/ads
            for result in results[:2]:
                href = str(result.get("href") or "")
                if any(skip in href.lower() for skip in
                       ["accounts.google", "servicelogin", "login", "signin", "ads.",
                        "googleadservices"]):
                    continue
                await publish_agent_activity(
                    bus,
                    task_id,
                    kind="source",
                    title="Lendo resultado",
                    detail=str(result.get("title") or href)[:220],
                    status="running",
                    tool="browser_extract_article",
                    metadata={"url": href, "source_title": result.get("title")},
                )
                await bt.navigate(href, task_id=task_id)
                article = await bt.extract_article()
                if article.get("url") and article.get("text"):
                    database.upsert_source(
                        task_id,
                        {
                            "url": article.get("url"),
                            "title": article.get("title") or result.get("title"),
                            "snippet": (article.get("description") or article.get("text", ""))[:280],
                            "extracted_text": article.get("text", "")[:10000],
                            "source_type": "web",
                            "quality_score": 80,
                            "used": True,
                            "created_at": _now(),
                        },
                    )
                break  # 1 resultado por consulta
        except Exception as exc:
            logger.warning("People search failed for query %s: %s: %s", query[:60], type(exc).__name__, exc)

    if not pesquisa_feita:
        # Se nao achou com queries especificas, tenta uma busca generica por nome
        try:
            generic = await bt.google_search(f'"{person_name}"', hl="pt-BR")
            results = generic.get("results", [])
            if results:
                pesquisa_feita = True
                href = str(results[0].get("href") or "")
                if not any(skip in href.lower() for skip in
                           ["accounts.google", "servicelogin", "login", "signin", "ads."]):
                    await bt.navigate(href, task_id=task_id)
                    article = await bt.extract_article()
                    if article.get("url") and article.get("text"):
                        database.upsert_source(
                            task_id,
                            {
                                "url": article.get("url"),
                                "title": article.get("title") or results[0].get("title"),
                                "snippet": (article.get("description") or article.get("text", ""))[:280],
                                "extracted_text": article.get("text", "")[:10000],
                                "source_type": "web",
                                "quality_score": 80,
                                "used": True,
                                "created_at": _now(),
                            },
                        )
        except Exception as exc:
            logger.warning("Fallback people search failed: %s: %s", type(exc).__name__, exc)

    if pesquisa_feita:
        await bus.publish(
            task_id,
            "agent_progress",
            {
                "label": "Pesquisa sobre pessoa concluida",
                "detail": f"Dados coletados sobre {person_name}.",
            },
        )
        await publish_agent_activity(
            bus,
            task_id,
            kind="source",
            title="Pesquisa concluída",
            detail=f"Dados coletados sobre {person_name}.",
            status="done",
        )

    research_history = _history_with_research_context(task_id, history)
    people_instruction = (
        "ATENCAO: Este pedido envolve pesquisa sobre uma PESSOA. "
        "Voce DEVE utilizar as fontes acima para montar um perfil completo. "
        "Para CADA informacao relevante, indique de qual URL/fonte veio. "
        "Se informacoes importantes nao foram encontradas (LinkedIn, GitHub, formacao, experiencia), "
        "declare explicitamente o que NAO foi encontrado. "
        "NAO resuma informacoes vagas — extraia dados concretos das fontes abertas. "
        f"Pessoa pesquisada: {person_name}. "
        f"Plataformas sugeridas: {', '.join(categories)}."
    )
    return [{"role": "system", "content": people_instruction}, *research_history]


def _history_with_authorized_session(task_id: str, history: list[dict[str, str]]) -> list[dict[str, str]]:
    metadata = credential_store.get_metadata(task_id)
    if not metadata:
        return history
    instruction = (
        "AUTORIZACAO SEGURA ATIVA: o usuario autorizou login no dominio "
        f"{metadata.get('origin')} para esta tarefa. Use browser_auth_login para autenticar; "
        "nunca peça, mostre ou inclua usuario/senha/tokens em mensagens ou parametros. "
        "Opere somente dentro destes dominios autorizados: "
        f"{', '.join(metadata.get('allowed_origins') or [])}. "
        "Se browser_auth_signup for usado, o backend gerara credenciais de cadastro fortes; inclua essas credenciais no resumo final para o usuario. "
        "Se surgir CAPTCHA, 2FA, OTP, paywall ou desafio de seguranca, pare e informe que precisa de intervencao do usuario."
    )
    return [{"role": "system", "content": instruction}, *history]


def _history_with_task_plan(task_id: str, history: list[dict[str, str]]) -> list[dict[str, str]]:
    all_steps = task_plan_store.list_steps(task_id)
    steps = [
        step
        for step in all_steps
        if step.get("tool_hint") != "deliver" or len(all_steps) > 1
    ]
    if not steps:
        return history

    lines = []
    for step in steps[:8]:
        status = str(step.get("status") or "pending")
        marker = "ATUAL" if status == "running" else status
        criteria = "; ".join(str(item) for item in (step.get("acceptance_criteria") or [])[:3])
        detail = str(step.get("detail") or "").strip()
        line = (
            f"{int(step.get('position') or len(lines) + 1)}. [{marker}] "
            f"{step.get('label')} | hint={step.get('tool_hint') or 'execute'}"
        )
        if detail:
            line += f" | detalhe={detail}"
        if criteria:
            line += f" | criterio={criteria}"
        lines.append(line)

    current = next((step for step in steps if step.get("status") == "running"), None)
    current = current or next((step for step in steps if step.get("status") == "pending"), None)
    instruction = (
        "PLANO DE TASKS DO VORTAX PARA ESTE PEDIDO. "
        "Quando a Groq esta configurada, este plano vem do planner Groq. "
        "Use este plano como roteiro operacional para escolher a proxima action. "
        "Priorize concluir a etapa marcada como ATUAL ou a primeira pending; alinhe suas ferramentas ao tool_hint. "
        "Nao trate este plano como resposta final ao usuario e nao invente que uma etapa foi concluida sem evidencia de ferramenta.\n"
        f"Etapa alvo: {current.get('label') if current else 'nenhuma'}.\n"
        + "\n".join(lines)
    )
    return [{"role": "system", "content": instruction}, *history]


async def _run_agent_task_inner(task_id: str, description: str, store: TaskStore, bus: EventBus) -> None:
    await _ensure_plan(task_id, description, bus)
    if not deepseek_configured():
        await _start_plan_step(task_id, "understand", bus)
        history, context_payload, compacted = await prepare_context_history(task_id, bus.history(task_id), description)
        _ = history
        if compacted:
            await bus.publish(task_id, "context_compacted", context_payload)
        await bus.publish(task_id, "context_status", context_payload)
        await bus.publish(
            task_id,
            "tool_result",
            {"name": "deepseek_config", "result": "Sem DEEPSEEK_API_KEY; usando runner mockado."},
        )
        await _complete_plan_step(task_id, "understand", bus)
        await _start_plan_step(task_id, "execute", bus)
        await run_mock_task(task_id, description, store, bus)
        if store.is_stopped(task_id):
            await _fail_running_plan_step(task_id, bus, "Tarefa interrompida pelo usuario.")
            return
        await _complete_plan_step(
            task_id,
            "execute",
            bus,
            evidence={"status": "ok", "summary": "Runner mockado concluiu a tarefa."},
        )
        await _start_plan_step(task_id, "deliver", bus)
        await _complete_plan_step(
            task_id,
            "deliver",
            bus,
            evidence={"status": "ok", "summary": "Resposta mockada entregue ao usuario."},
        )
        return

    try:
        store.update_status(task_id, "running")
        await _start_plan_step(task_id, "understand", bus)
        history, context_payload, compacted = await prepare_context_history(task_id, bus.history(task_id), description)
        if compacted:
            await bus.publish(task_id, "context_compacted", context_payload)
        await bus.publish(task_id, "context_status", context_payload)
        await bus.publish(task_id, "agent_status", {"status": "thinking", "label": "Trabalhando"})
        await bus.publish(task_id, "agent_progress", {"label": "Analisando pedido", "detail": description})

        latest_prompt = _latest_user_prompt(history) or description
        if is_exact_prompt(latest_prompt):
            await _complete_plan_step(task_id, "understand", bus)
            await _start_plan_step(task_id, "execute", bus)
            await _answer_exact_prompt(task_id, latest_prompt, history, store, bus)
            return
        if should_answer_directly(latest_prompt):
            await _complete_plan_step(task_id, "understand", bus)
            await _answer_simple_prompt(task_id, latest_prompt, history, store, bus)
            return

        await publish_agent_activity(
            bus,
            task_id,
            kind="analysis",
            title="Analisando pedido",
            detail=latest_prompt,
            status="done",
        )

        # Pesquisa previa automatica antes do loop ReAct
        await _complete_plan_step(task_id, "understand", bus)
        history = await _inject_pre_research_if_needed(task_id, latest_prompt, history, bus)

        # Pesquisa factual para documentos PDF/Markdown antes do loop ReAct
        history = await _inject_document_research_if_needed(task_id, latest_prompt, history, bus)

        # Pesquisa automatica de pessoas antes do loop ReAct
        history = await _inject_people_research_if_needed(task_id, latest_prompt, history, bus)

        MAX_CODE_AGENT_CALLS = 3
        code_agent_call_count = 0

        for iteration in range(settings.MAX_ITERATIONS):
            if not await _wait_if_paused_or_stopped(task_id, store, bus):
                await _cleanup_project_runtime(task_id, bus, "Tarefa parada; preview interno fechado.")
                return

            await bus.publish(task_id, "agent_progress", {"label": "Planejando proximo passo", "step": iteration + 1})
            await publish_agent_activity(
                bus,
                task_id,
                kind="analysis",
                title="Planejando próximo passo",
                detail="Escolhendo a próxima ação para cumprir o pedido.",
                status="running",
                metadata={"step": iteration + 1},
            )
            action_history = _history_with_task_plan(task_id, history)
            action_history = _history_with_research_context(task_id, action_history)
            action_history = _history_with_authorized_session(task_id, action_history)
            action = await request_deepseek_action(action_history)
            history.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})

            action_name = str(action.get("action", "")).strip()

            # Detecção de ciclo: 3 ações consecutivas idênticas → forçar finish
            if action_name != "finish":
                recent_assistant = [m["content"] for m in history if m.get("role") == "assistant"]
                if len(recent_assistant) >= 3 and len(set(recent_assistant[-3:])) == 1:
                    await bus.publish(
                        task_id,
                        "agent_progress",
                        {"label": "Ciclo detectado", "detail": "Ações repetidas sem avanço; finalizando com o resultado atual."},
                    )
                    await publish_agent_activity(
                        bus,
                        task_id,
                        kind="analysis",
                        title="Ciclo detectado",
                        detail="O agente repetiu a mesma ação 3 vezes consecutivas; forçando finalização.",
                        status="failed",
                    )
                    action = {"action": "finish", "result": str(action.get("result") or "Tarefa finalizada (ciclo de ações detectado).")}
                    action_name = "finish"

            if action_name == "finish":
                # Limite de chamadas ao agente de codigo: forcar finalizacao se ja chamou demais
                if code_agent_call_count >= MAX_CODE_AGENT_CALLS:
                    await bus.publish(
                        task_id,
                        "agent_progress",
                        {
                            "label": "Finalizando",
                            "detail": f"Limite de chamadas ao {CODE_AGENT_LABEL} atingido ({MAX_CODE_AGENT_CALLS}x). Entregando o que foi produzido.",
                        },
                    )
                    await publish_agent_activity(
                        bus,
                        task_id,
                        kind="finalizing",
                        title="Finalizando entrega",
                        detail=f"Limite de chamadas ao {CODE_AGENT_LABEL} atingido. Preparando o resultado.",
                        status="running",
                    )
                    result = str(action.get("result") or action.get("params", {}).get("result") or "Tarefa concluida.")
                    research_prompt = _latest_user_prompt(history) or description
                    research_status = cross_check_status(research_prompt, database.list_sources(task_id))
                    result = result + _format_research_note(research_status)
                    await _finish_text_response(task_id, description, result, store, bus)
                    return

                # Gate de validacao de projeto (so para codigo, nao para documentos puros)
                has_code_files = any(
                    str(f.get("extension") or "").lower() in {".py", ".js", ".html", ".css", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java"}
                    for f in database.list_generated_files(task_id)
                )
                if has_code_files:
                    validation_gate = _latest_code_agent_quality_gate(bus.history(task_id))
                    if validation_gate.get("required") and validation_gate.get("status") != "passed":
                        status = str(validation_gate.get("status") or "pending")
                        if status == "blocked":
                            reason = str(validation_gate.get("reason") or "Revisao automatica obrigatoria indisponivel.")
                            raise DeepSeekError(reason)

                        bugs = validation_gate.get("bugs") or []
                        bug_text = "; ".join(str(item) for item in bugs[:8]) or str(validation_gate.get("reason") or "Revisao automatica ainda nao foi aprovada.")
                        await _start_plan_step(task_id, "validate", bus)
                        await _append_plan_evidence(
                            task_id,
                            "validate",
                            bus,
                            {"status": status, "summary": bug_text[:500]},
                        )
                        await bus.publish(
                            task_id,
                            "agent_progress",
                            {
                                "label": "Corrigindo bugs do projeto",
                                "detail": "A tarefa nao pode finalizar antes da revisao automatica passar.",
                            },
                        )
                        await publish_agent_activity(
                            bus,
                            task_id,
                            kind="validation",
                            title="Corrigindo revisão",
                            detail="A entrega precisa passar pela revisão automática antes de finalizar.",
                            status="running",
                            metadata={"validation_status": status},
                        )
                        history.append(
                            {
                                "role": "user",
                                "content": (
                                    "Controle automatico de revisao da entrega: nao finalize ainda. "
                                    f"Status da revisao do projeto: {status}. "
                                    f"Problemas encontrados: {bug_text}. "
                                    f"Use shell_run com {CODE_AGENT_COMMAND} para corrigir exatamente esses bugs no projeto atual. "
                                    "Isso vale para sites, sistemas, APIs, scripts Python, apps Node e qualquer outro codigo criado. "
                                    "Depois da correcao, o Vortax repetira a revisao automatica e so entao podera finalizar. "
                                    "Para HTML/CSS/JS estatico, nao suba servidor manual; o Vortax abrira o preview interno."
                                ),
                            }
                        )
                        continue

                result = str(action.get("result") or action.get("params", {}).get("result") or "Tarefa concluida.")
                document_profile = document_artifact_profile(description)
                if is_document_edit_request(description) and not document_profile.get("requires_artifact"):
                    target = resolve_document_target(task_id, description, database.list_generated_files(task_id))
                    target_extension = Path(str((target or {}).get("path") or "")).suffix.lower()
                    if target_extension in {".md", ".markdown", ".pdf"}:
                        document_profile["requires_artifact"] = True
                        document_profile["wants_markdown"] = target_extension in {".md", ".markdown"}
                        document_profile["wants_pdf"] = target_extension == ".pdf"

                document_research = document_research_profile(description)
                if document_research.get("requires_research"):
                    required = int(document_research.get("required_sources") or 3)
                    found_sources = relevant_sources_for_query(
                        str(document_research.get("subject") or description),
                        database.list_sources(task_id),
                        limit=required,
                        min_quality=50,
                    )
                    if len(found_sources) < required:
                        await bus.publish(
                            task_id,
                            "agent_progress",
                            {
                                "label": "Buscando mais fontes",
                                "detail": f"Documento factual ainda precisa de {required} fonte(s); ha {len(found_sources)}.",
                            },
                        )
                        await publish_agent_activity(
                            bus,
                            task_id,
                            kind="search",
                            title="Buscando mais fontes",
                            detail=f"Documento factual precisa de {required} fonte(s); ha {len(found_sources)}.",
                            status="running",
                            metadata={"required_sources": required, "found_sources": len(found_sources)},
                        )
                        history.append(
                            {
                                "role": "user",
                                "content": _format_document_research_gate_instruction(
                                    description,
                                    {**document_research, "found_sources": len(found_sources)},
                                ),
                            }
                        )
                        continue

                # Gates de documento unificados: documento e relatorio sao tratados juntos
                needs_document = document_profile.get("requires_artifact") and not _has_requested_document_artifact(task_id, document_profile)
                report_profile = report_artifact_profile(description)
                needs_report = report_profile.get("requires_markdown") and not _has_markdown_artifact(task_id)

                if needs_document or needs_report:
                    label = "Preparando arquivo final"
                    detail = "A resposta precisa anexar o PDF/Markdown solicitado antes de finalizar."
                    if needs_document and needs_report:
                        combined = {**report_profile, **document_profile}
                        gate_content = _format_document_gate_instruction(description, combined)
                    elif needs_document:
                        gate_content = _format_document_gate_instruction(description, document_profile)
                    else:
                        gate_content = _format_report_gate_instruction(description, report_profile)
                        label = "Preparando relatorio"
                        detail = "A resposta tecnica precisa anexar um Markdown legivel antes de finalizar."

                    await bus.publish(
                        task_id,
                        "agent_progress",
                        {"label": label, "detail": detail},
                    )
                    await publish_agent_activity(
                        bus,
                        task_id,
                        kind="file",
                        title=label,
                        detail=detail,
                        status="running",
                    )
                    history.append({"role": "user", "content": gate_content})
                    continue

                research_prompt = _latest_user_prompt(history) or description
                research_status = cross_check_status(research_prompt, database.list_sources(task_id))
                if not research_status.get("satisfied"):
                    required = int(research_status.get("required_sources") or 0)
                    found = int(research_status.get("source_count") or 0)
                    if required > 0:
                        await bus.publish(
                            task_id,
                            "agent_progress",
                            {
                                "label": "Verificando fontes",
                                "detail": f"Resposta ainda precisa de {required} fonte(s) relevante(s); ha {found}.",
                            },
                        )
                        await publish_agent_activity(
                            bus,
                            task_id,
                            kind="validation",
                            title="Verificando fontes",
                            detail=f"Resposta ainda precisa de {required} fonte(s) relevante(s); ha {found}.",
                            status="running",
                            metadata={"required_sources": required, "found_sources": found},
                        )
                        history.append(
                            {
                                "role": "user",
                                "content": _format_research_gate_instruction(research_status, required, found),
                            }
                        )
                        continue
                result = result + _format_research_note(research_status)
                await _finish_text_response(task_id, description, result, store, bus)
                return

            if action.get("requires_confirmation"):
                message = action.get("confirmation_message") or action.get("description") or "Confirmar acao?"
                await bus.publish(
                    task_id,
                    "confirmation_request",
                    {"message": message, "action": action_name, "params": action.get("params", {})},
                )
                raise DeepSeekError("Planner pediu confirmacao; fluxo de confirmacao sera ligado no proximo bloco.")

            progress_label = _progress_label(action_name, str(action.get("description") or ""))
            action_params = action.get("params") if isinstance(action.get("params"), dict) else {}

            # Enriquece chamadas ao OpenClaude com ExecutionPackage estruturado + snippets relevantes
            if action_name == "shell_run" and _is_code_agent_shell_call_from_params(action_params):
                raw_cmd = str(action_params.get("command") or "")
                snippets = snippet_library.search(description, limit=2)
                snippets_block = snippet_library.format_for_prompt(snippets) if snippets else ""
                enriched = enrich_code_agent_command(raw_cmd, task_id, snippets_block=snippets_block)
                if enriched != raw_cmd:
                    action_params = {**action_params, "command": enriched}

            action_hint = _action_plan_hint(action_name, action_params)
            await _start_plan_step(task_id, action_hint, bus)
            await bus.publish(
                task_id,
                "agent_progress",
                {"label": progress_label, "detail": action.get("description") or action_name, "tool": action_name},
            )
            await _publish_action_activity(
                task_id,
                bus,
                action_name,
                action_params,
                str(action.get("description") or action_name),
                status="running",
            )
            await bus.publish(task_id, "agent_status", {"status": "executing", "label": "Executando"})

            # Checa se foi interrompido antes de executar a ferramenta
            if store.is_stopped(task_id):
                break

            tool_result = await execute_tool(
                action_name,
                action_params,
                task_id=task_id,
                bus=bus,
                description=str(action.get("description") or action_name),
            )

            if action_name == "shell_run" and _is_code_agent_shell_call_from_params(action_params):
                code_agent_call_count += 1

            # Checa se foi interrompido apos a ferramenta (o usuario pode ter clicado stop durante)
            if store.is_stopped(task_id):
                break

            result_for_model = compact_tool_result(tool_result.get("data", tool_result) if isinstance(tool_result, dict) else {"result": tool_result})
            evidence_source = tool_result.get("data", tool_result) if isinstance(tool_result, dict) else {"result": tool_result}
            if isinstance(evidence_source, dict):
                await _publish_action_activity(
                    task_id,
                    bus,
                    action_name,
                    action_params,
                    str(evidence_source.get("summary") or evidence_source.get("title") or evidence_source.get("stdout") or "Ação concluída.")[:220],
                    status="done" if _result_succeeded(evidence_source) else "failed",
                )
                await _append_plan_evidence(task_id, action_hint, bus, _tool_evidence(action_name, evidence_source))
                if action_hint == "research" and action_name in {"browser_extract_article", "browser_extract_text", "browser_google_search"}:
                    await _complete_plan_step(
                        task_id,
                        "research",
                        bus,
                        evidence={"status": "ok", "summary": "Pesquisa ou leitura registrada na conversa."},
                    )
                if action_name == "shell_run" and evidence_source.get("success"):
                    await _complete_plan_step(task_id, "execute", bus, evidence=_tool_evidence(action_name, evidence_source))
                    await _sync_validation_plan(task_id, bus, evidence_source)
            history.append(
                {
                    "role": "user",
                    "content": "Resultado da ferramenta: " + json.dumps(result_for_model, ensure_ascii=False),
                }
            )

        if store.is_stopped(task_id):
            store.update_status(task_id, "stopped", result="Tarefa interrompida pelo usuario.")
            await bus.publish(task_id, "assistant_message_done", {"content": "Tarefa interrompida pelo usuario."})
            await _fail_running_plan_step(task_id, bus, "Tarefa interrompida pelo usuario.")
            await _cleanup_project_runtime(task_id, bus, "Tarefa interrompida; preview interno fechado.")
            await bus.publish(task_id, "agent_status", {"status": "stopped", "label": "Interrompido"})
            return

        raise DeepSeekError(f"Limite de iteracoes atingido ({settings.MAX_ITERATIONS}).")
    except asyncio.CancelledError:
        store.update_status(task_id, "stopped", result="Tarefa interrompida pelo usuario.")
        await bus.publish(task_id, "assistant_message_done", {"content": "Tarefa interrompida pelo usuario."})
        await _fail_running_plan_step(task_id, bus, "Tarefa cancelada.")
        await _cleanup_project_runtime(task_id, bus, "Tarefa cancelada; preview interno fechado.")
        await bus.publish(task_id, "agent_status", {"status": "stopped", "label": "Interrompido"})
        return
    except DeepSeekError as exc:
        store.update_status(task_id, "error", result=str(exc))
        await bus.publish(task_id, "error", {"message": str(exc)})
        await _fail_running_plan_step(task_id, bus, str(exc))
        await _cleanup_project_runtime(task_id, bus, "Tarefa finalizada com erro; preview interno fechado.")
        await bus.publish(task_id, "agent_status", {"status": "error", "label": "Erro no DeepSeek"})
    except Exception as exc:
        store.update_status(task_id, "error", result=str(exc))
        await bus.publish(task_id, "error", {"message": str(exc)})
        await _fail_running_plan_step(task_id, bus, str(exc))
        await _cleanup_project_runtime(task_id, bus, "Tarefa finalizada com erro; preview interno fechado.")
        await bus.publish(task_id, "agent_status", {"status": "error", "label": "Erro"})


async def run_agent_task(task_id: str, description: str, store: TaskStore, bus: EventBus) -> None:
    try:
        await _run_agent_task_inner(task_id, description, store, bus)
    finally:
        await browser_pool.release(task_id)
