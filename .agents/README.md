# Vortax - Documentacao dos Agentes

Atualizado em: 2026-05-07

Este documento registra o que foi implementado no Vortax durante a rodada recente de trabalho, o estado atual de producao e os pontos que futuros agentes devem respeitar.

## Estado Atual

- Frontend publicado no Firebase Hosting:
  - `https://notazap-2520f.web.app`
- Backend publicado via Cloudflare Tunnel:
  - `https://vortax-api.cursar.space`
- Autenticacao do backend esta ativa:
  - `/health` retorna `"auth":"enabled"`.
  - `/api/tasks/` sem token retorna `401`.
- Banco ativo foi zerado para receber novos usuarios:
  - `tasks`: 0
  - `events`: 0
  - `screenshots`: 0
  - `chat_images`: 0
  - `sources`: 0
  - `generated_projects`: 0
  - `generated_files`: 0
  - `task_steps`: 0
  - `conversation_contexts`: 0
- Pasta ativa de projetos foi esvaziada:
  - `/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados/Vortax/projetos`
- Backup antes do reset:
  - `/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados/Vortax/backups/reset-20260507-130933`
- Contas do Firebase Authentication nao foram apagadas.

## Mudancas Implementadas

### Autenticacao e Usuarios

- Adicionado Firebase Web SDK no frontend.
- Criado `AuthProvider` React com:
  - `user`
  - `loading`
  - `getIdToken`
  - `loginWithEmail`
  - `registerWithEmail`
  - `loginWithGoogle`
  - `signOut`
- Criada tela de login/cadastro com:
  - Email e senha.
  - Google popup.
  - Tratamento de erros comuns do Firebase.
  - Linguagem focada em usuario final.
- Removidas informacoes operacionais da tela de login:
  - Sem mencao a Firebase Auth.
  - Sem linguagem de workspace tecnico.
  - Sem detalhes internos do sistema.
- Header do app mostra usuario atual e botao de sair.

### API Autenticada

- Criado `backend/auth.py`.
- Backend valida Firebase ID Token com `firebase-admin`.
- REST usa `Authorization: Bearer <firebase_id_token>`.
- WebSocket usa token via query string:
  - `/ws/{task_id}?token=<firebase_id_token>`
- Downloads e previews tambem passam token na URL.
- `ALLOW_NO_AUTH=false` foi ativado no ambiente atual do backend publicado.
- Variaveis previstas:
  - `FIREBASE_PROJECT_ID=notazap-2520f`
  - `FIREBASE_SERVICE_ACCOUNT_JSON`
  - `FIREBASE_CREDENTIALS_PATH`
  - `ALLOW_NO_AUTH`
  - `DEV_USER_ID`

### Chats Separados por Usuario

- Adicionada coluna `tasks.user_id`.
- Criado indice:
  - `idx_tasks_user_id_created_at`
- Criacao de task grava `user_id`.
- Listagem retorna somente conversas do usuario logado.
- Endpoints protegidos verificam dono da conversa:
  - get task
  - delete task
  - messages
  - images
  - files
  - downloads
  - previews
  - control
  - websocket
- Conversas antigas sem `user_id` ficam invisiveis para usuarios autenticados.

### Fluxo Visual do Chat

- Andamentos da IA agora aparecem entre:
  - mensagem do usuario;
  - resposta final do Vortax.
- A resposta final so aparece depois que a execucao/andamento esta pronta.
- Planos simples foram reduzidos visualmente para mensagens simples.
- Planos aparecem de forma progressiva, em vez de tudo de uma vez.
- Timeline inline virou um bloco com cara de mensagem do Vortax.
- Busca ativa tambem aparece como atividade intermediaria no chat.

### Computador do Vortax

- O stream do computador foi redesenhado para parecer uma sessao real de desenvolvimento.
- Quando o Vertex esta trabalhando, o painel exibe:
  - editor;
  - arvore de arquivos;
  - aba do arquivo ativo;
  - linhas de codigo simuladas com base nos eventos reais;
  - terminal;
  - status de validacao;
  - arquivo atual, quando disponivel.
- O painel usa eventos reais quando existem:
  - `vertex_progress`
  - `files_created`
  - `shell_stdout`
  - `shell_stderr`
  - `web_validation_result`
  - `project_validation_result`
  - `screen_frame`
- O objetivo visual foi manter precisao sem poluir a interface.

### Detalhes e UI

- Botao de detalhes foi destacado no header.
- Aba lateral de detalhes foi melhorada.
- A antiga aba de tela foi removida da lateral, pois a tela/stream agora pertence ao computador do Vortax.
- Barra de rolagem foi ajustada para ficar no canto direito do site, nao colada no chat.

### Firebase Hosting

- Adicionado `firebase.json` com:
  - `public: frontend/dist`
  - fallback SPA para `/index.html`
  - cache longo para assets versionados
  - cache menor para imagens
- Adicionado `.firebaserc` apontando para:
  - `notazap-2520f`
- `frontend/.env.production` aponta para:
  - `VITE_API_BASE_URL=https://vortax-api.cursar.space`

## Arquivos Principais Alterados

Frontend:

- `frontend/src/components/AuthScreen.jsx`
- `frontend/src/auth/AuthProvider.jsx`
- `frontend/src/lib/firebase.js`
- `frontend/src/lib/api.js`
- `frontend/src/hooks/useWebSocket.js`
- `frontend/src/hooks/useLiveTaskPlan.js`
- `frontend/src/App.jsx`
- `frontend/src/components/MessageList.jsx`
- `frontend/src/components/InlineTaskTimeline.jsx`
- `frontend/src/components/VortaxComputerDock.jsx`
- `frontend/src/components/TaskDetailDrawer.jsx`
- `frontend/src/components/FileList.jsx`
- `frontend/src/components/PreviewPanel.jsx`
- `frontend/src/index.css`

Backend:

- `backend/auth.py`
- `backend/config.py`
- `backend/database.py`
- `backend/services/task_store.py`
- `backend/api/tasks.py`
- `backend/api/files.py`
- `backend/api/control.py`
- `backend/api/ws.py`
- `backend/api/providers.py`
- `backend/requirements.txt`

Infra:

- `firebase.json`
- `.firebaserc`
- `.env.example`
- `.gitignore`

Testes:

- `backend/tests/test_task_auth_isolation.py`
- `backend/tests/test_files_api.py`
- `backend/tests/test_exact_solver.py`

## Validacoes Realizadas

Frontend:

```bash
npm run build
```

Resultado:

- Build Vite passou.
- Permanece apenas o aviso de chunk grande por causa do Firebase SDK.

Backend:

```bash
.venv/bin/python3 -m pytest tests
```

Resultado:

- `85 passed`
- `1 warning` conhecido do Pydantic sobre `class Config`.

Producao:

```bash
curl https://vortax-api.cursar.space/health
```

Resultado esperado:

```json
{
  "status": "ok",
  "auth": "enabled"
}
```

Sem token:

```bash
curl -i https://vortax-api.cursar.space/api/tasks/
```

Resultado esperado:

```json
{"detail":"Autenticacao obrigatoria."}
```

Hosting:

```bash
curl -I https://notazap-2520f.web.app
```

Resultado:

- `HTTP/2 200`

## Deploy

Frontend:

```bash
npm --prefix frontend run build
firebase deploy --only hosting --project notazap-2520f
```

Backend:

- Servico systemd:
  - `vortax-backend.service`
- Tunnel:
  - `vortax-cloudflared.service`

Comandos uteis:

```bash
systemctl --user status vortax-backend.service --no-pager -l
systemctl --user status vortax-cloudflared.service --no-pager -l
systemctl --user restart vortax-backend.service
systemctl --user restart vortax-cloudflared.service
```

Observacao: em 2026-05-07 o tunnel ficou inativo depois do reset/restart e foi reativado com:

```bash
systemctl --user start vortax-cloudflared.service
```

## Banco de Dados

Banco ativo:

```text
/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados/Vortax/vortax.sqlite
```

Pastas relacionadas:

```text
/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados/Vortax/projetos
/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados/Vortax/runtime
/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados/Vortax/backups
```

Reset executado em 2026-05-07:

- Backend foi parado temporariamente.
- Banco foi copiado para backup.
- Projetos antigos foram movidos para backup.
- Tabelas de conversa foram limpas via SQLite.
- `VACUUM` e checkpoint WAL foram executados.
- Backend foi iniciado novamente.
- Tunnel foi reativado.

## Cuidados Para Proximos Agentes

- Nao colocar segredos em arquivos versionados.
- Nao apagar backups sem pedido explicito.
- Nao reativar `ALLOW_NO_AUTH=true` em producao.
- Se mexer em auth, testar REST e WebSocket.
- Se mexer na UI do chat, manter a ordem:
  - usuario;
  - andamento;
  - resposta final.
- Se mexer no computador do Vortax, manter baixa poluicao visual.
- Antes de publicar:
  - rodar build frontend;
  - rodar testes backend;
  - verificar `health`;
  - verificar Hosting `HTTP 200`.

