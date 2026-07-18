# Tools Vortax — alinhamento Manus leak + Claude CLI

**Data:** 2026-07-18  
**Commit alvo:** main (tools phase 2)

## Inspiração

| Fonte | Padrões adotados |
|-------|------------------|
| **Manus (leak)** | `file_*`, `shell_exec/view/write/kill` com sessões, `message_*`, `todo`, fetch HTTP sem browser, verify step |
| **Claude Code / CLI** | `Read`→`Edit` obrigatório, `Glob`/`Grep` (prefer rg), `Bash` com timeout/background, `WebFetch`, TodoWrite, validação antes de entregar |

## Suite atual (registry + executor)

### Arquivos (Claude Read/Write/Edit + Manus file_*)
| Tool | Notas |
|------|--------|
| `file_read` | Linhas numeradas; marca arquivo como lido na task |
| `file_write` / `file_append` | Workspace confinado |
| `file_edit` | **Recusa se não houve `file_read` na task** (anti edição cega) |
| `glob` / `grep` | `grep` usa **ripgrep** se instalado, senão Python |

### Shell (Manus sessions + Claude Bash)
| Tool | Notas |
|------|--------|
| `shell_run` | One-shot (compat) |
| `shell_exec` | `background=true` → `session_id`; timeout promove a background |
| `shell_view` | Delta de stdout/stderr |
| `shell_write` | Input interativo (sem auto-reply frouxo) |
| `shell_kill` | SIGTERM/SIGKILL + cleanup |

Whitelist ampliada: `pytest`, `ruff`, `jq`, `zip`/`tar`, `rg`, `pnpm`, `diff`, `stat`, …

### Web
| Tool | Notas |
|------|--------|
| `web_search` | Alias de `browser_google_search` |
| `web_fetch` | HTTP+httpx, HTML→texto, SSRF block, salva fonte |
| `browser_*` | Mantidos para JS/login/interação |

### Agente / entrega
| Tool | Notas |
|------|--------|
| `message_notify_user` / `message_ask_user` | Loop nativo |
| `todo_write` | Plano Vivo |
| `validate_project` | Validação explícita do workspace |
| `document_render` | MD → PDF sob demanda |
| `vision_analyze` / `exact_solve` | Mantidos |

## Arquivos novos/alterados

- `backend/tools/shell_sessions.py` (novo)
- `backend/tools/web_fetch.py` (novo)
- `backend/tools/agent_tools.py` (novo)
- `backend/tools/files.py` (read-tracking + rg)
- `backend/tools/shell.py` (whitelist + prompts interativos mais estritos)
- `backend/tools/tool_executor.py` (dispatch)
- `backend/agent/tools/registry.py` (schemas OpenAI)
- `backend/agent/loop.py` (system prompt menciona as tools)
- `backend/services/permissions.py` (capabilities)
- `backend/tests/test_manus_claude_tools.py`

## Ainda falta (próximo)

- [ ] `task_spawn` subagentes (researcher / code-reviewer)
- [ ] `preview_expose` via tunnel
- [ ] Unificar 100% o registry como única fonte (remover TOOLS_SCHEMA legado no path JSON)
- [ ] Frontend: evento `assistant_notice` separado de `assistant_message_done` para notify
- [ ] Testes e2e live shell_exec background com npm

## Como testar

```bash
cd backend
PYTHONPATH=. ./venv/bin/python -m unittest tests.test_manus_claude_tools -v
```
