# Entrega de software no chat — 09/10/2026

Autor: Codex. Continuação de `4e81d39`, preservando a base de Claude `365a26f` e as correções de navegador/pesquisa.

## Diagnóstico e escopo

A inspeção direta e somente leitura do SQLite identificou a conversa FastAPI `2e94cba7-0568-4575-baba-e3d1ec291f29`. Sua primeira resposta final tinha **17.002 caracteres e 15 blocos de código**. Os arquivos já estavam gravados: **19 arquivos úteis**, mais cinco registros de cache. A última validação de software dessa entrega estava aprovada.

O loop nativo publicava o texto bruto do modelo e não usava o finalizador comum de arquivos/documentação. O prompt legado também mandava incluir código na resposta. Ambos foram corrigidos. O arquivo anexado de melhoria de frontend foi usado como referência de preservação e compatibilidade; esta entrega não representa a execução integral de suas fases de modernização.

## Comportamento

- Criação/alteração de software: código nos arquivos; resposta curta com objetivo, arquivos existentes, documentação, validação registrada e pendências. Não há ZIP automático no chat.
- O conteúdo bruto do modelo não é transmitido como deltas nesses pedidos. O finalizador entrega a descrição baseada no manifesto real do workspace.
- Solicitar ZIP de um projeto existente gera o cartão de download, sem recriar os arquivos, chamar o planejador, o modelo ou compactar contexto com IA. A resposta funciona mesmo sem provedor configurado.
- A validação de uma nova criação/alteração é limitada aos eventos desse turno. Um sucesso antigo não prova uma alteração nova. Ao pedir apenas o ZIP, a resposta informa a última verificação registrada dos arquivos existentes.
- Trechos explicitamente pedidos para explicação/cópia continuam permitidos. Perguntas conceituais sobre ZIP e pedidos sem ZIP não acionam a entrega de arquivo.
- Entregas antigas com código extenso recebem apresentação compacta quando há arquivos e eventos de criação comprovados antes da resposta. A conversa e seus eventos originais permanecem preservados; uma pesquisa posterior no mesmo chat mantém sua própria apresentação.

O formato `assistant_message_done` ganhou os campos opcionais `delivery` e `archive`. A API e WebSocket existentes continuam compatíveis. O link do cartão usa a mesma autenticação por token dos demais downloads, com atualização do token ao montar o cartão.

## Arquivo ZIP

`GET /api/tasks/{task_id}/download` mantém verificação de dono/capacidade e nome `vortax-{id-curto}.zip`. A compactação roda fora do loop assíncrono. Inclui fontes, testes, documentação e configuração de dependências; exclui Git, node_modules, ambientes virtuais, caches, bytecode, `.env` real e links simbólicos. Modelos `.env.example/.sample/.template` e diretórios legítimos de aplicação são preservados. Sem arquivos, retorna 404.

## Validação

- Backend: **231 testes OK**, cinco testes externos opcionais pulados (`VORTAX_LIVE=0`); banco isolado. Cobertura inclui fonte bruta sem streaming, ZIP sem provedor/planejador, validação por turno, integridade/exclusões do ZIP e preservação de explicações.
- Frontend: **sete testes OK** e build de produção. O aviso preexistente de bundle acima de 500 kB continua; não foi ocultado.
- Provedor real, ambiente isolado: tarefa `6e07dea7-cc87-4b4d-9852-41212b2b6611`, conversor Python com três arquivos, testes e `validate_project` aprovado; **68,22 s**, estado `done`, **zero deltas** de resposta bruta e resumo sem blocos de código.
- Cópia isolada da FastAPI `c1d5a57f-9e0a-43a3-ad5a-f4ad67c89a50`: UI mostrou resumo de 19 arquivos. Pedido de ZIP completou em aproximadamente **0,12 s**, sem ferramentas, com plano local e cartão. Tempos são amostras, não SLA.
- Download HTTP: status 200, ZIP lido e íntegro (`testzip()` sem erros), 19 arquivos incluindo README e sem caches. Clique no cartão também atingiu a rota com 200. O navegador interno não retornou evento/caminho de download; o salvamento pelo gerenciador de downloads não foi comprovado por esse teste.

## Operação e retorno

Publicar em `main`, compilar front com `VITE_API_BASE_URL= npm run build` e reiniciar as units de backend/front somente sem tarefas em execução. Não versionar os envs/backups locais. Produção continua privada em LAN/Tailscale (`:5173`), proxy para backend `:8010`; dados da conversa original preservados. Para retornar ao comportamento anterior, usar `4e81d39` em checkout separado, rebuild e troca de release; as mensagens originais continuam no banco.
