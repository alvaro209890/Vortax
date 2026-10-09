# Experiência de acompanhamento do agente — 09/10/2026

Autor: Claude. Base: `3a84c37` (`main`). Estado: **implementação parcial, publicada a pedido do responsável para outro agente continuar**. A validação visual completa ainda não foi feita; veja a seção "O que falta".

## 1. Diagnóstico (antes)

Capturas em `docs/capturas-2026-10-09/before-*.png`, feitas com eventos reais (ver seção 5).

- **Spinners parados**: não existia regra `.spinner` global. Os ícones de execução do cartão de progresso do dock, da barra de endereço, da documentação e do plano não giravam. `.spin` (ZIP) também não existia. Etapas `running` continuavam marcadas como "em execução" depois de a tarefa terminar ("3:32 · Concluído" com a etapa girando).
- **Computador com pseudocódigo**: `CodingWorkspace` exibia linhas inventadas (`workspace.open(...)`, `applyChanges`, `syncComputerScene()`, `reportProgressToChat()`), `Ln 84, Col 12` fixo e arquivos de fallback (`src/App.jsx`…). A busca focada inventava URL do DuckDuckGo.
- **Navegador**: `AnimatePresence mode="wait"` causava flash entre capturas; "ao vivo" aparecia em tarefa concluída; a cena ficava vazia ("Aguardando uma página", `browser_go_back`) mesmo com capturas válidas; a URL interna `127.0.0.1:8011/api/files/preview/...` era exibida.
- **Terminal e preview inacessíveis**: `ShellOutput`, `PreviewPanel`, `ScreenView`, `InlineTaskTimeline` e `TaskPlanPanel` não eram usados.
- **Chat**: a chave do cartão de progresso mudava a cada evento (remontagem/reanimação); a rolagem sempre ia ao fim; o contador mostrava `0/1` sem plano.
- **Backend**: `tool_call`/`tool_result` sem id de correlação; exceções no executor publicavam só `error` (a chamada ficava aberta — reproduzido com `browser_go_back` expirando); capturas idênticas eram reenviadas (navegação gerava dois JPEGs iguais).
- O navegador produz **capturas por ação** (antes/depois de clique, digitação, rolagem e navegação), não transmissão contínua. A interface não deve chamar isso de vídeo ao vivo.

## 2. O que foi implementado

### Backend (contratos opcionais e compatíveis)

| Arquivo | Mudança |
|---|---|
| `backend/services/tool_context.py` (novo) | `ContextVar` com o `call_id` da ferramenta em execução; lista de eventos derivados. |
| `backend/services/event_bus.py` | Eventos derivados (`shell_stdout/stderr`, `screen_frame*`, `browser_view`, `files_created`, `source_saved`, validações, `vertex_progress`, `error`…) publicados durante uma ferramenta recebem `call_id`. Chamadas paralelas não se misturam (contexto por tarefa asyncio). |
| `backend/tools/tool_executor.py` | `execute_tool(..., call_id=None)`; `tool_call`/`tool_result` com `call_id`; **exceção e ferramenta desconhecida agora publicam `tool_result` de falha**; `_publish_browser_frame` único com `captured_at`, `trigger` e descarte de captura idêntica consecutiva (mesmo JPEG e cursor); após `screen_frame_blocked` a próxima captura sempre sai. |
| `backend/agent/loop.py` | Gera o `call_id` e o reutiliza no `tool_result` de tempo limite. |
| `backend/tools/files.py` | `file_write` retorna `created` e `line_count`; `file_edit` retorna `start_line`, `end_line` (linhas reais no arquivo novo) e `line_count`. |
| `backend/tests/test_tool_call_correlation.py` (novo) | 10 testes: herança/isolamento do `call_id`, `tool_result` em exceção e ferramenta desconhecida, deduplicação de capturas, captura após bloqueio, metadados de linhas. |

Nenhum tipo de evento novo foi criado; todos os campos são opcionais. Conversas antigas continuam funcionando (o frontend pareia por ordem quando não há `call_id`).

### Frontend

| Arquivo | Papel |
|---|---|
| `src/lib/activity.js` (novo) | Modelo de atividade puro a partir dos eventos: pareamento `tool_call`/`tool_result` (por `call_id` ou ordem), estados por ação (`running`, `done`, `failed`, `paused`, `waiting`, `interrupted`, `unknown`), títulos humanos ("Criando index.html", "Pesquisou “…”", "Comando falhou (código 1)"), alvo real (arquivo/URL/comando/consulta), saída do terminal, capturas, arquivos e fontes por ação, agrupamento de ações repetidas, resultado por turno. Uma ação sem retorno só fica "em execução" enquanto o turno está ativo. |
| `src/lib/workspace.js` (novo) | Árvore real de arquivos, versões registradas (`file_write`/`file_edit`/`file_append`), reconstrução só com o registrado, diff Myers com memória limitada, entrada de preview. |
| `src/lib/text.js` (novo) | Utilitários comuns (`publicText`, caminhos curtos, horários, preview interno exibido como "Preview do projeto · index.html"). |
| `src/lib/browserScenes.js` | Origem da cena (`capture`, `http`, `search`, `cache`, `blocked`), `captured_at`, cálculo de letterbox (`containRect`, `pointerInBox`). |
| `src/components/StatusIndicator.jsx` (novo) | Indicador único: pendente, em execução (anel CSS girando por `transform`), concluído, falhou, pausado, aguardando você, interrompido, sem confirmação. Rótulo acessível; estático com movimento reduzido. |
| `src/hooks/useComputer.js` (novo) | Estado único do Computador compartilhado por dock e painel: ao vivo × histórico, escolha manual de aba/arquivo/comando preservada até "Seguir o agente", "Voltar à atividade atual". |
| `src/hooks/useFileContent.js`, `src/hooks/useStickToBottom.js` (novos) | Conteúdo atual do arquivo (cache por hash) e rolagem que só acompanha o fim quando a pessoa está no fim (botão "Novas atualizações"/"Ir para o fim"). |
| `src/components/computer/*` (novo) | `ComputerPanel` (abas Navegador/Arquivos/Terminal/Preview, banner de histórico, plano), `FilesPane` (árvore, versão atual × registro da ação, diff, "Aguardando gravação do arquivo"), `TerminalPane` (comando real, stdout/stderr, código de saída, duração, checks de validação reais, rolagem pausável), `PreviewPane` (preparando/disponível/indisponível, recarga após mudança de arquivos, iframe **sem** `allow-same-origin`), `CodeView`/`DiffView`. |
| `src/components/BrowserSurface.jsx` | Reescrito: mantém a última imagem decodificada e sobrepõe a nova com fade (sem flash), remove imagem e ponteiro imediatamente em tela protegida, mostra origem/URL/título/horário/estado da conexão, "Última captura" quando o agente está em outra ferramenta, zoom ajustar/100%, palco com a proporção do viewport (container queries) para o ponteiro não errar com letterbox, efeitos de clique/digitação/rolagem só quando o evento registrou essa ação. |
| `src/components/VortaxComputerDock.jsx` | Reescrito: mesma cena do painel, estado do turno, contagem só de etapas do plano ("A contagem considera apenas as etapas do plano"). |
| `src/components/TurnActivity.jsx` (novo) + `MessageList.jsx` | Atividade por turno no chat: resumo do que acontece agora, grupos expansíveis, alvo de cada ação, detalhes técnicos sob demanda (nome da ferramenta, `call_id`, parâmetros resumidos), erros, arquivos e fontes produzidos; clique abre a cena correspondente no Computador. Chaves estáveis. |
| `src/App.jsx` | Um único `buildActivity` e `useComputer`; painel acoplado ao lado do chat em ≥1100 px e sobreposto (diálogo) abaixo disso; botão "Computador" no cabeçalho. |
| `src/hooks/useLiveTaskPlan.js` | `planStepStatus`: etapa `running` vira pausada/interrompida/sem confirmação quando a tarefa não está ativa. |
| `src/styles/experience.css` (novo, carregado por último) | Tokens de espaçamento, movimento (micro 160 ms, cena 200 ms, painel 240 ms), estados, foco visível por teclado, todos os componentes novos, mobile. |
| Removidos | `ScreenView`, `ShellOutput`, `PreviewPanel`, `InlineTaskTimeline`, `TaskPlanPanel`, `lib/events.js` (sem uso). |
| `frontend/tests/activity.test.js` + `tests/fixtures/*.json` | 11 testes do modelo de atividade. As fixtures são **eventos reais gravados** numa execução de QA isolada (imagens trocadas por marcadores), identificadas no campo `_fixture`. |

## 3. Origem dos dados de cada cena

- **Navegador**: `screen_frame` (JPEG real + `viewport` + `cursor`), `browser_view` (texto/resultados realmente recebidos por HTTP ou cache da conversa), `screen_frame_blocked` (sem imagem).
- **Arquivos**: lista real (`GET /api/files/task/{id}` + `files_created`); conteúdo atual via `GET /api/files/task/{id}/{path}`; registro histórico = `params.content` de `file_write` e `old_string/new_string` de `file_edit` (já sanitizados pelo backend; e-mails/caminhos podem aparecer como `[REDACTED]`). Linhas destacadas só com `start_line/end_line` do backend e se o arquivo não mudou depois.
- **Terminal**: `tool_call.params.command` (sanitizado), `shell_stdout/stderr` da chamada; sem transmissão, a saída do `tool_result`; validação = `checks` reais de `project_validation_result`.
- **Preview**: `GET /api/files/preview/{id}/` (index.html do workspace).

## 4. Testes executados

- Backend (venv isolado, banco/workspace temporários, `VORTAX_LIVE=0`): **241 testes; 1 falha preexistente** `test_fetch_example_com` (proxy desta sessão bloqueia `example.com`; falha igual na base). Linha de base antes das mudanças: 232 testes com a mesma falha.
- Frontend: `npm test` **18/18**; `vite build` ok, com o aviso **preexistente** de bundle > 500 kB.
- Execução real isolada (`scripts/qa/`): backend real + Chromium + site local + **modelo roteirizado (fixture: só escolhe as ferramentas; a execução é real)**. Rodadas com o código antigo: site (8 ferramentas, preview capturado) e navegação (clique, digitação, rolagem, tela protegida, `go_back` expirando). A conversa antiga abre na interface nova (`docs/capturas-2026-10-09/after-legacy-site-chat.png`).

## 5. Como reproduzir o QA

```bash
python3 -m venv /tmp/vqa && /tmp/vqa/bin/pip install -r backend/requirements.txt   # em Python 3.13 use playwright>=1.49
(cd frontend && npm ci)
QA_DIR=/tmp/vortax-qa PYTHON=/tmp/vqa/bin/python scripts/qa/run_qa_stack.sh
# front: http://127.0.0.1:5174 — criar tarefas com "site", "api", "pesquise", "navegue", "longo", "continue"
```

O script não toca no `.env`, banco ou projetos de produção. Ele sobrescreve `VITE_API_BASE_URL` vazio porque `frontend/.env.development` aponta para o IP de produção. Em ambiente sem internet, abortar as requisições a `fonts.googleapis.com` no navegador de teste (a folha de fontes bloqueia o carregamento do app).

## 6. O que falta (plano para o próximo agente)

Prioridade em ordem. Nada abaixo foi verificado visualmente ainda.

1. **QA visual do Computador novo** (desktop 1440 px e mobile 390 px, temas claro/escuro): abrir cada aba nas tarefas novas e antigas, conferir overflow horizontal, controles encobertos, rótulos longos e o modo sobreposto no mobile. Ajustar `styles/experience.css`. O CSS antigo do dock (`.computer-*`, `.vortax-computer-dock` em `index.css`) ficou sem uso e pode ser removido depois da conferência.
2. **Rotação no navegador**: em tarefa "longo", verificar com Playwright que `.vx-status__ring` tem `getAnimations()` rodando e que, após "Parar", o indicador vira "Interrompido" (sem animação). Com `reduced_motion="reduce"`, conferir anel estático.
3. **Cenários A–I com o backend novo** (todos via `scripts/qa`): A site (arquivo, diff da edição em `index.html` linhas reais, preview), B "api" (falha real de teste → correção → testes passam), C pesquisa (`web_search` falha sem rede pública; `web_fetch` de páginas locais; navegador), D erro de ferramenta, E interromper "longo" e retomar com "continue", F queda/reconexão (`context.set_offline`) sem duplicar mensagens, G troca de tarefa/histórico, H teclado/tema/movimento reduzido, I 390 px. Gravar capturas "depois" em `docs/capturas-2026-10-09/`.
4. **Medir o navegador**: tamanho médio dos JPEGs, latência de captura (o timeout é 4 s) e quantas capturas a deduplicação evita por tarefa; registrar aqui. Não foi implementado screencast contínuo — capturas por ação bastam para as ações discretas do agente; só reavaliar se a medição mostrar lacunas.
5. **Pendências conhecidas**: (a) a etapa final do plano fica `running` quando a entrega de software usa `_finish_text_response` (a interface mostra "sem confirmação"; decidir no backend se deve concluir o plano); (b) o preview estático depende da mesma autenticação por IP/LAN para CSS/JS (sem token em sub-recursos); (c) o histórico só tem conteúdo de arquivo para `file_write`/`file_edit`; arquivos do motor de código externo mostram apenas a versão atual; (d) teste de interface automatizado (Playwright) ainda não está no repositório.
6. Atualizar `README.md` e `frontend/README.md` com um resumo e o link deste documento depois da validação.

Referências: Manus, interfaces de agentes da OpenAI e os padrões Task/Tool/Web Preview do AI Elements foram usados só como conceito (estados da ferramenta, entrada/saída recolhíveis, grupos com arquivos, barra de URL + recarregar + corpo isolado). A documentação online do AI Elements não estava acessível a partir desta sessão (proxy).
