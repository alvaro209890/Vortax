# 02 — Nova Arquitetura do Agente (loop, planejamento, subagentes)

> **Prioridade:** P0
> **Inspiração:** agent loop do Manus (leak) + Task/TodoWrite/plan mode do Claude Code
> **Arquivos principais:** `backend/services/agent_runner.py` (quebrar), novos módulos em `backend/agent/`

---

## 1. Objetivo

Substituir o loop monolítico de `agent_runner.py` (2.062 linhas) por um núcleo de agente pequeno e módulos claros, seguindo o padrão dos agentes de referência:

```
backend/agent/
├── loop.py            # núcleo: while → chamar modelo → executar tools → observar → repetir
├── state.py           # estado da task: fase, todo list, contadores, artefatos
├── gates.py           # gates de finalização (validação, fontes, documentos) como módulo único
├── prompts/           # system prompt modular (doc 04)
├── tools/registry.py  # registro central de tools com schema (doc 03)
└── subagents.py       # execução de subagentes (fase 2)
```

`agent_runner.py` vira uma casca fina de compatibilidade que chama `backend/agent/loop.py` (mantém a assinatura `run_agent_task` usada por `api/tasks.py`).

## 2. O agent loop (padrão Manus, adaptado)

O leak do Manus descreve o loop canônico que o Vortax já quase segue, mas com três diferenças importantes a adotar:

1. **Analisar evento → selecionar UMA tool → executar → observar → iterar** — já existe, manter.
2. **O plano é do modelo, não de heurística.** Hoje o Plano Vivo é gerado pela Groq e as etapas são "casadas" por `tool_hint` com heurísticas (`_action_plan_hint`, `_real_completion_evidence` em `agent_runner.py:98-320`). No novo desenho o modelo mantém o próprio plano com a tool `todo_write` (ver doc 03 §3.4): ele cria as etapas, marca `in_progress`/`completed` e o backend apenas persiste e re-emite os eventos `task_step_*` existentes. As heurísticas de "evidência real" viram validadores (podem rebaixar um passo marcado como completo sem evidência, mas nunca adivinham).
3. **Mensagens ao usuário são tools.** Adotar `message_notify_user` (não bloqueia) e `message_ask_user` (bloqueia aguardando resposta) como no Manus. Isso conserta de vez o fluxo de confirmação quebrado (`agent_runner.py:2149-2156` — ver bug #1 no doc 07): pedir confirmação passa a ser `message_ask_user` com `suggested_replies`, o backend publica `confirmation_request`, pausa a task (`store.is_paused` já existe) e retoma quando `POST /api/control/{task_id}/confirm` responder.

### 2.1 Fases explícitas do loop

Estado por task (persistido em `state.py`), inspirado no ciclo Manus `understand → plan → execute → verify → deliver`:

```
INTAKE      → classificação de intenção (1 chamada Flash, doc 04 §5) + roteio rápido
PLAN        → modelo cria/atualiza todo list (tarefas não-triviais)
EXECUTE     → loop de tools
VERIFY      → gates de validação (gates.py) — hoje espalhados no meio do loop
DELIVER     → resposta final em streaming + anexos (cards de arquivo)
```

Os "gates" atuais (revisão de código, documento obrigatório, mínimo de fontes — `agent_runner.py:1977-2144`) são movidos para `gates.py` com uma interface única:

```python
class DeliveryGate(Protocol):
    def check(self, ctx: TaskContext) -> GateResult  # ok | retry(instrução) | blocked(motivo)
```

O loop consulta a lista de gates registrados antes de aceitar a resposta final. A instrução de retry volta ao modelo como mensagem de sistema estruturada (`role: "system"` curta, prefixo estável `[GATE]`), não como mensagem `user` disfarçada.

### 2.2 Controle de derrapagem

- **Detecção de ciclo melhor:** hoje só detecta 3 ações *idênticas* seguidas (`agent_runner.py:1931-1949`). Trocar por: (a) mesma tool com mesmos params 2x seguidas → aviso ao modelo; (b) 3x → forçar mudança de estratégia com mensagem de sistema; (c) janela de 8 iterações sem nenhum progresso observável (nenhum arquivo novo, fonte nova ou passo de todo concluído) → encerrar com o melhor resultado parcial + explicação honesta.
- **Orçamentos por task:** `MAX_ITERATIONS` (manter 30), `MAX_CODE_AGENT_CALLS` (manter 3), novo `MAX_TOOL_FAILURES_PER_TOOL=3` e orçamento de tokens por task (via `llm_usage`, doc 01 §3.4) com aviso ao usuário ao atingir 80%.

## 3. Módulos de conhecimento por contexto (padrão Manus)

O Manus anexa "módulos" ao prompt conforme o contexto (Planner/Knowledge/Datasource). Equivalente Vortax (detalhado no doc 04):

- o system prompt central encolhe para ~60 linhas;
- regras de **pesquisa de pessoas**, **criação de sites**, **documentos/PDF**, **análise de GitHub** viram módulos anexados só quando o classificador de intenção (ou uma tool chamada) indica o contexto;
- as pré-pesquisas automáticas (`_inject_pre_research_if_needed`, `_inject_document_research_if_needed`, `_inject_people_research_if_needed` — `agent_runner.py:1187-1681`) deixam de ser hardcoded: viram uma única rotina `pre_research(profile)` acionada pelo classificador, e o modelo pode também pesquisar por conta própria.

## 4. Subagentes (fase 2)

Padrão Task do Claude Code: o cérebro delega trabalho isolado a um subagente com contexto próprio e recebe só o resumo. Aplicações no Vortax:

| Subagente | Modelo | Uso |
|---|---|---|
| `researcher` | V4 Pro | Pesquisa larga em paralelo (3 fios de busca+leitura simultâneos no lugar do deep_research sequencial) |
| `code-reviewer` | V4 Pro | Revisão do diff/projeto gerado antes da entrega (doc 06 §5) |
| `summarizer` | V4 Flash | Compactação de contexto e resumo de fontes longas |

Infra: `subagents.py` roda um mini-loop com o próprio registry de tools mas subconjunto permitido (researcher só browser; reviewer só leitura de arquivos), com orçamento próprio de iterações, publicando atividade agregada no `EventBus` ("Pesquisando em 3 frentes..."). Requer o browser pool com múltiplas instâncias (`BROWSER_POOL_MAX_INSTANCES=4` já existe).

## 5. Interrupção, pausa e retomada

- Manter `store.is_stopped/is_paused` e o replay de eventos.
- Novo: `message_ask_user` cria um estado `WAITING_USER` persistido — se o backend reiniciar, a task retoma do ponto (o histórico já é reconstruível pelos eventos).
- Novo endpoint `POST /api/control/{task_id}/answer` para responder perguntas do agente (corpo: `{"answer": "..."}`), distinto de nova mensagem de chat.

## 6. Passos de implementação

1. Criar `backend/agent/` com `loop.py` mínimo funcionando com as tools atuais + function calling (junto com doc 01).
2. Migrar gates para `gates.py` um a um, com os testes atuais (`test_agent_task_plan_context.py`, `test_research_policy.py`) apontando para o novo módulo.
3. Implementar `todo_write` + adaptação do `task_plan_store` (o schema `task_steps` atual serve; adicionar origem `model`).
4. Implementar `message_notify_user`/`message_ask_user` + endpoint de resposta + evento `confirmation_request` reaproveitado.
5. Detecção de derrapagem e orçamentos.
6. (Fase 2) `subagents.py` com `researcher` primeiro.

## 7. Critérios de aceite

- [ ] `agent_runner.py` reduzido a compatibilidade (< 100 linhas); lógica em `backend/agent/`.
- [ ] Task com `requires_confirmation` pausa e retoma em vez de morrer com erro.
- [ ] Plano Vivo atualizado pelo próprio modelo via `todo_write`; frontend continua renderizando sem mudanças.
- [ ] Pergunta do agente ao usuário aparece no chat e a resposta retoma a execução.
- [ ] Loop nunca repete a mesma ação falha mais de 3 vezes.
- [ ] Todos os eventos do contrato atual (`stream_contract.py`) continuam sendo emitidos.
