# 00 — Diagnóstico da Arquitetura Atual

> Leitura obrigatória antes de qualquer implementação. Todos os caminhos e linhas foram verificados no commit `f3304cc` (branch `main`).

---

## 1. Visão geral do fluxo atual

```
Usuário → POST /api/tasks → run_agent_task (backend/services/agent_runner.py)
   ├── /remember → user_memory
   ├── _ensure_plan → planner Groq llama-3.3-70b (fallback DeepSeek) → task_steps (Plano Vivo)
   ├── Roteador heurístico:
   │     ├── is_exact_prompt() → exact_solve + resposta direta
   │     ├── should_answer_directly() → chat direto sem tools
   │     └── senão → loop ReAct
   ├── Pré-pesquisas automáticas (software / documento / pessoas / deep research)
   └── Loop ReAct (até MAX_ITERATIONS=30):
         ├── request_deepseek_action() → JSON {"action": ..., "params": ...}
         ├── execute_tool() (backend/tools/tool_executor.py)
         ├── resultado vira mensagem role="user" ("Resultado da ferramenta: {...}")
         └── "finish" passa por gates (validação, documento, relatório, fontes)
```

## 2. Componentes principais

| Componente | Arquivo | Observação |
|---|---|---|
| Loop ReAct | `backend/services/agent_runner.py` (2.062 linhas) | Monolítico; loop, gates, pesquisas e entrega no mesmo arquivo |
| Cliente DeepSeek | `backend/services/deepseek_client.py` | `deepseek-v4-flash`, sem function calling, sem streaming |
| Executor de tools | `backend/tools/tool_executor.py` (892 linhas) | Muita lógica de negócio embutida (PDF, GitHub, preview) |
| Shell seguro | `backend/tools/shell.py` | Whitelist + PTY; usa `fcntl`/`pty`/`termios` (Linux-only) |
| Browser | `backend/tools/browser.py` (1.065 linhas) | Chrome CDP via Playwright, pool por task |
| Contexto | `backend/services/context_manager.py` | Estimativa de tokens por caracteres; limite 24.000 |
| Plano Vivo | `backend/services/task_plan_store.py` | Etapas casadas por `tool_hint`, não pelo modelo |
| Memória | `backend/services/user_memory.py` | SQLite `user_memories`, injeção no system prompt |
| Pesquisa profunda | `backend/services/deep_research.py` | N rodadas busca+leitura+síntese |
| Heurísticas de intenção | `document_intent.py`, `research_policy.py`, `web_validation.py`, `document_artifacts.py`, `github_repos.py` | Dezenas de regex em português para classificar pedidos |

## 3. Pontos fortes (preservar)

- **Contrato de eventos WebSocket sólido** (`stream_contract.py`): replay persistido, tipos desconhecidos degradam com segurança.
- **Validação pós-desenvolvimento com gate de `finish`**: `web_validation` + `project_validation` impedem entrega com bug — este é o diferencial do produto e deve ser mantido e ampliado.
- **Pool de browser por task** com bloqueio de telas sensíveis e política de fontes/qualidade.
- **Boa cobertura de testes** (27 arquivos em `backend/tests/`).
- **Cache efêmero cross-task de pesquisa** (`ephemeral_cache.py`) e biblioteca de snippets (`code_snippet_library.py`).
- **Sanitização de segredos** (`safe_diagnostics.py`, `credential_store.py`).

## 4. Fraquezas estruturais (o que este plano ataca)

### 4.1 O cérebro decide por "JSON no texto"
`request_deepseek_action` (`deepseek_client.py:511`) pede um objeto JSON dentro de `content` com `response_format: json_object` e faz parsing manual (`_extract_balanced_json_object`) + rodada extra de "repair" quando quebra. A API do DeepSeek suporta `tools`/`tool_calls` nativos — mais confiável, mais barato e elimina o repair.

### 4.2 Resultados de tool viram mensagens `user`
`agent_runner.py:2228-2233` injeta `"Resultado da ferramenta: {json}"` com `role="user"`. Consequências:
- o modelo confunde instrução do usuário com observação de ferramenta;
- filtros por prefixo de string (`_latest_user_prompt`, `agent_runner.py:439-453`) são frágeis;
- os "gates" também falam com o modelo por mensagens `user` sintéticas ("Controle automatico de..."), competindo com o pedido real.

### 4.3 System prompt monolítico
`_build_agent_system_prompt` (`deepseek_client.py:388-508`) tem ~110 linhas de regras misturadas (pesquisa de pessoas, e-commerce, PDF, GitHub, validação...). Tudo é enviado em toda iteração, para qualquer tipo de tarefa. O leak do Manus mostra o padrão certo: prompt central curto + módulos anexados por contexto.

### 4.4 O agente não tem mãos para código
Não existem tools de arquivo (`file_read`, `file_write`, edição). Para corrigir uma vírgula num HTML gerado, o fluxo é: chamar `vertex` de novo (custo alto, até 3x por `MAX_CODE_AGENT_CALLS`), com um comando aumentado por ~500 linhas de heurísticas em `tool_executor.py` (`_augment_code_agent_command_for_quality` e afins). O modelo nunca vê o conteúdo dos arquivos que "criou".

### 4.5 Heurísticas regex demais decidindo fluxo
`document_intent`, `research_policy`, `web_intent_from_command`, `people_research_profile`, `is_exact_prompt`, `should_answer_directly`, `_code_agent_creation_intent`… são centenas de regex PT-BR que roteiam o agente antes/à revelia do modelo. Falham em inglês, em sinônimos, e são caras de manter. Com V4 Pro + function calling, a maior parte dessas decisões pode ser do modelo (ou de um classificador barato de 1 chamada).

### 4.6 Contexto pequeno e mal contabilizado
`CONTEXT_TOKEN_LIMIT=24000` com estimativa por caracteres (`context_manager.py`), enquanto o campo `usage` retornado pela API (tokens reais) é ignorado. Modelos V4 têm janela muito maior; o limite atual força compactação prematura e perde contexto de projeto.

### 4.7 Sem paralelismo, sem subagentes, sem streaming
- Uma tool por iteração, sempre sequencial (pesquisas largas demoram).
- A resposta final não é transmitida token a token (`stream: False` em todas as chamadas) — o evento `assistant_message_delta` existe no contrato mas o planner não o alimenta.
- Não há subagentes (padrão Task do Claude Code) para pesquisa/validação paralela.

### 4.8 Confirmação de ação está quebrada
`agent_runner.py:2149-2156`: quando o modelo marca `requires_confirmation: true`, o backend publica `confirmation_request` e em seguida **levanta `DeepSeekError`**, matando a task ("fluxo de confirmacao sera ligado no proximo bloco"). Detalhes no [07-correcao-de-bugs.md](07-correcao-de-bugs.md).

### 4.9 Duplicação de lógica do code agent
A detecção "este comando chama o vertex?" existe em três lugares com implementações diferentes: `agent_runner.py:456-498`, `tool_executor.py:240-330`, `shell.py:19-21`. `LEGACY_CODE_AGENT_COMMANDS` está definida em dois módulos. Risco de drift já visível.

### 4.10 Segurança / prompt injection
Texto extraído de páginas web entra no histórico sem delimitação nem instrução de desconfiança — uma página maliciosa pode injetar "instruções" que o planner obedece. O backend público via túnel segue sem autenticação (risco já registrado no `PLANO_VORTAX.md §11`).

## 5. Inventário de tools atuais

| Tool | Origem | Estado |
|---|---|---|
| `browser_navigate`, `browser_google_search`, `browser_extract_*`, `browser_click_*`, `browser_type`, `browser_press_key`, `browser_scroll`, `browser_screenshot`, `browser_wait_for_text`, `browser_go_back`, `browser_get_state` | `browser.py` | OK, manter |
| `browser_auth_signup/login/status/logout` | `browser.py` + `credential_store` | OK, manter |
| `shell_run` | `shell.py` | Única porta para arquivos e código; sobrecarregada |
| `vision_analyze` | `vision.py` (Groq/Llama 4 Scout) | OK, manter |
| `exact_solve` | `exact.py` | OK, manter |
| `finish` | virtual | Vira `message_result` no novo desenho |

**Não existem:** tools de arquivo, tools de busca em arquivos, shell com sessão/background, todo/plano controlado pelo modelo, pergunta ao usuário, deploy/exposição de porta, subagentes. Ver [03-novas-tools.md](03-novas-tools.md).
