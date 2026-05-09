# Frontend do Vortax

Frontend React/Vite do Vortax. Ele entrega a interface de chat, autenticação Firebase, streaming em tempo real por WebSocket, painel do Computador do Vortax, arquivos gerados, fontes, screenshots, drawers e diálogos da aplicação.

## Stack

- React 18
- Vite 5
- Firebase Auth
- Framer Motion
- Lucide React
- React Markdown + Remark GFM

## Estrutura principal

```text
frontend/
├── index.html
├── package.json
├── vite.config.js
├── public/                 # logos e ícones públicos
└── src/
    ├── main.jsx            # entrada React
    ├── App.jsx             # composição da tela principal
    ├── index.css           # estilos globais e responsividade
    ├── auth/               # AuthProvider/Firebase Auth
    ├── components/         # chat, mensagens, composer, dock, drawers e painéis
    ├── hooks/              # WebSocket, eventos, dados persistentes e task data
    └── lib/                # cliente HTTP/Firebase
```

## Pontos de entrada

- `src/main.jsx` renderiza o app e envolve `App` com `AuthProvider`.
- `src/App.jsx` coordena task ativa, mensagens, eventos, arquivos, fontes, estado do backend, dialogs e layout principal.
- `src/lib/api.js` centraliza chamadas REST e URLs de download/preview.
- `src/hooks/useWebSocket.js` mantém o stream de eventos em tempo real.
- `src/index.css` concentra o visual do produto e os breakpoints mobile.

## Tela de chat

A tela principal é formada por:

- `components/ChatShell.jsx` — shell da aplicação, sidebar de conversas e botão de menu.
- `components/MessageList.jsx` — timeline de mensagens, progresso, documentos e overlay de visualização.
- `components/Composer.jsx` — input de mensagem, anexos, login seguro, voz e enviar/parar.
- `components/VortaxComputerDock.jsx` — dock do Computador do Vortax, preview, status e painel lateral.
- `components/TaskDetailDrawer.jsx` — drawer com detalhes, arquivos, fontes, timeline e plano da task.

## API e WebSocket

`src/lib/api.js` define a base da API assim:

```js
const explicitBaseUrl = import.meta.env.VITE_API_BASE_URL;
const defaultBaseUrl = `${window.location.protocol}//${window.location.hostname}:8010`;

export const API_BASE_URL = explicitBaseUrl || defaultBaseUrl;
export const WS_BASE_URL = API_BASE_URL.replace(/^http/, "ws");
```

Em desenvolvimento local, sem variável de ambiente, o frontend usa o mesmo host na porta `8010`. Em produção, use `VITE_API_BASE_URL` para apontar para o backend público.

Arquivo de produção esperado:

```bash
frontend/.env.production
```

Exemplo:

```bash
VITE_API_BASE_URL=https://vortax-api.cursar.space
```

## Desenvolvimento local

Instale dependências:

```bash
npm install
```

Inicie o Vite:

```bash
npm run dev
```

O servidor sobe em:

```text
http://localhost:5173
```

O `vite.config.js` também expõe em `0.0.0.0`, permitindo acesso pela LAN, e faz proxy local para:

- `/api` → `http://127.0.0.1:8010`
- `/health` → `http://127.0.0.1:8010`
- `/ws` → `ws://127.0.0.1:8010`

## Build

```bash
npm run build
```

O Vite gera a versão de produção em:

```text
frontend/dist
```

Os arquivos JS/CSS gerados em `dist/assets` recebem hash no nome. Isso permite cache longo dos assets sem prender o usuário em uma versão antiga.

## Preview local do build

```bash
npm run preview
```

O preview sobe em `0.0.0.0:5173`.

## Deploy no Firebase Hosting

O Firebase Hosting publica `frontend/dist`, conforme `../firebase.json`.

Fluxo recomendado a partir da raiz do projeto:

```bash
cd frontend
npm run build
cd ..
firebase deploy --project notazap-2520f --only hosting:notazap-2520f
```

Se o target específico não for necessário no ambiente atual, também pode ser usado:

```bash
firebase deploy --project notazap-2520f --only hosting
```

## Cache e atualização sem Ctrl+F5

A política de cache fica em `../firebase.json`.

Comportamento esperado:

- `index.html` e rotas da SPA: `Cache-Control: no-cache, no-store, must-revalidate`
- `/assets/**`: `Cache-Control: public,max-age=31536000,immutable`
- imagens públicas: cache de 1 dia

Essa combinação faz com que o navegador sempre revalide o HTML da aplicação. Quando há um novo deploy, o HTML novo aponta para novos assets hashados do Vite. Assim, um reload normal ou uma nova navegação já deve receber a versão nova, sem Ctrl+F5.

Valide após deploy:

```bash
curl -I https://notazap-2520f.web.app/
curl -I https://notazap-2520f.web.app/index.html
```

Para validar assets, use o nome real gerado em `frontend/dist/assets`:

```bash
curl -I https://notazap-2520f.web.app/assets/NOME_DO_ASSET.js
```

Resultado esperado:

- `/` e `/index.html` sem cache agressivo.
- `/assets/*.js` e `/assets/*.css` com cache longo e `immutable`.

## Responsividade mobile

A maior parte da responsividade está em `src/index.css`.

Áreas críticas:

- sidebar mobile em `ChatShell`
- header do chat
- `MessageList`
- `Composer`
- `VortaxComputerDock`
- `TaskDetailDrawer`
- dialogs e overlays

Checklist mínimo antes de publicar mudanças visuais:

- testar 360px, 375px, 390px, 430px e 768px de largura;
- confirmar que não há scroll horizontal;
- confirmar que a sidebar abre e fecha no mobile;
- confirmar que o composer continua acessível com teclado virtual;
- confirmar que mensagens longas, markdown, código e anexos não estouram a largura;
- confirmar que dock, drawers e dialogs cabem na viewport.

## Scripts

```bash
npm run dev      # Vite dev server em 0.0.0.0:5173
npm run build    # build de produção em dist/
npm run preview  # preview local do build
```
