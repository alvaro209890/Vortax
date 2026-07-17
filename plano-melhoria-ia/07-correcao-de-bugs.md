# 07 — Correção de Bugs e Inconsistências Encontrados

> **Prioridade:** P0 — a maioria pode ser corrigida antes/independente da refatoração grande.
> Todos verificados no código em `main` (commit `f3304cc`). Ordenados por gravidade.

---

## Bug 1 — `requires_confirmation` mata a task com exceção
**Onde:** `backend/services/agent_runner.py:2149-2156`
**O que acontece:** quando o planner responde `requires_confirmation: true`, o backend publica `confirmation_request` e imediatamente levanta `DeepSeekError("Planner pediu confirmacao; fluxo de confirmacao sera ligado no proximo bloco.")` — a task inteira termina em erro para o usuário.
**Correção curta (antes da refatoração):** em vez de raise, pausar a task (`store` já tem pause) e aguardar `POST /api/control/{task_id}/confirm` (endpoint em `api/control.py`); em negação, devolver mensagem ao modelo pedindo alternativa.
**Correção definitiva:** tool `message_ask_user` (doc 02 §2 / doc 03 §3.2).

## Bug 2 — Contexto de fontes duplicado a cada iteração
**Onde:** `agent_runner.py:1923-1925` combinado com `1187-1352`
**O que acontece:** as pré-pesquisas retornam o histórico já com o bloco "Fontes ja abertas..." (`_history_with_research_context`); dentro do loop, **a cada iteração**, `action_history` chama `_history_with_research_context` de novo sobre esse histórico — o bloco de fontes (que pode ter 8 fontes × 520 chars) aparece duplicado, e cresce o custo de todas as iterações.
**Correção:** montar os blocos dinâmicos (plano, fontes, auth) uma única vez por iteração a partir do histórico *limpo*, nunca salvá-los no histórico persistente. (A refatoração do doc 02 resolve estruturalmente; o hotfix é remover a chamada de dentro das funções `_inject_*` OU do loop.)

## Bug 3 — `TOOLS_SCHEMA` e system prompt com "vertex" hardcoded
**Onde:** `backend/services/deepseek_client.py:154, 424-487` (dezenas de menções literais a "vertex"/"Vertex")
**O que acontece:** `CODE_AGENT_COMMAND`/`CODE_AGENT_LABEL` são configuráveis (`config.py:58-59`), e `tool_executor`/`shell` os respeitam — mas o prompt que ensina o modelo a chamar o agente usa "vertex" literal. Se o comando mudar, o modelo continuará chamando `vertex` e tudo quebra silenciosamente.
**Correção:** interpolar `settings.CODE_AGENT_COMMAND` no schema/prompt (f-string no módulo já importa `settings`).

## Bug 4 — Branch morto na pesquisa de documentos
**Onde:** `agent_runner.py:1477-1483`
```python
if isinstance(navigate_result, dict) and navigate_result.get("blocked"):
    article = await bt.extract_article(task_id=task_id)
else:
    article = await bt.extract_article(task_id=task_id)
```
Os dois ramos são idênticos — página bloqueada (CAPTCHA/anti-bot) é tratada como página boa e o texto do bloqueio pode ser salvo como "fonte" com score 80.
**Correção:** quando `blocked`, pular o resultado (continue) e tentar o próximo, como o executor faz em `tool_executor.py:959-971`.

## Bug 5 — Fontes de pré-pesquisa com score fixo 80
**Onde:** `agent_runner.py:1322` (pre-research), `1614` e `1645` (people research)
**O que acontece:** essas rotinas salvam `quality_score: 80` fixo, enquanto o fluxo normal usa `source_quality_score(url, title, text)` (`agent_runner.py:1369`). Fontes ruins ganham score alto e passam nos gates de pesquisa (`min_quality=50`), furando a política de qualidade.
**Correção:** usar `source_quality_score` nos três pontos.

## Bug 6 — Detecção do code agent triplicada e divergente
**Onde:** `agent_runner.py:456-498` (`_is_code_agent_name` + parsing próprio), `tool_executor.py:240-330` (`_is_code_agent_token` + `_split_code_agent_command`), `shell.py:19-21`; `LEGACY_CODE_AGENT_COMMANDS` definida 2x (`agent_runner.py:456`, `tool_executor.py:42`)
**O que acontece:** três implementações de "este comando chama o vertex?" com regras levemente diferentes (uma varre todos os tokens, outra só o primeiro após `cd X &&`). Um comando pode ser tratado como code-agent num módulo e não no outro → validações/gates inconsistentes.
**Correção:** módulo único `backend/services/code_agent.py` com `is_code_agent_command`, `split_command`, `normalize_invocation` e as constantes; os três módulos importam dele.

## Bug 7 — Prompt legado enganoso em `request_deepseek_response`
**Onde:** `deepseek_client.py:290-327`
**O que acontece:** o system prompt diz "voce ainda nao pode controlar ferramentas reais do PC... automacao sera ligada no proximo bloco" — texto do MVP antigo. Se algum caminho ainda usa essa função, o modelo nega capacidades que o produto tem.
**Correção:** verificar chamadas (`grep request_deepseek_response`); remover a função ou atualizar o prompt.

## Bug 8 — Gates e tool results como mensagens `user` + filtro por prefixo frágil
**Onde:** `agent_runner.py:2228-2233` (tool result como user), `439-453` (`_latest_user_prompt` filtra por 6 prefixos literais)
**O que acontece:** qualquer novo gate que esqueça de registrar seu prefixo em `_latest_user_prompt` faz o "último pedido do usuário" virar uma instrução interna — e os perfis de pesquisa/documento passam a ser calculados sobre texto de gate. Além de confundir o modelo (instrução do usuário vs. observação).
**Correção definitiva:** roles nativos (doc 01 §3.2). **Hotfix:** marcar mensagens sintéticas com metadado no histórico interno (lista de dicts própria com `synthetic: true`) em vez de detectar por prefixo de string.

## Bug 9 — `shell.py` não importa em Windows
**Onde:** `backend/tools/shell.py:3-11` (`import fcntl, pty, termios` no topo)
**O que acontece:** em ambiente de desenvolvimento Windows (este repositório é editado em `C:\GIS\Vortax`), qualquer import de `shell.py` explode com `ModuleNotFoundError: fcntl` — impossibilitando rodar a suíte de testes local fora do Linux.
**Correção:** import tardio dentro das funções TTY (só o caminho do code agent usa PTY) + skip dos testes TTY quando `sys.platform == "win32"`.

## Bug 10 — Auto-resposta a prompts interativos com regex frouxa
**Onde:** `shell.py:118-137` (`INTERACTIVE_PROMPT_PATTERNS`)
**O que acontece:** padrões como `\w+.*\?\s*$` marcam praticamente qualquer linha terminada em `?` como prompt interativo — output normal do vertex (ex.: "Deseja que eu detalhe algo mais?") pode disparar resposta automática indevida no TTY.
**Correção:** restringir a detecção a quando o processo está *aguardando input* (stdin do PTY sem consumo, sem output novo por N segundos) E o texto casa com padrão; com a tool `shell_write` (doc 03 §2), rebaixar a auto-resposta para notificação ao modelo decidir.

## Bug 11 — Contabilidade de contexto ignora usage real
**Onde:** `context_manager.py` (estimativa por chars) vs. `usage` descartado nas chamadas
**Correção:** doc 05 §1.2 (fator de calibração). Registrado aqui porque é um erro atual mensurável, não só melhoria.

## Bug 12 — Prompt injection sem defesa
**Onde:** todo texto de `browser_extract_*` entra no histórico sem delimitação (`_history_with_research_context`, resultados de tool)
**Correção:** doc 04 §6 (delimitadores + instrução + sanitização + teste).

## Inconsistências menores (arrumar de passagem)

| # | Onde | Problema | Ação |
|---|---|---|---|
| M1 | `config.py:30` vs `deepseek_client.py:518` | `DEEPSEEK_TEMPERATURE=0.1` configurável, mas ações usam `0.0` hardcoded | Decidir um; remover o outro |
| M2 | `config.py:17` (`ALLOW_NO_AUTH=False`) vs README ("`ALLOW_NO_AUTH=true`") | Documentação diverge do default | Alinhar README/.env.example |
| M3 | `deepseek_client.py:232-234` | `_json_error` recebe `exc` e ignora (dois ramos idênticos) | Simplificar assinatura |
| M4 | `agent_runner.py:1178` | `import asyncio` dentro de função (já importado no topo) | Remover |
| M5 | `tool_executor.py:121` | Mensagem fixa cita "vertex_progress e web_validation_result" mesmo p/ projetos não-web | Texto condicional |
| M6 | `shell.py:83` | `BLOCKED_RM_PATTERN` compilado e nunca usado (verificar com grep) | Usar ou remover |
| M7 | `PLANO_VORTAX.md` §10 | Comando de teste usa `./venv/` e `./.venv/` em docs diferentes | Padronizar |
| M8 | `browser_pool` release duplo (`_cleanup_project_runtime` + `finally` de `run_agent_task`) | Idempotente hoje, mas frágil | Comentar contrato ou centralizar |

## Critérios de aceite

- [ ] Cada bug com teste de regressão dedicado (exceto M*).
- [ ] Bug 1: task com confirmação completa o ciclo pausar→confirmar→continuar.
- [ ] Bug 2: histórico enviado ao modelo contém no máximo 1 bloco de fontes por iteração (assert em teste com mock).
- [ ] Bug 9: `python -c "import tools.shell"` funciona em Windows; suíte roda com skips corretos.
- [ ] Suíte completa verde após cada correção individual (commits separados por bug).
