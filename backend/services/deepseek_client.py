import json
import re
from typing import Any

import httpx

from config import settings
from services.provider_errors import map_httpx_error
from services.safe_diagnostics import format_exception_for_user, text_len_hint


class DeepSeekError(RuntimeError):
    pass


TOOLS_SCHEMA = [
    {
        "action": "browser_navigate",
        "params": {"url": "https://example.com"},
        "use": "Abrir uma URL no Chrome deste PC.",
    },
    {
        "action": "browser_google_search",
        "params": {"query": "consulta de pesquisa", "hl": "pt-BR"},
        "use": "Pesquisar no Google e retornar resultados estruturados.",
    },
    {
        "action": "browser_extract_links",
        "params": {"limit": 10, "prefer_google_results": True},
        "use": "Extrair links visiveis ou resultados estruturados da pagina atual.",
    },
    {
        "action": "browser_click_link_by_index",
        "params": {"index": 1},
        "use": "Abrir o link visivel pelo indice retornado em browser_extract_links ou browser_google_search.",
    },
    {
        "action": "browser_get_state",
        "params": {},
        "use": "Observar URL, titulo e modo de lancamento do Chrome.",
    },
    {
        "action": "browser_click_text",
        "params": {"text": "Entrar"},
        "use": "Clicar no primeiro elemento que contenha texto visivel.",
    },
    {
        "action": "browser_click_selector",
        "params": {"selector": "a.result"},
        "use": "Clicar no primeiro elemento que corresponda ao seletor CSS.",
    },
    {
        "action": "browser_type",
        "params": {"selector": "input[name='q']", "text": "consulta"},
        "use": "Digitar/preencher texto. Se nao houver selector, digita no foco atual.",
    },
    {
        "action": "browser_press_key",
        "params": {"key": "Enter"},
        "use": "Pressionar tecla no Chrome.",
    },
    {
        "action": "browser_wait_for_text",
        "params": {"text": "Resultado", "timeout_ms": 10000},
        "use": "Aguardar texto aparecer na pagina.",
    },
    {
        "action": "browser_go_back",
        "params": {},
        "use": "Voltar para a pagina anterior.",
    },
    {
        "action": "browser_extract_text",
        "params": {},
        "use": "Extrair titulo, URL e texto visivel da pagina atual.",
    },
    {
        "action": "browser_extract_article",
        "params": {},
        "use": "Extrair conteudo principal limpo da pagina atual, com titulo, URL, descricao, data e texto principal.",
    },
    {
        "action": "browser_screenshot",
        "params": {},
        "use": "Capturar screenshot da pagina atual.",
    },
    {
        "action": "browser_scroll",
        "params": {"direction": "down", "amount": 700},
        "use": "Rolar a pagina.",
    },
    {
        "action": "shell_run",
        "params": {"command": "echo hello"},
        "use": "Executar um comando seguro no terminal Linux deste PC. Comandos permitidos: python3, node, npm, npx, vertex, git, curl, wget, ls, cat, mkdir, cp, mv, grep, find, echo, pwd e outros utilitarios basicos. Para desenvolver software/sites/scripts, use 'vertex \"descricao da tarefa\"'. O comando roda na pasta persistente de projetos da conversa no Vortax. Retorna stdout, stderr e returncode.",
    },
    {
        "action": "vision_analyze",
        "params": {"question": "O que aparece nesta tela?"},
        "use": "Tool de visao computacional. Captura screenshot automaticamente e descreve a tela. Use SOMENTE quando texto extraido nao for suficiente — prefira browser_extract_text ou browser_extract_article para ler textos.",
    },
    {
        "action": "exact_solve",
        "params": {"problem": "Resolva 2x + 3 = 11", "context": ""},
        "use": "Ferramenta deterministica para matematica e exatas. Use para contas, porcentagem, equacoes simples, fisica/quimica com numeros e problemas extraidos de imagem antes de finalizar.",
    },
    {
        "action": "finish",
        "params": {},
        "use": "Finalizar com o campo result.",
    },
]


def deepseek_configured() -> bool:
    return bool(settings.DEEPSEEK_API_KEY.strip())


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }


def _deepseek_url() -> str:
    return f"{settings.DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions"


async def _post_deepseek(payload: dict[str, Any]) -> dict[str, Any]:
    timeout = httpx.Timeout(settings.DEEPSEEK_TIMEOUT_SECONDS, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(_deepseek_url(), headers=_headers(), json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        mapped = map_httpx_error(exc, provider_name="DeepSeek")
        if settings.LOG_API_ERROR_DETAILS:
            raise DeepSeekError(format_exception_for_user(mapped)) from exc
        raise DeepSeekError(str(mapped)) from exc


def _extract_json_object(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise DeepSeekError("Planner DeepSeek nao retornou JSON")
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise DeepSeekError("Planner DeepSeek retornou JSON que nao e objeto")
    return data


async def request_deepseek_response(description: str) -> dict[str, Any]:
    if not deepseek_configured():
        raise DeepSeekError("DEEPSEEK_API_KEY nao configurada")

    system_prompt = (
        "Voce e o Vortax, um agente autonomo controlado por chat. "
        "Esta resposta esta sendo gerada pela integracao real com DeepSeek V4 Flash. "
        "Neste momento voce ainda nao pode controlar ferramentas reais do PC; responda como assistente de texto, "
        "explique o que faria em passos curtos e seja direto. "
        "Se perguntarem se o DeepSeek esta conectado, responda que sim. "
        "Se perguntarem sobre controle real do PC, explique que essa automacao ainda sera ligada no proximo bloco. "
        "Nunca diga que ja mexeu no PC se nenhuma ferramenta real foi executada."
    )
    payload = {
        "model": settings.DEEPSEEK_MODEL,
        "temperature": settings.DEEPSEEK_TEMPERATURE,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": description},
        ],
    }
    data = await _post_deepseek(payload)

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DeepSeekError("Resposta DeepSeek sem choices[0].message.content") from exc

    usage = data.get("usage") or {}
    result = content.strip()
    return {
        "content": result,
        "usage": usage,
        "model": data.get("model", settings.DEEPSEEK_MODEL),
        "input_length": text_len_hint(description),
        "output_length": text_len_hint(result),
    }


async def request_direct_chat_response(
    history: list[dict[str, str]],
    *,
    mode: str = "direct",
    tool_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not deepseek_configured():
        raise DeepSeekError("DEEPSEEK_API_KEY nao configurada")

    if mode == "exact":
        system_prompt = (
            "Voce e o modo direto de matematica e exatas do Vortax. Responda sem acionar o planner e sem delegar ao Vertex. "
            "Resolva com rigor, mostre passos curtos e confira as contas. Se o contexto trouxer resultado de exact_solve, use-o como ferramenta de calculo. "
            "Se houver analise de imagem, use a transcricao/visible_text como enunciado; quando a imagem estiver ambigua, diga exatamente o que falta. "
            "Nao invente dados externos e nao pesquise; se a pergunta depender de dado atual, diga que precisa de pesquisa."
        )
    else:
        system_prompt = (
            "Voce e o modo rapido do Vortax. Responda diretamente no chat, sem planejamento, sem ferramentas e sem Vertex. "
            "Seja claro e curto. Nao diga que executou acoes no PC. Se o pedido exigir internet, arquivos, sistema, codigo, automacao ou dado atual, diga que precisa do modo com ferramentas."
        )

    messages = list(history)
    if tool_context:
        messages.insert(
            0,
            {
                "role": "system",
                "content": "Contexto de ferramentas ja executadas:\n" + json.dumps(tool_context, ensure_ascii=False),
            },
        )

    payload = {
        "model": settings.DEEPSEEK_MODEL,
        "temperature": settings.DEEPSEEK_TEMPERATURE if mode != "exact" else 0.0,
        "stream": False,
        "messages": [{"role": "system", "content": system_prompt}, *messages],
    }
    data = await _post_deepseek(payload)

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DeepSeekError("Resposta DeepSeek sem choices[0].message.content") from exc

    result = str(content).strip()
    return {
        "content": result,
        "usage": data.get("usage") or {},
        "model": data.get("model", settings.DEEPSEEK_MODEL),
        "output_length": text_len_hint(result),
    }


async def request_deepseek_action(history: list[dict[str, str]]) -> dict[str, Any]:
    if not deepseek_configured():
        raise DeepSeekError("DEEPSEEK_API_KEY nao configurada")

    system_prompt = (
        "Voce e o planner JSON do Vortax, um agente autonomo que pesquisa, cria software, gera arquivos e coordena o Vertex. "
        "Responda sempre com um unico objeto JSON valido, sem markdown e sem texto fora do JSON. "
        "Escolha exatamente uma action por resposta. "
        "Se a tarefa envolver pesquisar, encontrar informacao atual, comparar sites, resumir conteudo da web ou responder algo que dependa da internet, seja proativo: "
        "primeiro use browser_google_search com uma consulta objetiva; depois observe results/links; abra resultados relevantes com browser_click_link_by_index ou browser_navigate; "
        "extraia conteudo da pagina aberta preferencialmente com browser_extract_article; use browser_extract_text se a extracao limpa vier fraca; volte e abra outra fonte quando a resposta exigir comparacao ou confirmacao. "
        "Os resultados de busca ja chegam ranqueados e deduplicados por confiabilidade, relevancia e dominio; priorize indices menores, mas ignore qualquer resultado que pareca login, anuncio, agregador fraco ou duplicado. "
        "Se o historico trouxer 'Fontes ja abertas e salvas nesta conversa', reutilize-as antes de pesquisar de novo quando forem suficientes para o mesmo assunto. "
        "Se browser_google_search retornar from_conversation_cache=true, nao use browser_click_link_by_index; responda com os trechos salvos ou use browser_navigate no href se precisar reler a pagina. "
        "Politica minima de fontes: pergunta simples pode usar 1 fonte oficial/confiavel; dados sensiveis, noticia, preco, versao, documentacao, disponibilidade ou informacao que muda no tempo exigem pelo menos 2 fontes; comparacao exige pelo menos 2 fontes por item quando possivel; especificacao oficial deve priorizar site oficial. "
        "Quando houver divergencia entre fontes, marque explicitamente a divergencia e diga qual dado veio de qual URL. "
        "Nunca tente fazer login em contas Google, contas de sites, paywalls ou paginas de autenticacao; se cair em login, use browser_go_back e escolha outro resultado. "
        "Evite resultados de accounts.google.com, ServiceLogin, paginas de preferencia/configuracao do Google, anuncios e links sem conteudo informativo. "
        "Nao finalize uma pesquisa complexa baseado apenas na lista de resultados; abra pelo menos uma fonte relevante e extraia conteudo. "
        "Para pesquisas simples, uma fonte confiavel pode bastar; para temas controversos ou dados que podem variar, consulte duas ou tres fontes. "
        "Se uma ferramenta falhar, tente uma consulta alternativa, outro resultado ou browser_extract_links antes de finalizar com erro. "
        "Use browser_get_state quando estiver incerto sobre a pagina atual. "
        "Depois que as ferramentas retornarem informacao suficiente, use action finish com result claro, direto e com as fontes/URLs visitadas. "
        "Na resposta final, estruture evidencias quando houver pesquisa: para cada conclusao importante, indique fonte/URL; diferencie 'confirmado em fonte aberta', 'inferido' e 'nao encontrado'. "
        "Para perguntas de matematica, fisica, quimica, estatistica, engenharia ou outras exatas, use exact_solve antes de finalizar quando houver conta, porcentagem, equacao ou numeros para calcular. "
        "Se o problema de exatas estiver em imagem, use vision_analyze primeiro pedindo transcricao do enunciado, depois use exact_solve com o texto extraido e finalize com passos curtos. "
        "Perguntas simples e conceituais devem ser respondidas diretamente pelo modo rapido do backend antes de chegar aqui; se chegarem ao planner, mantenha o caminho mais curto possivel. "
        "Para desenvolvimento de software (sites, scripts, APIs, qualquer codigo), use shell_run com o comando vertex: shell_run command=\"vertex 'descricao completa do software que o usuario quer'\". "
        "O Vertex CLI criara todos os arquivos dentro da pasta persistente de projetos da conversa. Nao tente escrever codigo manualmente — delegue ao Vertex. "
        "Para pedidos de arquivos finais ou documentos (.md, PDF, TXT, DOCX, CSV, XLSX, JSON, PPTX), tambem use shell_run com vertex e seja explicito sobre nome, formato, conteudo esperado e que o arquivo final precisa ficar salvo no diretorio atual para download. "
        "Quando o usuario pedir site, pagina, landing, frontend, dashboard ou interface, alem do projeto funcional, exija que o Vertex gere um DOCUMENTACAO.md em Markdown com o que foi criado, estrutura, funcionalidades e como testar. "
        "Depois de cada execucao do Vertex, o Vortax roda revisao automatica do projeto. Para scripts Python, APIs, apps Node e outros codigos, observe project_validation; "
        "Para documentos/arquivos, observe project_validation: se o arquivo pedido ou DOCUMENTACAO.md estiver ausente/vazio, a revisao falhara. "
        "Se project_validation.status='failed', use shell_run com vertex novamente para corrigir exatamente os bugs descritos em project_validation.bugs e aguarde nova revisao. "
        "Depois que o vertex terminar criando site, pagina, frontend, dashboard, React/Vite/Vue/Next ou HTML/CSS, NAO finalize direto: "
        "nao tente iniciar python -m http.server, vite ou outro servidor manualmente para HTML/CSS/JS estatico; o Vortax abre o preview interno automaticamente. "
        "Para projetos que realmente exigem dev server, o Vortax pode subir um preview temporario apenas para revisao e deve encerra-lo antes da entrega. "
        "Nunca inclua localhost, 127.0.0.1, 0.0.0.0 ou LINK_LOCAL_DO_SITE na resposta final ao usuario. "
        "O Vortax abrira o projeto no Chrome, testara funcionalidades de frontend, streamara screenshots, analisara o frontend com visao e rolara paginas longas ate o fim. "
        "Se o resultado da ferramenta trouxer web_validation.status='failed', use shell_run com vertex novamente para corrigir exatamente os bugs descritos em web_validation.bugs; "
        "so use finish quando project_validation.status='passed' para projetos de codigo e, para sites, quando web_validation.status='passed' ou web_validation.requires_validation=false. "
        "Se web_validation.status='blocked' ou project_validation.status='blocked', informe o erro de configuracao em vez de fingir que testou. "
        "Quando finalizar site ou arquivo gerado, responda de forma proativa e curta: diga o que foi criado, cite que a documentacao/download esta disponivel no card do Vortax e nao cole o Markdown inteiro no chat. "
        "Se um preview interno foi usado, diga no maximo que a revisao foi concluida; nao forneca link local porque usuarios do Firebase Hosting nao conseguem abrir enderecos locais deste PC. "
        "Extrair texto de paginas: prefira browser_extract_article ou browser_extract_text — eles sao mais rapidos, mais baratos e mais precisos que visao computacional. "
        "Use vision_analyze SOMENTE quando o texto extraido nao for suficiente: imagens, graficos, videos, layout visual, botoes sem texto, CAPTCHA, confirmacao visual de que algo apareceu/desapareceu na tela. "
        "Nao use vision_analyze para ler texto de paginas web comuns — browser_extract_article ou browser_extract_text resolvem melhor. "
        "vision_analyze e uma tool como as outras: o sistema captura a screenshot automaticamente, voce so precisa passar a question. "
        "Se o vision_analyze retornar confidence baixo ou medium, refine a question e tente de novo. "
        "Se confidence for high, use a descricao para decidir a proxima acao. "
        "Acoes disponiveis: "
        f"{json.dumps(TOOLS_SCHEMA, ensure_ascii=False)}. "
        "Formato obrigatorio: "
        "{\"action\":\"browser_navigate\",\"description\":\"Abrindo site\",\"params\":{\"url\":\"https://example.com\"},\"requires_confirmation\":false}. "
        "Para finalizar: {\"action\":\"finish\",\"result\":\"resposta final\"}."
    )
    payload = {
        "model": settings.DEEPSEEK_MODEL,
        "temperature": 0.0,
        "stream": False,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system_prompt}, *history],
    }
    data = await _post_deepseek(payload)
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DeepSeekError("Resposta DeepSeek sem choices[0].message.content") from exc

    action = _extract_json_object(content)
    if "action" not in action:
        raise DeepSeekError("Planner DeepSeek retornou JSON sem action")
    return action


async def request_context_summary(
    previous_summary: str,
    messages: list[dict[str, str]],
    *,
    max_chars: int,
) -> str:
    if not deepseek_configured():
        raise DeepSeekError("DEEPSEEK_API_KEY nao configurada")

    transcript = "\n".join(
        f"{message.get('role', 'unknown')}: {message.get('content', '')}"
        for message in messages
        if str(message.get("content") or "").strip()
    )
    system_prompt = (
        "Voce compacta historico de uma conversa do Vortax para preservar contexto. "
        "Produza um resumo denso em portugues, sem markdown pesado, mantendo: pedidos do usuario, "
        "decisoes tomadas, resultados entregues, URLs/fontes importantes, arquivos/projetos criados, "
        "restricoes e pendencias. Nao invente fatos. A saida deve caber no limite indicado."
    )
    user_prompt = (
        f"Resumo anterior:\n{previous_summary or '(vazio)'}\n\n"
        f"Novos turnos a compactar:\n{transcript}\n\n"
        f"Escreva um resumo consolidado com no maximo {max_chars} caracteres."
    )
    payload = {
        "model": settings.DEEPSEEK_MODEL,
        "temperature": 0.0,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    data = await _post_deepseek(payload)
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DeepSeekError("Resposta DeepSeek sem choices[0].message.content") from exc
    return content.strip()[:max_chars]


async def request_task_plan(description: str) -> list[dict[str, str]]:
    """Gera 4-6 etapas dinamicas de acompanhamento baseadas no pedido do usuario."""
    if not deepseek_configured():
        raise DeepSeekError("DEEPSEEK_API_KEY nao configurada")

    system_prompt = (
        "Voce gera planos de acompanhamento para usuarios do Vortax acompanharem o progresso do agente. "
        "Analise o pedido do usuario e produza dois conjuntos de dados em um unico JSON:\n\n"
        "1. \"plan\": 4-6 etapas curtas e sequenciais que o agente Vortax (DeepSeek) provavelmente seguira. "
        "Cada etapa com \"label\" (2-4 palavras) e \"detail\" (1 frase).\n\n"
        "2. \"vertex_steps\": Se o pedido envolver desenvolvimento de software/site/script/codigo/arquivo, "
        "produza 5-8 etapas ESPECIFICAS do que o Vertex CLI fara para criar o projeto. "
        "Exemplos de vertex_steps: \"Analisar requisitos do site\", \"Criar index.html com estrutura principal\", "
        "\"Estilizar com CSS responsivo\", \"Adicionar JavaScript para interatividade\", "
        "\"Gerar DOCUMENTACAO.md\", \"Revisar e corrigir bugs\". "
        "Se o pedido NAO envolver criacao de software/codigo/arquivos, retorne vertex_steps como array vazio [].\n\n"
        "Seja ESPECIFICO ao pedido. Exemplos:\n"
        "- Pedido \"crie um site de portfolio\": plan com etapas de desenvolvimento, vertex_steps com etapas de criacao HTML/CSS/JS\n"
        "- Pedido \"pesquise noticias sobre IA\": plan com etapas de pesquisa, vertex_steps vazio []\n"
        "- Pedido \"corrija o bug no login\": plan com etapas de debug, vertex_steps com edicao de arquivos\n"
        "Responda APENAS com JSON: {\"plan\":[{\"label\":\"...\",\"detail\":\"...\"},...],\"vertex_steps\":[{\"label\":\"...\",\"detail\":\"...\"},...]}"
    )

    payload = {
        "model": settings.DEEPSEEK_MODEL,
        "temperature": 0.2,
        "stream": False,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Pedido do usuario: {description}"},
        ],
    }
    data = await _post_deepseek(payload)
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DeepSeekError("Resposta DeepSeek sem choices[0].message.content") from exc

    parsed = _extract_json_object(content)

    plan = parsed.get("plan") if isinstance(parsed, dict) else parsed
    if not isinstance(plan, list) or len(plan) == 0:
        raise DeepSeekError("Plano de tasks retornou array vazio")

    result_plan = []
    for step in plan[:6]:
        if isinstance(step, dict):
            result_plan.append({
                "label": str(step.get("label") or "Etapa"),
                "detail": str(step.get("detail") or ""),
            })
    if not result_plan:
        raise DeepSeekError("Plano de tasks sem etapas validas")

    vertex_steps = []
    raw_vertex = parsed.get("vertex_steps") if isinstance(parsed, dict) else None
    if isinstance(raw_vertex, list):
        for step in raw_vertex[:8]:
            if isinstance(step, dict):
                vertex_steps.append({
                    "label": str(step.get("label") or "Etapa Vertex"),
                    "detail": str(step.get("detail") or ""),
                })

    return {"plan": result_plan, "vertex_steps": vertex_steps}
