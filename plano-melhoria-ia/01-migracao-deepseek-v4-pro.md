# 01 — Migração para DeepSeek V4 Pro como cérebro padrão

> **Prioridade:** P0 (base de todo o resto)
> **Arquivos principais:** `backend/services/deepseek_client.py`, `backend/config.py`, `backend/services/agent_runner.py`, `.env.example`

---

## 1. Objetivo

Padronizar o **DeepSeek V4 Pro** como o modelo de planejamento, decisão de ações, raciocínio sobre código e resposta final do Vortax, com:

1. **Function calling nativo** (`tools`/`tool_calls` no formato OpenAI) substituindo o JSON-no-texto;
2. **Streaming** da resposta final (`assistant_message_delta` de verdade);
3. **Roteamento por camadas de modelo** (Pro para pensar, Flash para tarefas auxiliares);
4. **Contabilidade real de tokens e custo** usando o campo `usage` da API.

## 2. Estado atual

- `config.py:28` → `DEEPSEEK_MODEL: str = "deepseek-v4-flash"` usado para TUDO: ações do agente, chat direto, sumarização de contexto, título da conversa, plano fallback.
- `request_deepseek_action` (`deepseek_client.py:511-554`): `response_format={"type":"json_object"}`, parsing manual com `_extract_balanced_json_object` + rodada de "repair" quando o JSON quebra (chamada extra paga).
- Nenhuma chamada usa `stream: true`. Nenhuma chamada usa `tools`.
- `usage` é retornado em alguns pontos mas nunca persistido/exposto.
- `DEEPSEEK_TIMEOUT_SECONDS=60` (pode ser curto para o Pro em prompts grandes).

## 3. Mudanças propostas

### 3.1 Configuração em camadas de modelo

```python
# config.py — substituir DEEPSEEK_MODEL único por camadas
DEEPSEEK_MODEL_BRAIN: str = "deepseek-v4-pro"     # planner/agente/código/resposta final
DEEPSEEK_MODEL_FAST: str = "deepseek-v4-flash"    # título, sumarização, classificação de intenção
DEEPSEEK_TIMEOUT_SECONDS: float = 120.0            # Pro pensa mais; subir timeout
DEEPSEEK_MAX_OUTPUT_TOKENS: int = 8192             # explicitar limite de saída
```

Regra de roteamento (implementar como função única `pick_model(purpose)` em `deepseek_client.py`):

| Uso | Modelo | Justificativa |
|---|---|---|
| Loop de ações do agente (`request_deepseek_action`) | **V4 Pro** | Decisão de tool e raciocínio são o core |
| Resposta final / chat direto | **V4 Pro** | Qualidade percebida pelo usuário |
| Raciocínio sobre código (novo fluxo do doc 06) | **V4 Pro** | Precisão em edição/diagnóstico |
| Sumarização de contexto (`request_context_summary`) | V4 Flash | Tarefa mecânica, alto volume |
| Título da conversa (`generate_task_title`) | V4 Flash | Trivial |
| Classificador de intenção (novo, doc 04 §5) | V4 Flash | 1 chamada curta e barata |
| Plano de tasks (`request_task_plan`) | Groq (mantém) com fallback **V4 Pro** | Já funciona; fallback melhora |

Manter `DEEPSEEK_MODEL` como alias legado lido do `.env` (se definido, vale para `BRAIN`) para não quebrar deploys existentes.

> **Atenção:** confirmar na documentação oficial do DeepSeek o nome exato do modelo (`deepseek-v4-pro`), o tamanho da janela de contexto, o limite de saída e o preço por 1M tokens antes de fixar os valores de `CONTEXT_TOKEN_LIMIT` (ver doc 05). Não assumir números.

### 3.2 Function calling nativo

Substituir o protocolo atual por `tools` no formato OpenAI (suportado pela API do DeepSeek):

```python
# deepseek_client.py — novo
payload = {
    "model": settings.DEEPSEEK_MODEL_BRAIN,
    "messages": messages,            # com roles corretos: system/user/assistant/tool
    "tools": build_tool_schemas(),   # JSON Schema real por tool (doc 03)
    "tool_choice": "auto",
    "stream": True,
}
```

Consequências em cascata:

1. **`TOOLS_SCHEMA` (`deepseek_client.py:55-171`) é substituído** por schemas JSON reais (`type`, `properties`, `required`, `description`) gerados por um registro central de tools (doc 03 §6). O texto "use" de cada tool vira `description` do schema.
2. **Histórico com roles corretos:** resultado de tool passa a ser `{"role": "tool", "tool_call_id": ..., "content": ...}` e a decisão do modelo fica em `assistant.tool_calls` — elimina o padrão "Resultado da ferramenta:" como mensagem `user` (`agent_runner.py:2228`) e os filtros por prefixo (`_latest_user_prompt`).
3. **Fim do parser manual e do repair:** remover `_extract_balanced_json_object`, `_extract_json_object`, `_parse_json_object` e a rodada de repair (`deepseek_client.py:529-551`) do caminho do agente. Manter parser apenas para o planner de tasks (que retorna JSON de dados, não ação).
4. **`finish` deixa de ser uma "action" mágica:** quando o modelo responde com `content` e sem `tool_calls`, isso É a resposta final (padrão Claude Code/OpenAI). Os gates de finalização continuam existindo, mas passam a responder com `role: "tool"`/mensagem de sistema estruturada em vez de mensagem `user` falsa.
5. **Paralelismo opcional:** a API pode retornar múltiplos `tool_calls` numa resposta; executar em paralelo quando as tools forem independentes e read-only (ex.: duas extrações de página), sequencial caso contrário. Flag `PARALLEL_TOOL_CALLS: bool = True`.

### 3.3 Streaming da resposta final

- Nas chamadas com `stream: True`, consumir SSE e publicar `assistant_message_delta` no `EventBus` a cada chunk de `content`; o `assistant_message_done` continua no fim (o frontend já suporta esses eventos pelo contrato).
- Tool calls chegam por delta também — acumular `tool_calls` até `finish_reason == "tool_calls"`.
- Fallback `stream: False` atrás de flag `DEEPSEEK_STREAMING: bool = True` para debug.

### 3.4 Contabilidade de tokens e custo

- Criar tabela `llm_usage` (SQLite): `task_id, provider, model, purpose, prompt_tokens, completion_tokens, cached_tokens, cost_estimate, created_at`.
- Registrar o `usage` de TODA chamada (DeepSeek e Groq) num helper único `record_usage()`.
- Expor agregado em `GET /api/tasks/{task_id}` (`tokens_used`, `estimated_cost`) e evento `usage_update` opcional no stream.
- Usar `prompt_cache_hit_tokens`/`prompt_cache_miss_tokens` (a API do DeepSeek reporta cache de prefixo) para monitorar eficiência do system prompt — o prompt modular do doc 04 deve manter o prefixo estável para maximizar cache hit.

### 3.5 Robustez de chamada

- Manter `with_retry` (backoff + jitter) — está bom.
- Adicionar tratamento explícito de `429` com respeito a `Retry-After` quando presente.
- Timeout separado para streaming (tempo até primeiro token vs. tempo total).
- Circuit breaker simples: após N falhas seguidas do provider, responder erro claro ao usuário em vez de estourar `MAX_ITERATIONS`.

## 4. Passos de implementação

1. `config.py`: novas settings + alias legado; atualizar `.env.example` e README.
2. `deepseek_client.py`: `pick_model()`, `build_payload()`, suporte a `tools` + streaming SSE (usar `httpx` com `client.stream`), `record_usage()`.
3. `agent_runner.py`: adaptar o loop para consumir `tool_calls`/`content` (isso se funde com a refatoração do doc 02 — implementar juntos).
4. `database.py`: tabela `llm_usage` + migração idempotente.
5. Testes: novo `test_deepseek_tools.py` (mock de resposta com `tool_calls`, streaming, usage), atualizar `test_deepseek_json_parser.py` (parser fica só para plano de tasks).

## 5. Critérios de aceite

- [ ] `request_deepseek_action` extinto; o loop usa `tool_calls` nativos com V4 Pro.
- [ ] Zero ocorrências de "Resultado da ferramenta:" no histórico enviado ao modelo.
- [ ] Resposta final aparece no chat token a token (`assistant_message_delta`).
- [ ] Título e sumarização continuam funcionando (agora explicitamente no Flash).
- [ ] `GET /api/tasks/{id}` retorna tokens/custo agregados da conversa.
- [ ] Suite `backend/tests` verde; mock runner (`mock_runner.py`) continua funcionando sem API key.

## 6. Riscos

| Risco | Mitigação |
|---|---|
| Custo maior com Pro em todo o loop | Camadas de modelo + cache de prefixo + contexto maior reduz re-pesquisa; monitorar via `llm_usage` |
| Streaming SSE mal tratado corta resposta | Flag `DEEPSEEK_STREAMING` para fallback imediato |
| Nome/limites do modelo diferentes do esperado | Passo 0 do roadmap: validar com 1 chamada real e documentar em `.env.example` |
