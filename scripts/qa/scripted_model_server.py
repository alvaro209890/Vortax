"""Modelo roteirizado para QA local do Vortax (FIXTURE — não é um modelo de IA).

Serve /v1/chat/completions no formato OpenAI. Só decide QUAIS ferramentas chamar,
seguindo roteiros fixos por cenário. O backend real executa cada ferramenta:
arquivos são gravados no workspace, comandos rodam no shell, páginas são lidas por
HTTP e o Chrome navega de verdade. Assim a interface recebe eventos, saídas e capturas
reais sem depender de chave de provedor.

Uso:
    python scripts/qa/scripted_model_server.py --port 8799 --site http://192.0.2.2:8765
    DEEPSEEK_API_KEY=qa DEEPSEEK_BASE_URL=http://127.0.0.1:8799/v1 <backend>

Cenários (pela última mensagem do usuário):
    "site"       → cria index.html/style.css/script.js, edita, valida, captura o preview
    "api"        → script Python + testes; primeira execução falha, corrige, passa
    "pesquis"    → busca (falha sem rede pública), leituras HTTP locais e síntese
    "naveg"      → Chrome: navegar, clicar, digitar, rolar, página protegida, voltar
    "longo"      → comando demorado com saída contínua (para interromper)
    "continu"    → retomada curta depois da interrupção
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DELAY = float(os.environ.get("QA_MODEL_DELAY", "1.1"))
SITE = "http://192.0.2.2:8765"

INDEX_HTML = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Ateliê Lume — Portfólio</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header class="topo">
    <strong class="marca">Ateliê Lume</strong>
    <nav><a href="#trabalhos">Trabalhos</a><a href="#contato">Contato</a></nav>
  </header>
  <main>
    <section class="hero">
      <h1>Design de interfaces</h1>
      <p>Projetos digitais com foco em clareza e acessibilidade.</p>
      <button id="tema" type="button">Alternar tema</button>
    </section>
    <section id="trabalhos" class="grade">
      <article><h2>Painel financeiro</h2><p>Dashboard responsivo para pequenas empresas.</p></article>
      <article><h2>App de leitura</h2><p>Leitor com modo noturno e marcações.</p></article>
      <article><h2>Loja local</h2><p>Catálogo com checkout simplificado.</p></article>
    </section>
    <section id="contato" class="contato">
      <h2>Contato</h2>
      <p>Escreva para contato@exemplo.com.br</p>
    </section>
  </main>
  <script src="script.js"></script>
</body>
</html>
"""

STYLE_CSS = """:root { --verde: #08c65d; --fundo: #f7f8f7; --texto: #1f2422; }
body.escuro { --fundo: #0e1113; --texto: #ecefec; }
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, sans-serif; background: var(--fundo); color: var(--texto); }
.topo { display: flex; justify-content: space-between; align-items: center; padding: 18px 6vw; }
.topo nav a { margin-left: 18px; color: inherit; text-decoration: none; }
.marca { font-size: 20px; }
.hero { padding: 72px 6vw 48px; }
.hero h1 { font-size: clamp(32px, 6vw, 56px); margin: 0 0 12px; }
.hero button { margin-top: 18px; padding: 10px 16px; border: 0; border-radius: 10px; background: var(--verde); color: #04140a; font-weight: 600; }
.grade { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; padding: 0 6vw 48px; }
.grade article { padding: 18px; border-radius: 14px; background: rgb(0 0 0 / 0.05); }
.contato { padding: 0 6vw 64px; }
"""

SCRIPT_JS = """const botao = document.getElementById("tema");
botao.addEventListener("click", () => {
  document.body.classList.toggle("escuro");
  botao.textContent = document.body.classList.contains("escuro") ? "Tema claro" : "Alternar tema";
});
"""

API_PY = '''"""API mínima de tarefas em memória."""


class TarefaInvalida(ValueError):
    pass


class Tarefas:
    def __init__(self):
        self._itens = {}
        self._proximo = 1

    def criar(self, titulo):
        titulo = str(titulo or "").strip()
        if not titulo:
            raise TarefaInvalida("título obrigatório")
        tarefa = {"id": self._proximo, "titulo": titulo, "feita": False}
        self._itens[tarefa["id"]] = tarefa
        self._proximo += 1
        return tarefa

    def concluir(self, tarefa_id):
        tarefa = self._itens.get(tarefa_id)
        tarefa["feita"] = True
        return tarefa

    def listar(self):
        return list(self._itens.values())
'''

TEST_PY = '''import unittest

from tarefas import TarefaInvalida, Tarefas


class TarefasTests(unittest.TestCase):
    def test_cria_e_lista(self):
        api = Tarefas()
        api.criar("Escrever relatório")
        self.assertEqual(len(api.listar()), 1)

    def test_titulo_obrigatorio(self):
        with self.assertRaises(TarefaInvalida):
            Tarefas().criar("   ")

    def test_concluir_inexistente(self):
        with self.assertRaises(TarefaInvalida):
            Tarefas().concluir(99)


if __name__ == "__main__":
    unittest.main()
'''


def plan(*items: tuple[str, str]) -> dict:
    return {"todos": [{"label": label, "status": status} for label, status in items]}


def scripts(site: str) -> dict[str, list[list[tuple[str, dict]]]]:
    return {
        "site": [
            [("todo_write", plan(("Criar a estrutura HTML", "in_progress"), ("Aplicar o estilo", "pending"), ("Adicionar interação", "pending"), ("Validar e revisar o preview", "pending")))],
            [("file_write", {"path": "index.html", "content": INDEX_HTML})],
            [("todo_write", plan(("Criar a estrutura HTML", "completed"), ("Aplicar o estilo", "in_progress"), ("Adicionar interação", "pending"), ("Validar e revisar o preview", "pending")))],
            [("file_write", {"path": "style.css", "content": STYLE_CSS})],
            [("todo_write", plan(("Criar a estrutura HTML", "completed"), ("Aplicar o estilo", "completed"), ("Adicionar interação", "in_progress"), ("Validar e revisar o preview", "pending")))],
            [("file_write", {"path": "script.js", "content": SCRIPT_JS})],
            [("file_read", {"path": "index.html"})],
            [("file_edit", {"path": "index.html", "old_string": "<h1>Design de interfaces</h1>", "new_string": "<h1>Design de interfaces claras</h1>"})],
            [("todo_write", plan(("Criar a estrutura HTML", "completed"), ("Aplicar o estilo", "completed"), ("Adicionar interação", "completed"), ("Validar e revisar o preview", "in_progress")))],
            [("validate_project", {})],
            [("shell_run", {"command": "ls -la"})],
            [("browser_screenshot", {})],
        ],
        "api": [
            [("todo_write", plan(("Implementar o módulo de tarefas", "in_progress"), ("Escrever testes", "pending"), ("Executar e corrigir", "pending")))],
            [("file_write", {"path": "tarefas.py", "content": API_PY})],
            [("file_write", {"path": "test_tarefas.py", "content": TEST_PY})],
            [("todo_write", plan(("Implementar o módulo de tarefas", "completed"), ("Escrever testes", "completed"), ("Executar e corrigir", "in_progress")))],
            [("shell_run", {"command": "python3 -m unittest -v"})],
            [("file_read", {"path": "tarefas.py"})],
            [("file_edit", {"path": "tarefas.py", "old_string": "        tarefa = self._itens.get(tarefa_id)\n", "new_string": "        tarefa = self._itens.get(tarefa_id)\n        if tarefa is None:\n            raise TarefaInvalida(f\"tarefa {tarefa_id} não existe\")\n"})],
            [("shell_run", {"command": "python3 -m unittest -v"})],
            [("validate_project", {})],
        ],
        "pesquis": [
            [("web_search", {"query": "boas práticas de interfaces de agentes"})],
            [("web_fetch", {"url": f"{site}/artigos/estados.html"}), ("web_fetch", {"url": f"{site}/artigos/transparencia.html"})],
            [("browser_navigate", {"url": f"{site}/artigos/estados.html"})],
            [("browser_scroll", {"direction": "down", "amount": 600})],
        ],
        "naveg": [
            [("browser_navigate", {"url": f"{site}/"})],
            [("browser_click_text", {"text": "Contato"})],
            [("browser_type", {"text": "Maria", "selector": "#nome"})],
            [("browser_scroll", {"direction": "down", "amount": 500})],
            [("browser_click_text", {"text": "Área do cliente"})],
            [("browser_go_back", {})],
        ],
        "longo": [
            [("shell_run", {"command": "python3 -c \"import time\nfor i in range(1, 41):\n    print(f'processando lote {i}/40', flush=True)\n    time.sleep(1)\""})],
        ],
        "continu": [
            [("shell_run", {"command": "python3 -c \"print('retomando: 3 lotes restantes'); print('lote 38/40'); print('lote 39/40'); print('lote 40/40')\""})],
        ],
    }


FINAL = {
    "site": "Criei o site com `index.html`, `style.css` e `script.js` e ajustei o título principal.",
    "api": "Implementei `tarefas.py` com testes em `test_tarefas.py`. A primeira execução encontrou uma falha em `concluir`; corrigi e os testes passaram.",
    "pesquis": "Síntese baseada nas páginas lidas:\n\n- Estados explícitos por etapa reduzem dúvidas ([estados]({site}/artigos/estados.html)).\n- Mostrar fontes e ações executadas aumenta a confiança ([transparência]({site}/artigos/transparencia.html)).\n\nA busca na web pública não respondeu neste ambiente; usei somente as páginas lidas.",
    "naveg": "Abri o site, entrei em Contato, preenchi o nome e rolei a página. A área do cliente pede senha, então a tela foi ocultada e voltei à página anterior.",
    "longo": "Processamento concluído: 40 lotes.",
    "continu": "Retomei o processamento e concluí os lotes restantes.",
}


def scenario_for(text: str) -> str:
    lowered = text.lower()
    for key in ("continu", "longo", "naveg", "pesquis", "api", "site"):
        if key in lowered:
            return key
    return "site"


def last_user_text(messages: list[dict]) -> tuple[str, int]:
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.get("role") == "user" and "Observações reais" not in str(message.get("content") or ""):
            return str(message.get("content") or ""), index
    return "", -1


def decide(body: dict, site: str) -> dict:
    messages = body.get("messages") or []
    system = " ".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")
    user_text, user_index = last_user_text(messages)
    scenario = scenario_for(user_text)

    if body.get("response_format", {}).get("type") == "json_object":
        steps = {
            "site": ["Criar arquivos do site", "Validar o preview"],
            "api": ["Implementar o módulo", "Executar os testes"],
            "pesquis": ["Pesquisar fontes", "Sintetizar"],
        }.get(scenario, ["Executar a tarefa", "Entregar o resultado"])
        return {"content": json.dumps({"plan": [{"label": s, "detail": "", "tool_hint": "execute"} for s in steps]})}

    if not body.get("tools"):
        if re.search(r"t[íi]tulo|title", system, re.IGNORECASE):
            return {"content": {"site": "Site de portfólio", "api": "API de tarefas", "pesquis": "Pesquisa sobre agentes", "naveg": "Navegação no site local"}.get(scenario, "Tarefa de QA")}
        return {"content": FINAL[scenario].replace("{site}", site)}

    rounds = sum(1 for m in messages[user_index + 1:] if m.get("role") == "assistant" and m.get("tool_calls"))
    plan_rounds = scripts(site)[scenario]
    if rounds >= len(plan_rounds):
        return {"content": FINAL[scenario].replace("{site}", site)}
    calls = [
        {"id": f"call_{uuid.uuid4().hex[:10]}", "type": "function", "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}
        for name, args in plan_rounds[rounds]
    ]
    return {"content": None, "tool_calls": calls}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):  # silencioso
        pass

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        decision = decide(body, self.server.site)
        time.sleep(DELAY)
        message = {"role": "assistant", "content": decision.get("content")}
        if decision.get("tool_calls"):
            message["tool_calls"] = decision["tool_calls"]
        finish = "tool_calls" if decision.get("tool_calls") else "stop"
        if body.get("stream"):
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.end_headers()
            delta: dict = {}
            if message["content"]:
                for piece in re.findall(r".{1,24}", message["content"], re.S):
                    self._sse({"choices": [{"index": 0, "delta": {"content": piece}}]})
                    time.sleep(0.03)
            for index, call in enumerate(decision.get("tool_calls") or []):
                delta = {"tool_calls": [{"index": index, "id": call["id"], "function": call["function"]}]}
                self._sse({"choices": [{"index": 0, "delta": delta}]})
            self._sse({"choices": [{"index": 0, "delta": {}, "finish_reason": finish}]})
            self.wfile.write(b"data: [DONE]\n\n")
            return
        payload = {"id": "qa", "model": "qa-scripted", "choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": {}}
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _sse(self, chunk: dict) -> None:
        self.wfile.write(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode())
        self.wfile.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8799)
    parser.add_argument("--site", default=SITE)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.site = args.site.rstrip("/")
    print(f"modelo roteirizado em http://127.0.0.1:{args.port}/v1 (site {server.site})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
