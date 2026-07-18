# CHANGELOG — execução do plano de melhoria da IA

## 2026-07-18 — Testes live DeepSeek + fixes

### Feito
- Suite live: `test_deepseek_live`, `test_web_fetch_live`, `test_shell_sessions_live`, `test_native_loop_integration`
- `live_helpers.py` carrega chave do Hermes/env **sem logar**
- Doc: `docs/TESTS_LIVE.md`
- **Bugfix título vazio** (`generate_task_title` max_tokens + fallback)
- **Bugfix agent turn** (folga de tokens + reasoning_effort + retry length)
- **shell_kill** fecha pipes (ResourceWarning)

### Como rodar
`set -a; source ~/.hermes/.env; set +a; VORTAX_LIVE=1 PYTHONPATH=. ./venv/bin/python -m unittest tests.test_deepseek_live -v`

---

## 2026-07-18 — Tools Manus + Claude CLI

### Feito
- **Shell sessions:** `shell_exec` / `shell_view` / `shell_write` / `shell_kill` (`tools/shell_sessions.py`)
- **web_fetch** HTTP sem Chrome + SSRF guard; **web_search** alias
- **validate_project** + **document_render** como tools explícitas
- **file_edit** exige `file_read` prévio na task (Claude Code)
- **grep** prefere ripgrep; whitelist shell ampliada; prompts interativos mais estritos (bug 10)
- Registry + permissions + loop prompt atualizados
- Doc: `docs/TOOLS_MANUS_CLAUDE.md` · testes `test_manus_claude_tools.py`

### Ainda falta
- task_spawn subagentes; preview_expose; unificar registry único no path legado JSON

---

## 2026-07-18 — Mobile front + status consolidado

### Feito
- Front **mobile-first polish**: ChatShell drawer (Esc, body lock, fecha ao escolher chat), viewport-fit/safe-area, touch ≥44px, composer sticky, detail full-screen, onboarding 1 col, landscape compacto.
- Docs: `docs/MOBILE_E_STATUS.md` (feito + falta + checklist QA).
- Arquivos: `frontend/index.html`, `ChatShell.jsx`, `App.jsx`, `index.css`.

### Ainda falta (ver doc)
- Deploy hosting + QA real iOS/Android; PWA; focus trap no drawer; resto Fases 2–4 do plano IA.

---

## 2026-07-18 — Fase 1 (núcleo) + docs + push main

### Feito

- **`backend/agent/`** novo:
  - `tools/registry.py` — 31 tools em JSON Schema OpenAI
  - `gates.py` — `ResearchSourcesGate`, `CycleGuardGate`, prefixo `[GATE:*]`
  - `state.py` — contadores/stagnação/fingerprint de tool
  - `loop.py` — loop nativo function calling + paralelo read-only + `todo_write` / `message_*`
- **`request_agent_turn`** + streaming SSE (`assistant_message_delta`) em `deepseek_client.py`
- **`run_agent_task`**: `USE_NATIVE_TOOLS` (default true) com fallback JSON legado
- **Usage na API**: `GET /api/tasks/{id}` → `tokens_used`, `estimated_cost`, `usage`
- **Defaults**: `DEEPSEEK_STREAMING=true`, brain=V4 Pro, flash para título
- **Testes**: `test_agent_registry_and_gates`, `test_native_agent_turn` (+ suíte fase 0)
- App version **0.2.0-local**

### Como desligar o nativo (rollback)

```env
USE_NATIVE_TOOLS=false
DEEPSEEK_STREAMING=false
```

### Próximo (Fase 1 residual + Fase 2/3)

- Portar pré-pesquisas e gates project/web validation para o loop nativo
- Encolher `agent_runner.py` para casca fina
- Prompts modulares `agent/prompts/`
- `shell_exec` sessions

---

## 2026-07-18 — Fase 0 (parcial) + tools de arquivo + backlog PLANO §12

### Feito

- **Validação API DeepSeek V4 Pro** com `tools` schema: ok (`deepseek-v4-pro` + `deepseek-v4-flash` listados).
- **Camadas de modelo** em `config.py`: `DEEPSEEK_MODEL_BRAIN=deepseek-v4-pro`, `DEEPSEEK_MODEL_FAST=deepseek-v4-flash`, `pick_model()`.
- **Flags** `DEEPSEEK_STREAMING`, `USE_NATIVE_TOOLS`, `PARALLEL_TOOL_CALLS` (default nativo desligado até Fase 1).
- **Bug 1** confirmation: pausa + `POST /confirm` em vez de `DeepSeekError`.
- **Bug 2** fontes: `_inject_*` não grava mais bloco de fontes no histórico persistente (só no loop).
- **Bug 3** vertex hardcoded: interpolação `CODE_AGENT_COMMAND/LABEL` no system prompt + schema.
- **Bug 4** branch morto document research: `blocked` → continue.
- **Bug 5** quality_score fixo 80 → `source_quality_score`.
- **Bug 6** detecção code agent unificada em `services/code_agent.py`.
- **Bug 7** prompt legado de `request_deepseek_response` atualizado.
- **Bug 9** `shell.py`: imports `fcntl/pty/termios` tardios.
- **Tools de arquivo** P0: `file_read/write/edit/append`, `glob`, `grep` (`tools/files.py` + executor + schema).
- **`llm_usage` table** + hook de persistência (best-effort) nas chamadas DeepSeek.
- **PLANO_VORTAX §12** backlog (export, replan mid-run, métricas, permissões, artefatos) entregue no commit `b0a5459` / stack local.

### Ainda pendente (próximo)

- Fase 1: loop nativo com function calling + streaming (`USE_NATIVE_TOOLS=true`).
- Fase 1: `agent/loop.py`, `gates.py`, registry central.
- Bugs 8/10/11/12 e shell sessions `shell_exec/view/write/kill`.
- Prompts modulares `backend/agent/prompts/`.
- Subagentes researcher/code-reviewer.

### Testes

```bash
cd backend && PYTHONPATH=. ./venv/bin/python -m unittest \
  tests.test_file_tools tests.test_plan_replan tests.test_session_export \
  tests.test_permissions_and_metrics tests.test_parallel_subtasks -v
```
