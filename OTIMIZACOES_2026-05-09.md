# Documentacao de Otimizacoes - Vortax v0.1.3

Data: 2026-05-09

---

## Resumo das Alteracoes

Foram implementadas 9 melhorias de performance, resiliencia, seguranca e operacao no sistema Vortax, abrangendo frontend, backend e infraestrutura.

---

## Frontend (3 arquivos)

### 1. `frontend/src/components/VortaxComputerDock.jsx`
**O que mudou**: Envolvidos 7 subcomponentes com `React.memo` para evitar re-renderizacoes desnecessarias durante streaming de eventos.

**Componentes memoizados**:
- `ComputerPreview` — preview da tela do computador
- `CodingWorkspace` — IDE simulada
- `ComputerStage` — stage do navegador/editor/terminal
- `ComputerProgressCard` — card de progresso
- `ComputerLiveControls` — controles de frame ao vivo
- `ComputerSidePanel` — painel lateral completo
- `VortaxComputerDock` — componente principal

**Outras melhorias**:
- Timer de progresso extraido para hook `useElapsedTimer` — atualiza a cada 1s sem re-renderizar o componente inteiro
- Callbacks (`handleOpenSide`, `handleCloseSide`, `handleToggleExpand`) estabilizados com `useCallback`
- Funcao `useNow` substituida por `useElapsedTimer` mais eficiente

### 2. `frontend/src/hooks/useWebSocket.js`
**O que mudou**: Reconexao resiliente com consciencia de estado da pagina.

**Melhorias**:
- **Visibility change**: Quando o usuario troca de aba e volta, o WebSocket reconecta imediatamente em vez de continuar em loop de falha
- **Online/Offline**: Detecta perda de conexao de rede e reconecta automaticamente quando a rede volta
- **Novo estado "paused"**: Indica quando a reconexao esta pausada (aba hidden)
- **Novo estado "offline"**: Indica quando o dispositivo esta sem rede

### 3. `frontend/src/hooks/useTaskFiles.js`
**O que mudou**: Debounce de 2 segundos para evitar chamadas redundantes a API durante streaming.

**Melhorias**:
- Chamadas `listFiles()` limitadas a 1 a cada 2 segundos durante streaming ativo
- Pending request tracker cancela requests concorrentes
- Eventos `files_created` (que ja trazem dados no payload) continuam com merge imediato (sem API call)
- Limpeza adequada de timers no unmount

---

## Backend (4 arquivos)

### 4. `backend/services/event_bus.py`
**O que mudou**: Broadcast WebSocket paralelo via `asyncio.gather`.

**Melhorias**:
- Envio de eventos para multiplos clientes WebSocket agora e paralelo
- Erros em sockets individuais sao isolados (`return_exceptions=True`)
- Cleanup de sockets desconectados mantido apos broadcast
- `close_task_connections` tambem paralelizado

### 5. `backend/database.py`
**O que mudou**: Insercao de eventos em lote e separacao de screenshots.

**Novos metodos**:
- `insert_events_batch(task_id, events)` — insere multiplos eventos em uma unica transacao com `executemany`
- `insert_screenshot(task_id, event_id, created_at, payload)` — metodo separado para screenshots

**Melhorias**:
- Screenshot insert removido da secao critica do `insert_event`
- Menos lock contention no SQLite durante alta frequencia de eventos

### 6. `backend/services/deepseek_client.py`
**O que mudou**: Retry com exponential backoff + jitter para chamadas HTTP.

**Nova funcao**: `with_retry(fn, *args, max_retries=3, base_delay=1.0, provider_name=...)`

**Politica de retry**:
- Retenta em: 429 (rate limit), 5xx (server errors), ConnectionError, TimeoutException, RemoteProtocolError
- NAO retenta em: 4xx (exceto 429)
- Backoff: 1s → 2s → 4s com jitter aleatorio de 0-0.5s
- Aplicado em `_post_deepseek` e `_post_groq`

### 7. `backend/tools/browser_pool.py`
**O que mudou**: Hibernacao automatica de browsers ociosos.

**Detalhes**:
- Loop de hibernacao roda a cada 60 segundos
- Timeout de ociosidade: `BROWSER_IDLE_TIMEOUT_SECONDS` (default 600s = 10 minutos)
- Rastreamento de ultima atividade via `_last_activity` dict
- Iniciado no `initialize()`, cancelado no `shutdown()`
- Logging de cada hibernacao

---

## Infraestrutura e Operacao (2 itens)

### 8. `backend/services/safe_diagnostics.py`
**O que mudou**: Sanitizacao expandida para PII.

**Novos padroes redatados**:
- Paths do sistema de arquivos contendo `/home/` → `[REDACTED]`
- Enderecos de email → `[REDACTED]`

### 9. Agente de programacao Vertex
**O que mudou**: O Vortax voltou a usar `vertex` como agente real de programacao no backend.

**Detalhes operacionais**:
- `CODE_AGENT_COMMAND=vertex` e `CODE_AGENT_LABEL=Vertex` viraram os defaults do backend
- O service systemd inclui `/home/server/.local/bin` no PATH efetivo do agente
- Comandos legados `openclaude ...` sao aceitos apenas como compatibilidade e normalizados para `vertex ...`
- Eventos publicos `vertex_progress` e `vertex_steps` foram preservados para nao quebrar o frontend nem historico salvo
- A documentacao de operacao foi atualizada com os env vars e o check `vertex --version`

---

## Build e Deploy

```bash
# Frontend
cd frontend && npm run build  # Sem erros, 8.9s
cd .. && firebase deploy --project notazap-2520f --only hosting  # OK

# Backend
systemctl --user restart vortax-backend.service  # OK
curl http://localhost:8010/health  # status: ok
```

## Verificacao

### Frontend
- [x] `npm run build` completou sem erros
- [x] Deploy Firebase concluido — `https://notazap-2520f.web.app`
- [x] Chunks: CSS 92KB, JS 735KB

### Backend
- [x] Backend restartou sem erros
- [x] Health check: status ok, deepseek configurado, groq task planner ativo
- [x] Cloudflare tunnel ativo — `vortax-api.cursar.space`

### Rollback
Todos os arquivos estao sob versionamento git em `/media/server/HD Backup/Servidores_NAO_MEXA/Vortax/.git/`.
Para reverter: `git checkout -- <arquivo>` ou `git stash`.
