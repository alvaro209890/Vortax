# Plano Técnico — Vortax

> **Versão:** 3.4 — OpenClaude como motor de desenvolvimento
> **Data:** 07/05/2026
> **Objetivo atual:** manter o Vortax como agente web estilo Manus para operar este PC, pesquisar, criar software via OpenClaude, validar entregas e mostrar o trabalho em tempo real com chat, Plano Vivo, arquivos, fontes e screenshots.

---

## 1. Estado Atual

O Vortax já está implementado como aplicação web com frontend React/Vite e backend FastAPI. O frontend pode rodar localmente em `http://localhost:5173` ou publicado no Firebase Hosting. O backend roda neste PC na porta `8010` e pode ser acessado localmente ou via Cloudflare Tunnel dedicado.

Endpoints públicos atuais:

- Frontend Firebase: `https://notazap-2520f.web.app`
- Backend via túnel: `https://vortax-api.cursar.space`
- Backend local: `http://127.0.0.1:8010`
- Frontend dev: `http://127.0.0.1:5173` ou `http://192.168.0.104:5173`

O backend continua com `ALLOW_NO_AUTH=true`, mas `LAN_ONLY=true` aceita acesso público apenas quando o host pertence a `PUBLIC_HOSTS` e a requisição chega com headers do Cloudflare Tunnel. A porta CDP do Chrome (`9222`) deve permanecer presa a `127.0.0.1`.

---

## 2. Arquitetura Real

```text
Usuario
  |
  | HTTP/WebSocket
  v
Frontend React/Vite
  |-- Chat, Composer, MessageList
  |-- Plano Vivo, Timeline, Fontes, Arquivos, Screenshots
  |
  v
Backend FastAPI :8010
  |-- api/tasks.py       cria conversas, mensagens, imagens e downloads
  |-- api/ws.py          WebSocket com replay de eventos persistidos
  |-- api/control.py     stop/confirmacao
  |-- api/files.py       arquivos, preview e ZIP
  |-- api/providers.py   status DeepSeek/Groq
  |
  v
Runner ReAct
  |-- DeepSeek V4 Flash decide acoes
  |-- Tool executor executa browser/shell/visao/exatas
  |-- OpenClaude cria/corrige projetos de software
  |-- Validadores bloqueiam finish ate passar
  |
  v
SQLite + workspace persistente
  |-- conversas, eventos, contexto, fontes, imagens, prints
  |-- task_steps do Plano Vivo
  |-- projetos e arquivos gerados por task
```

Motor de software:

- O Vortax delega criação/correção de software ao `openclaude` via `shell_run`.
- O OpenClaude cria arquivos em `WORKSPACE_PATH/<task_id>/`.
- Após cada execução OpenClaude, o Vortax indexa arquivos, roda validação e só permite finalizar quando a revisão obrigatória passar.

Modelos:

- Texto e planejamento: `deepseek-v4-flash`
- Visão: Groq OpenAI-compatible com `meta-llama/llama-4-scout-17b-16e-instruct`
- Exatas: tool local `exact_solve`

---

## 3. Estrutura Atual do Projeto

```text
Vortax/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── access.py
│   ├── database.py
│   ├── api/
│   │   ├── control.py
│   │   ├── files.py
│   │   ├── providers.py
│   │   ├── tasks.py
│   │   └── ws.py
│   ├── services/
│   │   ├── agent_runner.py
│   │   ├── context_manager.py
│   │   ├── deepseek_client.py
│   │   ├── event_bus.py
│   │   ├── project_files.py
│   │   ├── project_validation.py
│   │   ├── research_policy.py
│   │   ├── stream_contract.py
│   │   ├── task_plan_store.py
│   │   ├── task_store.py
│   │   └── web_validation.py
│   ├── tools/
│   │   ├── browser.py
│   │   ├── exact.py
│   │   ├── shell.py
│   │   ├── tool_executor.py
│   │   └── vision.py
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── AgentActivity.jsx
│   │   │   ├── ActionTimeline.jsx
│   │   │   ├── ChatShell.jsx
│   │   │   ├── Composer.jsx
│   │   │   ├── DocumentationPanel.jsx
│   │   │   ├── FileList.jsx
│   │   │   ├── MessageList.jsx
│   │   │   ├── PreviewPanel.jsx
│   │   │   ├── ScreenView.jsx
│   │   │   ├── SourceList.jsx
│   │   │   └── TaskPlanPanel.jsx
│   │   ├── hooks/
│   │   └── lib/api.js
│   ├── package.json
│   └── vite.config.js
├── deploy/
│   ├── cloudflared/vortax-api.yml
│   └── systemd/user/
├── scripts/start-dev.sh
├── firebase.json
├── .firebaserc
├── README.md
└── PLANO_VORTAX.md
```

Coisas removidas deste plano por não refletirem mais o projeto:

- `backend/agent/*`, `file_manager.py`, `screenshot.py` e `pyautogui_tool.py` como módulos separados.
- `tailwind.config.js`, `postcss.config.js`, `scripts/install.sh`, `scripts/start-prod.sh`, `scripts/stop.sh` e `systemd/` antigo na raiz.
- Banco por `ses_N/session.sqlite`; o banco real atual é único em `Banco_de_dados/Vortax/vortax.sqlite`.
- Premissa antiga de "sem Cloudflare/sem hospedagem externa"; o deploy externo já existe.
- Fases especulativas antigas que já foram implementadas ou descartadas.

---

## 4. Banco, Workspace e Persistência

Base de dados:

```text
/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados/Vortax/vortax.sqlite
```

Workspace persistente:

```text
/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados/Vortax/projetos/<task_id>/
```

Runtime:

```text
/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados/Vortax/runtime/
```

Tabelas principais:

- `tasks` — conversa/tarefa principal.
- `events` — histórico completo do stream WebSocket.
- `screenshots` — prints ligados a eventos `screen_frame`.
- `chat_images` — imagens enviadas pelo usuário.
- `sources` — fontes web abertas, extraídas e pontuadas.
- `conversation_contexts` — resumo, tokens estimados e compactação.
- `generated_projects` — projetos detectados por conversa.
- `generated_files` — arquivos gerados e indexados por conversa/projeto.
- `task_steps` — Plano Vivo persistido com status, critérios e evidências.

O SQLite usa `PRAGMA foreign_keys = ON` e `journal_mode = WAL`. Excluir uma conversa remove em cascata eventos, imagens, prints, fontes, contexto, projetos, arquivos e etapas do Plano Vivo.

---

## 5. Contratos de API e Eventos

Rotas principais:

- `POST /api/tasks/` — cria task, gera Plano Vivo inicial e dispara `run_agent_task`.
- `POST /api/tasks/{task_id}/messages` — adiciona mensagem na conversa existente e dispara nova execução.
- `POST /api/tasks/images` — cria conversa com imagem.
- `POST /api/tasks/{task_id}/images` — adiciona imagem na conversa.
- `GET /api/tasks/` — lista conversas.
- `GET /api/tasks/{task_id}` — retorna task, eventos, fontes, imagens, arquivos, projetos, contexto e `plan.steps`.
- `GET /api/tasks/{task_id}/download` — ZIP dos arquivos gerados.
- `POST /api/control/{task_id}/stop` — interrompe runner e subprocessos.
- `WS /ws/{task_id}` — replay + stream em tempo real.

Eventos importantes:

- Chat: `user_message`, `assistant_message_delta`, `assistant_message_done`.
- Estado: `agent_status`, `agent_progress`, `error`.
- Tools: `tool_call`, `tool_result`, `shell_stdout`, `shell_stderr`, `shell_interactive_prompt`.
- Navegador/tela: `screen_frame`, `source_saved`.
- OpenClaude: `ai_exchange`, `vertex_progress` (nome legado do contrato), `files_created`.
- Validação: `web_validation_*`, `project_validation_*`.
- Plano Vivo: `task_plan_created`, `task_plan_replanned`, `task_step_started`, `task_step_updated`, `task_step_completed`, `task_step_failed`.
- Runtime web: `dev_server_started`, `dev_server_stopped`.

Todos os eventos passam por `stream_contract.py`; tipos desconhecidos viram `error` seguro em vez de quebrar o frontend.

---

## 6. Fluxo do Agente

1. O usuário cria ou continua uma conversa.
2. O backend publica `user_message`.
3. Para tasks novas, `task_plan_store` cria `task_steps`; se o DeepSeek falhar, usa fallback em 4 etapas.
4. `run_agent_task` prepara histórico e contexto compactado.
5. Se for pergunta simples, responde direto.
6. Se for exatas, chama `exact_solve`.
7. Se for tarefa complexa, entra no loop ReAct com DeepSeek.
8. Se for criação de software que se beneficia de referência, roda pesquisa prévia e salva fontes.
9. Se for pesquisa sobre pessoa, roda consultas específicas e exige fontes suficientes.
10. O planner escolhe uma tool por iteração.
11. `tool_executor` executa a tool, publica eventos e resume resultado para o modelo.
12. Se houver `shell_run openclaude`, o Vortax indexa arquivos e roda validações.
13. Se validação falhar, o runner impede `finish`, registra bugs e manda corrigir.
14. Quando a entrega está validada, publica `assistant_message_done` e encerra runtimes temporários.

Plano Vivo:

- Cada etapa tem `pending`, `running`, `passed`, `failed` ou `skipped`.
- O runner inicia/conclui etapas conforme entende, executa, valida e entrega.
- Evidências de tools, bugs de validação e entrega final ficam salvas em `evidence_json`.
- O frontend renderiza o plano em `TaskPlanPanel`, separado da timeline técnica.

---

## 7. Ferramentas Ativas

Browser:

- Google Chrome do sistema via CDP.
- Pesquisa Google estruturada.
- Navegação, clique por texto/seletor, digitação, teclas, scroll.
- Extração de texto, links e artigo limpo.
- Screenshot e smoke test frontend.

Shell:

- `shell_run` com whitelist e bloqueio de padrões perigosos.
- Workspace por conversa.
- Streaming stdout/stderr.
- Detecção de prompts interativos e resposta automática limitada.
- Detecção de servidores de desenvolvimento e cleanup por task.
- Integração OpenClaude em TTY real.

Validação:

- `project_validation`: scan de arquivos, assets HTML, `py_compile`, `unittest`, `node --check`, build/test Node quando aplicável.
- `web_validation`: preview interno, Chrome, smoke test, screenshots e visão.

Pesquisa:

- Cache de fontes por conversa.
- Política mínima de fontes para dados atuais/sensíveis.
- Detecção simples de divergências.
- Pesquisa pré-criação de software.
- Pesquisa específica de pessoas.

Visão:

- `vision_analyze` via Groq/Llama 4 Scout.
- Usada para imagens do chat, screenshots ambíguos, exercícios e validação visual.

Exatas:

- `exact_solve` para aritmética, porcentagem, equações simples e problemas extraídos de imagem.

---

## 8. Frontend

Stack real:

- React 18
- Vite
- Framer Motion
- Lucide React
- React Markdown + Remark GFM
- CSS próprio em `frontend/src/index.css`

Painéis atuais:

- Chat principal com mensagens e composer.
- `AgentActivity` com atividade dinâmica e progresso OpenClaude.
- `TaskPlanPanel` com Plano Vivo persistido.
- `ActionTimeline` com marcos técnicos enxutos.
- `ScreenView` com galeria de screenshots.
- `DocumentationPanel` para Markdown gerado.
- `SourceList` para fontes.
- `FileList` para arquivos e ZIP.
- `PreviewPanel` para projetos web.
- `AiExchangePanel` para DeepSeek ↔ OpenClaude.

Regras de UX:

- A tela principal continua chat-first.
- O Plano Vivo mostra a narrativa do trabalho.
- A timeline técnica fica complementar e filtrada.
- Mensagens simples não geram tasks fantasmas.
- Links locais (`localhost`, `127.0.0.1`) não aparecem na resposta final para usuários do Firebase.

---

## 9. Deploy e Operação

Dev local:

```bash
cd "/media/server/HD Backup1/Servidores_NAO_MEXA/Vortax"
./scripts/start-dev.sh
```

Backend manual:

```bash
cd backend
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8010
```

Frontend:

```bash
cd frontend
npm run dev
npm run build
```

Deploy frontend:

```bash
cd frontend
npm run build
cd ..
firebase deploy --project notazap-2520f --only hosting:notazap-2520f
```

Serviços de usuário:

- `deploy/systemd/user/vortax-backend.service`
- `deploy/systemd/user/vortax-cloudflared.service`

Túnel:

- Config: `deploy/cloudflared/vortax-api.yml`
- Host público: `vortax-api.cursar.space`
- Serviço local: `http://127.0.0.1:8010`

Validação operacional:

```bash
systemctl --user is-active vortax-backend.service vortax-cloudflared.service
curl https://vortax-api.cursar.space/health
curl https://notazap-2520f.web.app
```

---

## 10. Testes e Verificação

Backend:

```bash
cd backend
PYTHONPATH=. ./venv/bin/python -m unittest discover -s tests
```

Testes focados recentes:

```bash
PYTHONPATH=. ./venv/bin/python -m unittest \
  tests/test_task_plan_store.py \
  tests/test_vertex_stream.py \
  tests/test_agent_history.py \
  tests/test_files_api.py
```

Frontend:

```bash
cd frontend
npm run build
```

Checagens mínimas antes de publicar:

- `/health` retorna `status=ok`.
- Nova task cria `task_plan_created`.
- `GET /api/tasks/{task_id}` retorna `plan.steps`.
- OpenClaude gera arquivos em `WORKSPACE_PATH/<task_id>`.
- Validação pós-OpenClaude bloqueia `finish` se houver bug.
- Download ZIP funciona.
- Firebase chama backend via `https://vortax-api.cursar.space`.

---

## 11. Riscos Atuais

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Backend sem autenticação exposto por túnel | Alto | Manter `PUBLIC_HOSTS` restrito e aceitar público apenas via headers Cloudflare; próxima etapa deve adicionar autenticação |
| Chrome CDP exposto | Alto | Nunca publicar `9222`; manter bind local |
| OpenClaude criar projeto incompleto | Médio | Validação automática + correção obrigatória antes do `finish` |
| Preview/dev server ficar órfão | Médio | Registry de processos, `stop_dev_server`, cleanup no lifespan |
| Custos DeepSeek/Groq | Médio | `MAX_ITERATIONS=30`, cache de fontes, visão só quando necessária |
| Informação atual com poucas fontes | Médio | `research_policy` bloqueia `finish` até atingir fontes mínimas |
| Plano Vivo desincronizar | Baixo | `GET /api/tasks/{task_id}` reconstrói estado por `task_steps`; eventos fazem atualização incremental |

---

## 12. Próximos Passos Relevantes

1. **Autenticação real para acesso público**
   - Login simples, sessão/JWT e proteção das rotas de task, arquivos e WebSocket.

2. **Permissões por ação**
   - Diferenciar leitura, criação de arquivos, shell, navegação e ações destrutivas.

3. **Replanejamento real**
   - Usar `task_plan_replanned` quando o runner detectar mudança relevante de objetivo, não apenas como contrato disponível.

4. **Subtasks paralelas**
   - Adicionar execução paralela controlada para pesquisas largas, comparações e varredura de muitos arquivos.

5. **Rastreamento fino de artefatos**
   - Hash, origem da tool, relação com etapa do Plano Vivo e status de validação por arquivo.

6. **Replay/export da sessão**
   - Exportar conversa, eventos, fontes, screenshots e arquivos em pacote auditável.

7. **Observabilidade**
   - Métricas de tempo por etapa, tokens aproximados, custo estimado e falhas por provider.

---

## 13. Log de Alterações Essencial

| Versão | Data | Alterações |
|--------|------|-----------|
| 3.4 | 07/05/2026 | OpenClaude assumiu a execução de código no lugar do antigo fluxo Vertex, preservando `vertex_progress` e `vertex_steps` como nomes legados de contrato. |
| 3.3 | 07/05/2026 | Plano Vivo persistido com `task_steps`, eventos `task_plan_*`/`task_step_*`, integração no runner e painel `TaskPlanPanel`. |
| 3.2 | 06/05/2026 | Resposta rápida, `exact_solve`, imagens de exercícios e typing dots. |
| 3.1 | 06/05/2026 | Backend promovido para serviço systemd de usuário com boot persistente. |
| 3.0 | 06/05/2026 | Deploy Firebase Hosting e Cloudflare Tunnel dedicado para backend. |
| 2.9 | 06/05/2026 | Validação pós-OpenClaude geral e correção automática antes do `finish`. |
| 2.8 | 06/05/2026 | Botão parar, interrupção de subprocessos, preview automático e painéis colapsáveis. |
| 2.7 | 06/05/2026 | Preview iframe, dev servers em background e `file_summary`. |
| 2.6 | 06/05/2026 | Terminal OpenClaude integrado, ZIP por conversa, cache de pesquisa e verificação cruzada. |
| 2.5 | 06/05/2026 | Shell seguro, OpenClaude via `shell_run`, streaming stdout/stderr e `files_created`. |
| 2.4 | 06/05/2026 | Documentação do OpenClaude como motor de desenvolvimento. |
| 2.3 | 06/05/2026 | Visão via Groq/Llama 4 Scout. |
| 2.2 | 06/05/2026 | Chat-first estilo Manus com DeepSeek V4 Flash. |
| 2.1 | 06/05/2026 | Adaptação para Linux Mint, Chrome CDP, SQLite e WebSocket. |
