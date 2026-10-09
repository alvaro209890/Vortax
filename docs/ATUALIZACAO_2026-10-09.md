# Atualização de 09/10/2026: reativação, Gemini via 9Router, bugs do chat e front no estilo Manus

O Vortax estava parado desde 05/08/2026. Nesta rodada ele voltou a rodar no servidor de casa,
só na rede local e no Tailscale, sem login, com o banco zerado.

## Modelo

- O cliente continua sendo o `services/deepseek_client.py`, que é compatível com a API da OpenAI.
  Só mudou o `.env` da raiz (que não vai para o Git):
  - `DEEPSEEK_BASE_URL=http://127.0.0.1:20128/v1` (9Router no próprio servidor)
  - `DEEPSEEK_MODEL` e `DEEPSEEK_MODEL_BRAIN` = `ag/gemini-3.8-flash-high` (loop com ferramentas)
  - `DEEPSEEK_MODEL_FAST` = `ag/gemini-3.8-flash-low` (resposta direta e tarefas leves)
  - `DEEPSEEK_API_KEY` = chave do 9Router
- A chave antiga da DeepSeek não funciona mais (HTTP 401/402).
- Os textos da interface que diziam "DeepSeek" passaram a dizer "Vortax" ou "Modelo".

## Bugs corrigidos

| Sintoma | Causa | Correção |
|---|---|---|
| A resposta aparecia 2 ou 3 vezes ("...é só me" / "dizer!" / resposta inteira) | O front transformava cada `assistant_message_delta` numa mensagem e ainda somava o `assistant_message_done` | `collapseAssistantDeltas` (`App.jsx`): uma mensagem por turno. Os deltas se juntam durante o streaming e são trocados pelo `done` quando ele chega |
| Durante o streaming, a resposta se repetia dentro da mesma mensagem | O loop nativo transmitia o texto de **todas** as iterações: a narração que vem junto com as ferramentas e as respostas recusadas pelo portão | Evento novo `assistant_message_discard` (backend `agent/loop.py`). O front zera o que já tinha acumulado |
| Tarefa em loop por mais de 4 min sem terminar (ex.: cotação do dólar, notebooks) | O portão de fontes (`ResearchSourcesGate`) recusava a entrega e o modelo reescrevia a mesma resposta. O contador de "sem progresso" só avança quando há ferramenta, então isso ia até `MAX_ITERATIONS` (100) | O portão recusa **no máximo 2 vezes**, e a 2ª só vale se o modelo usou ferramenta depois da 1ª. Também há orçamento de tempo `AGENT_TIME_BUDGET_SECONDS` (padrão 300 s): ao estourar, a próxima rodada é sem ferramentas e a entrega passa direto. Na última iteração vale o mesmo |
| "oi" levava 5 s e mostrava plano, "Loop nativo DeepSeek" e "Entrega final" | O loop nativo ignorava o roteador de resposta rápida, que já existia no runner legado | `should_answer_directly` / `is_exact_prompt` agora valem também no loop nativo: uma chamada direta ao modelo |
| O modelo esquecia a conversa anterior no mesmo chat | O loop nativo mandava só a mensagem atual | O loop nativo usa `prepare_context_history` (com compactação) e publica `context_status`. Isso também corrige o indicador de contexto travado em 0% |
| O cronômetro do Computador do Vortax ficava em 0:00 | O relógio do servidor está ~30 s adiantado em relação aos clientes; início "no futuro" → elapsed negativo | `useElapsedTimer` conta a partir de quando o front viu a tarefa rodar, se o início vier no futuro |
| O Computador do Vortax abria em conversa simples, com "Concluído · Pedido concluído · Concluído · open" | Qualquer `agent_progress` abria o dock; a linha de status repetia o estado e mostrava o estado do WebSocket | O dock só abre com trabalho de ferramenta (`lib/events.js`). A linha mostra etapa · tempo e só fala da conexão quando ela tem problema |
| Cartões "Executando etapa / web_fetch" | As ferramentas do loop nativo não tinham rótulo | Rótulos para `web_search`, `web_fetch`, `shell_*`, `file_*`, `glob`, `grep` etc. no backend e no front |
| O título da conversa nunca atualizava (e o descarte de delta também se perderia) | `task_title_updated` não estava no `KNOWN_EVENT_TYPES` (`services/stream_contract.py`), então virava evento `error` no stream | Os dois tipos entraram na lista. O teste `test_stream_contract_coverage.py` varre o código e falha se algum `publish()` usar um tipo fora da lista |
| Resposta simples demorava ~8 s | A resposta direta usava o modelo principal (`flash-high`, raciocínio máximo) | O modo direto usa `pick_model("fast")` → `DEEPSEEK_MODEL_FAST`, hoje `ag/gemini-3.8-flash-low` (~2 s contra ~6 s no 9Router). Matemática/exatas continuam no modelo forte |
| "Backend offline" no navegador embutido, e o front quebrava atrás de túnel/proxy | O front chamava `<host>:8010` direto | Por padrão ele chama a mesma origem, e o proxy do Vite (dev e preview) leva ao backend |

## Front no estilo Manus

- **Tema:** escuro grafite por padrão, com o verde do Vortax (`#08C65D`) como cor principal. O tema claro é opcional (botão no rodapé da barra lateral). As cores estão em tokens no topo de `index.css`. As 432 cores fixas (`rgba(255,255,255,…)`, verde, sombras) viraram `rgb(var(--ov) / a)`, `rgb(var(--accent-rgb) / a)` etc. para funcionar nos dois temas.
- **`theme-manus.css`:** camada carregada depois do `index.css` que redesenha:
  - barra lateral fixa com "Nova tarefa", busca e lista com indicador de status
  - cabeçalho com o título da tarefa
  - mensagens: bolha só para o usuário; o Vortax escreve sem bolha, com o ícone e o nome em cima
  - composer em cartão
  - Computador do Vortax
- **Tela inicial:** saudação, composer centralizado e sugestões em chips, como no Manus.
- **Fontes:** Inter (interface), Source Serif 4 (saudação) e JetBrains Mono (código).
- **Mobile:** a barra lateral continua como gaveta e o composer se adapta. Conferido em 375 px.

## Testes

- Novo: `backend/tests/test_native_loop_exits.py`. Cobre:
  - resposta rápida
  - teto de recusas do portão
  - descarte de delta
  - orçamento de tempo
- Suíte do backend: 209 passaram. As 5 falhas também acontecem no código anterior a esta rodada:
  - 2 testes *live* chamam a DeepSeek com a chave antiga
  - 3 precisam do `python-docx`, que não está no venv do servidor
