# 08 — Roadmap de Execução

> Ordem pensada para: (1) cada fase entregar valor sozinha, (2) testes verdes sempre, (3) o risco grande (mudança de protocolo do modelo) acontecer cedo mas isolado.

---

## Fase 0 — Preparação e correções imediatas (1-2 dias de agente)

Sem mudança de arquitetura; pode ser feita hoje.

1. [x] **Validar o DeepSeek V4 Pro**: chamada real com `tools` OK (`deepseek-v4-pro` / `deepseek-v4-flash`); defaults BRAIN=Pro em config/.env.example.
2. [x] **Bugs P0 rápidos** (doc 07): Bug 3, 4, 5, 6 (`code_agent.py`), 7, 9; M1 (temp 0.0 alinhado). Restam M2–M8 parciais.
3. [x] **Bug 1 (hotfix)**: confirmação pausa e espera `POST /confirm`.
4. [x] **Bug 2 (hotfix)**: bloco de fontes só no loop (não nas `_inject_*`).
5. [x] Tabela `llm_usage` + `record_llm_usage()` + métricas em memória.

**Gate de saída:** suíte dos novos testes verde (2026-07-18). Baseline em tasks reais: pendente (backend offline neste desktop sem `/media/server` — fallback local ativo).

**Extra adiantado da Fase 2:** tools `file_read/write/edit/append/glob/grep` já no executor + schema (flags nativas ainda off).

## Fase 1 — Cérebro novo (docs 01 + 02 núcleo) (3-5 dias)

1. [x] `backend/agent/loop.py` com function calling nativo no **V4 Pro**, streaming opcional, roles `assistant.tool_calls` / `role:"tool"`.
2. [x] Registro central `backend/agent/tools/registry.py` (browser/shell/vision/exact/files + message_* + todo_write).
3. [x] Gates em `backend/agent/gates.py` com padrão `[GATE:*]`.
4. [x] Camadas `pick_model` (título/sumário no Flash).
5. [x] `agent_runner.run_agent_task` escolhe nativo (`USE_NATIVE_TOOLS`) com **fallback legado** se falhar.

**Entregue 2026-07-18:** defaults `USE_NATIVE_TOOLS=true`, `DEEPSEEK_STREAMING=true`; `GET /api/tasks/{id}` com `tokens_used`/`estimated_cost`; tools `message_notify_user` / `message_ask_user` / `todo_write` no loop nativo.

**Ainda afinar (paridade total):** pré-pesquisas automáticas legadas no path nativo; agent_runner ainda grande (não <100 linhas); validação project/web gates no path nativo.

**Gate de saída:** paridade funcional com o fluxo atual (site, pesquisa, PDF, pessoa, exatas — os 5 cenários canônicos), custo/latência comparados ao baseline, streaming visível no chat.

## Fase 2 — Mãos para código (docs 03 §1-2 + 06) (3-5 dias)

1. Tools de arquivo: `file_read`, `file_write`, `file_edit`, `glob`, `grep` (+ testes de confinamento).
2. `shell_exec/view/write/kill` com sessões e background.
3. Módulo de prompt `coding.md` com a matriz de decisão cérebro × vertex.
4. Parser de traceback → leitura dirigida.
5. `validate_project` como tool chamável.
6. Análise de GitHub migrada para navegação direta do cérebro.
7. Início do desmonte das heurísticas do `tool_executor` (doc 06 §6).

**Gate de saída:** os 3 primeiros critérios de aceite do doc 06 (correção sem vertex; ajuste pequeno < 5 tool calls; análise de repo sem vertex).

## Fase 3 — Prompt modular + classificador + contexto (docs 04 + 05) (3-4 dias)

1. `prompts/` com core + módulos + loader; aposentar `_build_agent_system_prompt`.
2. Classificador de intenção no Flash substituindo as regex de roteamento (com fallback).
3. `CONTEXT_TOKEN_LIMIT` novo + calibração por usage + compactação em duas camadas + bloco `[WORKSPACE]`.
4. Defesa de prompt injection (delimitadores + teste).
5. Memória tipada com injeção seletiva.
6. Tools `message_notify_user`/`message_ask_user` + endpoint de resposta (fecha o Bug 1 em definitivo).
7. `todo_write` — Plano Vivo do modelo.

**Gate de saída:** cache hit de prefixo confirmado; pedidos em inglês funcionando; teste de injection passando; Plano Vivo atualizado pelo modelo.

## Fase 4 — Paralelismo e polimento (docs 02 §4 + 03 §4-5 + 06 §5-7) (4-6 dias)

1. Subagente `researcher` (deep research paralelo) e `code-reviewer` pré-entrega.
2. `web_fetch` (busca HTTP sem Chrome).
3. `document_render` como tool explícita; `preview_expose` via túnel (avaliar custo/risco antes).
4. Reforços do `web_validation` (console errors, links internos, mobile).
5. Memória de trabalho em arquivos (notas de pesquisa/decisões).
6. Observabilidade: custo/tokens por task no frontend.

**Gate de saída:** deep research ≥ 2x mais rápido; revisão pré-entrega gerando findings acionáveis; custo por task visível.

## Dependências entre documentos

```
07 (bugs rápidos) ──────────────┐
01 (V4 Pro + tools nativas) ──→ 02 (loop novo) ──→ 03 (tools novas) ──→ 06 (código)
                                        └────────→ 04 (prompts) ──→ 05 (contexto/memória)
Fase 4 depende de 02+03.
```

## Métricas de sucesso (medir com `llm_usage` + eventos)

| Métrica | Baseline (medir na Fase 0) | Meta |
|---|---|---|
| Custo médio por task de código | ? | −30% (menos chamadas de vertex) |
| Tempo até 1º token da resposta final | ? (hoje = resposta inteira) | < 3s (streaming) |
| Rodadas de correção até validação passar | ? | −50% (edição direta) |
| Taxa de task morta por erro de protocolo (JSON inválido/repair) | ? | ~0 (function calling) |
| Iterações desperdiçadas em ciclo/derrapagem | ? | −80% |
| Cache hit de prefixo (iterações 2+) | 0 | > 70% |

## Regras para o agente que for implementar

1. **Um bug/feature por commit**, com teste. Rodar `PYTHONPATH=. ./venv/bin/python -m unittest discover -s tests` (backend) e `npm run build` (frontend) antes de cada commit.
2. **Não quebrar o contrato de eventos** (`stream_contract.py`) — o frontend e o histórico dependem dele; `vertex_progress`/`vertex_steps` são nomes legados intencionais.
3. **Não tocar em deploy/systemd/túnel** neste plano — é só backend/IA.
4. **Feature flags para mudanças de comportamento do modelo** (`DEEPSEEK_STREAMING`, `PARALLEL_TOOL_CALLS`, `USE_NATIVE_TOOLS`) permitindo rollback por `.env`.
5. Em dúvida de produto (ex.: expor custo ao usuário final?), perguntar ao Álvaro antes de implementar.
6. Manter este diretório atualizado: marcar checkboxes dos critérios de aceite conforme completa e registrar desvios de plano num `CHANGELOG.md` local.
