# CHANGELOG — execução do plano de melhoria da IA

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
