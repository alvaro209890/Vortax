# Navegador, animações e pesquisa — 09/10/2026

Autor: Codex. Base: `365a26f68a294a593de428cf8fcae7068d1b425e`, a versão mais recente de Claude em `main` no início desta correção. As melhorias anteriores de LAN, proxy, modelo rápido e saída do loop foram preservadas.

## Diagnóstico confirmado

- Buscas HTTP e resultados reutilizados da conversa não navegavam no Chrome. A interface só entendia screenshots, então mostrava uma captura de `about:blank` no lugar dos resultados recebidos.
- A captura posterior às ferramentas incluía `shell_run` e podia abrir o Chrome sem necessidade. O timeout de screenshot anterior era de dez minutos.
- O Chrome do server respondia no CDP, mas `Page.goto` expirava mesmo numa página HTTP local. `--password-store=basic` nos perfis temporários eliminou a espera pelo chaveiro do desktop: a navegação de teste passou em menos de um segundo. O perfil é descartável; as credenciais autorizadas continuam no mecanismo próprio do Vortax.
- Caminhos temporários longos causaram também `Socket path too long` em um Chromium de diagnóstico. Agora cada Chrome usa um diretório temporário curto e exclusivo, removido ao terminar.
- Pesquisas podiam repetir buscas, receber chamadas de ferramentas após o orçamento e gastar tempo com o modelo principal. Resultados compactados demais e XML bruto de feeds também prejudicavam a síntese.
- O teste pela interface publicada encontrou um desvio adicional: “URLs exatas” ativava o roteador de matemática, respondendo sem pesquisa. Pedidos de informação atual/pesquisa agora têm prioridade sobre palavras isoladas como “exatas”, “energia” ou “média”.

## Comportamento atual

O dock e o painel Tela usam a mesma `BrowserSurface`. Capturas vazias são ignoradas. Buscas e páginas lidas por HTTP são exibidas com o conteúdo realmente retornado, identificadas como “Leitura web”; cache aparece como “Fontes da conversa”. Resultados sem conteúdo mostram um estado de espera claro.

No navegador real, clique, digitação e rolagem publicam coordenadas do mouse e dimensões da captura. O ponteiro é normalizado pela viewport e animado entre posições. Há transições de página, indicação de carregamento, clique, digitação e rolagem; a preferência de movimento reduzido é respeitada. A captura tem timeout de três segundos e o observador tem limite total de quatro segundos. Páginas com campos sensíveis continuam ocultadas. Não há ponteiro inventado para leitura HTTP.

O modo de pesquisa usa o modelo FAST configurado, ferramentas de leitura e um orçamento menor. Pedidos de criação de código/arquivos continuam usando o fluxo completo. Notícias usam primeiro RSS com título, data, link e identificação do publicador; outras buscas usam Bing RSS, com alternativas HTTP paralelas quando necessário. Buscas repetidas são limitadas a duas, inclusive quando vêm juntas na mesma rodada. Leituras HTTP independentes podem ocorrer em paralelo; ações do mesmo navegador são sequenciais.

Os índices de busca são salvos como `source_type=search_index`, marcados no texto como artigo não lido. Não substituem artigos já extraídos nem contam como leitura completa para antecipar o encerramento. A síntese recebe as observações reais, data atual e instruções para citar URLs exatas e declarar quando só há manchetes. Se o provedor expira ou continua chamando ferramentas após o orçamento, o Vortax entrega as fontes disponíveis com a limitação explícita.

| Configuração | Padrão | Significado |
|---|---:|---|
| `RESEARCH_TIME_BUDGET_SECONDS` | 90 | Orçamento de trabalho antes da síntese final |
| `RESEARCH_TOOL_TIMEOUT_SECONDS` | 25 | Limite por ferramenta |
| `RESEARCH_MODEL_TIMEOUT_SECONDS` | 35 | Limite por chamada de modelo, inclusive síntese |

O trabalho encerra também após seis rodadas no modo comum; pesquisa profunda permite doze rodadas e até 180 segundos de trabalho. A síntese final pode acrescentar até 35 segundos ao orçamento; não é promessa de duração fixa nem de sucesso em sites bloqueados.

O loop publica a conclusão das etapas para atualizar o progresso ao vivo. O indicador de contexto trata números inválidos sem exibir `NaN`; o sanitizador preserva apenas contadores numéricos de tokens conhecidos, mantendo a ocultação de tokens de autenticação e valores textuais.

## Contrato de eventos

- `browser_view`: `{kind, url, title, via, query?, results?, text?}`. Conteúdo de busca/leitura HTTP, sem imagem fictícia.
- `screen_frame`: imagem JPEG/base64 real, URL/título, `viewport: {width, height}`, `cursor?: {x, y, action}`. Ações: `move`, `click`, `type`, `scroll`.
- `screen_frame_blocked`: motivo de proteção, sem imagem sensível. Substitui a imagem anterior no replay.

Os eventos persistem no SQLite e participam do replay. Conteúdo de leitura é renderizado como texto; links aceitam apenas HTTP/HTTPS. Base64 não entra como conteúdo de imagem no contexto textual do modelo.

## Validação

Ambiente isolado no server, a partir da mesma base de produção, com banco e workspace próprios. Nenhuma tarefa antiga do usuário foi usada como fixture.

- Backend: **219 testes, OK; cinco testes externos opcionais desativados** com `VORTAX_LIVE=0`.
- Frontend: build Vite concluído e três testes de seleção de cenas/proteção/escala do ponteiro passaram.
- Navegador real, Chrome instalado e Playwright já existente: página HTTP local, digitação, clique e rolagem; **oito capturas**, ações `move/type/click/scroll`, nenhuma URL `about:blank`. Última execução: navegação 0,87 s, digitação 0,79 s, clique 0,65 s, rolagem 0,63 s.
- Pesquisa real pelo 9Router: três notícias com datas/fontes em **35,82 s** e cotação com fontes em **22,33 s**, ambas `done`. A pesquisa de notícias declarou corretamente a limitação de manchetes. São amostras, não um benchmark geral.
- QA visual no navegador interno do Codex: dock, conteúdo real, replay, ponteiro sobre o botão clicado e viewport de 390 px sem overflow horizontal.

O teste com Playwright mais novo não resolveu o bloqueio do chaveiro; não foi aplicado upgrade do driver em produção. Dependências de documentos já declaradas (`python-docx`, `python-pptx`, `openpyxl`) foram instaladas no venv ativo para permitir a suíte completa.

## Operação e publicação

Produção: `/media/server/HD Backup/Vortax` no **server-desktop**. Serviços `vortax-backend` (`8010`) e `vortax-frontend` (`5173`). Acesso pela LAN: `http://192.168.0.104:5173`; Tailscale: `http://100.65.138.58:5173`.

O frontend deve ser compilado com `VITE_API_BASE_URL= npm run build`, usando proxy do mesmo host. O `.env` real e o `.env.production` local não entram nesta alteração. Túnel público e auto-update permanecem no estado operacional definido anteriormente.

Para verificar após publicação: conferir `GET /health`, serviços ativos, SHA de `main` igual a `origin/main`, abrir uma tarefa nova e conferir resposta final, fontes, progresso e navegador/replay. Para rollback, usar o commit anterior `365a26f`, recompilar o front com base vazia e reiniciar os dois serviços; preservar configurações locais e dados. Usar `git revert` se a correção já foi enviada ao GitHub.
