# Vortax

**Agente de IA web local** — inspirado no fluxo do Manus. Converse em um chat e veja a IA operar este computador: pesquisar na web, navegar em páginas, extrair conteúdo, capturar screenshots e gerenciar arquivos — tudo em tempo real.

> Versão MVP local em LAN. Sem autenticação, sem hospedagem externa.

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
└──────────────────┘    └────────┬─────────┘    └──────────────────┘
                                 │
                                 ▼
            ┌────────────────────────────────────┐
            │         Ferramentas Locais          │
            │  • Chrome CDP (Playwright)          │
            │  • Shell seguro (whitelist)         │
            │  • Screenshot (MSS/X11)             │
            │  • PyAutoGUI (desktop)              │
            │  • File Manager (workspace/)        │
            └────────────────────────────────────┘
```

---

## Funcionalidades

- **Chat contínuo** — múltiplas mensagens na mesma conversa, histórico persistido
- **Navegação web** — Google Chrome do sistema via CDP, pesquisa estruturada, extração de artigos
- **Stream em tempo real** — WebSocket com eventos de ação, screenshots e resultados
- **Fontes com qualidade** — URLs visitadas são classificadas e pontuadas automaticamente
- **Galeria de screenshots** — todos os prints da sessão, com navegação e modal ampliado
- **Painel de atividade** — timeline lateral com resumo das ações do agente
- **Agente ReAct** — DeepSeek V4 Flash decide ferramenta → executa → avalia resultado → repete
- **Segurança LAN-only** — middleware que bloqueia IPs públicos, sem exposição externa

---

## Estrutura

```
Vortax/
├── backend/              # FastAPI + Uvicorn
│   ├── api/              # REST + WebSocket
│   ├── services/         # Agente, stream, qualidade de fontes
│   ├── tools/            # Browser, executor
│   └── tests/            # Testes automatizados
├── frontend/             # React 18 + Vite
│   └── src/
│       ├── components/   # 10 componentes de UI
│       ├── hooks/        # WebSocket hook
│       └── lib/          # API client
├── scripts/              # start-dev.sh
└── workspace/            # Área isolada do agente
```

---

## Requisitos

- Python 3.10+
- Node.js 18+
- Google Chrome instalado
- Chave de API DeepSeek (ou roda em modo mock)

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

## Stack

| Categoria | Tecnologia |
|-----------|------------|
| Backend | Python, FastAPI, Uvicorn, httpx |
| Frontend | React 18, Vite, Lucide React |
| Navegador | Playwright + Google Chrome CDP |
| IA | DeepSeek V4 Flash (planejamento) |
| Banco | SQLite com WAL |
| Streaming | WebSocket com replay de eventos |
| Segurança | Middleware LAN-only, sanitização de segredos |

---

## Licença

MIT
