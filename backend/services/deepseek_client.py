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
        "use": "Executar um comando seguro no terminal Linux deste PC. Comandos permitidos: python3, node, npm, npx, vertex, git, curl, wget, ls, cat, mkdir, cp, mv, grep, find, echo, pwd e outros utilitarios basicos. Para desenvolver software/sites/scripts, use 'vertex \"descricao da tarefa\"'. O comando roda na workspace/ do Vortax. Retorna stdout, stderr e returncode.",
    },
    {
        "action": "vision_analyze",
        "params": {"question": "O que aparece nesta tela?"},
        "use": "Tool de visao computacional. Captura screenshot automaticamente e descreve a tela. Use SOMENTE quando texto extraido nao for suficiente — prefira browser_extract_text ou browser_extract_article para ler textos.",
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
        "Voce e o Vortax, um agente local controlado por chat em rede LAN. "
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


async def request_deepseek_action(history: list[dict[str, str]]) -> dict[str, Any]:
    if not deepseek_configured():
        raise DeepSeekError("DEEPSEEK_API_KEY nao configurada")

    system_prompt = (
        "Voce e o planner JSON do Vortax, um agente local que controla o Chrome deste PC. "
        "Responda sempre com um unico objeto JSON valido, sem markdown e sem texto fora do JSON. "
        "Escolha exatamente uma action por resposta. "
        "Se a tarefa envolver pesquisar, encontrar informacao atual, comparar sites, resumir conteudo da web ou responder algo que dependa da internet, seja proativo: "
        "primeiro use browser_google_search com uma consulta objetiva; depois observe results/links; abra resultados relevantes com browser_click_link_by_index ou browser_navigate; "
        "extraia conteudo da pagina aberta preferencialmente com browser_extract_article; use browser_extract_text se a extracao limpa vier fraca; volte e abra outra fonte quando a resposta exigir comparacao ou confirmacao. "
        "Nunca tente fazer login em contas Google, contas de sites, paywalls ou paginas de autenticacao; se cair em login, use browser_go_back e escolha outro resultado. "
        "Evite resultados de accounts.google.com, ServiceLogin, paginas de preferencia/configuracao do Google, anuncios e links sem conteudo informativo. "
        "Nao finalize uma pesquisa complexa baseado apenas na lista de resultados; abra pelo menos uma fonte relevante e extraia conteudo. "
        "Para pesquisas simples, uma fonte confiavel pode bastar; para temas controversos ou dados que podem variar, consulte duas ou tres fontes. "
        "Se uma ferramenta falhar, tente uma consulta alternativa, outro resultado ou browser_extract_links antes de finalizar com erro. "
        "Use browser_get_state quando estiver incerto sobre a pagina atual. "
        "Depois que as ferramentas retornarem informacao suficiente, use action finish com result claro, direto e com as fontes/URLs visitadas. "
        "Na resposta final, diferencie informacao confirmada em fonte aberta de informacao apenas sugerida por resultado de busca. "
        "Para desenvolvimento de software (sites, scripts, APIs, qualquer codigo), use shell_run com o comando vertex: shell_run command=\"vertex 'descricao completa do software que o usuario quer'\". "
        "O Vertex CLI criara todos os arquivos do projeto dentro da workspace/. Nao tente escrever codigo manualmente — delegue ao Vertex. "
        "Depois que o vertex terminar, use finish e informe ao usuario que os arquivos estao prontos para download. "
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
