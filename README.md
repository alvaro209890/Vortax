# Vortax

**Agente de IA web local** — inspirado no fluxo do Manus. Converse em um chat e veja a IA operar este computador: pesquisar na web, navegar em páginas, extrair conteúdo, capturar screenshots, **desenvolver software completo usando o Vertex CLI** e gerenciar arquivos — tudo em tempo real.

> Versão MVP local em LAN. Sem autenticação, sem hospedagem externa.

> Deploy externo atual: frontend publicado no Firebase Hosting em `https://notazap-2520f.web.app`; backend local exposto por Cloudflare Tunnel em `https://vortax-api.cursar.space`.

---

## Vertex CLI — Motor de Desenvolvimento de Software

O Vortax usa o **Vertex CLI** como motor para desenvolver software, sites, scripts e qualquer projeto de código que você pedir.

O Vertex é um assistente de codificação por terminal que roda localmente. Ele entende linguagem natural e cria arquivos completos de código. Quando você pede "Crie um site de portfólio" ou "Faça uma API em Python", o agente do Vortax:

1. Abre o terminal e executa o comando `vertex` com suas instruções
2. O Vertex CLI desenvolve o projeto completo dentro da pasta persistente da conversa (`WORKSPACE_PATH/<task_id>/`)
3. O Vortax valida o projeto antes de deixar a IA finalizar
4. Se aparecer bug, erro de build, sintaxe quebrada, asset ausente ou problema visual, o agente manda o Vertex corrigir e valida novamente
5. Os arquivos gerados aparecem automaticamente no chat
6. Você pode baixar cada arquivo individualmente ou todos juntos em um arquivo **.zip**

### Como usar o Vertex diretamente

O Vertex CLI está disponível como comando global do sistema neste computador:

```bash
# Abrir o chat interativo do Vertex
vertex

# Execução direta de uma tarefa
vertex "Crie um sistema de login em Python com Flask e SQLite"
```

No Vortax, essa chamada é feita automaticamente pelo agente quando você solicita desenvolvimento de software.

### Onde está instalado

- **Vertex CLI:** `/media/server/HD Backup/Servidores_NAO_MEXA/vertex-cli` (v1.2.6)
- **Vertex Server:** `/media/server/HD Backup/Servidores_NAO_MEXA/vertex-server`

---

## Download de Arquivos

Tudo que o agente (ou o Vertex CLI) criar durante uma conversa fica armazenado e disponível para download:

- **Download individual** — cada arquivo gerado aparece no painel "Arquivos" com link direto
- **Download completo em ZIP** — um botão de download reúne todos os arquivos da conversa em um único `.zip`
- **Persistência** — os arquivos ficam salvos em `WORKSPACE_PATH/<task_id>/` e vinculados à conversa no banco de dados

Por padrão, `WORKSPACE_PATH` aponta para:

```bash
/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados/Vortax/projetos
```

---

## Funcionalidades

- **Chat contínuo** — múltiplas mensagens na mesma conversa, histórico persistido
- **Resposta rápida sem planner** — perguntas simples são respondidas direto no chat, sem passar por Vertex ou ciclo ReAct
- **Exatas com tools** — matemática, física, química, estatística e contas usam `exact_solve`; se o enunciado vier por imagem, o Vortax faz OCR/visão e resolve a partir da transcrição
- **Contexto por conversa** — cada chat mantém estado de contexto, estimativa de tokens e compactação automática
- **Navegação web** — Google Chrome do sistema via CDP, pesquisa estruturada, extração de artigos
- **Stream em tempo real** — WebSocket com eventos de ação, screenshots e resultados
- **Fontes com qualidade** — URLs visitadas são classificadas e pontuadas automaticamente
- **Cache de pesquisa por conversa** — antes de chamar o Google, o executor reutiliza fontes boas já salvas para a mesma consulta
- **Verificação cruzada automática** — preço, versão, documentação, notícia, comparação e dados sensíveis exigem múltiplas fontes e marcação de divergências
- **Galeria de screenshots** — todos os prints da sessão, com navegação e modal ampliado
- **Painel de atividade enxuto** — timeline lateral mostra só marcos úteis, sem ruído de stdout, status repetido ou screenshots intermediários
- **Indicador de contexto** — bolinha no topo do chat mostra se o contexto está ok, quase cheio ou compactado
- **Upload de imagens** — envie prints ou fotos para análise com IA (Groq/Llama 4 Scout)
- **Indicador de digitação** — enquanto a IA prepara a resposta, o chat mostra os três pontos animados no balão do Vortax
- **Agente ReAct** — DeepSeek V4 Flash decide ferramenta → executa → avalia resultado → repete
- **Desenvolvimento de software** — usa o Vertex CLI via shell_run para criar projetos completos
- **Validação pós-Vertex** — sites passam por preview/Chrome/visão; scripts Python passam por `py_compile`; projetos Node/JS passam por checagem de sintaxe, build e testes quando aplicável
- **Correção automática de bugs** — se `web_validation` ou `project_validation` falhar, o runner impede `finish`, envia os bugs ao Vertex e repete a validação
- **Stream detalhado do Vertex** — card com etapa atual, legenda estimada, arquivo atual, trilha de progresso e status da validação
- **Shell seguro** — comandos com whitelist, bloqueio de padrões perigosos e workspace isolada
- **Download em ZIP** — todos os arquivos gerados na conversa em um único arquivo
- **Segurança LAN-only** — middleware que bloqueia IPs públicos, sem exposição externa

---

## Arquitetura

```
Usuário na LAN (http://IP:5173)
        │
        ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│   Frontend       │───▶│   Backend        │───▶│   DeepSeek API   │
│   React + Vite   │    │   FastAPI :8010  │    │   V4 Flash       │
│   :5173          │◀───│   WebSocket      │    │   (planejamento) │
└──────────────────┘    └────────┬─────────┘    └───────┬──────────┘
                                 │                       │
                                 ▼                       ▼
            ┌────────────────────────────┐   ┌──────────────────────┐
            │    Ferramentas Locais      │   │   Vertex CLI         │
            │  • Chrome CDP (Playwright) │   │   (via shell_run)    │
            │  • Shell seguro + Vertex   │   │                      │
            │  • Visão (Groq/Llama 4)    │   │                      │
            │  • Exatas (exact_solve)    │   │                      │
            └────────────────────────────┘   └──────────────────────┘
                                 │                    │
                                 ▼                    ▼
            ┌───────────────────────────────────────────┐
            │  Banco_de_dados/Vortax/projetos + SQLite  │
            │   • Arquivos gerados → download ZIP      │
            │   • Histórico persistido por conversa    │
            └───────────────────────────────────────────┘
```

---

## Estrutura

```
Vortax/
├── backend/              # FastAPI + Uvicorn
│   ├── api/              # REST + WebSocket
│   ├── services/         # Agente, stream, validação, qualidade de fontes
│   ├── tools/            # Browser, visão, executor
│   └── tests/            # Testes automatizados
├── frontend/             # React 18 + Vite
│   └── src/
│       ├── components/   # Chat, stream, preview, arquivos e painéis
│       ├── hooks/        # WebSocket, estado persistente e dados da task
│       └── lib/          # API client
├── scripts/              # start-dev.sh
└── PLANO_VORTAX.md       # Plano técnico e log de evolução
```

---

## Requisitos

- Python 3.10+
- Node.js 18+
- Google Chrome instalado
- Chave de API DeepSeek (ou roda em modo mock)
- Vertex CLI instalado (para desenvolvimento de software)

## Instalação e execução

```bash
# Clone
git clone git@github.com:alvaro209890/Vortax.git
cd Vortax

# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install-deps chromium
cd ..

# Frontend
cd frontend
npm install
cd ..

# Configurar chave DeepSeek
cp .env.example .env
# Edite .env com DEEPSEEK_API_KEY

# Iniciar
./scripts/start-dev.sh
```

Acesse o frontend em `http://localhost:5173` ou pelo IP da máquina na LAN.

---

## Respostas Rápidas e Exatas

O runner possui um roteador antes do planner:

- Perguntas simples, conceituais e curtas usam resposta direta do DeepSeek no chat, sem abrir ciclo de planejamento.
- Pedidos de criação, correção, publicação, automação, pesquisa ou dado atual continuam no planner com ferramentas.
- Perguntas de matemática/exatas chamam `exact_solve` antes de responder. A tool resolve contas, porcentagens e equações simples de forma determinística.
- Imagens com exercícios passam primeiro por `vision_analyze`, que transcreve enunciado, números, fórmulas e unidades; depois o backend tenta `exact_solve` e usa o DeepSeek para explicar quando o problema exige raciocínio além da conta determinística.

---

## Deploy Firebase + Cloudflare

O deploy externo separa frontend e backend:

- **Frontend:** Firebase Hosting no projeto `notazap-2520f`, site `notazap-2520f`, URL `https://notazap-2520f.web.app`.
- **Backend:** continua rodando neste PC em `127.0.0.1:8010`.
- **Túnel público do backend:** Cloudflare Tunnel dedicado `vortax-api`, UUID `8c063535-c3cd-427a-9546-e8d48b9e4822`, hostname `https://vortax-api.cursar.space`.

Arquivos versionados de deploy:

- `firebase.json` — publica `frontend/dist` como SPA no Firebase Hosting.
- `.firebaserc` — aponta o projeto default para `notazap-2520f`.
- `frontend/.env.production` — define `VITE_API_BASE_URL=https://vortax-api.cursar.space`.
- `deploy/cloudflared/vortax-api.yml` — ingress isolado do túnel Vortax para `http://127.0.0.1:8010`.
- `deploy/systemd/user/vortax-backend.service` — serviço systemd de usuário para iniciar o backend automaticamente no boot.
- `deploy/systemd/user/vortax-cloudflared.service` — serviço systemd de usuário para manter o túnel ativo.

Comandos usados no servidor:

```bash
# Instalar config local do túnel
install -D -m 600 deploy/cloudflared/vortax-api.yml ~/.cloudflared/vortax-api.yml
install -D -m 644 deploy/systemd/user/vortax-backend.service ~/.config/systemd/user/vortax-backend.service
install -D -m 644 deploy/systemd/user/vortax-cloudflared.service ~/.config/systemd/user/vortax-cloudflared.service

# DNS do túnel
cloudflared tunnel route dns --overwrite-dns 8c063535-c3cd-427a-9546-e8d48b9e4822 vortax-api.cursar.space

# Serviços persistentes no boot do PC
loginctl enable-linger server
systemctl --user daemon-reload
systemctl --user enable --now vortax-backend.service
systemctl --user enable --now vortax-cloudflared.service

# Build e deploy do frontend
cd frontend
npm run build
cd ..
firebase deploy --project notazap-2520f --only hosting:notazap-2520f
```

Validação esperada:

```bash
systemctl --user is-enabled vortax-backend.service vortax-cloudflared.service
systemctl --user is-active vortax-backend.service vortax-cloudflared.service
curl https://vortax-api.cursar.space/health
curl https://notazap-2520f.web.app
```

O backend precisa permitir CORS para `https://notazap-2520f.web.app` e `https://notazap-2520f.firebaseapp.com`; isso já está no default de `ALLOWED_ORIGINS` e em `.env.example`.

Como `LAN_ONLY=true` continua ativo, o acesso público ao backend só é aceito quando o hostname está em `PUBLIC_HOSTS` e a requisição vem com headers do Cloudflare Tunnel. O valor padrão é:

```bash
PUBLIC_HOSTS=vortax-api.cursar.space
```

---

## Stack

| Categoria | Tecnologia |
|-----------|------------|
| Backend | Python, FastAPI, Uvicorn, httpx |
| Frontend | React 18, Vite, Lucide React |
| Navegador | Playwright + Google Chrome CDP |
| IA (planejamento) | DeepSeek V4 Flash |
| IA (visão) | Groq + Llama 4 Scout |
| Motor de software | Vertex CLI via shell_run |
| Shell | Whitelist, bloqueio de padrões perigosos, timeout |
| Banco | SQLite com WAL |
| Streaming | WebSocket com replay de eventos |
| Validação | `py_compile`, `node --check`, `npm run build`, `npm test`, Chrome/visão |
| Segurança | Middleware LAN-only, sanitização de segredos |

## Validação e Correção Automática

Depois de cada execução do Vertex, o Vortax registra eventos de validação:

- `web_validation_*` para sites, interfaces, dashboards e apps web;
- `project_validation_*` para qualquer projeto de código, incluindo Python, Node/JS, scripts, APIs e sistemas locais.

O runner só permite finalizar quando a validação obrigatória passa. Se houver bug, o próprio histórico enviado ao planner inclui os problemas encontrados e obriga uma nova chamada ao Vertex para correção no projeto atual.

Checagens atuais:

- HTML: referências locais ausentes em `href`/`src`;
- frontend web: preview interno, smoke test de interação, screenshots e visão;
- Python: `python3 -m py_compile` e `unittest discover` quando existir `tests/`;
- JavaScript/Node: `node --check`, `npm run build` e `npm test` quando os scripts/dependências permitem.

## Verificação Local

```bash
cd backend
./.venv/bin/python -m unittest discover -s tests

cd ../frontend
npm run build
```

## Contexto e Compactação

O Vortax mantém contexto por conversa no SQLite, inspirado na lógica de sessão do Vertex:

- cada `task_id` tem um registro em `conversation_contexts`;
- o backend estima tokens por histórico textual, imagens e resumo compactado;
- quando a conversa passa de 70% do limite, o frontend mostra `Quase cheio`;
- quando passa de 88%, os turnos antigos são compactados em um resumo e os turnos recentes continuam completos;
- o limite padrão é `24000` tokens estimados, menor que janelas máximas de modelos grandes para deixar margem ao prompt do planner, schema de tools e resultados de ferramentas.

Configuração via `.env`:

```bash
CONTEXT_TOKEN_LIMIT=24000
CONTEXT_WARNING_RATIO=0.70
CONTEXT_COMPACT_RATIO=0.88
CONTEXT_RECENT_MESSAGES=8
CONTEXT_SUMMARY_MAX_CHARS=5000
```

---

## Licença

MIT
