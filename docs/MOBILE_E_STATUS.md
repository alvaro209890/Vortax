# Vortax — Mobile + status do que foi feito e o que falta

**Data:** 2026-07-18  
**Versão app (frontend/backend):** ciclo 0.2.x (main)  
**Repo:** `github.com/alvaro209890/Vortax` · branch **main**

---

## 1. Melhoria mobile (esta entrega)

### Objetivo
Chat utilizável em telefone (iOS/Android): drawer de conversas, header compacto, composer estável, safe-area (notch/home), alvos de toque ≥ 44px, sem zoom indesejado no iOS.

### Arquivos
| Arquivo | Mudança |
|---------|---------|
| `frontend/index.html` | `viewport-fit=cover`, theme-color, apple-mobile-web-app meta |
| `frontend/src/components/ChatShell.jsx` | Sidebar aberta no desktop / fechada no mobile; Esc fecha drawer; trava scroll do body; fecha ao escolher conversa/tab |
| `frontend/src/App.jsx` | `aria-label` nos botões do header; classe `user-menu-label` para esconder texto no mobile |
| `frontend/src/index.css` | Safe-area no body; font-size 16px inputs no mobile; bloco **Mobile polish 2026-07-18** (drawer, header, composer sticky, dock, detail full-screen, onboarding 1 col, landscape) |

### Comportamento
- **≤768px:** menu de conversas = drawer overlay (não grid de 2 colunas).
- Botão ☰ fixo com safe-area; backdrop fecha o menu.
- Header com padding à esquerda para o ☰; botões “Detalhes”/usuário viram só ícone.
- Composer sticky no fundo + `env(safe-area-inset-bottom)`.
- Drawer de detalhes em tela cheia no mobile.
- Landscape baixo: esconde computer dock para ganhar altura.

### Como validar
```bash
cd frontend && npm run build
# Dev: npm run dev → Chrome DevTools device toolbar (iPhone 13 / Pixel 7)
# Ou abrir https://notazap-2520f.web.app no celular após deploy hosting
```

Checklist visual:
- [ ] Abrir/fechar conversas com o dedo
- [ ] Digitar sem zoom no iOS
- [ ] Enviar mensagem com teclado virtual aberto
- [ ] Detalhes (fontes/arquivos) full-screen e fechar
- [ ] Notch / home bar não cobrem o composer

---

## 2. O que já fizemos no projeto (histórico recente no main)

### Plano técnico produto (`PLANO_VORTAX.md`)
| Versão | Entrega |
|--------|---------|
| **3.5–3.6** | Identidade Computador do Vortax; backlog §12 (auth Firebase, replan mid-run, export auditável, artefatos hash/step, permissões, métricas, subtasks paralelas deep research) |
| **3.7** | Loop nativo DeepSeek V4 Pro + function calling + streaming + usage na API |

### Plano melhoria IA (`plano-melhoria-ia/`)
| Fase | Status |
|------|--------|
| **0** | Feita: bugs P0 (confirm pause, fontes, vertex dinâmico, quality score, `code_agent`, shell import, …), V4 Pro brain, file tools, `llm_usage` |
| **1** | **Núcleo feito:** `backend/agent/{loop,gates,state,tools/registry}.py`, `USE_NATIVE_TOOLS` + fallback legado, `message_*` / `todo_write`, tokens/custo em GET task |
| **2** | Parcial: file tools adiantadas; falta shell sessions, coding prompt, validate_project tool |
| **3** | Pendente: prompts modulares, classificador Flash, injection defense |
| **4** | Pendente: subagentes researcher/reviewer, web_fetch, custo no frontend |

### Outros
- Memória entre conversas, pesquisa profunda, checkpoint de contexto  
- Onboarding, settings, AlertDialog, busca na sidebar  
- Otimizações performance (memo, WS resiliente, batch events, retry API)

Commits de referência (main):
- `f3304cc` memória / deep research / checkpoint  
- `b0a5459` backlog §12  
- `2f33d96` fase 0 IA  
- `6052e0a` fase 1 loop nativo  
- *(este)* mobile polish + documentação de status  

---

## 3. O que falta

### Frontend / mobile
- [ ] Deploy Firebase Hosting da build mobile (se ainda não rodado no ambiente de produção)
- [ ] QA real em iPhone + Android (Safari/Chrome)
- [ ] PWA opcional (manifest + service worker) se quiser “instalar app”
- [ ] Esconder/melhorar computer dock em portrait muito estreito (já compacto; landscape esconde)
- [ ] A11y: foco preso no drawer aberto (focus trap)

### Backend / agente (plano IA)
- [ ] Pré-pesquisas automáticas no **path nativo** (hoje mais completas no legado)
- [ ] Gates `project_validation` / `web_validation` no loop nativo
- [ ] Encolher `agent_runner.py` para casca fina
- [ ] Fase 2: `shell_exec/view/write/kill`, matriz coding × vertex
- [ ] Fase 3: `agent/prompts/` modular + classificador de intenção
- [ ] Fase 4: subagentes, `web_fetch`, custo no UI

### Ops
- [ ] Reiniciar `vortax-backend` em produção com flags `USE_NATIVE_TOOLS` / `DEEPSEEK_*` se `.env` antigo
- [ ] Baseline de custo em ~10 tasks reais (`llm_usage`)

### Rollback rápido
```env
USE_NATIVE_TOOLS=false
DEEPSEEK_STREAMING=false
```

---

## 4. Comandos úteis

```bash
cd ~/Documentos/Vortax

# Frontend
cd frontend && npm run build
# Deploy (quando autorizado):
# firebase deploy --project notazap-2520f --only hosting

# Backend tests (novos)
cd ../backend
PYTHONPATH=. ./venv/bin/python -m unittest \
  tests.test_agent_registry_and_gates \
  tests.test_native_agent_turn \
  tests.test_file_tools -v
```

---

## 5. Links

- Front produção: `https://notazap-2520f.web.app`  
- API: `https://vortax-api.cursar.space`  
- Plano vivo: `PLANO_VORTAX.md`  
- Execução IA: `plano-melhoria-ia/CHANGELOG.md` · `08-roadmap.md`  
