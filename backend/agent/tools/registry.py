"""Registro central de tools com JSON Schema OpenAI (plano-melhoria-ia §03.6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from services.code_agent import CODE_AGENT_COMMAND, CODE_AGENT_LABEL


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    read_only: bool = False


def _obj(props: dict[str, Any], required: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": props, "additionalProperties": False}
    if required:
        schema["required"] = required
    schema.update(extra)
    return schema


def _str(desc: str = "", **kw: Any) -> dict[str, Any]:
    d: dict[str, Any] = {"type": "string", "description": desc}
    d.update(kw)
    return d


def _int(desc: str = "", **kw: Any) -> dict[str, Any]:
    d: dict[str, Any] = {"type": "integer", "description": desc}
    d.update(kw)
    return d


def _bool(desc: str = "") -> dict[str, Any]:
    return {"type": "boolean", "description": desc}


def build_tool_specs() -> list[ToolSpec]:
    """Lista canônica de tools expostas ao modelo (function calling)."""
    specs: list[ToolSpec] = [
        ToolSpec(
            "browser_navigate",
            "Abrir uma URL no Chrome deste PC.",
            _obj({"url": _str("URL completa https://...")}, ["url"]),
            read_only=False,
        ),
        ToolSpec(
            "browser_google_search",
            "Pesquisar na web e retornar resultados estruturados (sem digitar na UI).",
            _obj(
                {
                    "query": _str("Consulta de pesquisa"),
                    "hl": _str("Idioma da interface, ex: pt-BR"),
                },
                ["query"],
            ),
            read_only=True,
        ),
        ToolSpec(
            "browser_extract_links",
            "Extrair links visíveis ou resultados da página atual.",
            _obj(
                {
                    "limit": _int("Máximo de links", default=10),
                    "prefer_google_results": _bool("Preferir resultados de busca Google"),
                }
            ),
            read_only=True,
        ),
        ToolSpec(
            "browser_click_link_by_index",
            "Abrir link pelo índice retornado em extract_links ou google_search.",
            _obj({"index": _int("Índice 1-based")}, ["index"]),
        ),
        ToolSpec("browser_get_state", "Observar URL, título e estado do Chrome.", _obj({}), read_only=True),
        ToolSpec(
            "browser_click_text",
            "Clicar no primeiro elemento com o texto visível.",
            _obj({"text": _str("Texto do botão/link")}, ["text"]),
        ),
        ToolSpec(
            "browser_click_selector",
            "Clicar no primeiro elemento CSS selector.",
            _obj({"selector": _str("Seletor CSS")}, ["selector"]),
        ),
        ToolSpec(
            "browser_type",
            "Digitar texto (selector opcional).",
            _obj(
                {
                    "text": _str("Texto a digitar"),
                    "selector": _str("Seletor CSS opcional"),
                },
                ["text"],
            ),
        ),
        ToolSpec(
            "browser_press_key",
            "Pressionar tecla no Chrome.",
            _obj({"key": _str("Ex: Enter, Tab, Escape")}, ["key"]),
        ),
        ToolSpec(
            "browser_wait_for_text",
            "Aguardar texto aparecer na página.",
            _obj(
                {
                    "text": _str("Texto esperado"),
                    "timeout_ms": _int("Timeout em ms", default=10000),
                },
                ["text"],
            ),
            read_only=True,
        ),
        ToolSpec("browser_go_back", "Voltar à página anterior.", _obj({})),
        ToolSpec(
            "browser_extract_text",
            "Extrair título, URL e texto visível da página.",
            _obj({}),
            read_only=True,
        ),
        ToolSpec(
            "browser_extract_article",
            "Extrair artigo limpo (título, descrição, texto principal).",
            _obj({}),
            read_only=True,
        ),
        ToolSpec("browser_screenshot", "Capturar screenshot da página atual.", _obj({}), read_only=True),
        ToolSpec(
            "browser_scroll",
            "Rolar a página.",
            _obj(
                {
                    "direction": _str("up ou down"),
                    "amount": _int("Pixels", default=700),
                }
            ),
            read_only=True,
        ),
        ToolSpec(
            "browser_auth_signup",
            "Criar cadastro quando o usuário pedir e não fornecer credenciais (backend gera senha forte).",
            _obj({"signup_url": _str("URL de cadastro")}, ["signup_url"]),
        ),
        ToolSpec(
            "browser_auth_login",
            "Login somente com autorização segura ativa nesta tarefa. Nunca envie senha nos params.",
            _obj({"login_url": _str("URL de login")}, ["login_url"]),
        ),
        ToolSpec("browser_auth_status", "Verificar sessão/autorização ativa.", _obj({}), read_only=True),
        ToolSpec("browser_auth_logout", "Encerrar sessão autorizada da tarefa.", _obj({})),
        ToolSpec(
            "shell_run",
            (
                f"Executar comando seguro no terminal Linux (whitelist). Workspace da conversa. "
                f"Para software grande use {CODE_AGENT_COMMAND} \"descrição\" ({CODE_AGENT_LABEL}). "
                f"Para correções pequenas prefira file_read/file_edit."
            ),
            _obj({"command": _str("Comando shell")}, ["command"]),
        ),
        ToolSpec(
            "vision_analyze",
            "Visão: descreve screenshot. Use só quando extract_text/article não bastar.",
            _obj({"question": _str("O que analisar na tela")}, ["question"]),
            read_only=True,
        ),
        ToolSpec(
            "exact_solve",
            "Matemática/exatas determinística (contas, equações simples).",
            _obj(
                {
                    "problem": _str("Enunciado do problema"),
                    "context": _str("Contexto opcional"),
                },
                ["problem"],
            ),
            read_only=True,
        ),
        ToolSpec(
            "file_read",
            "Ler arquivo do workspace da conversa com números de linha.",
            _obj(
                {
                    "path": _str("Caminho relativo ao workspace"),
                    "offset": _int("Linha inicial 1-based", default=1),
                    "limit": _int("Máximo de linhas", default=200),
                },
                ["path"],
            ),
            read_only=True,
        ),
        ToolSpec(
            "file_write",
            "Criar/sobrescrever arquivo no workspace.",
            _obj(
                {
                    "path": _str("Caminho relativo"),
                    "content": _str("Conteúdo completo"),
                },
                ["path", "content"],
            ),
        ),
        ToolSpec(
            "file_edit",
            "Substituir trecho exato. Use file_read antes. replace_all se houver várias ocorrências.",
            _obj(
                {
                    "path": _str("Caminho relativo"),
                    "old_string": _str("Texto atual"),
                    "new_string": _str("Texto novo"),
                    "replace_all": _bool("Substituir todas as ocorrências"),
                },
                ["path", "old_string", "new_string"],
            ),
        ),
        ToolSpec(
            "file_append",
            "Anexar conteúdo ao final do arquivo.",
            _obj(
                {"path": _str("Caminho"), "content": _str("Texto a anexar")},
                ["path", "content"],
            ),
        ),
        ToolSpec(
            "glob",
            "Listar arquivos do workspace por padrão glob.",
            _obj(
                {
                    "pattern": _str("Ex: **/*.py"),
                    "path": _str("Subpasta opcional"),
                },
                ["pattern"],
            ),
            read_only=True,
        ),
        ToolSpec(
            "grep",
            "Buscar regex no workspace.",
            _obj(
                {
                    "pattern": _str("Regex"),
                    "path": _str("Subpasta opcional"),
                    "glob": _str("Filtro de nome, ex: *.py"),
                    "output_mode": _str("files_with_matches | content | count"),
                    "case_insensitive": _bool("Ignore case"),
                    "context": _int("Linhas de contexto", default=0),
                },
                ["pattern"],
            ),
            read_only=True,
        ),
        ToolSpec(
            "message_notify_user",
            "Mensagem intermediária não-bloqueante no chat (progresso/resultado parcial).",
            _obj({"text": _str("Texto em markdown curto")}, ["text"]),
            read_only=True,
        ),
        ToolSpec(
            "message_ask_user",
            "Perguntar ao usuário e pausar até confirmação/resposta (confirmation_request).",
            _obj(
                {
                    "question": _str("Pergunta clara"),
                    "kind": _str("question ou confirmation"),
                    "suggested_replies": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Sugestões de resposta",
                    },
                },
                ["question"],
            ),
            read_only=True,
        ),
        ToolSpec(
            "todo_write",
            "Atualizar o Plano Vivo (task steps). Exatamente 1 item in_progress por vez.",
            _obj(
                {
                    "todos": {
                        "type": "array",
                        "description": "Lista de etapas",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": _str("Id estável opcional"),
                                "label": _str("Título curto"),
                                "detail": _str("Detalhe"),
                                "status": _str("pending|in_progress|completed|skipped|failed"),
                            },
                            "required": ["label", "status"],
                        },
                    }
                },
                ["todos"],
            ),
            read_only=True,
        ),
    ]
    return specs


def openai_tools_payload(specs: list[ToolSpec] | None = None) -> list[dict[str, Any]]:
    """Formato tools[] da API OpenAI/DeepSeek."""
    out: list[dict[str, Any]] = []
    for spec in specs or build_tool_specs():
        out.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
        )
    return out


def tool_is_read_only(name: str) -> bool:
    for spec in build_tool_specs():
        if spec.name == name:
            return spec.read_only
    return False


def legacy_tools_schema_from_registry() -> list[dict[str, Any]]:
    """Compat: formato antigo {action, params, use} usado pelo prompt JSON."""
    legacy: list[dict[str, Any]] = []
    for spec in build_tool_specs():
        props = spec.parameters.get("properties") or {}
        sample: dict[str, Any] = {}
        for key, schema in props.items():
            if "default" in schema:
                sample[key] = schema["default"]
            elif schema.get("type") == "integer":
                sample[key] = 1
            elif schema.get("type") == "boolean":
                sample[key] = False
            elif schema.get("type") == "array":
                sample[key] = []
            else:
                sample[key] = ""
        legacy.append({"action": spec.name, "params": sample, "use": spec.description})
    return legacy
