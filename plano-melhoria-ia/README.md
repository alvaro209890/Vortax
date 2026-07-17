# Plano de Melhoria da IA do Vortax

> **Data:** 17/07/2026
> **Objetivo:** transformar o agente do Vortax em um sistema de IA de nível Manus/Claude Code, com o **DeepSeek V4 Pro como cérebro padrão**, novas ferramentas, trabalho de código muito melhor e correção dos bugs encontrados na análise.
> **Escopo:** este plano é somente planejamento — nenhuma alteração de código foi feita. Ele foi escrito para ser executado por outro agente de desenvolvimento, arquivo por arquivo.

---

## Como usar este plano

Cada arquivo é autocontido: tem contexto, estado atual (com caminhos `arquivo:linha` reais do repositório), mudanças propostas, arquivos afetados e critérios de aceite. A ordem recomendada de execução está em [08-roadmap.md](08-roadmap.md).

| Arquivo | Conteúdo | Prioridade |
|---------|----------|-----------|
| [00-diagnostico-atual.md](00-diagnostico-atual.md) | Arquitetura atual, pontos fortes e fracos | Leitura obrigatória |
| [01-migracao-deepseek-v4-pro.md](01-migracao-deepseek-v4-pro.md) | DeepSeek V4 Pro como cérebro + function calling nativo + streaming | P0 |
| [02-arquitetura-agente.md](02-arquitetura-agente.md) | Novo agent loop inspirado em Manus e Claude Code | P0 |
| [03-novas-tools.md](03-novas-tools.md) | Catálogo completo das novas ferramentas | P1 |
| [04-engenharia-de-prompts.md](04-engenharia-de-prompts.md) | Reescrita modular do system prompt | P1 |
| [05-contexto-e-memoria.md](05-contexto-e-memoria.md) | Janela de contexto, compactação e memória persistente | P1 |
| [06-codigo-e-validacao.md](06-codigo-e-validacao.md) | Trabalho com código: edição direta, verificação, correção | P0 |
| [07-correcao-de-bugs.md](07-correcao-de-bugs.md) | Bugs concretos encontrados, com arquivo e linha | P0 |
| [08-roadmap.md](08-roadmap.md) | Fases, dependências, critérios de aceite e métricas | Leitura obrigatória |

## Referências usadas

- **Tools do Manus (leak):** https://gist.github.com/jlia0/db0a9695b3ca7609c9b1a08dcbf872c9 — agent loop, módulos (Planner/Knowledge/Datasource), suíte de tools `file_*`, `shell_*`, `browser_*`, `message_notify_user`/`message_ask_user`, padrão `todo.md`, `deploy_expose_port`.
- **System prompts de ferramentas de IA:** https://github.com/x1xhlol/system-prompts-and-models-of-ai-tools — padrões de prompt de Cursor, Devin, Windsurf, v0, Manus etc.
- **Claude Code:** https://github.com/anthropics/claude-code — tools `Read`/`Write`/`Edit`/`Glob`/`Grep`/`Bash`, TodoWrite, subagentes (Task), plan mode, compactação de contexto, memória em arquivos (`CLAUDE.md`), loop editar → rodar → testar.

## Princípios do plano

1. **DeepSeek V4 Pro é o cérebro padrão** de planejamento, decisão de ações e resposta final. Modelos menores (V4 Flash, Groq) só para tarefas auxiliares baratas (título, sumarização, visão).
2. **Function calling nativo em vez de JSON-no-texto.** O formato atual (JSON dentro de `content`) é frágil e caro; a API do DeepSeek suporta `tools`/`tool_calls` no padrão OpenAI.
3. **O agente ganha mãos próprias para código.** Hoje ele delega 100% ao CLI `vertex`; passará a ler, editar e verificar arquivos diretamente para correções e ajustes, reservando o `vertex` para scaffolding de projetos grandes.
4. **Menos heurística regex, mais decisão do modelo.** Grande parte dos módulos `*_intent`, `*_policy` e dos "gates" por prefixo de string será substituída por tools explícitas e decisões do próprio modelo.
5. **Compatibilidade incremental.** O contrato de eventos WebSocket (`vertex_progress`, `task_step_*` etc.) é preservado; cada fase entrega valor sozinha e mantém os testes verdes.
