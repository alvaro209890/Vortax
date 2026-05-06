# 🌀 Plano Técnico — Vortax (Agente Web Local com Acesso a Este PC)

> **Versão:** 2.3 — MVP local em LAN, interface de chat estilo Manus e visão via Groq  
> **Objetivo:** Desenvolver um site web local, parecido no fluxo com o Manus, para controlar uma IA que opera este PC Linux Mint. A primeira versão roda somente na rede local, sem autenticação e sem hospedagem externa, com chat em tempo real, stream das ações executadas no computador, DeepSeek V4 Flash para texto/planejamento e `meta-llama/llama-4-scout-17b-16e-instruct` via API da Groq para análise de imagem.

---

## 📋 Índice

1. [Análise do Ambiente](#1-análise-do-ambiente)
2. [Arquitetura do Sistema](#2-arquitetura-do-sistema)
3. [Estrutura de Pastas](#3-estrutura-de-pastas)
4. [Fase 1 — MVP Funcional](#4-fase-1--mvp-funcional)
5. [Fase 2 — Ferramentas Completas](#5-fase-2--ferramentas-completas)
6. [Fase 3 — Segurança e Produção Futura](#6-fase-3--segurança-e-produção-futura)
7. [Fase 4 — Melhorias Futuras](#7-fase-4--melhorias-futuras)
8. [Instalação e Execução Local](#8-instalação-e-execução-local)
9. [Riscos e Mitigações](#9-riscos-e-mitigações)
10. [Checklist de Desenvolvimento](#10-checklist-de-desenvolvimento)

---

## 1. Análise do Ambiente

### Hardware Real (levantado em 06/05/2026)

| Componente | Especificação | Status |
|------------|---------------|--------|
| CPU | Intel Core i5-3470 @ 3.20GHz (4 cores) | OK — folga para Vortax |
| RAM | 15GB total, ~8.1GB disponível | ⚠️ Moderado — Vortax usará ~1GB, deixar headroom |
| SO | Linux Mint 22.2 (Zara), base Ubuntu Noble | Compatível com tudo |
| GPU | Intel HD Graphics (integrada) | Não usada (IA é externa) |
| Google Chrome | 147.0.7727.137 | Já instalado, Playwright conectará via CDP |
| cloudflared | 2026.1.1 | Já instalado em `/usr/local/bin/cloudflared` |
| Git | Já configurado (user: alvaro209890) | OK |

### Serviços em Execução (06/05/2026)

| Serviço | Porta | RAM Aprox. | Cuidado |
|---------|-------|------------|---------|
| GeoServer (Java/Tomcat) | 8081, 8079 | ~1.8 GB | ⚠️ Não derrubar — é o maior consumidor |
| Nexus (FastAPI + ChromaDB) | 18000, 8001 | ~170 MB | Leve, sem risco |
| GeoForest-IA (Node/Vite/TSX) | 3002, 3003 | ~200 MB | Ambiente dev ativo |
| vertex-server (Node proxy + Vite) | 4000, 4001, 5174 | ~500 MB | Ambiente dev ativo |
| grouter-auth (Bun) | 3099, 3100, 3101, 3102 | Pequeno | Gateway de autenticação |
| Cloudflare Tunnels (4x) | 20241-20245 (localhost) | Pequeno | Túneis existentes |
| WMS Proxy (Python) | 8082 | Pequeno | Proxy GeoServer |

### Porta Escolhida para Vortax

**Porta 8010** — Livre e sem conflitos. Fora do range das aplicações existentes.

Durante desenvolvimento, o frontend Vite usará **porta 5173** com bind em `0.0.0.0` para acesso por outro computador na mesma rede local.

### Escopo de Acesso Local

O Vortax será executado e terá acesso operacional **a este PC Linux Mint**:

- **Navegador:** controla o Google Chrome instalado neste computador via Chrome DevTools Protocol em `127.0.0.1:9222`.
- **Tela:** captura o estado visual da sessão gráfica local via MSS/X11 (`DISPLAY=:0`).
- **Mouse e teclado:** pode usar PyAutoGUI/Xlib para operar interfaces fora do navegador quando a tarefa exigir.
- **Shell e arquivos:** por padrão rodam dentro da `workspace/` do projeto, com whitelist e bloqueios para comandos perigosos.
- **Ações críticas:** exclusão, envio de dados reais, comandos fora da workspace, automação desktop e qualquer ação irreversível exigem confirmação explícita do usuário.
- **Rede no MVP:** backend e frontend ficam acessíveis apenas pela LAN para testes de outro PC. Sem Cloudflare Tunnel, sem domínio público, sem HTTPS obrigatório e sem autenticação nesta primeira etapa.
- **Limite de exposição:** a porta CDP do Chrome (`9222`) deve continuar presa em `127.0.0.1` e nunca deve ser exposta na LAN, no Cloudflare ou em qualquer túnel.

### Viabilidade da RAM

| Serviço | RAM Estimada |
|---------|-------------|
| FastAPI + Uvicorn (Vortax) | ~150 MB |
| Playwright + Chrome via CDP | ~400-700 MB |
| MSS + Pillow + PyAutoGUI | ~50-120 MB |
| SQLite | ~20 MB |
| **Total Vortax MVP LAN** | **~620 MB - 970 MB** |
| **Já em uso pelo sistema** | **~6.9 GB** |
| **Total geral** | **~7.5 GB - 7.9 GB de 15 GB** |

**Folga de ~7 GB** — completamente viável. O Chrome via CDP ainda economiza disco porque não exige baixar outro Chromium para automação.

---

### Vertex CLI/Server — Motor de Desenvolvimento de Software

O Vertex é um **assistente de codificação por terminal** que roda localmente neste PC. Ele está instalado em dois projetos complementares:

- **Vertex CLI** (`/media/server/HD Backup/Servidores_NAO_MEXA/vertex-cli` v1.2.6) — Cliente de linha de comando. Aceita comandos em linguagem natural e desenvolve software, sites, scripts e quaisquer arquivos de código que o usuário solicitar. Usa o modelo `deepseek-v4-flash` ou `deepseek-v4-pro` como cérebro, com plena capacidade de ler, editar e criar arquivos no sistema.

- **Vertex Server** (`/media/server/HD Backup/Servidores_NAO_MEXA/vertex-server`) — Proxy FastAPI que traduz chamadas no formato Anthropic para DeepSeek. Inclui backend Express (porta 4000) para autenticação e dashboard web. O Vertex CLI se conecta a este servidor para funcionar.

**Como o Vortax usará o Vertex:**

O Vortax é o **frontend web** (chat em LAN) que permite ao usuário pedir tarefas de desenvolvimento de software. Quando o usuário solicitar a criação de um site, script, API ou qualquer código, o agente do Vortax:

1. Abre o terminal (`shell_run`)
2. Executa o comando `vertex` (que está no PATH)
3. Passa as instruções do usuário para o Vertex CLI
4. O Vertex CLI desenvolve o software, criando todos os arquivos necessários na `workspace/`
5. Captura o resultado e o progresso
6. Os arquivos gerados ficam disponíveis para download

**Exemplo de fluxo:** O usuário digita "Crie um site de portfólio com HTML, CSS e JS". O agente Vortax executa `vertex "Crie um site portfolio em workspace/portfolio com HTML, CSS e JS responsivo"`, o Vertex desenvolve o projeto completo, e os arquivos aparecem no painel de arquivos do chat.

**Comando de ativação:** O Vertex CLI está registrado como comando global do sistema. Basta executar no terminal:
```bash
vertex "descrição do software que deseja criar"
```
Para desenvolvimento de software pelo Vortax, o agente usará `shell_run` com o comando `vertex`.

---

## 2. Arquitetura do Sistema

```
┌─────────────────────────────────────────────────────────┐
│          USUÁRIO NA LAN (outro PC, notebook ou celular) │
│          http://IP-DESTE-PC:5173                         │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP/WebSocket na rede local
                       ▼
┌─────────────────────────────────────────────────────────┐
│       ESTE PC — LINUX MINT 22.2, i5-3470 + 15GB RAM     │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │       Frontend React/Vite (:5173, LAN)           │   │
│  │  • Interface chat-first estilo Manus             │   │
│  │  • Stream visual do que o agente está fazendo    │   │
│  │  • Timeline de passos, logs, screenshots, status │   │
│  └──────────────────┬──────────────────────────────┘   │
│                     │ REST + WebSocket                 │
│  ┌──────────────────▼──────────────────────────────┐   │
│  │         FastAPI + Uvicorn (:8010, LAN)           │   │
│  │  • REST API (tarefas, arquivos, controle)        │   │
│  │  • WebSocket/SSE (eventos em tempo real)         │   │
│  │  • Sem login no MVP; uso restrito a rede local   │   │
│  └──────────────────┬──────────────────────────────┘   │
│                     │                                   │
│  ┌──────────────────▼──────────────────────────────┐   │
│  │           ORQUESTRADOR (Loop ReAct)              │   │
│  │  1. Recebe tarefa do usuário                    │   │
│  │  2. Consulta DeepSeek V4 Flash                   │   │
│  │  3. DeepSeek decide ferramenta + parâmetros      │   │
│  │  4. Executa ferramenta localmente                │   │
│  │  5. Publica eventos para o chat em tempo real    │   │
│  │  6. Loop até "finish" ou max_iterations          │   │
│  └──────────────────┬──────────────────────────────┘   │
│                     │                                   │
│  ┌──────────────────▼──────────────────────────────┐   │
│  │              FERRAMENTAS LOCAIS                   │   │
│  │  🌐 Playwright + Chrome CDP → Chrome deste PC     │   │
│  │  🖱  PyAutoGUI/Xlib → mouse/teclado local         │   │
│  │  💻 Shell Seguro → bash whitelisted na workspace  │   │
│  │  📁 File Manager → leitura/escrita isolada        │   │
│  │  📸 Screenshot (MSS/X11) → captura da tela local  │   │
│  │  👁  Visão → Llama 4 Scout via Groq               │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │              ARMAZENAMENTO LOCAL                  │   │
│  │  • SQLite por sessão no HD de backup              │   │
│  │  • /workspace/ → arquivos gerados e área segura   │   │
│  │  • logs/status reproduzíveis por task e sessão    │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                  APIs EXTERNAS                           │
│  • DeepSeek API: deepseek-v4-flash (texto/planejamento)│
│  • Groq Vision: meta-llama/llama-4-scout-17b-16e-instruct │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Estrutura de Pastas

```
/media/server/HD Backup/Servidores_NAO_MEXA/Vortax/
│
├── backend/
│   ├── main.py                  # FastAPI — entrypoint
│   ├── config.py                # pydantic-settings (.env)
│   ├── access.py                # MVP: guard simples de LAN, sem login
│   ├── database.py              # SQLite por sessão no HD de backup
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── orchestrator.py      # Loop principal ReAct
│   │   ├── planner.py           # DeepSeek V4 Flash API
│   │   └── state.py             # AgentStatus enum + AgentState
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── browser.py           # Playwright + Google Chrome via CDP
│   │   ├── shell.py             # Subprocess seguro
│   │   ├── file_manager.py      # Arquivos na workspace/
│   │   ├── screenshot.py        # MSS/X11 — captura de tela local
│   │   ├── pyautogui_tool.py    # Mouse/teclado fora do navegador
│   │   ├── vision.py            # Visão plugável
│   │   └── tool_executor.py     # Dispatcher por nome
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── tasks.py             # CRUD tarefas
│   │   ├── files.py             # Download/list arquivos
│   │   ├── ws.py                # WebSocket de eventos do chat/agente
│   │   └── control.py           # Pausar/parar/confirmar
│   │
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   ├── index.css
│   │   ├── components/
│   │   │   ├── ChatShell.jsx
│   │   │   ├── Composer.jsx
│   │   │   ├── MessageList.jsx
│   │   │   ├── ActionTimeline.jsx
│   │   │   ├── ScreenView.jsx
│   │   │   ├── FileList.jsx
│   │   │   ├── StatusBadge.jsx
│   │   │   └── ConfirmDialog.jsx
│   │   └── hooks/
│   │       └── useWebSocket.js
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── postcss.config.js
│
├── workspace/                   # Isolada — escrita padrão do agente
│   └── .gitkeep
│
├── systemd/                     # Somente fases futuras
│   ├── vortax-backend.service
│   └── vortax-tunnel.service
│
├── scripts/
│   ├── start-dev.sh             # Script de dev local
│   ├── start-prod.sh            # Script de produção
│   ├── stop.sh                  # Para processos manuais
│   └── install.sh               # Instalação automatizada
│
├── .env.example
├── .gitignore
├── cloudflared-config.yml.example # Somente fase futura com hospedagem externa
├── PLANO_VORTAX.md              # Este arquivo
└── README.md
```

### Banco de Dados no HD de Backup

O projeto está em `/media/server/HD Backup/Servidores_NAO_MEXA/Vortax`, dentro do HD de backup montado em `/media/server/HD Backup` (`/dev/sdb4`, ~1.9 TB). Já existe uma pasta real de bancos em:

```text
/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados/
```

O Vortax deve criar e usar:

```text
/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados/Vortax/
├── ses_1/
│   └── session.sqlite
├── ses_2/
│   └── session.sqlite
└── ...
```

Cada inicialização cria uma nova pasta `ses_N/`, mantendo logs e tarefas isolados por sessão. Os bancos já existentes em `AgroOliveira/`, `Eco_Gestor/`, `SaldoPro/` e outros projetos devem ser tratados como somente leitura para detecção de padrão e nunca alterados.

---

## 4. Fase 1 — MVP Funcional

**Objetivo:** site web local estilo Manus — usuário conversa em um chat → DeepSeek V4 Flash planeja → ferramentas operam este PC → frontend exibe respostas, passos, screenshots e logs em tempo real.

Premissas obrigatórias da Fase 1:

- Sem autenticação, login, JWT ou senha.
- Sem hospedagem externa, sem Cloudflare Tunnel e sem domínio público.
- Acesso apenas pela rede local, usando `http://IP-DESTE-PC:5173` para o frontend e `http://IP-DESTE-PC:8010` para a API.
- Interface principal deve ser um chat, não um painel técnico. O painel técnico aparece como stream lateral/inferior das ações da IA.
- Texto/planejamento usa `deepseek-v4-flash`.
- Visão usa inicialmente `meta-llama/llama-4-scout-17b-16e-instruct` via API da Groq, em backend, e fica desligada por padrão até `ENABLE_VISION_TESTS=true`.

### 4.1 `.env.example`

```env
# Acesso local
APP_ENV=local_lan
APP_HOST=0.0.0.0
BACKEND_PORT=8010
FRONTEND_PORT=5173
LAN_ONLY=true
ALLOW_NO_AUTH=true
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://IP-DESTE-PC:5173

# IA de texto/planejamento
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TEMPERATURE=0.1

# Visão experimental: usar apenas na fase de testes via Groq
ENABLE_VISION_TESTS=false
VISION_PROVIDER=groq_llama4_scout
GROQ_API_KEY=gsk_...
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_VISION_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
GROQ_VISION_TEMPERATURE=0.1
GROQ_VISION_TIMEOUT_SECONDS=60

# Agente
MAX_ITERATIONS=30
WORKSPACE_PATH="/media/server/HD Backup/Servidores_NAO_MEXA/Vortax/workspace"
SCREENSHOT_INTERVAL=5
STREAM_SCREENSHOT_INTERVAL=2

# Google Chrome deste PC
CHROME_BINARY=/usr/bin/google-chrome
CHROME_DEBUG_PORT=9222
CHROME_PROFILE_PATH=/tmp/vortax-chrome-profile

# Automação desktop local
ENABLE_DESKTOP_AUTOMATION=true
REQUIRE_CONFIRMATION_FOR_DESKTOP=true

# Banco de dados no HD de backup
DATABASE_BASE_PATH="/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados"
DATABASE_EXTENSION=.sqlite
```

### 4.2 `.gitignore`

```gitignore
.env
venv/
__pycache__/
*.pyc
node_modules/
dist/
workspace/*
!workspace/.gitkeep
*.db
*.sqlite
*.db-journal
*.db-wal
cloudflared-config.yml
frontend/dist/
```

### 4.3 `backend/config.py`

```python
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    # Acesso local
    APP_ENV: str = "local_lan"
    APP_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8010
    FRONTEND_PORT: int = 5173
    LAN_ONLY: bool = True
    ALLOW_NO_AUTH: bool = True
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # IA de texto/planejamento
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"
    DEEPSEEK_TEMPERATURE: float = 0.1

    # Visão experimental via Groq/Llama 4 Scout
    ENABLE_VISION_TESTS: bool = False
    VISION_PROVIDER: str = "groq_llama4_scout"
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_VISION_MODEL: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    GROQ_VISION_TEMPERATURE: float = 0.1
    GROQ_VISION_TIMEOUT_SECONDS: float = 60.0

    # Agente
    MAX_ITERATIONS: int = 30
    WORKSPACE_PATH: Path = Path("/media/server/HD Backup/Servidores_NAO_MEXA/Vortax/workspace")
    SCREENSHOT_INTERVAL: int = 5
    STREAM_SCREENSHOT_INTERVAL: int = 2

    # Chrome local via CDP
    CHROME_BINARY: str = "/usr/bin/google-chrome"
    CHROME_DEBUG_PORT: int = 9222
    CHROME_PROFILE_PATH: Path = Path("/tmp/vortax-chrome-profile")

    # Desktop local
    ENABLE_DESKTOP_AUTOMATION: bool = True
    REQUIRE_CONFIRMATION_FOR_DESKTOP: bool = True

    # Banco no HD de backup
    DATABASE_BASE_PATH: Path = Path("/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados")
    DATABASE_EXTENSION: str = ".sqlite"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
settings.WORKSPACE_PATH.mkdir(parents=True, exist_ok=True)
```

### Armazenamento e Download de Arquivos por Conversa

Os arquivos que o agente (via Vertex CLI ou ferramentas shell) gerar durante uma tarefa ficam salvos na pasta `workspace/`. O sistema deve permitir:

- **Listagem por conversa:** `GET /api/tasks/{task_id}/files` — lista apenas os arquivos gerados durante aquela conversa específica, retornando nome, tamanho e data de modificação.
- **Download completo em ZIP:** `GET /api/tasks/{task_id}/download` — gera e retorna um arquivo `.zip` contendo **todos** os arquivos que o agente criou na workspace durante aquela conversa. O ZIP é gerado sob demanda e descartado após o download.
- **Download individual:** `GET /api/files/{path}` — já existe para baixar um arquivo específico da workspace.

**Regras:**
- O download ZIP lista arquivos da workspace cujos nomes/timestamps correspondam ao período de execução da tarefa.
- Na primeira implementação, o ZIP incluirá todos os arquivos da workspace que foram criados ou modificados durante a janela de atividade da tarefa (entre `created_at` e `updated_at` da task, com margem de 5 minutos).
- O nome do arquivo ZIP segue o padrão: `vortax-{task_id[:8]}.zip`.
- O ZIP é gerado em memória com `io.BytesIO` e `zipfile.ZipFile`, nunca escrito em disco.
- O botão de download no frontend fica no painel de arquivos (FileList) e em um botão de destaque no cabeçalho da conversa quando há arquivos disponíveis.

### 4.4 `backend/database.py`

Status atual: **concluído e funcional**.

Base real deste PC:

```text
/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados/Vortax/
```

Arquivo atual:

```text
/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados/Vortax/vortax.sqlite
```

Implementação atual:

1. `DATABASE_BASE_PATH` aponta para `/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados`.
2. O backend cria/usa a subpasta `Vortax/`.
3. O SQLite é inicializado automaticamente em `vortax.sqlite`.
4. `PRAGMA foreign_keys = ON` garante exclusão em cascata.
5. O histórico do chat e os screenshots são persistidos e reapresentados no replay do WebSocket.

Tabelas:

- **tasks** — `id TEXT PK, description TEXT, status TEXT, created_at TEXT, updated_at TEXT, result TEXT`
- **events** — `id INTEGER PK AUTOINCREMENT, task_id TEXT FK, event_type TEXT, created_at TEXT, payload_json TEXT`
- **screenshots** — `id INTEGER PK AUTOINCREMENT, task_id TEXT FK, event_id INTEGER FK, created_at TEXT, caption TEXT, title TEXT, url TEXT, image_base64 TEXT`
- **chat_images** — `id INTEGER PK AUTOINCREMENT, task_id TEXT FK, event_id INTEGER FK, created_at TEXT, filename TEXT, content_type TEXT, question TEXT, analysis TEXT, image_base64 TEXT`

Funções mínimas:

- `create_task(task)`
- `update_task(task_id, status, result, updated_at)`
- `get_task(task_id)`
- `list_tasks()`
- `insert_event(task_id, event_type, created_at, payload)`
- `list_events(task_id)`
- `delete_task(task_id)`

### 4.5 `backend/access.py`

No MVP não haverá autenticação. Este arquivo deve existir apenas para concentrar proteções mínimas de rede local e deixar claro onde a autenticação entrará depois.

Regras:

- `ALLOW_NO_AUTH=true` por padrão na Fase 1.
- Validar `LAN_ONLY=true` em startup e registrar aviso explícito no log: "Vortax sem autenticação, use apenas em rede local confiável".
- Bloquear inicialização se `ALLOW_NO_AUTH=true` e alguma configuração futura tentar ativar túnel público/domínio externo.
- Opcional: middleware simples para aceitar apenas IPs privados (`127.0.0.1`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) quando `LAN_ONLY=true`.
- Não criar `/auth/login`, JWT, tela de login ou cadastro nesta fase.

### 4.6 `backend/agent/state.py`

```python
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone

class AgentStatus(str, Enum):
    STOPPED = "stopped"
    THINKING = "thinking"
    EXECUTING = "executing"
    WAITING_CONFIRMATION = "waiting_confirmation"
    DONE = "done"
    ERROR = "error"

@dataclass
class AgentState:
    task_id: str
    status: AgentStatus = AgentStatus.STOPPED
    current_step: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
```

### 4.7 `backend/agent/planner.py`

- Classe `DeepSeekPlanner`.
- Método `async get_next_action(conversation_history) -> dict`.
- Prompt de sistema com schema JSON das ferramentas ativas: no MVP, browser via CDP; na Fase 2, todas as ferramentas do agente.
- `POST ${DEEPSEEK_BASE_URL}/chat/completions` com `model: settings.DEEPSEEK_MODEL` (`deepseek-v4-flash`), `temperature: settings.DEEPSEEK_TEMPERATURE`, `response_format: {"type": "json_object"}`.
- Timeout 60s via httpx.
- Retorna JSON parseado com `action`, `description`, `params`, `requires_confirmation`.
- Não usar `deepseek-chat` como padrão novo; manter apenas como fallback manual, pois os aliases legados devem sair do caminho principal.
- Para o chat, separar dois tipos de saída:
  - **resposta do assistente:** texto final ou parcial que aparece como mensagem.
  - **evento operacional:** ação, ferramenta, screenshot, stdout/stderr, confirmação ou erro que aparece no stream de execução.

**Formato de resposta esperado do modelo:**

```json
{
  "action": "browser_navigate",
  "description": "Abrindo Google para pesquisar",
  "params": {"url": "https://www.google.com"},
  "requires_confirmation": false
}
```

Ou para finalizar:

```json
{
  "action": "finish",
  "result": "Tarefa concluída: arquivo relatorio.csv salvo com 3 preços"
}
```

### 4.8 `backend/tools/browser.py`

- Classe `BrowserTool` com Playwright conectado ao **Google Chrome instalado neste PC**.
- Inicialização lazy: `_ensure_browser()` tenta conectar em `http://127.0.0.1:9222`; se não houver Chrome com debug ativo, chama `_launch_chrome()`.
- `_launch_chrome()` executa `settings.CHROME_BINARY` com:
  - `--remote-debugging-port=9222`
  - `--no-first-run`
  - `--no-default-browser-check`
  - `--user-data-dir=/tmp/vortax-chrome-profile`
- **Não baixar Chromium do Playwright para navegação.** Usar `playwright install-deps chromium` apenas para dependências Linux.
- Métodos:
  - `navigate(url, task_id)` — `page.goto()` com timeout 30s.
  - `click(selector, task_id)` — `page.click()` com timeout 10s.
  - `click_text(text, task_id)` — `page.get_by_text(text, exact=False).first.click()`; preferível ao seletor CSS.
  - `type_text(selector, text, task_id)` — `page.fill()`.
  - `press_key(key, task_id)` — `page.keyboard.press()`.
  - `extract_text(task_id)` — `page.inner_text("body")[:6000]`.
  - `extract_links(task_id)` — lista até 30 links `{text, href}`.
  - `take_screenshot(task_id)` — screenshot JPEG base64.
  - `scroll(direction="down", amount=500, task_id)` — `page.mouse.wheel()`.
  - `wait_for_element(selector, timeout, task_id)` — aguarda seletor.
  - `evaluate_js(script, task_id)` — executa JS controlado na página e limita retorno.

### 4.9 `backend/tools/tool_executor.py`

No MVP, registrar apenas as ações `browser_*` necessárias para navegar, clicar, digitar, extrair texto e capturar screenshot. A estrutura abaixo já mostra o dispatcher final que será completado na Fase 2.

```python
from tools.browser import BrowserTool
from tools.shell import ShellTool
from tools.file_manager import FileManagerTool
from tools.screenshot import ScreenshotTool
from tools.pyautogui_tool import PyAutoGUITool
from tools.vision import VisionTool

browser_tool = BrowserTool()
shell_tool = ShellTool()
file_tool = FileManagerTool()
screenshot_tool = ScreenshotTool()
desktop_tool = PyAutoGUITool()
vision_tool = VisionTool()

TOOLS = {
    "browser_navigate": browser_tool.navigate,
    "browser_click": browser_tool.click,
    "browser_click_text": browser_tool.click_text,
    "browser_type": browser_tool.type_text,
    "browser_press_key": browser_tool.press_key,
    "browser_extract_text": browser_tool.extract_text,
    "browser_extract_links": browser_tool.extract_links,
    "browser_screenshot": browser_tool.take_screenshot,
    "browser_scroll": browser_tool.scroll,
    "browser_wait_for_element": browser_tool.wait_for_element,
    "browser_evaluate_js": browser_tool.evaluate_js,

    "shell_run": shell_tool.run,

    "file_read": file_tool.read,
    "file_write": file_tool.write,
    "file_append": file_tool.append,
    "file_list": file_tool.list_files,
    "file_delete": file_tool.delete,

    "screenshot_capture": screenshot_tool.capture,
    "screenshot_region": screenshot_tool.capture_region,
    "vision_analyze": vision_tool.analyze,

    "pyautogui_click": desktop_tool.click_at,
    "pyautogui_type": desktop_tool.type_string,
    "pyautogui_hotkey": desktop_tool.hotkey,
}

async def execute_tool(tool_name: str, params: dict, task_id: str) -> dict:
    if tool_name not in TOOLS:
        return {"success": False, "error": f"Ferramenta desconhecida: {tool_name}"}
    try:
        result = await TOOLS[tool_name](**params, task_id=task_id)
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### 4.10 `backend/agent/orchestrator.py`

Loop ReAct completo:

Eventos emitidos para o frontend:

- `assistant_message_delta` — pedaços de resposta textual quando houver streaming do modelo.
- `assistant_message_done` — resposta final da IA para o chat.
- `agent_status` — `thinking`, `executing`, `waiting_confirmation`, `done`, `error`.
- `tool_call` — nome da ferramenta, descrição e parâmetros seguros.
- `tool_result` — retorno resumido da ferramenta.
- `screen_frame` — screenshot JPEG base64 em baixa frequência para mostrar o que acontece no PC.
- `confirmation_request` — ação que precisa de aprovação do usuário antes de continuar.
- `error` — falha recuperável ou fatal.

```python
class AgentOrchestrator:
    def __init__(self, task_id, task_description, ws_broadcaster):
        self.task_id = task_id
        self.task = task_description
        self.broadcast = ws_broadcaster
        self.planner = DeepSeekPlanner()
        self.state = AgentState(task_id=task_id)
        self.history = []
        self.max_iterations = settings.MAX_ITERATIONS
        self._paused = False
        self._stopped = False
        self._confirm_event = asyncio.Event()

    async def run(self):
        # Adiciona tarefa inicial ao histórico
        self.history.append({"role": "user", "content": f"Tarefa: {self.task}"})

        for i in range(self.max_iterations):
            if self._stopped: break
            while self._paused: await asyncio.sleep(0.5)

            await self.log(f"Iteração {i+1} — consultando DeepSeek V4 Flash...")
            await self.set_status(AgentStatus.THINKING)

            response = await self.planner.get_next_action(self.history)
            self.history.append({"role": "assistant", "content": json.dumps(response)})

            if response.get("action") == "finish":
                await self.emit("assistant_message_done", {"content": response.get("result", "")})
                await self.log(f"Concluído: {response.get('result')}", "success")
                await self.set_status(AgentStatus.DONE)
                break

            if response.get("requires_confirmation"):
                approved = await self.request_confirmation(response.get("confirmation_message", "Confirmar?"))
                if not approved:
                    await self.log("Ação cancelada pelo usuário", "warning")
                    self.history.append({"role": "user", "content": "O usuário recusou a ação. Replaneje sem executar esse passo."})
                    continue

            await self.emit("tool_call", {"name": response.get("action"), "description": response.get("description")})
            await self.log(f"{response.get('action')} — {response.get('description')}", "action")
            await self.set_status(AgentStatus.EXECUTING)

            result = await execute_tool(response["action"], response.get("params", {}), self.task_id)
            await self.emit("tool_result", {"name": response.get("action"), "result": result})
            self.history.append({"role": "user", "content": f"Resultado: {json.dumps(result)}"})

            # Após ações visuais, envia screenshot para o frontend sem interromper a tarefa se falhar.
            if response["action"].startswith(("browser_", "pyautogui_")) and "screenshot" not in response["action"]:
                await self.send_auto_screenshot()

        else:
            await self.log("Limite de iterações atingido", "warning")
            await self.set_status(AgentStatus.ERROR)

    # Métodos auxiliares: emit, log, set_status, request_confirmation, confirm, pause, resume, stop
```

### 4.11 `backend/api/ws.py`

- `WS /ws/{task_id}` — WebSocket sem token no MVP, restrito pela rede local.
- `active_connections: dict[str, list[WebSocket]]`.
- `broadcast_to_task(task_id, message)` — envia JSON para todos os clientes da task.
- Heartbeat a cada 30s para manter conexão viva.
- Mensagens sempre em JSON com `type`, `task_id`, `created_at` e `payload`.
- O frontend usa esse canal para renderizar chat, timeline de ações, screenshots e solicitações de confirmação.

### 4.12 `backend/api/tasks.py`

- `POST /api/tasks/` — recebe `{"description": "..."}`. Cria task no banco, gera UUID, inicia `AgentOrchestrator.run()` via `asyncio.create_task()`. Retorna `{"task_id": "..."}`.
- `GET /api/tasks/` — lista todas as tasks do banco.
- `GET /api/tasks/{task_id}` — detalhes de uma task + eventos persistidos.
- `DELETE /api/tasks/{task_id}` — exclui o chat e apaga em cascata task, eventos e screenshots.

### 4.13 `backend/api/control.py`

- `POST /api/control/{task_id}/pause`
- `POST /api/control/{task_id}/resume`
- `POST /api/control/{task_id}/stop`
- `POST /api/control/{task_id}/confirm?approved=true`

No MVP, estas rotas ficam sem autenticação. A proteção é apenas o isolamento de LAN e confirmações explícitas para ações críticas.

### 4.14 `backend/main.py`

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from config import settings
from database import init_db
from api import tasks, files, ws, control
from access import install_lan_guard

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_result = await init_db()
    print(f"Vortax DB session: {init_result}")
    yield

app = FastAPI(title="Vortax", version="0.2.2", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
install_lan_guard(app)

app.include_router(tasks.router, prefix="/api/tasks")
app.include_router(control.router, prefix="/api/control")
app.include_router(files.router, prefix="/api/files")
app.include_router(ws.router)

# Futuro: servir frontend buildado
# app.mount("/", StaticFiles(directory="../frontend/dist", html=True), name="frontend")
```

### 4.15 `backend/requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
pydantic==2.8.2
pydantic-settings==2.4.0
httpx==0.27.2
playwright==1.47.0
mss==9.0.2
Pillow==10.4.0
aiofiles==24.1.0
aiosqlite==0.20.0
python-multipart==0.0.9
pyautogui==0.9.54
python-xlib==0.33
opencv-python-headless==4.10.0.84
```

### 4.16 Frontend — React + Vite + Tailwind

Objetivo de UX: a primeira tela já deve ser o chat operacional, inspirado no fluxo do Manus, sem landing page. Não copiar marca, nome, textos ou identidade visual do Manus; usar apenas o padrão de interação: chat central, execução visível, estado do agente e histórico de passos.

**package.json:**
```json
{
  "name": "vortax-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite --host 0.0.0.0 --port 5173",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@heyputer/puter.js": "latest",
    "lucide-react": "^0.468.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.0",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.40",
    "tailwindcss": "^3.4.7",
    "vite": "^5.3.0"
  }
}
```

**vite.config.js** — proxy `/api` e `/ws` para `http://127.0.0.1:8010` durante dev no mesmo PC. Quando acessado por outro PC na LAN, o frontend deve usar `VITE_API_BASE_URL=http://IP-DESTE-PC:8010`.

**Layout do App.jsx:**
- Sidebar esquerda estreita: sessões/tarefas recentes, botão de nova conversa e status do backend.
- Coluna central: chat com mensagens do usuário, respostas da IA e composer fixo no rodapé.
- Painel direito: tela ao vivo/screenshot atual do PC, estado do agente, botões pausar/continuar/parar e confirmações pendentes.
- Faixa inferior ou timeline lateral: stream de execução com eventos `thinking`, `tool_call`, `tool_result`, `screen_frame`, `error`.
- FileList discreto para arquivos gerados/downloads.
- ConfirmDialog para ações que exigem confirmação.

Regras de interface:

- A área principal deve parecer um produto de agente, não um dashboard de logs.
- O stream deve mostrar o que a IA está fazendo em linguagem curta: "Abrindo Chrome", "Lendo texto da página", "Digitando no campo de busca".
- O screenshot deve atualizar sem recarregar a página e sem travar o chat.
- Botões principais usam ícones (`Send`, `Pause`, `Square`, `Play`, `Monitor`, `Folder`, `Check`, `X`) com tooltip.
- Tema escuro sofisticado com cinza/neutro, branco e acentos em cyan/verde; evitar uma tela dominada por uma única cor.
- Layout responsivo: em telas pequenas, painel de tela/timeline vira aba, mantendo o chat como prioridade.

### 4.16.1 Visão experimental no backend com Groq/Llama 4 Scout

Durante a fase de testes, a análise de imagem pode ser ligada por `ENABLE_VISION_TESTS=true`.

Implementação recomendada:

- Criar `backend/tools/vision.py` e manter a chamada de visão no backend, nunca no frontend, para não expor `GROQ_API_KEY`.
- Usar endpoint OpenAI-compatible da Groq em `${GROQ_BASE_URL}/chat/completions`.
- Modelo inicial: `meta-llama/llama-4-scout-17b-16e-instruct`, configurável por `GROQ_VISION_MODEL`.
- Enviar imagens como data URL (`data:image/jpeg;base64,...`) dentro do conteúdo multimodal da mensagem.
- Retornar JSON simples para o planner: `summary`, `visible_text`, `objects`, `ui_elements`, `suggested_action`, `confidence`.
- Limitar resolução/tamanho antes do envio: reaproveitar screenshots JPEG 1280x720 ou menor, quality 75.
- Registrar no stream quando uma screenshot for enviada para análise externa, sem registrar o base64.
- Não tratar Puter/Qwen como caminho principal nesta fase; pode ficar apenas como fallback futuro se houver necessidade.

### 4.17 `scripts/start-dev.sh`

```bash
#!/bin/bash
cd "$(dirname "$0")/.."

# Inicia backend
cd backend
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt
# Usa o Google Chrome do sistema via CDP; instala só dependências Linux do Playwright
playwright install-deps chromium 2>/dev/null || true
uvicorn main:app --host 0.0.0.0 --port 8010 --reload &
BACKEND_PID=$!

# Inicia frontend
cd ../frontend
npm install --silent 2>/dev/null
npm run dev &
FRONTEND_PID=$!

LAN_IP=$(hostname -I | awk '{print $1}')

echo "🌀 Vortax rodando:"
echo "   Backend:  http://localhost:8010"
echo "   Frontend: http://localhost:5173"
echo "   Outro PC na LAN: http://$LAN_IP:5173"
echo "   MVP sem autenticação: use apenas em rede local confiável."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
```

### 4.18 `scripts/install.sh`

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")/.."

echo "🌀 Instalando Vortax..."

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
npm run build
cd ..

# Workspace
mkdir -p workspace
touch workspace/.gitkeep

# .env
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  Edite o arquivo .env com suas chaves de API"
fi

echo "✅ Instalacao concluida!"
echo "   Execute: ./scripts/start-dev.sh"
```

### Verificação da Fase 1

```bash
# Terminal 1 — backend em LAN
cd backend && source .venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 8010

# Terminal 2 — frontend (dev)
cd frontend && npm run dev

# Teste sem autenticação no MVP
curl -X POST http://localhost:8010/api/tasks/ \
  -H "Content-Type: application/json" \
  -d '{"description": "Abra google.com e me diga o titulo da pagina"}'

# Ver eventos via WebSocket: ws://localhost:8010/ws/{task_id}
# Em outro PC da rede: http://IP-DESTE-PC:5173
```

---

## 5. Fase 2 — Ferramentas Completas

### 5.19 `backend/tools/shell.py`

- Whitelist: `python3`, `python`, `pip3`, `pip`, `node`, `npm`, `npx`, `echo`, `pwd`, `ls`, `cat`, `mkdir`, `cp`, `mv`, `touch`, `curl`, `wget`, `git`, `pandoc`, `ffmpeg`, `libreoffice`, `convert`, `grep`, `find`, `wc`, `head`, `tail`, `sort`, `uniq`, `awk`, `sed`, `cut`, `tr`, `df`, `free`, `uname`.
- `subprocess.run()` com `timeout=30`, `cwd=./workspace`, `capture_output=True`.
- Retorna `stdout[:3000]`, `stderr[:500]`, `returncode`.
- Bloqueia comandos não whitelistados.
- Bloqueia padrões perigosos: `sudo`, `su`, `chmod`, `chown`, `passwd`, `systemctl`, `service`, `kill`, `dd`, `mkfs`, `fdisk`, `format`, `rm -rf /`, `rm -rf ~`, escrita em `/dev/`, `curl | sh`, `curl | bash`.
- `rm` só deve ser permitido dentro da workspace e com confirmação quando apagar arquivos gerados importantes.

### 5.20 `backend/tools/file_manager.py`

- `_safe_path(filename)` — resolve caminho e verifica se está dentro de `WORKSPACE`.
- `read(filename)` — retorna conteúdo texto (max 10k chars) + tamanho.
- `write(filename, content)` — escreve arquivo, cria subpastas se necessário.
- `append(filename, content)` — adiciona conteúdo ao final de arquivo dentro da workspace.
- `list_files()` — recursivo com nome, tamanho, extensão.
- `delete(filename)` — remove arquivo dentro da workspace, com confirmação para arquivos relevantes.

### 5.21 `backend/tools/screenshot.py` (MSS)

- `capture(monitor=1)` — usa `mss` para capturar tela do monitor primário.
- Redimensiona para 1280x720 via Pillow.
- Comprime JPEG quality=75.
- Retorna base64 + dimensões.
- Garante `DISPLAY=:0` quando rodando via systemd.
- `capture_region(x, y, width, height)` — captura uma região específica da tela local.

### 5.22 `backend/tools/vision.py`

- `analyze(image_base64, question)` — arquitetura plugável.
- Suporte inicial de teste: `groq_llama4_scout`.
- Modelo inicial: `meta-llama/llama-4-scout-17b-16e-instruct`, configurável por `GROQ_VISION_MODEL`.
- Chamada via endpoint OpenAI-compatible da Groq: `POST ${GROQ_BASE_URL}/chat/completions`.
- `GROQ_API_KEY` fica apenas no backend. O frontend nunca deve chamar a Groq diretamente.
- Payload esperado:
  - `model: settings.GROQ_VISION_MODEL`
  - `temperature: settings.GROQ_VISION_TEMPERATURE`
  - `messages[0]` com prompt de sistema curto orientando saída JSON
  - `messages[1].content` com texto da pergunta e `image_url.url = "data:image/jpeg;base64,{image_base64}"`
- Resposta normalizada para o agente:
  - `summary`: descrição curta da tela/imagem
  - `visible_text`: textos relevantes encontrados
  - `ui_elements`: botões, menus, campos ou regiões clicáveis prováveis
  - `objects`: objetos visuais importantes
  - `suggested_action`: próxima ação visual sugerida, sem executar nada
  - `confidence`: `low`, `medium` ou `high`
- Se a Groq retornar texto fora de JSON, tentar extrair o primeiro objeto JSON; se falhar, retornar `summary` textual e marcar `confidence=low`.
- Não usar GPT-4o, Gemini, Puter/Qwen ou outro provider para visão no plano atual, salvo decisão futura.
- Provider definido em `VISION_PROVIDER` no .env.

#### Fluxo recomendado para visão

1. O planner detecta incerteza visual e chama `screenshot_capture` ou usa o último `screen_frame`.
2. `vision_analyze` recebe `image_base64` e uma pergunta específica, por exemplo: "Qual botão de login está visível e onde devo clicar?".
3. `VisionTool` reduz/valida tamanho da imagem, publica evento seguro de envio externo e chama Groq.
4. O resultado volta ao histórico como JSON compacto, sem base64.
5. O planner decide a próxima ferramenta: `browser_click_text`, `browser_click_selector` ou, em desktop, `pyautogui_click` com confirmação quando necessário.

#### Upload de imagens pelo chat

Implementado em 06/05/2026:

- Frontend aceita anexos `png`, `jpeg` e `webp` no composer do chat.
- `POST /api/tasks/images` cria uma conversa nova com imagem e pergunta.
- `POST /api/tasks/{task_id}/images` adiciona imagem a uma conversa existente.
- Backend limita cada imagem a 6 MB, converte para base64, publica `user_message` com `images[]` e salva em `chat_images`.
- A resposta da Groq é publicada como `assistant_message_done` e a imagem permanece visível no histórico do chat ao recarregar.
- `GET /api/tasks/{task_id}` retorna também `images` com os uploads persistidos.

### 5.23 `backend/tools/pyautogui_tool.py`

- Usa PyAutoGUI + Xlib para controlar **este desktop Linux Mint** fora do navegador.
- Configura `pyautogui.FAILSAFE = True` e `pyautogui.PAUSE = 0.3`.
- Métodos:
  - `move_mouse(x, y, duration=0.5)`
  - `click_at(x, y, button="left")`
  - `type_string(text, interval=0.05)`
  - `hotkey(*keys)`
  - `screenshot_position()`
- Sempre exigir confirmação antes de ações desktop que enviem dados, cliquem em botões de confirmação, alterem arquivos reais ou interajam com sistemas externos.

### 5.24 Atualizar `tool_executor.py`

Adicionar:
- `shell_run` → `shell_tool.run`
- `file_read` → `file_tool.read`
- `file_write` → `file_tool.write`
- `file_append` → `file_tool.append`
- `file_list` → `file_tool.list_files`
- `file_delete` → `file_tool.delete`
- `screenshot_capture` → `screenshot_tool.capture`
- `screenshot_region` → `screenshot_tool.capture_region`
- `vision_analyze` → `vision_tool.analyze`
- `pyautogui_click` → `desktop_tool.click_at`
- `pyautogui_type` → `desktop_tool.type_string`
- `pyautogui_hotkey` → `desktop_tool.hotkey`

### 5.25 Atualizar `planner.py` — TOOLS_SCHEMA completo

Adicionar browser completo, shell, file_manager, screenshot, vision e pyautogui ao prompt de sistema.

Regras obrigatórias no prompt:

1. Responder sempre com um único JSON válido.
2. Preferir `browser_click_text` a `browser_click` quando houver texto visível.
3. Usar `screenshot_capture` + `vision_analyze` quando não souber o estado visual atual, apenas se `ENABLE_VISION_TESTS=true`.
4. Salvar arquivos importantes na workspace antes de `finish`.
5. Ações destrutivas, envio de formulário com dados reais, comandos sensíveis e automação desktop exigem `requires_confirmation: true`.
6. Se uma ferramenta falhar, reavaliar e tentar abordagem diferente em vez de repetir cegamente.
7. Narrar ações em frases curtas para o chat, separando mensagem ao usuário de logs técnicos.

### 5.26 `backend/api/files.py`

- `GET /api/files/` — lista `workspace/` recursivamente.
- `GET /api/files/{path}` — download de arquivo com `FileResponse`.

---

## 6. Fase 3 — Segurança e Produção Futura

Esta fase não faz parte do primeiro teste. Só deve ser iniciada depois que o chat local em LAN estiver estável.

### 6.26 Build integrado

```bash
cd frontend && npm run build  # gera dist/
```

Em `main.py`, ativar `StaticFiles` para servir `frontend/dist/` no path `/`.
SPA mode: rotas não-API caem no `index.html`.

### 6.27 Cloudflare Tunnel (novo, isolado)

```bash
# Criar tunnel específico para Vortax
cloudflared tunnel create vortax

# Configurar ~/.cloudflared/vortax.yml
# tunnel: <UUID>
# credentials-file: /home/server/.cloudflared/<UUID>.json
# ingress:
#   - hostname: vortax.seudominio.com
#     service: http://localhost:8010
#   - service: http_status:404

# Rota DNS
cloudflared tunnel route dns vortax vortax.seudominio.com

# Rodar (inicialmente manual, depois systemd)
cloudflared tunnel --config ~/.cloudflared/vortax.yml run vortax
```

### 6.28 Serviço systemd (Linux, não Windows)

Como o caminho real contém espaço (`HD Backup`), a produção deve criar um symlink estável sem espaços antes de instalar os serviços:

```bash
ln -sfn "/media/server/HD Backup/Servidores_NAO_MEXA/Vortax" /home/server/vortax
```

```ini
# /etc/systemd/system/vortax-backend.service
[Unit]
Description=Vortax Backend
After=network.target

[Service]
Type=simple
User=server
WorkingDirectory=/home/server/vortax/backend
EnvironmentFile=/home/server/vortax/.env
Environment="PATH=/home/server/vortax/backend/.venv/bin:/usr/bin"
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/server/.Xauthority
ExecStart=/home/server/vortax/backend/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8010 --workers 1
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/vortax-tunnel.service
[Unit]
Description=Vortax Cloudflare Tunnel
After=vortax-backend.service

[Service]
Type=simple
User=server
ExecStart=/usr/local/bin/cloudflared tunnel --config /home/server/.cloudflared/vortax.yml run vortax
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 6.29 Rate limiting + bcrypt

- Criar `backend/auth.py` somente nesta fase.
- Adicionar tela de login ao frontend somente quando houver acesso fora da LAN.
- JWT com expiração curta e refresh explícito.
- `slowapi` middleware nos endpoints `/auth/login` (5/min) e `/api/tasks/` (10/min).
- Trocar senha plain-text por `bcrypt` via `passlib`.

### 6.30 Segurança final

- `.env` e `.gitignore` verificados.
- Path traversal testado com `../../../etc/passwd`.
- Comandos não-whitelist testados (`rm -rf`, `shutdown`).
- Token JWT com expiração.
- workspace/ com permissões restritas (750).

---

## 7. Fase 4 — Melhorias Futuras

- [ ] Memória persistente entre tarefas — RAG com embeddings via ChromaDB (reutilizar Nexus na porta 8001?).
- [ ] Upload de arquivos do usuário para o agente processar.
- [ ] Fila de tarefas com workers (múltiplas tarefas simultâneas).
- [ ] Dashboard de histórico com filtro por data/status e sessões `ses_N/`.
- [ ] Suporte a modelos alternativos: Claude, GPT-4, Llama local.
- [ ] Voice input (Web Speech API) / output (TTS).
- [ ] Agendamento de tarefas recorrentes.
- [ ] Export de sessão como replay (WebSocket dump).
- [ ] OpenCV/template matching para localizar elementos visuais por imagem.
- [ ] Notificação via email/Telegram quando tarefas longas terminarem.
- [ ] Rastreamento fino de arquivos por tarefa com metadados no banco (tabela `task_files` ligando `task_id` a caminhos e hashes dos arquivos gerados).
- [ ] Download ZIP com progresso para tarefas com muitos arquivos grandes.

---

## 8. Instalação e Execução Local

### Dependências do Sistema

```bash
sudo apt update
sudo apt install -y \
  python3 python3-pip python3-venv python3-dev \
  python3-xlib scrot xdotool libx11-dev libxtst-dev libpng-dev \
  nodejs npm git sqlite3
```

Para Playwright com Chrome do sistema:

```bash
cd "/media/server/HD Backup/Servidores_NAO_MEXA/Vortax/backend"
source .venv/bin/activate
playwright install-deps chromium
```

### Setup rápido (dev)

```bash
cd "/media/server/HD Backup/Servidores_NAO_MEXA/Vortax"
chmod +x scripts/*.sh
./scripts/install.sh
./scripts/start-dev.sh
```

### Produção futura (systemd + túnel)

Não executar na primeira fase de testes locais.

```bash
ln -sfn "/media/server/HD Backup/Servidores_NAO_MEXA/Vortax" /home/server/vortax
sudo cp scripts/vortax-backend.service /etc/systemd/system/
sudo cp scripts/vortax-tunnel.service /etc/systemd/system/
sudo chmod 600 /home/server/vortax/.env
sudo chmod 750 /home/server/vortax/workspace
sudo systemctl daemon-reload
sudo systemctl enable --now vortax-backend vortax-tunnel
```

### Comandos úteis

```bash
# Logs
sudo journalctl -u vortax-backend -f
sudo journalctl -u vortax-tunnel -f

# Status
sudo systemctl status vortax-backend vortax-tunnel

# Restart
sudo systemctl restart vortax-backend
```

---

## 9. Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| RAM esgotar se GeoServer + Vortax + outros picos | Média | Alto — OOM killer derruba processos | Monitorar com `htop`. Headroom de ~7GB é suficiente, mas vigiar. |
| GeoServer (Java, ~1.8GB) sofrer com competição de CPU | Baixa | Médio | Vortax usa CPU só durante chamadas de ferramenta. Evitar múltiplas tarefas pesadas em paralelo no MVP. |
| Chrome via CDP ser fechado manualmente | Média | Médio | `BrowserTool` tenta reconectar e relançar Chrome na próxima chamada. |
| Porta CDP `9222` exposta por engano | Baixa | Alto | Bind somente em `127.0.0.1`; nunca publicar `9222` no Cloudflare ou LAN. |
| MVP sem autenticação ser acessado por alguém na rede local | Média | Alto | Usar apenas em rede confiável, não abrir roteador/port forwarding, não ativar túnel, opcionalmente limitar IPs privados no middleware `LAN_ONLY`. |
| PyAutoGUI clicar no lugar errado | Média | Alto | Usar screenshot/visão antes de ações, FAILSAFE ativo e confirmação obrigatória para ações críticas. |
| MSS/PyAutoGUI falhar sem sessão X11 | Média | Médio | systemd com `DISPLAY=:0` e `XAUTHORITY=/home/server/.Xauthority`. |
| Banco criar sessão no lugar errado | Baixa | Médio | Fixar `DATABASE_BASE_PATH` no `.env` para `/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados/Vortax`. |
| DeepSeek API fora do ar | Baixa | Alto | Pausar tarefa e mostrar erro claro no chat. Fallback de modelo fica para fase futura. |
| Groq/Llama 4 Scout indisponível ou sem suporte multimodal esperado | Média | Médio | Manter `GROQ_VISION_MODEL` configurável, mapear erros do provider e deixar visão desligável por `ENABLE_VISION_TESTS=false`. |
| Agente executar ação inesperada | Média | Médio | Confirmação do usuário para ações destrutivas. Whitelist shell. Workspace isolada. |
| Consumo de API (custo) | Média | Baixo | `MAX_ITERATIONS=30`, limitar screenshots enviadas para visão e mostrar contadores de iteração no stream. |

---

## Resumo por Fase

| Fase | Arquivos | Horas Est. | Entregável |
|------|----------|-----------|------------|
| **1** | 19 arquivos | 8-12h | Site local em LAN: chat estilo Manus → DeepSeek V4 Flash → Chrome CDP → stream de ações e screenshots |
| **2** | 9 arquivos | 5-8h | Shell, arquivos, screenshot, visão experimental Groq/Llama 4 Scout e PyAutoGUI com confirmações |
| **3** | 5 arquivos + systemd | 3-5h | Produção futura: autenticação, HTTPS público via domínio próprio, serviço automático com X11, rate limit, bcrypt |
| **4** | Contínuo | — | RAG, fila, voice, multi-modelo |
| **Total MVP+futuro** | **33+ arquivos** | **16-25h** | Agente de IA web local primeiro; acesso externo só depois de segurança e autenticação |

---

## Log de Alterações

| Versão | Data | Alterações |
|--------|------|-----------|
| 2.4 | 06/05/2026 | Adicionada seção sobre Vertex CLI/Server como motor de desenvolvimento de software; documentado sistema de download ZIP de arquivos por conversa; atualizado checklist com novos itens de arquivamento e integração Vertex |
| 2.3 | 06/05/2026 | Plano de visão alterado para `meta-llama/llama-4-scout-17b-16e-instruct` via API da Groq; Puter/Qwen removido do caminho principal; adicionada arquitetura backend para `VisionTool` multimodal |
| 2.2 | 06/05/2026 | Ajustado escopo para MVP local em LAN, sem autenticação e sem hospedagem externa; frontend chat-first estilo Manus com stream de ações; DeepSeek V4 Flash para texto; Qwen3-VL via Puter apenas para testes de visão |
| 2.1 | 06/05/2026 | Incorporadas especificações do PDF: Chrome via CDP usando Google Chrome deste PC, PyAutoGUI/X11, MSS com `DISPLAY=:0`, banco por sessão no HD de backup em `Banco_de_dados/Vortax`, WebSocket autenticado e systemd preparado para desktop local |
| 2.0 | 06/05/2026 | Adaptado para Linux Mint 22.2, Chrome 147, porta 8010, systemd, análise de backends existentes, nome Vortax |
| 1.0 | 06/05/2026 | Versão inicial genérica (Windows) |

---

## 10. Checklist de Desenvolvimento

### MVP Local — Chat Básico

- [x] Preparação do projeto e arquivos base
- [x] Backend FastAPI local sem autenticação
- [x] Guard simples para uso em LAN
- [x] Rotas de tarefas com execução mockada
- [x] WebSocket de eventos em tempo real
- [x] Frontend React/Vite chat-first
- [x] Timeline/stream de ações do agente
- [x] Script `scripts/start-dev.sh`
- [x] Verificação local por API/WebSocket
- [x] Verificação de acesso por outro PC da LAN

### Próximos Blocos

- [x] Banco SQLite persistente em `/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados/Vortax/vortax.sqlite`
- [x] Integração DeepSeek V4 Flash
- [x] Reaproveitamento útil dos projetos Vertex
- [x] Integração Chrome CDP
- [x] Screenshot/stream visual real
- [ ] Visão experimental Groq/Llama 4 Scout
- [ ] Ferramentas reais de arquivos/shell com whitelist
- [x] Exclusão de chats com remoção no banco de dados
- [x] Persistência de screenshots/prints no banco de dados
- [x] Upload de imagens no chat para análise via Groq/Llama 4 Scout
- [x] Persistência de imagens enviadas pelo chat na tabela `chat_images`
- [x] Pesquisa estruturada no Google via `browser_google_search`
- [x] Extração de links/resultados via `browser_extract_links`
- [x] Abertura de resultados por índice via `browser_click_link_by_index`
- [x] Ferramentas auxiliares de navegação: `browser_get_state`, `browser_click_selector`, `browser_wait_for_text`, `browser_go_back`
- [x] Planner mais proativo para pesquisa web multi-etapa
- [x] Testes automatizados das ferramentas de pesquisa do navegador
- [x] Bloqueio de links de login/contas Google durante pesquisa
- [x] Continuidade de chat: novas mensagens entram na conversa ativa em vez de criar uma conversa por mensagem
- [x] Eventos `user_message` persistidos no histórico da conversa
- [x] Contexto de conversa persistido enviado ao planner em novas mensagens
- [x] Stream reorganizado em formato de atividade resumida, sem excesso de `agent_status`
- [x] Indicador de andamento no chat com estilo de execução tipo CLI
- [x] Galeria de prints por conversa com voltar/avançar e modal ampliado
- [x] Tabela `sources` para fontes visitadas por conversa
- [x] Ferramenta `browser_extract_article` para extracao limpa de conteudo principal
- [x] Registro automatico de fontes abertas/extraias com pontuacao de qualidade
- [x] Painel de fontes no frontend com tipo e score
- [ ] Download ZIP de arquivos por conversa via `GET /api/tasks/{task_id}/download`
- [ ] Botão de download ZIP no frontend por conversa com todos os arquivos gerados
- [ ] Integração Vertex CLI: agente usa `shell_run` com `vertex` para desenvolver software
- [ ] Documentação do Vertex CLI/Server e seu papel como motor de desenvolvimento

### Vertex CLI — Motor de Desenvolvimento de Software

O Vertex é o motor que permite ao Vortax desenvolver software, sites e scripts completos. Instalado em:

- **Vertex CLI:** `/media/server/HD Backup/Servidores_NAO_MEXA/vertex-cli` (v1.2.6)
- **Vertex Server:** `/media/server/HD Backup/Servidores_NAO_MEXA/vertex-server` (proxy DeepSeek)

**Como o Vortax invoca o Vertex:**

1. Usuário pede: "Crie um sistema de login em Python"
2. Agente do Vortax usa `shell_run` com `cwd=./workspace`
3. Executa: `vertex "Crie um sistema de login em Python com Flask e SQLite, salve em workspace/" --output-dir ./workspace/login-system`
4. Vertex CLI processa o pedido e gera todos os arquivos do projeto
5. Vortax captura o resultado e lista os arquivos no painel
6. Usuário pode baixar os arquivos individualmente ou como ZIP

**O Vertex CLI é um comando global do sistema.** Basta abrir o terminal e digitar `vertex` para usar interativamente, ou `vertex "instrução"` para execução direta. No contexto do Vortax, o agente faz essa chamada automaticamente.

### BrowserTool + Planner JSON

Implementado no backend:

- `backend/tools/browser.py` conecta ao Chrome via CDP em `127.0.0.1:9222`.
- Se não houver Chrome com debug ativo, o Vortax inicia o Google Chrome com perfil isolado em `CHROME_PROFILE_PATH`.
- Se a sessão gráfica não aceitar Chrome visível, há fallback headless para manter o teste funcional.
- No teste de 06/05/2026, a porta `9222` já estava ocupada por um Chrome debug externo com perfil `/home/server/.gemini/antigravity-browser-profile`; por isso o Vortax conectou nesse Chrome existente. Para forçar perfil isolado do Vortax, liberar a porta `9222` antes de iniciar uma tarefa ou trocar `CHROME_DEBUG_PORT`.
- Ferramentas disponíveis: `browser_navigate`, `browser_get_state`, `browser_google_search`, `browser_extract_links`, `browser_click_link_by_index`, `browser_click_text`, `browser_click_selector`, `browser_type`, `browser_press_key`, `browser_wait_for_text`, `browser_go_back`, `browser_extract_text`, `browser_screenshot`, `browser_scroll`.
- `backend/tools/tool_executor.py` centraliza `execute_tool()`, publica `tool_call`, `tool_result`, `screen_frame` e `error`, e reaproveita sanitização de payloads.
- `backend/services/deepseek_client.py` agora inclui `request_deepseek_action()`, que força resposta JSON do DeepSeek.
- `backend/services/agent_runner.py` roda loop ReAct simples: tarefa -> planner JSON -> tool executor -> resultado volta ao planner -> `finish`.
- O planner foi ajustado para ser mais proativo em pesquisas: usar Google quando a tarefa depender da internet, abrir resultados relevantes, extrair conteúdo de páginas e consultar mais fontes quando a pergunta exigir comparação ou confirmação.
- O planner foi ajustado para evitar páginas de login: não deve abrir `accounts.google.com`, `ServiceLogin`, preferências/configurações do Google, paywalls ou páginas de autenticação. Se cair em login, deve voltar e escolher outro resultado.
- `browser_click_link_by_index` agora usa resultados orgânicos estruturados quando a página atual é uma busca do Google, em vez de clicar em links genéricos como login, preferências ou navegação interna.
- Testes adicionados em `backend/tests/test_browser_search_tools.py` cobrem busca Google estruturada, extração de links e abertura de link por índice sem depender de internet.
- Os testes também cobrem bloqueio de URLs de login/conta Google.
- Smoke test real em 06/05/2026 validou `browser_google_search` contra o Google com retorno de 10 resultados estruturados.

### Chat Persistente e Stream

Implementado no backend/frontend:

- `POST /api/tasks/` cria uma conversa/tarefa nova apenas quando não há conversa ativa.
- `POST /api/tasks/{task_id}/messages` adiciona uma nova mensagem na conversa existente e dispara nova execução no mesmo histórico.
- A sidebar tem ação explícita de novo chat para iniciar outra conversa sem perder a continuidade da conversa atual.
- Eventos `user_message` são salvos no SQLite e usados para reconstruir o chat ao recarregar a página.
- Antes de cada execução, o runner reconstrói o contexto do modelo a partir dos últimos turnos persistidos (`user_message` e `assistant_message_done`), seguindo o padrão de reutilizar a conversa existente em vez de responder só à última mensagem isolada.
- O frontend monta as mensagens a partir de `user_message`, `assistant_message_delta` e `assistant_message_done`.
- O stream lateral oculta ruído técnico como `task_created` e `agent_status`, exibindo atividade resumida: pesquisa, abertura de resultado, leitura de página, tela atualizada e erros.
- O chat mostra um indicador de andamento com o último `agent_progress`, inspirado em feedback de execução de CLI.
- Enquanto o agente está executando, o composer fica bloqueado para evitar duas execuções simultâneas no mesmo chat.

### Prints Persistentes por Conversa

Implementado:

- Todo `screen_frame` com `image_base64` é salvo no SQLite na tabela `screenshots`, ligado ao `task_id` e ao evento original.
- Ao reabrir uma conversa, os prints voltam pelo histórico persistido de eventos.
- O card de tela no frontend funciona como galeria: mostra o print atual, contador, botões de voltar/avançar e modal ampliado ao clicar na imagem.
- A exclusão de chat remove os prints em cascata junto com os eventos da conversa.

### Fontes e Qualidade de Pesquisa

Implementado:

- Tabela `sources` no SQLite ligada ao `task_id`, com `url`, `title`, `snippet`, `extracted_text`, `source_type`, `quality_score`, `used` e `created_at`.
- `browser_extract_article` extrai conteudo principal limpo da pagina, removendo menus, rodapes, scripts, iframes, formularios e blocos laterais.
- `tool_executor` registra automaticamente uma fonte quando `browser_extract_article` ou `browser_extract_text` retorna uma URL real.
- `services/source_quality.py` classifica fontes como `official`, `news`, `video`, `forum`, `marketplace` ou `web`, e gera score de 0 a 100.
- O planner foi orientado a preferir `browser_extract_article`, citar URLs visitadas e diferenciar conteudo confirmado em fonte aberta de sugestoes vindas apenas dos resultados de busca.
- O frontend mostra painel `Fontes` com titulo, tipo, score e link externo.
- A exclusao de chat apaga as fontes em cascata junto com eventos e screenshots.

### Reaproveitamento dos Projetos Vertex

Análise feita em:

- `/media/server/HD Backup/Servidores_NAO_MEXA/vertex-cli`
- `/media/server/HD Backup/Servidores_NAO_MEXA/vertex-server`

Reaproveitado no Vortax:

- **Contratos de stream:** inspirado nos testes de contrato/SSE do Vertex Server. O Vortax agora centraliza tipos válidos de evento em `backend/services/stream_contract.py` e normaliza eventos desconhecidos para evitar quebrar o frontend.
- **Diagnóstico seguro:** inspirado em `messaging/safe_diagnostics.py`. O Vortax agora tem `backend/services/safe_diagnostics.py` para redigir chaves, tokens e Authorization em eventos/erros antes de enviar ao WebSocket.
- **Mapeamento de erros de provider:** inspirado em `providers/error_mapping.py`. O Vortax agora mapeia 401/403, 429, 5xx e timeout do DeepSeek para mensagens de usuário mais claras em `backend/services/provider_errors.py`.
- **Registry de processos:** inspirado em `cli/process_registry.py`. O Vortax agora tem `backend/services/process_registry.py` e cleanup no lifespan do FastAPI, preparando o terreno para Chrome CDP/shell sem deixar subprocessos órfãos.
- **Status de providers:** inspirado no endpoint de modelos/health do Vertex Server. O Vortax agora expõe `/api/providers/` e mostra DeepSeek e Groq/Llama 4 Scout na sidebar do frontend; o próximo ajuste é criar `backend/tools/vision.py`.

Não reaproveitado agora:

- Autenticação, billing, Firebase/Supabase, Telegram/Discord e painel administrativo do Vertex Server ficam fora do MVP porque o Vortax atual roda sem autenticação e apenas na LAN.
- Camada Anthropic/SSE completa do Vertex não foi copiada porque o Vortax usa um contrato WebSocket mais simples para chat e ferramentas locais.

### Log de Andamento

| Data | Etapa | Arquivos | Verificação |
|------|-------|----------|-------------|
| 06/05/2026 | Início do desenvolvimento do MVP local com documentação no próprio plano | `PLANO_VORTAX.md` | Checklist criado |
| 06/05/2026 | Scaffold inicial do projeto local | `.env.example`, `.gitignore`, `backend/`, `frontend/`, `scripts/`, `workspace/` | Estrutura criada no diretório do Vortax |
| 06/05/2026 | Backend FastAPI MVP com task mockada e stream WebSocket | `backend/main.py`, `backend/api/*`, `backend/services/*`, `backend/config.py`, `backend/access.py` | `GET /health`, `POST /api/tasks/` e `WS /ws/{task_id}` validados |
| 06/05/2026 | Frontend React/Vite chat-first com painel de stream | `frontend/src/App.jsx`, `frontend/src/components/*`, `frontend/src/hooks/useWebSocket.js`, `frontend/src/index.css` | `npm run build` passou e Chrome headless renderizou chat/stream |
| 06/05/2026 | Servidores dev iniciados para teste local | `scripts/start-dev.sh`, unidades `vortax-backend-dev.service` e `vortax-frontend-dev.service` | Backend `8010` e frontend `5173` ativos localmente |
| 06/05/2026 | Integração inicial DeepSeek V4 Flash | `backend/services/deepseek_client.py`, `backend/services/agent_runner.py`, `backend/api/tasks.py`, `backend/requirements.txt` | Cliente DeepSeek adicionado com fallback mockado quando `.env` não tiver chave |
| 06/05/2026 | `.env` local configurado com chave DeepSeek | `.env` | Chave detectada sem imprimir o valor; aviso: volume montado não respeitou `chmod 600` |
| 06/05/2026 | Validação real DeepSeek V4 Flash | `backend/services/deepseek_client.py` | Task via API/WebSocket retornou resposta real do modelo `deepseek-v4-flash` com uso de tokens |
| 06/05/2026 | Análise e reaproveitamento dos projetos Vertex | `backend/services/safe_diagnostics.py`, `backend/services/provider_errors.py`, `backend/services/stream_contract.py`, `backend/services/process_registry.py`, `backend/api/providers.py` | Padrões úteis incorporados sem trazer auth/billing/admin |
| 06/05/2026 | Ajuste do stream/tools para rolagem limitada | `frontend/src/index.css`, `frontend/src/components/ActionTimeline.jsx`, `frontend/src/App.jsx` | Painel de stream virou card com altura limitada e rolagem interna |
| 06/05/2026 | Verificação de acesso por outro PC da LAN | frontend/backend ativos | Backend recebeu `POST /api/tasks/` e `WS /ws/{task_id}` de `192.168.0.101` |
| 06/05/2026 | BrowserTool CDP + Tool Executor + planner JSON | `backend/tools/browser.py`, `backend/tools/tool_executor.py`, `backend/services/deepseek_client.py`, `backend/services/agent_runner.py`, `backend/requirements.txt` | Implementado loop ReAct simples com ferramentas de navegador |
| 06/05/2026 | Validação BrowserTool direta | `backend/tools/browser.py` | Navegou em `data:text/html`, extraiu título/texto e gerou screenshot base64 via CDP |
| 06/05/2026 | Validação ReAct navegador | backend ativo | Task via API/WebSocket abriu `data:text/html` e `https://example.com`, publicou `tool_call`, `tool_result`, `screen_frame` e finalizou com o título |
| 06/05/2026 | Visão Groq/Llama 4 Scout funcional | `backend/tools/vision.py`, `backend/api/tasks.py`, `frontend/src/components/Composer.jsx`, `frontend/src/components/MessageList.jsx` | Smoke test real com `meta-llama/llama-4-scout-17b-16e-instruct`; rota `POST /api/tasks/images` salvou imagem em `chat_images` e retornou análise |
