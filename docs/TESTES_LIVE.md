# Testes live Vortax (DeepSeek)

**Data:** 2026-07-18  
**Importante:** a chave **nunca** vai para o git. Use a do Hermes neste PC ou `DEEPSEEK_API_KEY` no ambiente.

## Como rodar

```bash
cd backend

# Opção A — chave já no ambiente (Hermes carrega ~/.hermes/.env)
set -a; source ~/.hermes/.env; set +a
export VORTAX_LIVE=1

# Opção B — só DEEPSEEK_API_KEY exportada
export DEEPSEEK_API_KEY=sk-...   # NÃO commitar

PYTHONPATH=. ./venv/bin/python -m unittest \
  tests.test_deepseek_live \
  tests.test_web_fetch_live \
  tests.test_shell_sessions_live \
  tests.test_native_loop_integration \
  tests.test_manus_claude_tools \
  -v
```

Sem chave: os testes live fazem **skip** automático (`live_helpers.live_enabled()`).

Desligar live mesmo com chave:
```bash
export VORTAX_LIVE=0
```

## Arquivos

| Arquivo | Papel |
|---------|--------|
| `tests/live_helpers.py` | Resolve chave (env → `~/.hermes/.env` → `Vortax/.env`) sem logar valor |
| `tests/test_deepseek_live.py` | Flash completion, Pro function calling, título, pick_model |
| `tests/test_web_fetch_live.py` | HTTP real + SSRF block |
| `tests/test_shell_sessions_live.py` | shell_exec background/oneshot real |
| `tests/test_native_loop_integration.py` | loop mock + schema de 39 tools aceito pela API |

## Resultado 2026-07-18 (este PC)

```
Ran 17 tests in ~12s — OK
```

Inclui chamadas reais a `api.deepseek.com` com a chave do Hermes (não registrada no repo).

## Bugs encontrados e corrigidos

1. **`generate_task_title` content vazio**  
   Causa: `max_tokens=24` insuficiente com reasoning do flash/pro → content `""`.  
   Fix: `max_tokens=128` (+ retry 256) e fallback `_fallback_title(description)`.

2. **`request_agent_turn` / Pro sem folga de tokens**  
   Causa: reasoning consome `max_tokens`; finish `length` com content vazio.  
   Fix: mínimo 2048 no brain pro; `reasoning_effort` high/low; retry 2× tokens se `finish_reason=length` sem tools.

3. **FDs abertos em `shell_kill`**  
   Fix: fechar stdin/stdout/stderr no kill da sessão.

## Segurança

- `.env` / `~/.hermes/.env` **gitignored**
- Testes e docs **não** embutem `sk-...`
- CI sem chave: suite unit continua; live skips
