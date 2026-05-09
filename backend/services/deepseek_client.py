import asyncio
import json
import random
from typing import Any

import httpx

from config import settings
from services.provider_errors import map_httpx_error
from services.safe_diagnostics import format_exception_for_user, text_len_hint


class DeepSeekError(RuntimeError):
    pass


_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


def _is_retryable_error(exc: httpx.HTTPError) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUSES
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError)):
        return True
    return False


async def with_retry(
    fn,
    *args,
    max_retries: int = 3,
    base_delay: float = 1.0,
    provider_name: str = "API",
    **kwargs,
) -> Any:
    """Executa fn(*args, **kwargs) com exponential backoff + jitter em erros transientes."""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return await fn(*args, **kwargs)
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt >= max_retries or not _is_retryable_error(exc):
                mapped = map_httpx_error(exc, provider_name=provider_name)
                if settings.LOG_API_ERROR_DETAILS:
                    raise DeepSeekError(format_exception_for_user(mapped)) from exc
                raise DeepSeekError(str(mapped)) from exc
            # Exponential backoff com jitter
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
            await asyncio.sleep(delay)
    # Nao deve chegar aqui, mas por seguranca
    raise last_error  # type: ignore[misc]


TOOLS_SCHEMA = [
    {
        "action": "browser_navigate",
        "params": {"url": "https://example.com"},
        "use": "Abrir uma URL no Chrome deste PC.",
    },
    {
        "action": "browser_google_search",
        "params": {"query": "consulta de pesquisa", "hl": "pt-BR"},
        "use": "Pesquisar na web sem abrir o Google no navegador e retornar resultados estruturados.",
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
        "action": "browser_auth_signup",
        "params": {"signup_url": "https://example.com/signup"},
        "use": "Criar cadastro somente quando o usuario pedir cadastro/registrar e nao fornecer credenciais. O backend gera usuario/email/senha fortes; nunca use senhas fracas ou emails de terceiros.",
    },
    {
        "action": "browser_auth_login",
        "params": {"login_url": "https://example.com/login"},
        "use": "Fazer login somente quando o backend informou autorizacao segura ativa para esta tarefa. Nunca envie usuario/senha nos params.",
    },
    {
        "action": "browser_auth_status",
        "params": {},
        "use": "Verificar se existe sessao/autorizacao segura ativa e se a pagina atual esta dentro do escopo autorizado.",
    },
    {
        "action": "browser_auth_logout",
        "params": {},
        "use": "Encerrar sessao autorizada e limpar cookies/storage do navegador isolado da tarefa.",
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
        "use": "Executar um comando seguro no terminal Linux deste PC. Comandos permitidos: python3, node, npm, npx, openclaude, git, curl, wget, ls, cat, mkdir, cp, mv, grep, find, echo, pwd e outros utilitarios basicos. Para desenvolver software/sites/scripts, analisar repositorios publicos do GitHub ou gerar arquivos finais (.md, .pdf, .docx, .pptx, .xlsx, .csv), use 'openclaude \"descricao da tarefa\"'. O comando roda na pasta persistente de projetos da conversa no Vortax. Retorna stdout, stderr e returncode.",
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


def groq_task_planner_configured() -> bool:
    return bool(settings.GROQ_API_KEY.strip())


def task_planner_configured() -> bool:
    return groq_task_planner_configured() or deepseek_configured()


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }


def _groq_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }


def _deepseek_url() -> str:
    return f"{settings.DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions"


def _groq_url() -> str:
    return f"{settings.GROQ_BASE_URL.rstrip('/')}/chat/completions"


async def _post_deepseek(payload: dict[str, Any]) -> dict[str, Any]:
    return await with_retry(_post_deepseek_inner, payload, provider_name="DeepSeek")


async def _post_deepseek_inner(payload: dict[str, Any]) -> dict[str, Any]:
    timeout = httpx.Timeout(settings.DEEPSEEK_TIMEOUT_SECONDS, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(_deepseek_url(), headers=_headers(), json=payload)
        response.raise_for_status()
        return response.json()


async def _post_groq(payload: dict[str, Any]) -> dict[str, Any]:
    return await with_retry(_post_groq_inner, payload, provider_name="Groq")


async def _post_groq_inner(payload: dict[str, Any]) -> dict[str, Any]:
    timeout = httpx.Timeout(settings.GROQ_TASK_PLANNER_TIMEOUT_SECONDS, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(_groq_url(), headers=_groq_headers(), json=payload)
        response.raise_for_status()
        return response.json()


def _json_error(message: str, text: str, exc: Exception | None = None) -> DeepSeekError:
    detail = f"{message}. Trecho recebido: {text[:500]}"
    return DeepSeekError(detail) if exc is None else DeepSeekError(detail)


def _extract_balanced_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _json_error("Planner DeepSeek retornou JSON invalido", text, exc) from exc
    if not isinstance(data, dict):
        raise DeepSeekError("Planner DeepSeek retornou JSON que nao e objeto")
    return data


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = str(text or "").strip()
    if not cleaned:
        raise DeepSeekError("Planner DeepSeek nao retornou JSON")
    try:
        return _parse_json_object(cleaned)
    except DeepSeekError as direct_error:
        candidate = _extract_balanced_json_object(cleaned)
        if not candidate:
            raise direct_error
        if candidate == cleaned:
            raise direct_error
        return _parse_json_object(candidate)


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
            "Voce e o modo direto de matematica e exatas do Vortax. Responda sem acionar o planner e sem delegar ao OpenClaude. "
            "Resolva com rigor, mostre passos curtos e confira as contas. Se o contexto trouxer resultado de exact_solve, use-o como ferramenta de calculo. "
            "Se houver analise de imagem, use a transcricao/visible_text como enunciado; quando a imagem estiver ambigua, diga exatamente o que falta. "
            "Nao invente dados externos e nao pesquise; se a pergunta depender de dado atual, diga que precisa de pesquisa."
        )
    else:
        system_prompt = (
            "Voce e o assistente de chat do Vortax. Responda diretamente no chat, sem planejamento, sem ferramentas. "
            "Seja claro, completo e bem formatado em Markdown. Use titulo curto em negrito quando ajudar, paragrafos curtos, "
            "listas com marcadores, tabelas pequenas quando compararem dados, e destaques em **negrito** para fatos importantes. "
            "Para respostas factuais, organize em: resumo direto, pontos principais, detalhes relevantes e limites/observacoes quando houver incerteza. "
            "Nao entregue um bloco unico de texto longo. Nao mencione que executou acoes no PC. "
            "Se nao conseguir responder sem internet, arquivos ou dados atuais, decline de forma natural e breve, sem revelar termos tecnicos ou modos internos do sistema."
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
        "Voce e o planner JSON do Vortax, um agente autonomo que pesquisa, cria software, gera arquivos e coordena o OpenClaude. "
        "Responda sempre com um unico objeto JSON valido, sem markdown e sem texto fora do JSON. "
        "Escolha exatamente uma action por resposta. "
        "Se a tarefa envolver pesquisar, encontrar informacao atual, comparar sites, resumir conteudo da web ou responder algo que dependa da internet, seja proativo: "
        "primeiro use browser_google_search com uma consulta objetiva; depois observe results/links; abra resultados relevantes com browser_click_link_by_index ou browser_navigate; "
        "extraia conteudo da pagina aberta preferencialmente com browser_extract_article; use browser_extract_text se a extracao limpa vier fraca; volte e abra outra fonte quando a resposta exigir comparacao ou confirmacao. "
        "Os resultados de busca ja chegam ranqueados e deduplicados por confiabilidade, relevancia e dominio; priorize indices menores, mas ignore qualquer resultado que pareca login, anuncio, agregador fraco ou duplicado. "
        "Se o historico trouxer 'Fontes ja abertas e salvas nesta conversa', reutilize-as antes de pesquisar de novo quando forem suficientes para o mesmo assunto. "
        "Se browser_google_search retornar from_conversation_cache=true, nao use browser_click_link_by_index; responda com os trechos salvos ou use browser_navigate no href se precisar reler a pagina. "
        "Politica minima de fontes: pergunta simples pode usar 1 fonte oficial/confiavel; dados sensiveis, noticia, preco, versao, documentacao, disponibilidade ou informacao que muda no tempo exigem pelo menos 2 fontes; comparacao exige pelo menos 2 fontes por item quando possivel; especificacao oficial deve priorizar site oficial. "
        "PESQUISA DE PESSOAS: Se o usuario pedir informacoes sobre uma pessoa, NUNCA se contente com resultados vagos. "
        "Siga estas estrategias obrigatoriamente: "
        "1) Use multiplas consultas variadas: nome completo entre aspas, nome + LinkedIn, nome + GitHub, nome + cidade, nome + profissao, nome + curriculo. "
        "2) Busque em plataformas especificas: site:linkedin.com/in \"NOME\", site:github.com \"NOME\", site:facebook.com \"NOME\", site:instagram.com \"NOME\", site:wikipedia.org \"NOME\". "
        "3) Busque noticias e artigos: \"NOME\" + noticias, \"NOME\" + site:.gov.br, \"NOME\" + site:.edu.br. "
        "4) Busque curriculos e perfis profissionais: \"NOME\" + curriculo, \"NOME\" + CV, \"NOME\" + lattes, \"NOME\" + portfolio. "
        "5) Se um resultado der informacoes parciais, ABRA a pagina e extraia o conteudo completo com browser_extract_article. "
        "6) CRUZE informacoes de multiplas fontes — nao aceite uma unica fonte como suficiente para perfil de pessoa. "
        "7) Se as primeiras buscas retornarem poucos resultados, terve consultas alternativas: nome sem sobrenome, nome + cidade provavel, nome + empresa/area de atuacao. "
        "8) So finalize quando tiver informacoes concretas: formacao, experiencia, redes sociais, portfolio, projetos e/ou noticias. "
        "9) SEPARE claramente na resposta o que veio de cada fonte e o que NAO foi encontrado. "
        "NUNCA responda 'nao encontrei' apos apenas uma tentativa — voce deve tentar pelo menos 4-5 consultas diferentes e abrir 2-3 fontes antes de concluir que nao ha informacao suficiente. "
        "Quando houver divergencia entre fontes, marque explicitamente a divergencia e diga qual dado veio de qual URL. "
        "Por padrao, nunca tente fazer login, pedir senha no chat, digitar senhas com browser_type ou acessar paywalls/paginas de autenticacao. "
        "Excecao: se o historico/contexto informar que existe autorizacao segura ativa para um dominio, use somente browser_auth_login/browser_auth_status para autenticar e operar apenas dentro do escopo autorizado. "
        "Nunca inclua usuario, senha, token, OTP ou segredo em params de ferramenta, respostas ou prompts. "
        "Nunca tente burlar CAPTCHA, 2FA, MFA, OTP, paywall ou desafio de seguranca; se aparecer, pare e informe que precisa de intervencao do usuario. "
        "Se o usuario pedir cadastro/registrar/criar conta dentro de uma sessao autorizada e nao fornecer credenciais, use browser_auth_signup; o backend gerara credenciais fortes e voce deve devolver essas credenciais ao final. "
        "Nunca invente emails de terceiros nem use senhas fracas como 12345678. "
        "Evite resultados de accounts.google.com, ServiceLogin, paginas de preferencia/configuracao do Google, anuncios e links sem conteudo informativo. "
        "REGRAS IMPORTANTES PARA CRIACAO DE SOFTWARE: "
        "Se o usuario pedir para criar site, landing page, dashboard, app, sistema, API ou qualquer "
        "codigo que envolva design, interface, experiencia do usuario ou tecnologias atuais, PESQUISE "
        "PRIMEIRO antes de chamar o OpenClaude. "
        "Exemplo: usuario pede 'crie um site de vendas moderno' -> PRIMEIRO busque 'tendencias design ecommerce 2026', "
        "abra uma referencia, extraia conteudo, DEPOIS chame openclaude com o prompt enriquecido pelas referencias. "
        "Exemplo: usuario pede 'crie uma calculadora em Python' -> pode ir direto ao OpenClaude sem pesquisa. "
        "Exemplo: usuario pede 'crie um dashboard financeiro' -> PRIMEIRO busque 'dashboard financeiro design exemplos 2026'. "
        "A pesquisa deve alimentar o prompt do OpenClaude com informacao concreta: "
        "'Crie um site estilo [dribbble/behance], com as seguintes referencias de cores e layout extraidas de [URL...]'. "
        "Quando o backend executar pesquisa automatica antes de voce, as fontes ja estarao disponiveis "
        "no contexto 'Fontes ja abertas e salvas nesta conversa'. USE-AS para enriquecer o prompt do OpenClaude "
        "com detalhes extraidos: tendencias de design, estrutura de layout, paleta de cores, "
        "exemplos de navegacao, tecnologias recomendadas e boas praticas encontradas nas referencias. "
        "Se houver resultado de vision_analyze no historico, ELE contem analise visual detalhada "
        "da pagina de referencia (cores exatas, estrutura de layout, estilo visual, tipografia, "
        "elementos de UI). INCORPORE esses detalhes visuais no prompt do OpenClaude para gerar um "
        "design mais fiel as referencias pesquisadas. "
        "NUNCA chame openclaude com um prompt generico como 'crie um site' — voce DEVE incluir referencias "
        "concretas das fontes pesquisadas. Exemplo de prompt bem estruturado: "
        "openclaude 'Crie uma landing page para [setor]. Inspirado nas referencias coletadas: "
        "layout com hero section de tela cheia, navegacao fixa no topo, secao de recursos em grid "
        "3 colunas, depoimentos em carrossel e rodape com formulario de contato. "
        "Use paleta de cores moderna (azul escuro #1a2332 + verde accent #08C65D), "
        "tipografia Inter e transicoes suaves. Responsivo e otimizado para mobile.' "
        "NUNCA chame openclaude diretamente sem antes verificar se pesquisa previa traria valor ao resultado final. "
        "Nao finalize uma pesquisa complexa baseado apenas na lista de resultados; abra pelo menos uma fonte relevante e extraia conteudo. "
        "Para pesquisas simples, uma fonte confiavel pode bastar; para temas controversos ou dados que podem variar, consulte duas ou tres fontes. "
        "Se uma ferramenta falhar, tente uma consulta alternativa, outro resultado ou browser_extract_links antes de finalizar com erro. "
        "Use browser_get_state quando estiver incerto sobre a pagina atual. "
        "Depois que as ferramentas retornarem informacao suficiente, use action finish com result claro, completo, bem formatado em Markdown e com as fontes/URLs visitadas. "
        "Na resposta final, estruture evidencias quando houver pesquisa: para cada conclusao importante, indique fonte/URL; diferencie 'confirmado em fonte aberta', 'inferido' e 'nao encontrado'. "
        "Respostas finais devem ser mais completas e mais bonitas por padrao: use titulo curto em negrito, uma conclusao/resumo inicial, secoes curtas, listas com marcadores, "
        "destaques em **negrito**, tabelas pequenas quando houver comparacao ou cronologia, e uma secao final de fontes/limites quando houver pesquisa. "
        "Nao entregue tudo em um unico paragrafo; quebre a resposta para leitura facil no chat. "
        "Nao finalize dizendo que nao foi possivel comparar apenas porque uma pagina bloqueou ou o cache nao tinha dados; tente consultas alternativas, dominios oficiais e uma busca por indicador antes de desistir. "
        "Para dados economicos comparativos (PIB, inflacao/IPCA, desemprego, Selic, cambio), pesquise por indicador e periodo, priorizando IBGE, Ipea, Banco Central, World Bank, OECD ou IMF; nao use biografias como evidencia quantitativa. "
        "Para perguntas de matematica, fisica, quimica, estatistica, engenharia ou outras exatas, use exact_solve antes de finalizar quando houver conta, porcentagem, equacao ou numeros para calcular. "
        "Se o problema de exatas estiver em imagem, use vision_analyze primeiro pedindo transcricao do enunciado, depois use exact_solve com o texto extraido e finalize com passos curtos. "
        "Perguntas simples e conceituais devem ser respondidas diretamente pelo modo rapido do backend antes de chegar aqui; se chegarem ao planner, mantenha o caminho mais curto possivel. "
        "Para analise de repositorios publicos do GitHub, aceite formatos https://github.com/owner/repo, github.com/owner/repo e owner/repo quando o usuario mencionar GitHub/repositorio. "
        "Use shell_run com openclaude e inclua a URL/owner/repo no prompt. O OpenClaude deve clonar por HTTPS dentro do workspace da conversa, analisar em modo read-only, nao alterar codigo clonado, "
        "mapear stack, arquitetura, pontos fortes, riscos, bugs provaveis, seguranca, performance e testes, citar caminhos de arquivos e gerar RELATORIO_TECNICO.md na raiz do workspace. "
        "Nao use token, login ou repos privados nesta primeira versao; se o repo for privado, explique que so repositorios publicos sao suportados por enquanto. "
        "Para desenvolvimento de software (sites, scripts, APIs, qualquer codigo), use shell_run com o comando openclaude: shell_run command=\"openclaude 'descricao completa do software que o usuario quer'\". "
        "O OpenClaude criara todos os arquivos dentro da pasta persistente de projetos da conversa. Nao tente escrever codigo manualmente — delegue ao OpenClaude para garantir que o projeto seja funcional e completo. "
        "IMPORTANTE: Sempre que o usuario pedir um codigo, script ou arquivo unico, alem de usar o OpenClaude para cria-lo, voce DEVE incluir o conteudo desse codigo na sua resposta final (action finish) dentro de um bloco de codigo Markdown com a linguagem correta (ex: ```python ... ```). "
        "Isso permite que o usuario copie o codigo instantaneamente usando o botao de copiar no chat, enquanto o download oficial fica disponivel no card do Vortax. "
        "Para pedidos de arquivos finais ou documentos (.md, PDF, TXT, DOCX, CSV, XLSX, JSON, PPTX), tambem use shell_run com openclaude e seja explicito sobre nome, formato, conteudo esperado e que o arquivo final precisa ficar salvo no diretorio atual para download. "
        "Quando o usuario pedir PDF ou Markdown factual sem fornecer conteudo suficiente (ex: historia de clube, perfil, relatorio, guia, comparativo), pesquise primeiro: use browser_google_search, abra fontes relevantes e extraia com browser_extract_article/browser_extract_text antes de chamar OpenClaude. "
        "Para documentos factuais, use no minimo 3 fontes boas quando possivel e passe ao OpenClaude os dados e URLs coletados. "
        "Quando o usuario pedir PDF, gere sempre um Markdown fonte bem estruturado e o .pdf final; o Vortax pode converter o Markdown em PDF automaticamente, mas o Markdown fonte deve existir. "
        "Se o usuario pedir para melhorar, alterar, atualizar ou corrigir 'o PDF', 'o markdown', 'esse arquivo' ou 'o documento anterior', use o contexto ARQUIVOS_DA_CONVERSA/ALVO_DA_EDICAO para atualizar o arquivo certo, preservando o nome logico da entrega. "
        "Quando o usuario pedir site, pagina, landing, frontend, dashboard, interface, sistema, app, script, API ou analise tecnica de codigo/repositorio, alem do resultado principal, exija que o OpenClaude gere um Markdown bonito e bem estruturado: DOCUMENTACAO.md para software criado ou RELATORIO_TECNICO.md para analises. "
        "Esse Markdown deve ter titulo, resumo, contexto, estrutura/arquitetura, como testar ou validar, limites e proximos passos, pois sera exibido em um card de leitura no chat. "
        "Depois de cada execucao do OpenClaude, o Vortax roda revisao automatica do projeto. Para scripts Python, APIs, apps Node e outros codigos, observe project_validation; "
        "Para documentos/arquivos, observe project_validation: se o arquivo pedido ou DOCUMENTACAO.md estiver ausente/vazio, a revisao falhara. "
        "Se project_validation.status='failed', use shell_run com openclaude novamente para corrigir exatamente os bugs descritos em project_validation.bugs e aguarde nova revisao. "
        "Depois que o openclaude terminar criando site, pagina, frontend, dashboard, React/Vite/Vue/Next ou HTML/CSS, NAO finalize direto: "
        "nao tente iniciar python -m http.server, vite ou outro servidor manualmente para HTML/CSS/JS estatico; o Vortax abre o preview interno automaticamente. "
        "Para projetos que realmente exigem dev server, o Vortax pode subir um preview temporario apenas para revisao e deve encerra-lo antes da entrega. "
        "Nunca inclua localhost, 127.0.0.1, 0.0.0.0 ou LINK_LOCAL_DO_SITE na resposta final ao usuario. "
        "O Vortax abrira o projeto no Chrome, testara funcionalidades de frontend, streamara screenshots, analisara o frontend com visao e rolara paginas longas ate o fim. "
        "Se o resultado da ferramenta trouxer web_validation.status='failed', use shell_run com openclaude novamente para corrigir exatamente os bugs descritos em web_validation.bugs; "
        "so use finish quando project_validation.status='passed' para projetos de codigo e, para sites, quando web_validation.status='passed' ou web_validation.requires_validation=false. "
        "Se web_validation.status='blocked' ou project_validation.status='blocked', informe o erro de configuracao em vez de fingir que testou. "
        "Quando finalizar site ou arquivo gerado, responda de forma proativa e curta: diga o que foi criado/alterado, cite que o documento/download esta disponivel no card do Vortax, mencione fontes usadas quando houve pesquisa e INCLUA o bloco de codigo no chat se for um script ou arquivo simples."
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

    try:
        action = _extract_json_object(content)
    except DeepSeekError:
        repair_payload = {
            **payload,
            "messages": [
                *payload["messages"],
                {"role": "assistant", "content": str(content or "")[:4000]},
                {
                    "role": "user",
                    "content": (
                        "A resposta anterior nao era um objeto JSON valido para o Vortax. "
                        "Responda agora somente com um unico JSON valido no schema de action, sem markdown e sem texto extra."
                    ),
                },
            ],
        }
        repair_data = await _post_deepseek(repair_payload)
        try:
            repaired_content = repair_data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DeepSeekError("Resposta DeepSeek sem choices[0].message.content") from exc
        action = _extract_json_object(repaired_content)
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


def _task_plan_system_prompt() -> str:
    return (
        "Voce gera planos de acompanhamento para usuarios do Vortax acompanharem o progresso do agente. "
        "Voce e apenas o planner de tarefas; nao execute o pedido e nao responda ao usuario final. "
        "Analise o pedido do usuario e produza dois conjuntos de dados em um unico JSON:\n\n"
        "1. \"plan\": 3-6 etapas curtas e sequenciais que o agente Vortax (DeepSeek) deve seguir para executar o pedido. "
        "Cada etapa com \"label\" (2-4 palavras), \"detail\" (1 frase), \"tool_hint\" "
        "(understand, research, execute, validate ou deliver) e \"acceptance_criteria\" "
        "(1-3 criterios objetivos para considerar a etapa concluida).\n\n"
        "2. \"vertex_steps\": Se o pedido envolver desenvolvimento de software/site/script/codigo/arquivo, "
        "produza 4-8 etapas ESPECIFICAS do que o OpenClaude fara para criar o projeto. "
        "Exemplos de vertex_steps: \"Analisar requisitos do site\", \"Criar index.html com estrutura principal\", "
        "\"Estilizar com CSS responsivo\", \"Adicionar JavaScript para interatividade\", "
        "\"Gerar DOCUMENTACAO.md\", \"Revisar e corrigir bugs\". "
        "Se o pedido NAO envolver criacao de software/codigo/arquivos, retorne vertex_steps como array vazio [].\n\n"
        "Nao crie plano para cumprimento simples que deveria ser resposta direta; nesses casos retorne plan vazio. "
        "Para pesquisa atual, inclua etapa research. Para criacao/edicao de arquivos, inclua execute e validate. "
        "Para resposta final, sempre inclua deliver. "
        "Seja ESPECIFICO ao pedido. Exemplos:\n"
        "- Pedido \"crie um site de portfolio\": plan com etapas de desenvolvimento, vertex_steps com etapas de criacao HTML/CSS/JS\n"
        "- Pedido \"pesquise noticias sobre IA\": plan com etapas de pesquisa, vertex_steps vazio []\n"
        "- Pedido \"corrija o bug no login\": plan com etapas de debug, vertex_steps com edicao de arquivos\n"
        "Responda APENAS com JSON: {\"plan\":[{\"label\":\"...\",\"detail\":\"...\",\"tool_hint\":\"execute\",\"acceptance_criteria\":[\"...\"]},...],\"vertex_steps\":[{\"label\":\"...\",\"detail\":\"...\"},...]}"
    )


def _normalize_task_plan_response(parsed: dict[str, Any], *, provider: str, model: str, usage: dict[str, Any] | None = None) -> dict[str, Any]:
    plan = parsed.get("plan") if isinstance(parsed, dict) else parsed
    if not isinstance(plan, list) or len(plan) == 0:
        raise DeepSeekError("Plano de tasks retornou array vazio")

    result_plan = []
    for step in plan[:6]:
        if isinstance(step, dict):
            result_plan.append({
                "label": str(step.get("label") or "Etapa"),
                "detail": str(step.get("detail") or ""),
                "tool_hint": str(step.get("tool_hint") or ""),
                "acceptance_criteria": [
                    str(item)
                    for item in (step.get("acceptance_criteria") if isinstance(step.get("acceptance_criteria"), list) else [])
                    if str(item).strip()
                ][:3],
            })
    if not result_plan:
        raise DeepSeekError("Plano de tasks sem etapas validas")

    code_agent_steps = []
    raw_code_agent = parsed.get("vertex_steps") if isinstance(parsed, dict) else None
    if isinstance(raw_code_agent, list):
        for step in raw_code_agent[:8]:
            if isinstance(step, dict):
                code_agent_steps.append({
                    "label": str(step.get("label") or "Etapa OpenClaude"),
                    "detail": str(step.get("detail") or ""),
                })

    return {
        "plan": result_plan,
        "vertex_steps": code_agent_steps,
        "planner_provider": provider,
        "planner_model": model,
        "usage": usage or {},
    }


async def request_groq_task_plan(description: str) -> dict[str, Any]:
    if not groq_task_planner_configured():
        raise DeepSeekError("GROQ_API_KEY nao configurada")

    payload = {
        "model": settings.GROQ_TASK_PLANNER_MODEL,
        "temperature": settings.GROQ_TASK_PLANNER_TEMPERATURE,
        "stream": False,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _task_plan_system_prompt()},
            {"role": "user", "content": f"Pedido do usuario: {description}"},
        ],
    }
    data = await _post_groq(payload)
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DeepSeekError("Resposta Groq sem choices[0].message.content") from exc

    parsed = _extract_json_object(content)
    return _normalize_task_plan_response(
        parsed,
        provider="groq",
        model=str(data.get("model") or settings.GROQ_TASK_PLANNER_MODEL),
        usage=data.get("usage") or {},
    )


async def request_deepseek_task_plan(description: str) -> dict[str, Any]:
    if not deepseek_configured():
        raise DeepSeekError("DEEPSEEK_API_KEY nao configurada")

    payload = {
        "model": settings.DEEPSEEK_MODEL,
        "temperature": 0.2,
        "stream": False,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _task_plan_system_prompt()},
            {"role": "user", "content": f"Pedido do usuario: {description}"},
        ],
    }
    data = await _post_deepseek(payload)
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DeepSeekError("Resposta DeepSeek sem choices[0].message.content") from exc

    parsed = _extract_json_object(content)
    return _normalize_task_plan_response(
        parsed,
        provider="deepseek",
        model=str(data.get("model") or settings.DEEPSEEK_MODEL),
        usage=data.get("usage") or {},
    )


async def request_task_plan(description: str) -> dict[str, Any]:
    """Gera tasks via Groq primeiro e usa DeepSeek apenas como fallback."""
    from services.exact_solver import should_answer_directly
    if should_answer_directly(description):
        return {"plan": [], "vertex_steps": [], "direct": True, "planner_provider": "direct"}

    groq_error = ""
    if groq_task_planner_configured():
        try:
            return await request_groq_task_plan(description)
        except DeepSeekError as exc:
            groq_error = str(exc)

    if deepseek_configured():
        result = await request_deepseek_task_plan(description)
        if groq_error:
            result["planner_warning"] = f"Planner Groq indisponivel; fallback DeepSeek usado: {groq_error}"
        return result

    if groq_error:
        raise DeepSeekError(groq_error)
    raise DeepSeekError("Nenhum planner configurado. Defina GROQ_API_KEY para gerar tasks com Groq.")
