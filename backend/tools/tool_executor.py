import re
import shlex
from typing import Any, Awaitable, Callable
from urllib.parse import quote

from database import database
from services.document_artifacts import (
    archive_edit_targets,
    artifact_profile,
    document_context_for_code_agent,
    preferred_markdown_for_pdf,
    render_markdown_to_pdf,
    resolve_document_target,
    valid_pdf_files,
)
from services.document_intent import document_extensions_from_text, document_intent_from_text, report_artifact_profile
from services.event_bus import EventBus
from services.project_validation import validate_project_after_code_agent
from services.research_policy import cached_search_result
from services.safe_diagnostics import sanitize_payload
from services.source_quality import source_quality_score, source_type_for_url
from services.stream_contract import utc_now
from services.web_validation import validate_web_project_after_code_agent, web_intent_from_command
from pathlib import Path
from services.project_files import sync_task_workspace_files

from config import settings
from tools.browser import browser_tool
from tools.exact import exact_tool
from tools.shell import _project_dir, run_shell
from tools.vision import vision_tool


ToolCallable = Callable[..., Awaitable[dict[str, Any]]]

CODE_AGENT_COMMAND = "openclaude"
CODE_AGENT_LABEL = "OpenClaude"


LOCAL_PREVIEW_RE = re.compile(
    r"(?:LINK_LOCAL_DO_SITE:\s*)?https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0):\d{2,5}(?:/[^\s\"'<>)]*)?",
    re.IGNORECASE,
)


def _redact_local_preview(value: Any) -> Any:
    if isinstance(value, str):
        return LOCAL_PREVIEW_RE.sub("preview interno do Vortax", value)
    if isinstance(value, list):
        return [_redact_local_preview(item) for item in value]
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"local_urls", "dev_server_url", "url_template"}:
                continue
            redacted[key] = _redact_local_preview(item)
        return redacted
    return value


TOOLS: dict[str, ToolCallable] = {
    "browser_navigate": browser_tool.navigate,
    "browser_get_state": browser_tool.get_state,
    "browser_click_text": browser_tool.click_text,
    "browser_click_selector": browser_tool.click_selector,
    "browser_click_link_by_index": browser_tool.click_link_by_index,
    "browser_type": browser_tool.type_text,
    "browser_press_key": browser_tool.press_key,
    "browser_wait_for_text": browser_tool.wait_for_text,
    "browser_go_back": browser_tool.go_back,
    "browser_google_search": browser_tool.google_search,
    "browser_extract_text": browser_tool.extract_text,
    "browser_extract_article": browser_tool.extract_article,
    "browser_extract_links": browser_tool.extract_links,
    "browser_screenshot": browser_tool.screenshot,
    "browser_scroll": browser_tool.scroll,
    "shell_run": run_shell,
    "vision_analyze": vision_tool.analyze,
    "exact_solve": exact_tool.solve,
}


def compact_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    compact = _redact_local_preview(dict(result))
    compact.pop("local_urls", None)
    compact.pop("dev_server_url", None)
    compact.pop("dev_server_port", None)
    if compact.get("tty"):
        if compact.get("missing_assets"):
            compact["stdout"] = f"{CODE_AGENT_LABEL} retornou projeto incompleto; ha referencias locais ausentes."
        else:
            compact["stdout"] = f"{CODE_AGENT_LABEL} executou a tarefa. O andamento esta disponivel em vertex_progress e a revisao em web_validation_result."
        compact["stderr"] = str(compact.get("stderr") or "")[:500]
    if "image_base64" in compact:
        compact["image_base64"] = "[base64-image]"
    text = compact.get("text")
    if isinstance(text, str) and len(text) > 1800:
        compact["text"] = f"{text[:1800]}... [truncated]"
    for key in ("links", "results"):
        items = compact.get(key)
        if isinstance(items, list):
            compact[key] = items[:10]

    # Se o resultado tem file_summary, preserva e adiciona nota de truncamento
    if compact.get("file_summary"):
        # Ja esta no formato certo, so garantir que nao e muito grande
        summary = compact["file_summary"]
        if isinstance(summary, dict) and summary.get("file_count", 0) > 100:
            summary["root_files"] = summary.get("root_files", [])[:30]
            summary["top_dirs"] = summary.get("top_dirs", [])[:15]
            summary["by_extension"] = dict(sorted(
                summary.get("by_extension", {}).items(),
                key=lambda x: -x[1]
            )[:10])
    if compact.get("stdout_truncated"):
        compact["_note"] = "A saida stdout foi truncada. Use o file_summary para ver a lista completa de arquivos gerados."

    for validation_key in ("web_validation", "project_validation"):
        validation = compact.get(validation_key)
        if isinstance(validation, dict):
            compact[validation_key] = {
                "status": validation.get("status"),
                "requires_validation": validation.get("requires_validation"),
                "reason": validation.get("reason"),
                "bugs": validation.get("bugs", [])[:8] if isinstance(validation.get("bugs"), list) else [],
                "warnings": validation.get("warnings", [])[:5] if isinstance(validation.get("warnings"), list) else [],
                "project": validation.get("project"),
            }

    return compact


async def _save_source_if_extracted(task_id: str, tool_name: str, result: dict[str, Any], bus: EventBus) -> None:
    if tool_name not in {"browser_extract_text", "browser_extract_article"}:
        return
    url = str(result.get("url") or "").strip()
    if not url or url.startswith("data:") or url == "about:blank":
        return
    text = str(result.get("text") or "").strip()
    title = str(result.get("title") or "").strip()
    source = database.upsert_source(
        task_id,
        {
            "url": url,
            "title": title,
            "snippet": result.get("description") or text[:280],
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


async def _publish_screenshot_if_browser_action(task_id: str, tool_name: str, bus: EventBus) -> None:
    if (not tool_name.startswith("browser_") and tool_name != "shell_run") or tool_name == "browser_screenshot":
        return
    try:
        frame = await browser_tool.screenshot(task_id=task_id)
        await bus.publish(
            task_id,
            "screen_frame",
            {
                "caption": frame.get("title") or frame.get("url") or "Tela do Chrome",
                "title": frame.get("title"),
                "url": frame.get("url"),
                "image_base64": frame.get("image_base64"),
            },
        )
    except Exception as exc:
        await bus.publish(task_id, "error", {"message": f"Screenshot apos tool falhou: {type(exc).__name__}"})


def _is_code_agent_command(command: str) -> bool:
    return _split_code_agent_command(command) is not None


def _code_agent_creation_intent(command: str) -> bool:
    split = _split_code_agent_command(command)
    if split is None:
        return False
    _, parts = split
    if any(part in {"--version", "-v", "--help", "help"} for part in parts[1:]):
        return False
    text = " ".join(parts[1:]).lower()
    report_profile = report_artifact_profile(text)
    return bool(
        web_intent_from_command(command)
        or document_intent_from_text(text)
        or report_profile.get("requires_markdown")
        or re.search(
            r"\b(crie|criar|faca|faça|desenvolva|implemente|gere|corrija|bug|erro|falha|"
            r"melhore|melhorar|atualize|atualizar|altere|alterar|edite|editar|revise|revisar|"
            r"software|sistema|script|api|backend|python|node|cli|automacao|automação|app|pdf|markdown|documento|arquivo)\b",
            text,
            re.IGNORECASE,
        )
    )


def _looks_like_manual_static_server(command: str) -> bool:
    text = str(command or "").lower()
    return "http.server" in text and ("python -m" in text or "python3 -m" in text)


def _preview_url_for_files(task_id: str, files: list[dict[str, Any]]) -> str | None:
    index_paths = sorted(
        str(file.get("path") or "")
        for file in files
        if str(file.get("path") or "").endswith("index.html")
    )
    if not index_paths:
        return None
    index_path = index_paths[0]
    url = f"http://127.0.0.1:{settings.BACKEND_PORT}/api/files/preview/{quote(task_id)}/"
    if index_path != "index.html":
        url += quote(index_path)
    return url


def _split_code_agent_command(command: str) -> tuple[str, list[str]] | None:
    cmd = str(command or "").strip()
    cd_prefix = ""
    cd_match = None
    try:
        cd_match = shlex.split(cmd)
    except ValueError:
        return None

    if len(cd_match) >= 4 and cd_match[0] == "cd" and cd_match[2] == "&&":
        cd_path = Path(cd_match[1])
        if cd_path.is_absolute() or ".." in cd_path.parts:
            return None
        cd_prefix = f"cd {shlex.quote(cd_match[1])} && "
        args = cd_match[3:]
    else:
        args = cd_match

    if not args or args[0] != CODE_AGENT_COMMAND:
        return None
    return cd_prefix, args


def _augment_code_agent_command_for_local_site(command: str) -> str:
    split = _split_code_agent_command(command)
    if split is None or not web_intent_from_command(command):
        return command

    cd_prefix, parts = split

    pass_through_flags = {"-p", "--print", "--permission-mode", "--dangerously-skip-permissions", "--no-session-persistence"}
    prompt_parts: list[str] = []
    skip_next = False
    for part in parts[1:]:
        if skip_next:
            skip_next = False
            continue
        if part == "--permission-mode":
            skip_next = True
            continue
        if part.startswith("--permission-mode=") or part in pass_through_flags:
            continue
        prompt_parts.append(part)

    prompt = " ".join(prompt_parts).strip()
    instructions = [
        "Obrigatorio para o Vortax: crie os arquivos do site dentro do diretorio atual. "
        "Para HTML/CSS/JavaScript estatico, NAO inicie servidor temporario e NAO rode modulo de servidor HTTP do Python; "
        "quando o pedido mencionar HTML, CSS e JavaScript/JS, crie obrigatoriamente arquivos separados index.html, style.css e script.js. "
        "Nao deixe href/src apontando para arquivos locais inexistentes. "
        "Garanta que exista um index.html funcional, pois o Vortax abrira o preview interno automaticamente. "
        "Revise responsividade, estados de botoes, erros no console, textos cortados e arquivos vazios antes de finalizar."
    ]
    prompt_upper = prompt.upper()
    if "DOCUMENTACAO.MD" not in prompt_upper and "DOCUMENTAÇÃO.MD" not in prompt_upper:
        instructions.append(
            "Tambem crie obrigatoriamente um arquivo DOCUMENTACAO.md em Markdown explicando o que foi criado, "
            "com titulo claro, resumo executivo, funcionalidades, estrutura dos arquivos, principais decisoes tecnicas, "
            "como testar/abrir o site, validacao realizada e proximos ajustes sugeridos. "
            "Use tabelas Markdown quando ajudarem a leitura e mantenha o documento bonito, escaneavel e pronto para o card de leitura do Vortax."
        )
    if "LINK_LOCAL_DO_SITE" not in prompt:
        instructions.append(
            "Somente se o projeto realmente exigir dev server para a revisao interna, informe LINK_LOCAL_DO_SITE para o Vortax testar. "
            "Esse endereco e interno, temporario e nunca deve ser citado na resposta ao usuario."
        )
    instruction = "\n\n" + " ".join(instructions)
    return (
        cd_prefix
        + f"{CODE_AGENT_COMMAND} -p --permission-mode bypassPermissions --dangerously-skip-permissions --no-session-persistence "
        + shlex.quote((prompt + instruction).strip())
    )


def _command_involves_code(prompt: str) -> bool:
    """Returns True only when the code-agent command is about creating/editing code, not just documents."""
    lowered = prompt.lower()
    code_keywords = [
        "python", ".py", "node", "javascript", ".js", "html", ".html", "css", ".css",
        "react", "vue", "angular", "next", "nuxt", "api", "backend", "frontend",
        "script", "server", "site", "app", "aplicativo", "typescript", ".ts",
        "java", "rust", "go", "c++", "cli", "compile", "compilar", "build",
        "test", "unittest", "pytest", "npm", "pip", "package.json",
        "requirements.txt", "docker", "dockerfile", "banco de dados",
        "sqlalchemy", "sqlite", "postgres", "mysql", "mongodb", "redis",
    ]
    return any(kw in lowered for kw in code_keywords)


def _augment_code_agent_command_for_quality(command: str, task_id: str | None = None) -> str:
    initial_split = _split_code_agent_command(command)
    initial_prompt = ""
    if initial_split is not None:
        _, initial_parts = initial_split
        initial_prompt = " ".join(part for part in initial_parts[1:] if part not in {"-p", "--print"}).strip()
    if web_intent_from_command(command) and not report_artifact_profile(initial_prompt).get("is_analysis"):
        return _augment_code_agent_command_for_local_site(command)

    split = initial_split
    if split is None or not _code_agent_creation_intent(command):
        return command

    cd_prefix, parts = split
    pass_through_flags = {"-p", "--print", "--permission-mode", "--dangerously-skip-permissions", "--no-session-persistence"}
    prompt_parts: list[str] = []
    skip_next = False
    for part in parts[1:]:
        if skip_next:
            skip_next = False
            continue
        if part == "--permission-mode":
            skip_next = True
            continue
        if part.startswith("--permission-mode=") or part in pass_through_flags:
            continue
        prompt_parts.append(part)

    prompt = " ".join(prompt_parts).strip()
    requested_extensions = document_extensions_from_text(prompt)
    report_profile = report_artifact_profile(prompt)
    artifact = artifact_profile(prompt)
    involves_code = _command_involves_code(prompt)

    if "VALIDACAO_AUTOMATICA_VORTAX" in prompt:
        instruction = ""
    else:
        instruction = ""
        # Instrucoes de validacao de codigo so para comandos que envolvem codigo
        if involves_code:
            instruction = (
                "\n\nVALIDACAO_AUTOMATICA_VORTAX: entregue um projeto executavel e revisado dentro do diretorio atual. "
                "Se for Python, garanta que todos os arquivos .py passam em python3 -m py_compile e crie testes unittest quando fizer sentido. "
                "Se for Node/JavaScript, garanta package.json valido, sintaxe JS valida e scripts build/test quando o projeto precisar. "
                "Se estiver corrigindo uma falha anterior, preserve o projeto existente e corrija exatamente os bugs descritos. "
                "Nao finalize deixando TODO, arquivo vazio, dependencia quebrada, caminho inexistente ou instrucao que impeca a revisao automatica."
            )
        if report_profile.get("requires_markdown"):
            filename = str(report_profile.get("preferred_filename") or "RELATORIO_TECNICO.md")
            if filename.upper() not in prompt.upper() and "DOCUMENTACAO.MD" not in prompt.upper() and "DOCUMENTAÇÃO.MD" not in prompt.upper():
                instruction += (
                    f" Crie tambem um arquivo {filename} em Markdown, bem formatado e pronto para leitura no card de leitura do Vortax. "
                    "O Markdown deve ter titulo, resumo, contexto do pedido, achados ou funcionalidades principais, "
                    "arquitetura/estrutura de arquivos quando houver codigo, como executar/testar, validacao feita, riscos/limites e proximos passos. "
                    "Use secoes curtas, listas e tabelas quando ajudarem; nao entregue um Markdown vazio ou generico."
                )
        if requested_extensions:
            extensions = ", ".join(requested_extensions)
            instruction += (
                f" Como o usuario pediu arquivo/documento final ({extensions}), crie pelo menos um arquivo nao vazio "
                "com essa(s) extensao(oes) diretamente no diretorio atual ou em subpasta clara. "
                "Use nome descritivo, conteudo completo e pronto para download pelo Vortax. "
                "Se gerar PDF, entregue o .pdf final e, quando fizer sentido, tambem deixe a fonte editavel em Markdown."
            )
        if artifact.get("wants_pdf"):
            instruction += (
                f" Para PDF, crie obrigatoriamente tambem o Markdown fonte {artifact.get('preferred_markdown')} "
                "com titulo H1, secoes claras, conclusao e fontes usadas. O Vortax convertera esse Markdown em PDF final se necessario."
            )
        if artifact.get("wants_markdown"):
            instruction += (
                f" Para Markdown final, use preferencialmente o nome {artifact.get('preferred_markdown')} "
                "e entregue um documento bonito, com H1, resumo, secoes, listas/tabelas quando ajudarem e fontes quando houver pesquisa."
            )

    if task_id:
        target = resolve_document_target(task_id, prompt, database.list_generated_files(task_id))
        target_extension = Path(str((target or {}).get("path") or "")).suffix.lower()
        if target_extension in {".md", ".markdown"} and not artifact.get("wants_markdown") and not artifact.get("wants_pdf"):
            instruction += " Este pedido parece editar um Markdown anterior; atualize o arquivo Markdown alvo mantendo H1, estrutura e conteudo suficiente."
        if target_extension == ".pdf" and not artifact.get("wants_pdf"):
            instruction += " Este pedido parece editar um PDF anterior; atualize o Markdown fonte correspondente e gere novamente a entrega para PDF."
        context = document_context_for_code_agent(
            task_id,
            prompt,
            database.list_generated_files(task_id),
            database.list_sources(task_id),
        )
        if context:
            instruction += (
                "\n\nCONTEXTO_VORTAX_PARA_OPENCLAUDE:\n"
                + context
                + "\nUse esse contexto ao criar ou editar arquivos. Se houver ALVO_DA_EDICAO, atualize esse arquivo fonte e preserve o nome logico da entrega."
            )

    return (
        cd_prefix
        + f"{CODE_AGENT_COMMAND} -p --permission-mode bypassPermissions --dangerously-skip-permissions --no-session-persistence "
        + shlex.quote((prompt + instruction).strip())
    )


async def _ensure_pdf_artifact_after_code_agent(task_id: str, command: str, bus: EventBus) -> dict[str, Any]:
    profile = artifact_profile(command)
    project_dir = _project_dir(task_id)
    existing_valid = valid_pdf_files(project_dir)
    target = resolve_document_target(task_id, command, database.list_generated_files(task_id))
    target_path = str((target or {}).get("path") or "")
    wants_pdf = bool(profile.get("wants_pdf") or Path(target_path).suffix.lower() == ".pdf")
    if not wants_pdf:
        return {"changed": False, "reason": "not_pdf_request"}
    preferred_pdf = target_path if Path(target_path).suffix.lower() == ".pdf" else str(profile.get("preferred_pdf") or "documento.pdf")
    source_markdown = preferred_markdown_for_pdf(task_id, preferred_pdf)
    if not source_markdown:
        return {"changed": False, "reason": "missing_markdown_source", "valid_pdfs": existing_valid}

    await bus.publish(
        task_id,
        "agent_progress",
        {
            "label": "Renderizando PDF",
            "detail": f"Convertendo {source_markdown} em {preferred_pdf}.",
            "tool": "document_render_pdf",
        },
    )
    result = await render_markdown_to_pdf(task_id, source_markdown, preferred_pdf)
    if result.get("success"):
        return {"changed": True, "rendered": result.get("path"), "source": source_markdown}
    await bus.publish(
        task_id,
        "error",
        {"message": f"Falha ao renderizar PDF: {result.get('error') or 'erro desconhecido'}"},
    )
    return {"changed": False, "reason": "render_failed", "error": result.get("error")}


async def _open_static_preview_if_available(task_id: str, files: list[dict[str, Any]], bus: EventBus) -> None:
    index_paths = sorted(
        str(file.get("path") or "")
        for file in files
        if str(file.get("path") or "").endswith("index.html")
    )
    if not index_paths:
        return

    index_path = index_paths[0]
    preview_url = f"http://127.0.0.1:{settings.BACKEND_PORT}/api/files/preview/{quote(task_id)}/"
    if index_path != "index.html":
        preview_url += quote(index_path)
    try:
        await bus.publish(
            task_id,
            "agent_progress",
            {
                "label": "Abrindo preview do site",
                "detail": "Carregando o index.html gerado no Chrome para validar visualmente.",
                "tool": "browser_navigate",
            },
        )
        await browser_tool.navigate(preview_url, task_id=task_id)
    except Exception as exc:
        await bus.publish(task_id, "error", {"message": f"Preview automatico falhou: {type(exc).__name__}: {exc}"})


async def execute_tool(
    tool_name: str,
    params: dict[str, Any] | None,
    *,
    task_id: str,
    bus: EventBus,
    description: str = "",
) -> dict[str, Any]:
    safe_params = sanitize_payload(params or {})
    await bus.publish(
        task_id,
        "tool_call",
        {"name": tool_name, "description": description or tool_name, "params": safe_params},
    )

    tool = TOOLS.get(tool_name)
    if tool is None:
        error = {"success": False, "error": f"Ferramenta desconhecida: {tool_name}"}
        await bus.publish(task_id, "error", {"message": error["error"]})
        return error

    try:
        if tool_name == "browser_google_search":
            query = str((params or {}).get("query") or "").strip()
            cached = cached_search_result(query, database.list_sources(task_id)) if query else None
            if cached:
                await bus.publish(
                    task_id,
                    "agent_progress",
                    {
                        "label": "Reutilizando fontes da conversa",
                        "detail": "Busca ignorada porque ja ha fontes boas salvas para esta consulta.",
                        "tool": tool_name,
                    },
                )
                compact = compact_tool_result(cached)
                await bus.publish(task_id, "tool_result", {"name": tool_name, "result": compact})
                return {"success": True, "data": cached}

        # shell_run recebe o bus para streaming de stdout
        if tool_name == "shell_run":
            command = str((params or {}).get("command", ""))
            if _looks_like_manual_static_server(command):
                project_dir = _project_dir(task_id)
                project_index = sync_task_workspace_files(task_id, project_dir)
                files = project_index["files"]
                preview_url = _preview_url_for_files(task_id, files)
                if preview_url:
                    await bus.publish(
                        task_id,
                        "agent_progress",
                        {
                            "label": "Usando preview interno",
                            "detail": "Servidor manual ignorado para evitar conflito de porta; abrindo o preview interno do Vortax.",
                            "tool": "browser_navigate",
                        },
                    )
                    await bus.publish(
                        task_id,
                        "files_created",
                        {"files": files, "projects": project_index["projects"], "directory": str(project_dir)},
                    )
                    await _open_static_preview_if_available(task_id, files, bus)
                    result = {
                        "success": True,
                        "stdout": "Preview interno do Vortax aberto para revisao.",
                        "stderr": "",
                        "returncode": 0,
                        "local_urls": [preview_url],
                        "skipped_manual_server": True,
                    }
                    compact = compact_tool_result(result)
                    await bus.publish(task_id, "tool_result", {"name": tool_name, "result": compact})
                    await _publish_screenshot_if_browser_action(task_id, tool_name, bus)
                    return {"success": True, "data": result}
            if _is_code_agent_command(command):
                project_index = sync_task_workspace_files(task_id, _project_dir(task_id))
                archived = archive_edit_targets(task_id, command, project_index["files"])
                if archived:
                    await bus.publish(
                        task_id,
                        "agent_progress",
                        {
                            "label": "Preservando versao anterior",
                            "detail": "Backup criado em: " + ", ".join(archived),
                            "tool": "document_versioning",
                        },
                    )
                await bus.publish(
                    task_id,
                    "ai_exchange",
                    {
                        "actor": "deepseek",
                        "target": "openclaude",
                        "message": f"DeepSeek delegou a criacao de codigo ao {CODE_AGENT_LABEL}.",
                        "kind": "delegation",
                    },
                )
            tool_params = dict(params or {})
            if _is_code_agent_command(command):
                command = _augment_code_agent_command_for_quality(command, task_id=task_id)
                tool_params["command"] = command
                await bus.publish(
                    task_id,
                    "vertex_progress",
                    {
                        "stage": "starting",
                        "message": f"{CODE_AGENT_LABEL} iniciou a criacao do projeto.",
                        "status": "running",
                    },
                )
            result = await tool(**tool_params, task_id=task_id, bus=bus)
        else:
            result = await tool(**(params or {}), task_id=task_id)
        # Após shell_run, lista arquivos criados e publica files_created
        if tool_name == "shell_run":
            project_dir = _project_dir(task_id)
            project_index = sync_task_workspace_files(task_id, project_dir)
            files = project_index["files"]
            command = str((params or {}).get("command", ""))
            validation = None
            project_validation = None
            if files:
                await bus.publish(
                    task_id,
                    "files_created",
                    {"files": files, "projects": project_index["projects"], "directory": str(project_dir)},
                )
                if _is_code_agent_command(command):
                    await bus.publish(
                        task_id,
                        "vertex_progress",
                        {
                            "stage": "creating",
                            "message": f"{CODE_AGENT_LABEL} gerou {len(files)} arquivo(s) no projeto.",
                            "status": "running",
                        },
                    )

            if _is_code_agent_command(command) and result.get("success"):
                document_prepare = await _ensure_pdf_artifact_after_code_agent(task_id, command, bus)
                if document_prepare.get("changed"):
                    project_index = sync_task_workspace_files(task_id, project_dir)
                    files = project_index["files"]
                    await bus.publish(
                        task_id,
                        "files_created",
                        {"files": files, "projects": project_index["projects"], "directory": str(project_dir)},
                    )

            # Se foi dev server, publica evento
            shell_data = result.get("data", result) if isinstance(result, dict) else {}
            if shell_data.get("is_dev_server") and shell_data.get("dev_server_url"):
                await bus.publish(
                    task_id,
                    "dev_server_started",
                    {
                        "port": shell_data.get("dev_server_port"),
                        "task_id": task_id,
                        "internal": True,
                    },
                )

            is_creation_code_agent = _is_code_agent_command(command) and _code_agent_creation_intent(command)
            if _is_code_agent_command(command) and result.get("success"):
                await bus.publish(
                    task_id,
                    "vertex_progress",
                    {
                        "stage": "validating",
                        "message": f"Vortax esta revisando a entrega criada pelo {CODE_AGENT_LABEL}.",
                        "status": "running",
                    },
                )
                validation = await validate_web_project_after_code_agent(task_id, command, bus, agent_result=result)
                if is_creation_code_agent:
                    project_validation = await validate_project_after_code_agent(task_id, command, bus, agent_result=result)
                if isinstance(result, dict):
                    result["web_validation"] = validation
                    if project_validation is not None:
                        result["project_validation"] = project_validation

            elif files:
                await _open_static_preview_if_available(task_id, files, bus)

            # Se foi agente de codigo, publica progresso final no evento legado vertex_progress.
            if _is_code_agent_command(command) and result.get("success"):
                validation_status = validation.get("status") if isinstance(validation, dict) else "skipped"
                project_validation_status = project_validation.get("status") if isinstance(project_validation, dict) else "skipped"
                if validation_status == "failed" or project_validation_status == "failed":
                    code_agent_done_message = "A entrega foi criada, mas a revisao encontrou pontos para corrigir."
                elif validation_status == "blocked" or project_validation_status == "blocked":
                    code_agent_done_message = "A entrega foi criada, mas a revisao visual esta bloqueada."
                elif validation_status == "passed" or project_validation_status == "passed":
                    code_agent_done_message = "Entrega pronta: projeto revisado, arquivos gerados e documentacao disponivel quando criada."
                else:
                    code_agent_done_message = f"Entrega criada pelo {CODE_AGENT_LABEL}."
                await bus.publish(
                    task_id,
                    "vertex_progress",
                    {
                        "stage": "done",
                        "message": code_agent_done_message,
                        "status": "done",
                        "interactive_rounds": shell_data.get("interactive_rounds", 0),
                    },
                )
                await bus.publish(
                    task_id,
                    "ai_exchange",
                    {
                        "actor": "openclaude",
                        "target": "deepseek",
                        "message": f"{CODE_AGENT_LABEL} terminou a criacao do projeto e devolveu o resultado.",
                        "kind": "completion",
                    },
                )

        result_blocked = isinstance(result, dict) and bool(result.get("blocked"))
        await _save_source_if_extracted(task_id, tool_name, result, bus)
        compact = compact_tool_result(result)
        await bus.publish(task_id, "tool_result", {"name": tool_name, "result": compact})

        if tool_name == "browser_screenshot":
            await bus.publish(
                task_id,
                "screen_frame",
                {
                    "caption": result.get("title") or result.get("url") or "Tela do Chrome",
                    "title": result.get("title"),
                    "url": result.get("url"),
                    "image_base64": result.get("image_base64"),
                },
            )
        elif not result_blocked:
            await _publish_screenshot_if_browser_action(task_id, tool_name, bus)
        if result_blocked:
            await bus.publish(
                task_id,
                "agent_progress",
                {
                    "label": "Pagina bloqueada",
                    "detail": "O navegador encontrou CAPTCHA/anti-bot; tentando seguir por fontes alternativas.",
                    "tool": tool_name,
                },
            )
            return {"success": False, "error": result.get("error") or "Pagina bloqueada por CAPTCHA/anti-bot", "data": result}
        return {"success": True, "data": result}
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        await bus.publish(task_id, "error", {"message": message, "tool": tool_name})
        return {"success": False, "error": message}
