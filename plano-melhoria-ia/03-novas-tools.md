# 03 — Catálogo de Novas Tools

> **Prioridade:** P1 (as tools de arquivo são P0 por serem pré-requisito do doc 06)
> **Inspiração:** suíte `file_*`/`shell_*`/`message_*`/`deploy_*` do Manus + `Read`/`Write`/`Edit`/`Glob`/`Grep`/`Bash`/`TodoWrite`/`Task` do Claude Code
> **Arquivos:** novos `backend/tools/files.py`, `backend/tools/todo.py`, `backend/tools/messaging.py`; evoluir `backend/tools/shell.py`; novo `backend/agent/tools/registry.py`

Todas as tools abaixo entram no **registro central** (§6) com JSON Schema para function calling. Caminhos de arquivo são sempre **relativos ao workspace da task** (`WORKSPACE_PATH/<task_id>/`), com validação anti path-traversal (reaproveitar o padrão de `document_artifacts.py` que já resolve/valida contra a base).

---

## 1. Tools de arquivo (P0 — destravam o doc 06)

| Tool | Params | Comportamento |
|---|---|---|
| `file_read` | `path`, `offset?`, `limit?` | Lê texto com números de linha (formato `cat -n`, padrão Claude Code). Limite ~2.000 linhas/50KB por chamada; binários retornam metadados. Imagens: retorna referência para `vision_analyze`. |
| `file_write` | `path`, `content` | Cria/sobrescreve. Cria diretórios pai. Publica `files_created` e sincroniza `generated_files` (reusar `sync_task_workspace_files`). |
| `file_edit` | `path`, `old_string`, `new_string`, `replace_all?` | Substituição exata de string (padrão Edit do Claude Code / `file_str_replace` do Manus). Falha se `old_string` não for único (a não ser `replace_all`) ou não existir — o erro instrui o modelo a reler o arquivo. **Exigir `file_read` prévio do arquivo na mesma task** (rastrear em `state.py`) para evitar edição às cegas. |
| `file_append` | `path`, `content` | Append simples (logs, todo.md). |
| `glob` | `pattern`, `path?` | Lista arquivos por padrão glob, ordenados por mtime. |
| `grep` | `pattern`, `path?`, `glob?`, `output_mode?`, `-i?`, `context?` | Busca regex no workspace (usar `ripgrep` se disponível, fallback Python). Modos: `files_with_matches` (default), `content`, `count`. |

Regras de segurança: raiz confinada ao workspace da task; negar symlinks para fora; limite de tamanho de escrita (ex.: 2MB); os eventos de atividade usam os rótulos amigáveis já existentes ("Vortax está editando `index.html`").

## 2. Shell com sessões (evolução do `shell_run`)

Hoje `shell_run` é one-shot com timeout de 30s (300s para o code agent) e a detecção de prompt interativo responde sozinha de forma limitada. Adotar o modelo de sessões do Manus:

| Tool | Params | Comportamento |
|---|---|---|
| `shell_exec` | `command`, `session_id?`, `background?`, `timeout?` | Executa no workspace. `background: true` registra processo no `process_registry` (já existe) e retorna imediatamente com `session_id`. |
| `shell_view` | `session_id` | Retorna stdout/stderr acumulados desde a última leitura + estado (running/exited/returncode). |
| `shell_write` | `session_id`, `input`, `press_enter?` | Envia input a processo interativo (substitui a auto-resposta heurística de `INTERACTIVE_PROMPT_PATTERNS`, que fica só como *detecção* para avisar o modelo). |
| `shell_kill` | `session_id` | Encerra processo da sessão (cleanup por task no lifespan já existe — reusar). |

- `shell_run` permanece como alias de `shell_exec` sem sessão (compatibilidade com testes e histórico).
- Manter whitelist + `BLOCKED_PATTERNS` de `shell.py:34-83`. Adicionar à whitelist: `pytest`, `ruff` (se instalado), `jq`, `unzip`, `zip`, `tar`, `sqlite3` (somente leitura via flag), `diff`, `stat`.
- **Portabilidade:** `shell.py` importa `fcntl`/`pty`/`termios` no topo (Linux-only; quebra import no Windows). Mover para import tardio dentro do caminho TTY (bug #9, doc 07).

## 3. Tools de agente

### 3.1 `message_notify_user`
`{ "text": str, "attachments?": [paths] }` — mensagem intermediária não-bloqueante no chat (progresso relevante, resultado parcial). Publica `assistant_message_done` parcial ou novo evento `assistant_notice` (decidir com o frontend; preferir evento novo para não poluir o histórico de mensagens).

### 3.2 `message_ask_user`
`{ "question": str, "suggested_replies?": [str], "kind": "question|confirmation" }` — bloqueia a task em `WAITING_USER` (doc 02 §5). Substitui o fluxo quebrado de `requires_confirmation`.

### 3.3 `finish` → implícito
Com function calling, resposta sem `tool_calls` é a entrega final (doc 01 §3.2). Não é mais uma tool.

### 3.4 `todo_write`
`{ "todos": [{"id?", "label", "detail?", "status": "pending|in_progress|completed|skipped"}] }` — o modelo mantém o Plano Vivo (doc 02 §2). Persistir em `task_steps` com `origin='model'`; re-emitir `task_plan_created`/`task_step_*`. Regra de prompt: exatamente 1 item `in_progress` por vez; atualizar imediatamente ao concluir (não em lote no final).

### 3.5 `task_spawn` (fase 2 — subagentes)
`{ "agent": "researcher|code-reviewer|summarizer", "prompt": str }` — roda subagente (doc 02 §4) e retorna o resumo final como resultado da tool.

## 4. Tools de pesquisa e web

- **`web_search`** — renomeação/generalização de `browser_google_search`: manter o Google CDP como backend, mas permitir provider plugável (ex.: SearXNG local ou API) atrás da mesma tool; o modelo não precisa saber o backend. Já retorna ranqueado/deduplicado — manter.
- **`web_fetch`** (novo) — buscar URL via HTTP (httpx) e converter para markdown/texto limpo **sem abrir o Chrome**: mais rápido e barato para páginas estáticas, docs e APIs JSON. O browser fica para páginas que exigem JS/interação. Reusar a extração de artigo/limpeza existente; salvar fonte com `source_quality_score` como hoje.
- **Suíte `browser_*` atual: manter como está** (navegate/click/type/extract/screenshot/auth já cobrem o essencial).
- **`deep_research`** — manter, mas mover para subagente `researcher` quando a fase 2 chegar (paraleliza as rodadas).

## 5. Tools de entrega e deploy (fase 3)

Inspiradas em `deploy_expose_port`/`deploy_apply_deployment` do Manus — o Vortax já tem Cloudflare Tunnel na infra:

- **`preview_expose`** — expõe temporariamente o preview interno de um projeto web via subdomínio do túnel (ex.: `preview-<task>.cursar.space`), com TTL e teardown automático no fim da task. Resolve a limitação atual de usuários do Firebase não poderem abrir `localhost` (hoje o link é simplesmente censurado por `_redact_local_preview`).
- **`document_render`** — expor a conversão Markdown→PDF já existente (`render_markdown_to_pdf` em `document_artifacts.py`) como tool explícita, em vez do pós-processamento automático escondido em `tool_executor.py:553-584`. O modelo decide quando renderizar.

## 6. Registro central de tools

Novo `backend/agent/tools/registry.py`:

```python
@dataclass
class ToolSpec:
    name: str
    description: str          # vira description do function schema
    parameters: dict          # JSON Schema
    handler: ToolCallable
    permission: Literal["read", "write", "shell", "network", "user"]
    subagent_allowed: set[str] = ...   # quais subagentes podem usar

REGISTRY: dict[str, ToolSpec] = {...}

def build_tool_schemas(context: TaskContext) -> list[dict]:
    """Filtra por contexto (ex.: auth tools só com sessão autorizada) e devolve schemas OpenAI."""
```

- Substitui os três mapas atuais (`TOOLS`, `_BROWSER_METHOD_MAP` em `tool_executor.py:66-92` e `TOOLS_SCHEMA` em `deepseek_client.py:55-171`) — hoje uma tool nova precisa ser registrada em 3 lugares.
- O campo `permission` prepara o item "Permissões por ação" do `PLANO_VORTAX.md §12.2`.
- `execute_tool` continua sendo o único ponto de execução (eventos, screenshot pós-ação, salvamento de fontes), mas resolve pelo registry.

## 7. Critérios de aceite

- [ ] Todas as tools expostas ao modelo vêm de `registry.py`; adicionar tool nova = 1 arquivo.
- [ ] `file_read`/`file_edit`/`file_write`/`glob`/`grep` funcionam confinadas ao workspace, com testes de path traversal.
- [ ] `file_edit` recusa editar arquivo não lido na task e recusa `old_string` ambíguo.
- [ ] `shell_exec` em background + `shell_view` permitem acompanhar um `npm run build` longo sem travar o loop.
- [ ] `message_ask_user` pausa e retoma a task de ponta a ponta (backend + frontend).
- [ ] `web_fetch` extrai artigo de página estática sem abrir o Chrome e salva fonte pontuada.
- [ ] Suíte de testes cobre cada tool nova (padrão dos testes atuais de `test_browser_search_tools.py`).
