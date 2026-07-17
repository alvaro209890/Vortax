# 05 — Contexto e Memória

> **Prioridade:** P1
> **Inspiração:** compactação do Claude Code; padrão "usar arquivos como memória de trabalho" e `todo.md` do Manus
> **Arquivos:** `backend/services/context_manager.py`, `backend/services/user_memory.py`, `backend/config.py`

---

## 1. Janela de contexto realista

### Estado atual
- `CONTEXT_TOKEN_LIMIT=24000` (`config.py:46`) — muito abaixo da janela dos modelos V4; força compactação prematura e perda de contexto de projeto.
- Estimativa de tokens por contagem de caracteres (`context_manager.py`), ignorando o `usage` real da API.
- Compaction em 88%, warning em 70%, últimos 8 turnos preservados.

### Mudanças
1. **Descobrir a janela real do V4 Pro** (passo 0 do roadmap) e definir `CONTEXT_TOKEN_LIMIT` como ~60% dela (margem para system prompt modular + schemas de tools + resultado de tools), esperado ≥ 96k.
2. **Calibrar a estimativa com o usage real:** a cada resposta da API, comparar `prompt_tokens` reais com a estimativa e ajustar um fator de correção por task (`chars_per_token` móvel). Elimina o erro sistemático de estimar PT-BR com heurística de EN.
3. **Compactação em duas camadas** (padrão Claude Code):
   - resultados de tools antigos são os primeiros a colapsar (viram 1 linha: "`web_search 'x'` → 8 resultados; fonte salva #12"), pois já estão persistidos em `sources`/`generated_files`;
   - só depois compactar turnos de conversa em resumo (fluxo atual com checkpoint — manter, está bom).
4. **O que nunca compactar:** o pedido original da task, a lista todo atual, o último resultado de validação com bugs abertos, e o mapa de arquivos do workspace (ver §2).

## 2. Contexto de projeto (novo — crítico para código)

Hoje o modelo não sabe o que existe no workspace a menos que um `file_summary` apareça num resultado de shell. Adicionar ao prompt de cada iteração em task com arquivos (bloco compacto, pós-core para não quebrar cache):

```
[WORKSPACE]
projetos/<task_id>/ — 14 arquivos, projeto: site-estatico
index.html (4.2KB, editado há 2 min) | style.css (8.1KB) | script.js (2.0KB) | ...
Validação: web_validation=failed (2 bugs abertos)
```

Gerado de `generated_files` + status de validação — dados que já existem no SQLite. Máx ~30 linhas; árvore resumida como o `file_summary` atual.

## 3. Memória de trabalho em arquivos (padrão Manus)

O Manus escreve `todo.md`, `notes.md` e rascunhos no workspace e os relê para não depender só da janela. Com as tools de arquivo (doc 03 §1) isso passa a ser possível e deve ser incentivado no prompt (`coding.md`/`research.md`):

- pesquisas longas: acumular achados em `notas_pesquisa.md` por rodada, e gerar o relatório final a partir do arquivo (não da janela);
- tasks longas de código: `DECISOES.md` com decisões técnicas tomadas — sobrevive à compactação e a mensagens futuras na mesma conversa.

Sem código novo além das file tools; é padrão de prompt + o fato de `WORKSPACE_PATH/<task_id>/` já ser persistente por conversa.

## 4. Memória entre conversas (evoluir `user_memory`)

### Estado atual
`user_memories` (chave:valor por user_id), comando `/remember`, auto-captura por regex ("eu prefiro", "eu gosto de"...), injeção total no system prompt.

### Mudanças
1. **Estrutura tipada** (inspirado no memory do Claude Code): `type: preference | fact | project | feedback`, com `description` curta. Migração: memórias atuais viram `preference`.
2. **Auto-captura pelo modelo, não por regex:** ao final de tasks bem-sucedidas, uma chamada Flash pergunta "há algo duradouro a lembrar?" com critérios rígidos (não salvar dados da tarefa, só do usuário/projeto); apresentar ao usuário no painel (já existe UI de gerenciamento).
3. **Injeção seletiva:** em vez de todas as memórias sempre, injetar as N mais relevantes ao pedido (match simples por embedding não é necessário; começar com escore lexical + tipo — `preference` sempre, `project` só se relacionado).
4. **Perfil consolidado:** mesclar com `_build_user_profile_block` (`agent_runner.py:1740-1765`) que hoje é um segundo mecanismo paralelo de perfil — unificar num bloco só.

## 5. Cache e reuso entre tasks

- Manter `ephemeral_cache` (pesquisa cross-task) e o cache de fontes por conversa — funcionam.
- Novo: cache de **resumo de fontes** — quando uma fonte de 10k chars for usada em nova task, reusar o resumo Flash já feito em vez de re-resumir.
- Registrar hit/miss no `llm_usage` para medir economia.

## 6. Critérios de aceite

- [ ] `CONTEXT_TOKEN_LIMIT` ≥ 4x o atual, com estimativa calibrada pelo usage real (< 15% de erro médio).
- [ ] Task de código com 20+ iterações mantém o pedido original e a validação pendente intactos após compactação.
- [ ] Bloco `[WORKSPACE]` presente em tasks com arquivos; modelo referencia arquivos existentes sem chamar `glob` primeiro em ~80% dos casos.
- [ ] Deep research grava e reusa `notas_pesquisa.md` no workspace.
- [ ] Memórias tipadas com injeção seletiva; painel do usuário continua funcionando.
