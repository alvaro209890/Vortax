# 06 — Trabalho com Código: edição direta, verificação e correção

> **Prioridade:** P0 — é o pedido central: "melhore muito como a IA trabalha principalmente em código"
> **Inspiração:** loop read → edit → run → test do Claude Code; verificação orientada a evidência
> **Depende de:** tools de arquivo (doc 03 §1), function calling (doc 01), prompt modular `coding.md` (doc 04)

---

## 1. Problema central

Hoje o cérebro (DeepSeek) **nunca vê nem toca código**. Todo o trabalho passa pelo CLI `vertex` via `shell_run`, com estas consequências:

- **Correção de bug é caríssima e cega:** a validação encontra "referência local ausente em `index.html`", e a única saída é reinvocar o `vertex` (até `MAX_CODE_AGENT_CALLS=3`) com o texto do bug — o modelo não pode abrir o arquivo e trocar uma linha.
- **Heurística no lugar de raciocínio:** `tool_executor.py` tem ~550 linhas (`_augment_code_agent_command_for_quality`, `_augment_code_agent_command_for_local_site`, `_office_artifact_instructions`...) só para injetar instruções no comando do vertex por regex de intenção.
- **Sem leitura de projeto:** análises tipo "explique esse repo" também viram prompt gigante ao vertex, sem o cérebro poder navegar os arquivos.
- **Validação boa, reparo fraco:** o gate de `finish` funciona, mas o ciclo de reparo tem uma ferramenta só (chamar o vertex de novo inteiro).

## 2. Novo modelo em dois níveis

```
┌────────────────────────────────────────────────────────┐
│ DeepSeek V4 Pro (cérebro)                              │
│  • decide a estratégia                                 │
│  • lê, busca e edita arquivos DIRETAMENTE              │
│  • roda build/teste via shell e interpreta o erro      │
│  • delega ao vertex apenas scaffolding grande          │
└──────────────┬─────────────────────────────────────────┘
               │ delega quando: projeto novo multiarquivo,
               │ refatoração larga, stack desconhecida
┌──────────────▼─────────────────────────────────────────┐
│ Vertex CLI (motor de scaffolding)                      │
│  • cria projetos completos do zero                     │
│  • recebe ExecutionPackage estruturado (já existe)     │
└────────────────────────────────────────────────────────┘
```

Regra de decisão (vai no `coding.md`, doc 04):

| Situação | Ferramenta |
|---|---|
| Criar projeto novo (site, API, app multiarquivo) | `vertex` (com contexto de pesquisa, como hoje) |
| Corrigir bug apontado pela validação | `file_read` + `file_edit` + revalidar |
| Ajuste pequeno pedido pelo usuário ("muda a cor", "troca o texto", "adiciona um campo") | `file_edit` direto |
| Arquivo único (script, config, doc curto) | `file_write` direto — sem vertex |
| Refatoração ampla / feature grande em projeto existente | `vertex` com contexto do workspace |
| Explicar/analisar código existente | `glob` + `grep` + `file_read` (sem vertex) |

Efeito esperado: a maioria das rodadas de correção deixa de gastar uma chamada do vertex e passa a ser 2-4 tool calls baratas do próprio cérebro, com diff mínimo em vez de regeneração.

## 3. Loop de verificação (padrão Claude Code: nunca entregar sem evidência)

Formalizar em `coding.md` + gates:

1. **Toda mudança de código termina com verificação executada** — `py_compile`/`pytest` para Python, `node --check`/build/test para JS, preview+screenshot para web (a infra de `project_validation`/`web_validation` já existe; ela passa a ser *chamável* pelo modelo como tool `validate_project`, além de automática pós-vertex).
2. **Erro de execução vira leitura dirigida:** ao receber stderr/traceback, o fluxo prescrito é: extrair arquivo:linha do erro → `file_read` do trecho → `file_edit` → rodar de novo. Adicionar parser leve de tracebacks (Python/Node) que anexa ao resultado do shell os caminhos+linhas detectados, prontos para o modelo.
3. **Proibido "deve funcionar":** o gate atual de finish já bloqueia; adicionar ao prompt a regra explícita de reportar o que foi executado e o resultado observado.
4. **Diagnóstico antes de ação destrutiva:** nunca regenerar projeto inteiro por causa de um erro pontual (isso hoje acontece — o vertex recria tudo).

## 4. Contexto de código para o cérebro e para o vertex

- Bloco `[WORKSPACE]` em toda iteração (doc 05 §2).
- **`enrich_code_agent_command` (execution_package.py) continua**, mas simplificado: com o cérebro podendo ler arquivos, o pacote passa a incluir *trechos reais* dos arquivos-alvo (assinaturas, estrutura) em vez de só instruções genéricas.
- **Snippets (`code_snippet_library.py`): manter** e alimentar também o caminho de edição direta (buscar snippet antes de `file_write` de arquivo novo).
- Análise de GitHub: substituir "clone + prompt gigante ao vertex" por clone via shell + navegação com `glob`/`grep`/`file_read` pelo cérebro, gerando `RELATORIO_TECNICO.md` com `file_write`. O vertex sai desse fluxo (a instrução `ANALISE_GITHUB_READONLY_VORTAX` em `tool_executor.py:484-493` é aposentada).

## 5. Revisão de código pré-entrega (fase 2)

Subagente `code-reviewer` (doc 02 §4): após validação passar e antes da entrega de projetos não-triviais, roda revisão read-only (`file_read`/`grep`) procurando: bugs lógicos que a validação sintática não pega, `href`/handlers mortos, estados de erro não tratados, responsividade (via screenshot + visão). Resultado: lista de findings → cérebro decide corrigir (via `file_edit`) ou entregar com ressalvas. Orçamento: 1 rodada, sem loop infinito de perfeccionismo.

## 6. Desmontar as heurísticas do tool_executor

Com os níveis acima funcionando, remover gradualmente de `tool_executor.py`:

| Heurística atual | Substituído por |
|---|---|
| `_augment_code_agent_command_for_local_site` / `_for_quality` (instruções injetadas por regex) | Módulo `coding.md`/`web-design.md` no prompt do cérebro, que escreve o comando do vertex já completo |
| `_office_artifact_instructions` | Módulo `documents.md` + gates de artefato (mantidos em `gates.py`) |
| `_ensure_pdf_artifact_after_code_agent` (conversão automática escondida) | Tool explícita `document_render` (doc 03 §5) |
| `_code_agent_creation_intent` (regex de criação) | Classificador de intenção (doc 04 §5) |
| Detecção triplicada de comando do code agent | Helper único `code_agent.py` importado pelos 3 módulos (bug #6, doc 07) |

O que fica no executor: eventos, screenshot pós-ação, sync de arquivos, validação automática pós-vertex — orquestração, não heurística de prompt.

## 7. Qualidade das entregas web (reforço)

- Adicionar ao `web_validation` checagens hoje ausentes: console errors do Chrome (coletáveis via CDP), links internos quebrados entre páginas, imagens 404, viewport mobile (screenshot 375px + visão).
- `validate_project`: expor lint quando disponível (`ruff`/`eslint` se instalados no projeto) como warnings, não bloqueio.
- Diferencial a manter: o Vortax é dos poucos que *prova* a entrega com screenshot — preservar isso no card final (screenshot da entrega junto da resposta).

## 8. Critérios de aceite

- [ ] Bug de validação simples (ex.: asset ausente) corrigido por `file_edit` sem nenhuma chamada extra ao vertex.
- [ ] "Muda a cor do botão para azul" resolve em < 5 tool calls e < 30s, com validação revalidada.
- [ ] Análise de repositório GitHub gera relatório citando arquivos reais lidos pelo cérebro, sem invocar o vertex.
- [ ] Criação de site novo continua delegando ao vertex e mantém `vertex_progress`/`vertex_steps` no frontend.
- [ ] Traceback de Python/Node resulta em `file_read` do arquivo:linha correto na iteração seguinte (observável nos eventos).
- [ ] `tool_executor.py` < 400 linhas ao final da fase (hoje 976).
- [ ] Nenhuma regressão nos testes de validação (`test_project_validation.py`, `test_web_validation.py`).
