# Documentacao de Upload, Edicao de Arquivos e Incidente DOCX

Atualizado em 2026-05-10.

## O que foi implementado

- Upload de documentos no chat para `.xlsx`, `.csv`, `.docx`, `.pdf`, `.txt`, `.md`, `.json` e `.zip`.
- Upload de imagens continua separado quando o envio tem apenas imagens, usando o fluxo de visao.
- Envio misto de documentos e imagens agora preserva todos os anexos no mesmo pedido.
- Drag-and-drop global no frontend: arrastar arquivos para a tela anexa ao Composer.
- Preview de anexos no Composer com icones para imagem, ZIP, planilha e documento.
- Eventos de stream para arquivos enviados e analisados:
  - `files_uploaded`
  - `file_analysis_done`
- Ingestao segura de ZIPs com extracao em `uploads/archives/<nome-do-zip>/`.
- Analise de shapefiles completos dentro de ZIPs, agrupando `.shp`, `.shx`, `.dbf`, `.prj` e `.cpg`.
- Regras para edicao geoespacial:
  - nunca alterar uploads originais;
  - gerar saidas em `outputs/` ou na raiz da task;
  - shapefile editado deve ser entregue como `.zip` com componentes obrigatorios.
- Entregas Office:
  - DOCX via `python-docx`;
  - XLSX via `openpyxl`;
  - CSV em UTF-8;
  - PDF via extracao com `pypdf`.
- Cards de download no chat para arquivos gerados.
- Cache do Firebase Hosting ajustado:
  - `/` e `/index.html` com `no-cache`;
  - assets versionados `.js` e `.css` com `immutable`.

## Correcoes de frontend

- O Composer aceita documentos, ZIPs e imagens pelo botao de anexo e por drag-and-drop.
- Arquivos rejeitados por extensao, duplicados ou acima do limite visual sao indicados sem quebrar o envio.
- Mensagens otimistas de upload agora usam `client_message_id` tambem em multipart.
- Isso evita duplicacao automatica quando o backend devolve o evento real do upload.

## Correcoes de backend

- Endpoints adicionados:
  - `POST /api/tasks/files`
  - `POST /api/tasks/{task_id}/files`
- Multipart aceita `question`, `client_message_id` e `files`.
- Uploads sao salvos em `WORKSPACE_PATH/<task_id>/uploads/`.
- ZIPs sao extraidos com bloqueio de path traversal, caminhos absolutos, arquivos vazios e excesso de tamanho/quantidade.
- O prompt do agente lista:
  - caminhos dos arquivos enviados;
  - conteudo extraido;
  - conteudo do ZIP;
  - camadas geoespaciais detectadas;
  - instrucoes para preservar uploads originais e criar novas versoes.

## Incidente Especies.docx

### Sintoma

O usuario enviou `Especies.docx` e pediu:

> analise esse worl, corrija erros de portugues, concordancia, frmatação e me envie ele denovo

O sistema criou `Especies_Corrigido.docx` e `RELATORIO_TECNICO.md`, mas a resposta final nao apareceu no chat.

### Causa raiz

Durante a finalizacao, o runner montava historico percorrendo qualquer payload com `files`.
Um evento interno `vertex_progress` usava:

```json
{"files": ["Especies_Corrigido.docx"]}
```

Esse formato e valido para progresso interno, mas o historico final assumia que todo item em `files` era um objeto com `.get("path")`.
Isso gerou:

```text
'str' object has no attribute 'get'
```

Como a falha ocorreu antes de `assistant_message_done`, o chat ficou com status de trabalho em andamento/erro, mesmo com o DOCX ja criado.

### Correcoes aplicadas

- `agent_runner._message_history_from_events` agora considera `files` apenas em eventos de chat:
  - `user_message`
  - `assistant_message_done`
- Itens de `files` que nao sejam objetos sao ignorados com seguranca.
- A deteccao de extensoes foi ajustada:
  - `worl` e `world` passam a ser tratados como Word/DOCX;
  - a palavra `texto` so gera `.txt` quando o usuario pede explicitamente arquivo de texto;
  - conteudo embutido depois de marcadores como `O texto corrigido e:` nao cria pedidos falsos de `.txt` ou `.xlsx`.
- A conversa travada `c66ac2f8-3e1e-4c4c-9bf7-a1b1300c9a3a` foi recuperada no banco com resposta final e anexos.

## Validacoes executadas

- `python -m py_compile` nos arquivos alterados do backend.
- Testes focados de documentos, ingestao, artefatos e API de arquivos.
- Build do frontend com `npm run build`.
- Validacao dos headers publicados no Firebase Hosting.
- Healthcheck local e publico do backend:
  - `http://127.0.0.1:8010/health`
  - `https://vortax-api.cursar.space/health`

## URLs de producao

- Frontend: `https://notazap-2520f.web.app`
- Backend publico: `https://vortax-api.cursar.space`
