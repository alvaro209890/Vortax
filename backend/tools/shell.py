import asyncio
import os
import re
import signal
import subprocess
from pathlib import Path
from typing import Any

from config import settings

# ── Dev server registry (processos em background) ──────────────────────────
# task_id -> {"process": Popen, "port": int, "url": str, "cwd": str}
_dev_servers: dict[str, dict[str, Any]] = {}


SHELL_WHITELIST = {
    "python3", "python", "pip3", "pip",
    "node", "npm", "npx",
    "echo", "pwd", "ls", "cat", "mkdir", "cp", "mv", "touch",
    "curl", "wget", "git", "pandoc", "ffmpeg", "libreoffice", "convert",
    "grep", "find", "wc", "head", "tail", "sort", "uniq", "awk", "sed", "cut", "tr",
    "df", "free", "uname",
    # Vertex CLI
    "vertex",
    # Node.js ecosystem (vertex depende disso)
    "which", "whereis", "dirname", "basename", "readlink",
    # Gerenciamento de arquivos na workspace
    "rm", "rmdir",
    # Utilitarios adicionais
    "clear", "date", "tee", "xargs", "true", "false",
}

BLOCKED_PATTERNS = [
    r"\bsudo\b",
    r"\bsu\b",
    r"\bchmod\b",
    r"\bchown\b",
    r"\bpasswd\b",
    r"\bsystemctl\b",
    r"\bservice\b",
    r"\bkill\b",
    r"\bpkill\b",
    r"\bkillall\b",
    r"\bdd\b.*if=",
    r"\bmkfs\b",
    r"\bfdisk\b",
    r"\bformat\b",
    r"rm\s+-rf\s+/",
    r"rm\s+-rf\s+~",
    r"rm\s+-rf\s+\$HOME",
    r">\s*/dev/",
    r"curl\s+.*\|\s*(ba)?sh",
    r"curl\s+.*\|\s*bash",
    r"wget\s+.*\|\s*(ba)?sh",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\binit\s+[0-6]\b",
    r">\s*/etc/",
    r"mkfs\.",
    r"\bscp\b",
    r"\brsync\b.*root",
]

BLOCKED_RM_PATTERN = re.compile(r"\brm\b")

# ── Vertex CLI progress patterns ───────────────────────────────────────────
# O Vertex emite linhas como:
#   "Planejando a tarefa..."
#   "Criando arquivo src/index.html"
#   "Instalando dependências..."
#   "Executando testes..."
#   "Tarefa concluída"

VERTEX_PROGRESS_PATTERNS = [
    (re.compile(r"\b(planejando|analisando|entendendo|lendo|mapeando|investigando)\b", re.IGNORECASE), "planning"),
    (re.compile(r"\b(criando|escrevendo|gerando)\s+(o\s+)?(arquivo|ficheiro|file)\b", re.IGNORECASE), "writing_file"),
    (re.compile(r"\b(criando|escrevendo|gerando)\b", re.IGNORECASE), "creating"),
    (re.compile(r"\b(instalando|baixando|download(ing)?)\b", re.IGNORECASE), "installing"),
    (re.compile(r"\b(executando|rodando|running|testando|compilando|buildando)\b", re.IGNORECASE), "executing"),
    (re.compile(r"\b(editando|modificando|alterando|atualizando)\b", re.IGNORECASE), "editing"),
    (re.compile(r"\b(conclu[ií]d[ao]|finalizad[ao]|pronto|completo|done|finished)\b", re.IGNORECASE), "done"),
    (re.compile(r"\b(lendo|extraindo|parseando|parse|analisando)\s+(o\s+)?(arquivo|ficheiro|file)\b", re.IGNORECASE), "reading_file"),
    (re.compile(r"\b(configurando|configuring|ajustando)\b", re.IGNORECASE), "configuring"),
    (re.compile(r"\b(verificando|validando|checando|chequeando)\b", re.IGNORECASE), "validating"),
]

# ── Interactive prompt detection ────────────────────────────────────────────
# Detecta quando um comando faz uma pergunta que precisa de resposta.
# Exemplos: "Qual framework quer usar?", "Continue? [y/N]", "Digite o nome:"

INTERACTIVE_PROMPT_PATTERNS = [
    # Perguntas explícitas
    re.compile(r"(?:qual|quais|qual\s+e|que)\s+\w+.*\?(?:\s|$)", re.IGNORECASE),
    re.compile(r"\w+.*\?\s*$", re.IGNORECASE),
    # Prompts de confirmação
    re.compile(r"(?:continue|continuar|confirmar|confirm)\s*\?\s*(?:\[.*?\])?\s*$", re.IGNORECASE),
    re.compile(r"\[(?:y|n|s|yes|no|sim|n[aã]o)\/(?:y|n|s|yes|no|sim|n[aã]o)\]\s*$", re.IGNORECASE),
    re.compile(r"\[(?:y|n|s|yes|no|sim|n[aã]o)\]\s*$", re.IGNORECASE),
    # Input requests
    re.compile(r"(?:digite|insira|informe|escreva|escolha|selecione|pressione|aperte)\s+\w+", re.IGNORECASE),
    re.compile(r"(?:enter|type)\s+\w+.*(?:to\s+continue|to\s+proceed)", re.IGNORECASE),
    # Authorization / permission requests
    re.compile(r"(?:preciso\s+de\s+autoriza[cç][aã]o|voc[eê]\s+pode\s+aprovar|autoriza[cç][aã]o\s+para)", re.IGNORECASE),
    re.compile(r"(?:permiss[aã]o\s+negada|permission\s+denied|n[aã]o\s+tem\s+permiss[aã]o)", re.IGNORECASE),
    # Choices
    re.compile(r"escolha\s+(?:uma|a)\s+op[cç][aã]o", re.IGNORECASE),
    re.compile(r"selecione\s+(?:uma|a)\s+op[cç][aã]o", re.IGNORECASE),
    # General prompts ending with :
    re.compile(r"(?:nome|name|path|caminho|dir|directory|port|porta|user|usu[aá]rio)\s*:\s*$", re.IGNORECASE),
]


# ── Dev server detection ────────────────────────────────────────────────────
# Detecta comandos que iniciam servidores de desenvolvimento:
#   npm run dev, npx vite, npx serve, python -m http.server, etc.

DEV_SERVER_PATTERNS = [
    re.compile(r"\b(npm\s+run\s+dev|npm\s+run\s+start|npm\s+start)\b", re.IGNORECASE),
    re.compile(r"\b(npx\s+vite|npx\s+serve|npx\s+http-server|npx\s+live-server)\b", re.IGNORECASE),
    re.compile(r"\b(python3?\s+-m\s+http\.server)\b", re.IGNORECASE),
    re.compile(r"\b(node\s+\S+\.(js|mjs|cjs))\b", re.IGNORECASE),
    re.compile(r"\b(yarn\s+dev|yarn\s+start|pnpm\s+dev|pnpm\s+start)\b", re.IGNORECASE),
    re.compile(r"\b(php\s+-S\s+\S+)\b", re.IGNORECASE),
]

# Portas detectadas no stdout: "localhost:5173", "0.0.0.0:3000", "http://127.0.0.1:8080"
PORT_DETECTION_PATTERNS = [
    re.compile(r"(?:localhost|127\.0\.0\.1|0\.0\.0\.0):(\d{4,5})", re.IGNORECASE),
    re.compile(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0):(\d{4,5})", re.IGNORECASE),
    re.compile(r"port\s*(\d{4,5})", re.IGNORECASE),
    re.compile(r"listening\s+on\s+.*?:(\d{4,5})", re.IGNORECASE),
]


def _is_dev_server_command(command: str) -> bool:
    """Detecta se o comando inicia um servidor de desenvolvimento."""
    for pattern in DEV_SERVER_PATTERNS:
        if pattern.search(command):
            return True
    return False


def _extract_port_from_output(output: str) -> int | None:
    """Tenta extrair a porta do servidor da saida stdout/stderr."""
    for pattern in PORT_DETECTION_PATTERNS:
        match = pattern.search(output)
        if match:
            port = int(match.group(1))
            if 1024 <= port <= 65535:
                return port
    return None


def _build_file_summary(cwd: Path) -> dict[str, Any]:
    """Gera um resumo estruturado dos arquivos no diretorio do projeto."""
    files = []
    total_size = 0
    try:
        for entry in sorted(cwd.rglob("*")):
            if entry.is_file() and not entry.name.startswith(".") and entry.name != ".gitkeep":
                rel = str(entry.relative_to(cwd))
                size = entry.stat().st_size
                total_size += size
                ext = entry.suffix.lower()
                files.append({"path": rel, "size": size, "ext": ext})
    except OSError:
        pass

    if not files:
        return {"file_count": 0, "total_size": 0, "files": []}

    # Agrupa por extensao
    by_ext: dict[str, int] = {}
    for f in files:
        ext = f["ext"] or "sem_extensao"
        by_ext[ext] = by_ext.get(ext, 0) + 1

    # Detecta tipo de projeto
    extensions = {f["ext"] for f in files}
    project_type = "generic"
    if ".html" in extensions:
        project_type = "static_web"
    if {".jsx", ".tsx"} & extensions or {".js", ".ts"} & extensions and "package.json" in {f["path"] for f in files}:
        project_type = "react_app"
    elif ".vue" in extensions:
        project_type = "vue_app"
    elif ".py" in extensions:
        project_type = "python"
    elif ".rs" in extensions:
        project_type = "rust"

    # Arquivos principais (root ou src/)
    root_files = [f for f in files if "/" not in f["path"]][:15]
    top_dirs = list({f["path"].split("/")[0] for f in files if "/" in f["path"]})[:10]

    return {
        "file_count": len(files),
        "total_size": total_size,
        "project_type": project_type,
        "by_extension": by_ext,
        "root_files": [f["path"] for f in root_files],
        "top_dirs": top_dirs,
        "has_index_html": any(f["path"] == "index.html" or f["path"].endswith("/index.html") for f in files),
        "has_package_json": any(f["path"] == "package.json" for f in files),
    }


def _shell_error(message: str) -> dict[str, Any]:
    return {
        "success": False,
        "stdout": "",
        "stderr": message,
        "returncode": -1,
    }


def _extract_command(cmd: str) -> str:
    """Extrai o primeiro comando de uma string (o que está antes do primeiro espaço)."""
    cmd = cmd.strip()
    for prefix in ("cd workspace && ", "cd ./workspace && ", "cd /workspace && "):
        if cmd.startswith(prefix):
            cmd = cmd[len(prefix):]
    return cmd.split()[0] if cmd.split() else ""


def _is_whitelisted(executable: str) -> bool:
    return executable in SHELL_WHITELIST


def _has_blocked_patterns(command: str) -> str | None:
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, command):
            return f"Comando bloqueado por seguranca (padrao perigoso): {pattern}"
    return None


def _shell_timeout(command: str) -> float:
    if "vertex" in command:
        return float(getattr(settings, "SHELL_VERTEX_TIMEOUT_SECONDS", 300) or 300)
    return float(getattr(settings, "SHELL_TIMEOUT_SECONDS", 30) or 30)


def _project_dir(task_id: str | None) -> Path:
    """Retorna o diretório do projeto dentro da workspace para um task_id."""
    if task_id:
        project = settings.WORKSPACE_PATH / task_id
    else:
        project = settings.WORKSPACE_PATH
    project.mkdir(parents=True, exist_ok=True)
    return project


async def _list_files(cwd: Path) -> list[dict[str, Any]]:
    """Lista arquivos no diretório para o evento files_created."""
    files = []
    try:
        for entry in sorted(cwd.rglob("*")):
            if entry.is_file() and not entry.name.startswith("."):
                rel = str(entry.relative_to(cwd))
                size = entry.stat().st_size
                files.append({"path": rel, "size": size})
    except OSError:
        pass
    return files[:100]


def _parse_vertex_progress(line: str) -> dict[str, Any] | None:
    """Tenta extrair progresso estruturado de uma linha de stdout do Vertex CLI."""
    stripped = line.strip()
    if not stripped:
        return None

    for pattern, stage in VERTEX_PROGRESS_PATTERNS:
        if pattern.search(stripped):
            # Tenta extrair nome de arquivo se for writing_file/reading_file
            file_name = None
            if stage in ("writing_file", "reading_file", "creating"):
                file_match = re.search(
                    r"(?:arquivo|ficheiro|file)\s+[\"']?([^\s\"']+)[\"']?",
                    stripped,
                    re.IGNORECASE,
                )
                if file_match:
                    file_name = file_match.group(1)

            return {
                "stage": stage,
                "message": stripped[:200],
                "file": file_name,
            }
    return None


def _detect_interactive_prompt(text: str) -> bool:
    """Detecta se o texto contém um prompt interativo que precisa de resposta."""
    if not text or not text.strip():
        return False

    # Verifica as últimas linhas (onde prompts geralmente aparecem)
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return False

    # Foca nas últimas 5 linhas
    recent = lines[-5:]
    for line in recent:
        for pattern in INTERACTIVE_PROMPT_PATTERNS:
            if pattern.search(line):
                return True

    # Também verifica o texto completo para perguntas com "?"
    if len(lines) <= 3 and any("?" in line for line in lines):
        return True

    return False


async def _ask_deepseek_for_response(
    prompt_text: str,
    original_command: str,
    task_id: str,
    bus: Any,
) -> str | None:
    """Pede ao DeepSeek para responder a um prompt interativo do shell."""
    from services.deepseek_client import _post_deepseek

    system_prompt = (
        "Voce e o Vortax respondendo a um prompt interativo de um comando shell. "
        "O comando original foi executado e agora esta pedindo uma resposta. "
        "Responda APENAS com o texto que deve ser enviado ao processo - nada mais. "
        "Nao use markdown, nao explique, nao use aspas. "
        "Seja direto e conciso. Se for uma pergunta de sim/nao, responda 'y' ou 'n'. "
        "Se for uma escolha, responda apenas a opcao escolhida."
    )
    user_prompt = (
        f"Comando original: {original_command}\n\n"
        f"Prompt do shell que precisa de resposta:\n{prompt_text}\n\n"
        f"Resposta (apenas o texto a enviar):"
    )

    try:
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
        content = data["choices"][0]["message"]["content"].strip()
        # Remove aspas, markdown, prefixos
        content = re.sub(r"^[\"']|[\"']$", "", content)
        content = re.sub(r"^```[\s\S]*?```$", "", content)
        if bus and task_id:
            await bus.publish(
                task_id,
                "shell_stdout",
                {"line": f"[Vortax auto-resposta: {content}]"},
            )
        return content[:500]
    except Exception:
        return None


async def run_shell(
    command: str,
    task_id: str | None = None,
    bus: Any = None,
    *,
    max_interactive_rounds: int = 3,
) -> dict[str, Any]:
    """Executa um comando shell seguro com streaming, progresso e follow-up interativo.

    Fluxo:
    1. Validação de segurança (whitelist, blocked patterns, rm restriction)
    2. Execução com Popen + streaming stdout/stderr via EventBus
    3. Parse de progresso do Vertex CLI → eventos vertex_progress
    4. Detecção de prompts interativos → consulta DeepSeek para auto-resposta
    5. Listagem de arquivos criados
    """
    cmd = str(command).strip()
    if not cmd:
        return _shell_error("Comando vazio.")

    executable = _extract_command(cmd)
    if not executable:
        return _shell_error(f"Nao foi possivel identificar o comando em: {cmd}")

    if not _is_whitelisted(executable):
        return _shell_error(
            f"Comando '{executable}' nao esta na whitelist do Vortax. "
            "Se precisar instalar algo, peca ao usuario que instale manualmente."
        )

    blocked = _has_blocked_patterns(cmd)
    if blocked:
        return _shell_error(blocked)

    is_rm = BLOCKED_RM_PATTERN.search(cmd)
    if is_rm:
        workspace_str = str(settings.WORKSPACE_PATH.resolve())
        if workspace_str not in cmd:
            return _shell_error(
                "rm so e permitido dentro da workspace. "
                f"Use caminhos dentro de {workspace_str}"
            )

    cwd = str(_project_dir(task_id))
    cwd_path = _project_dir(task_id)
    is_vertex = "vertex" in executable
    is_dev_server = _is_dev_server_command(cmd)

    env = os.environ.copy()
    if is_vertex:
        env["VERTEX_OUTPUT_DIR"] = cwd
    # Para dev servers, adiciona CI=true e FORCE_COLOR=0 para evitar prompts
    if is_dev_server:
        env["CI"] = "true"
        env["FORCE_COLOR"] = "0"
        env["BROWSER"] = "none"  # Evita abrir navegador automatico (create-react-app etc)

    timeout = _shell_timeout(cmd)
    try:
        process = subprocess.Popen(
            cmd,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            text=True,
            env=env,
            # Dev servers: grupo de processo proprio para cleanup
            preexec_fn=os.setsid if is_dev_server else None,
        )
    except OSError as exc:
        return _shell_error(f"Erro ao executar comando: {exc}")

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    interactive_rounds = 0
    detected_port: int | None = None

    async def _publish_line(line: str, event_type: str) -> None:
        nonlocal detected_port
        stripped = line.rstrip("\n\r")
        if not stripped:
            return
        if not bus or not task_id:
            return
        await bus.publish(task_id, event_type, {"line": stripped})

        # Detecta porta do dev server
        if is_dev_server and detected_port is None and event_type == "shell_stdout":
            detected_port = _extract_port_from_output(stripped)

        # Parse de progresso (funciona para qualquer comando, mas os labels são otimizados para Vertex)
        if event_type == "shell_stdout":
            progress = _parse_vertex_progress(stripped)
            if progress:
                await bus.publish(task_id, "vertex_progress", progress)

    async def _drain_and_interact(stream, lines_list: list[str], event_type: str) -> None:
        """Le um stream com detecção de prompts interativos e auto-resposta."""
        nonlocal interactive_rounds
        loop = asyncio.get_event_loop()

        accumulated = ""
        while True:
            try:
                line = await asyncio.wait_for(
                    loop.run_in_executor(None, stream.readline),
                    timeout=0.3,
                )
            except asyncio.TimeoutError:
                # Verifica se o processo ainda está rodando e pode estar esperando input
                if process.poll() is None and event_type == "stdout":
                    # Se acumulou texto mas não tem newline e o processo está parado,
                    # pode ser um prompt esperando resposta
                    pass
                continue

            if not line:
                break

            lines_list.append(line)
            await _publish_line(line, event_type)

            # Acumula linhas recentes para detecção de prompt
            if event_type == "shell_stdout":
                accumulated += line
                # Mantém só as últimas linhas
                acc_lines = accumulated.split("\n")
                if len(acc_lines) > 10:
                    accumulated = "\n".join(acc_lines[-10:])

                if interactive_rounds < max_interactive_rounds and _detect_interactive_prompt(accumulated):
                    interactive_rounds += 1
                    prompt_snapshot = "\n".join(acc_lines[-5:])

                    if bus and task_id:
                        await bus.publish(
                            task_id,
                            "shell_interactive_prompt",
                            {"prompt": prompt_snapshot[:500], "round": interactive_rounds},
                        )

                    response = await _ask_deepseek_for_response(
                        prompt_snapshot,
                        cmd,
                        task_id,
                        bus,
                    )

                    if response and process.poll() is None:
                        try:
                            await asyncio.wait_for(
                                loop.run_in_executor(None, process.stdin.write, response + "\n"),
                                timeout=2.0,
                            )
                            await asyncio.wait_for(
                                loop.run_in_executor(None, process.stdin.flush),
                                timeout=2.0,
                            )
                            accumulated = ""  # Reset após resposta
                        except Exception:
                            break
                    else:
                        break  # Processo terminou ou não conseguiu responder

    # ── Dev server: drena por um periodo curto e depois deixa em background ──
    if is_dev_server and bus and task_id:
        # Drena os primeiros segundos para detectar porta e erros de inicializacao
        drain_task = asyncio.gather(
            _drain_and_interact(process.stdout, stdout_lines, "shell_stdout"),
            _drain_and_interact(process.stderr, stderr_lines, "shell_stderr"),
        )
        try:
            await asyncio.wait_for(drain_task, timeout=12.0)
        except asyncio.TimeoutError:
            pass  # Esperado — dev server continua rodando

        # Se o processo ja morreu, foi erro
        if process.poll() is not None:
            returncode = process.returncode or -1
            stderr_text = "".join(stderr_lines)[:1000]
            return {
                "success": False,
                "stdout": "".join(stdout_lines)[:2000],
                "stderr": stderr_text,
                "returncode": returncode,
                "is_dev_server": True,
                "dev_server_failed": True,
            }

        # Dev server esta rodando — registra no registry
        if not detected_port:
            detected_port = _extract_port_from_output("".join(stdout_lines + stderr_lines))

        # Se ainda nao detectou porta, tenta inferir do comando
        if not detected_port:
            # Portas padrao
            if "vite" in cmd:
                detected_port = 5173
            elif "react" in cmd or "create-react-app" in cmd:
                detected_port = 3000
            elif "serve" in cmd:
                detected_port = 5000
            elif "python" in cmd and "http.server" in cmd:
                port_match = re.search(r"http\.server\s+(\d+)", cmd)
                detected_port = int(port_match.group(1)) if port_match else 8000
            elif "next" in cmd:
                detected_port = 3000
            elif "nuxt" in cmd:
                detected_port = 3000

        dev_url = f"http://localhost:{detected_port}"

        # Registra o servidor
        _dev_servers[task_id] = {
            "process": process,
            "port": detected_port,
            "url": dev_url,
            "cwd": cwd,
            "command": cmd,
        }

        stdout_text = "".join(stdout_lines)[:3000]
        stderr_text = "".join(stderr_lines)[:500]

        await bus.publish(
            task_id,
            "dev_server_started",
            {
                "url": dev_url,
                "port": detected_port,
                "task_id": task_id,
            },
        )

        # Resumo de arquivos
        file_summary = _build_file_summary(cwd_path)

        return {
            "success": True,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "returncode": 0,
            "is_dev_server": True,
            "dev_server_url": dev_url,
            "dev_server_port": detected_port,
            "file_summary": file_summary,
        }

    # ── Comando normal (nao dev server) ────────────────────────────────────
    async def _drain_with_timeout() -> None:
        """Drena ambos os streams com timeout global."""
        drain_task = asyncio.gather(
            _drain_and_interact(process.stdout, stdout_lines, "shell_stdout"),
            _drain_and_interact(process.stderr, stderr_lines, "shell_stderr"),
        )
        try:
            await asyncio.wait_for(drain_task, timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()

    await _drain_with_timeout()

    # Garante que o processo terminou
    loop = asyncio.get_event_loop()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(None, process.wait),
            timeout=5.0,
        )
    except asyncio.TimeoutError:
        process.kill()
        await loop.run_in_executor(None, process.wait)

    returncode = process.returncode if process.returncode is not None else -1
    stdout_full = "".join(stdout_lines)
    stderr_full = "".join(stderr_lines)
    stdout_truncated = len(stdout_full) > 3000
    stderr_truncated = len(stderr_full) > 500
    stdout = stdout_full[:3000]
    stderr = stderr_full[:500]

    # Resumo de arquivos pos-execucao
    file_summary = _build_file_summary(cwd_path)

    result = {
        "success": returncode == 0,
        "stdout": stdout,
        "stderr": stderr,
        "returncode": returncode,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "file_summary": file_summary,
    }
    if interactive_rounds > 0:
        result["interactive_rounds"] = interactive_rounds

    return result


async def run_vertex(task_description: str, task_id: str | None = None) -> dict[str, Any]:
    """Executa o Vertex CLI com uma descricao de tarefa de desenvolvimento."""
    safe_desc = str(task_description).replace("'", "'\\''")[:500]
    cmd = f"vertex '{safe_desc}'"
    return await run_shell(cmd, task_id=task_id)


def get_dev_server(task_id: str) -> dict[str, Any] | None:
    """Retorna informacoes do dev server em background para um task_id."""
    server = _dev_servers.get(task_id)
    if not server:
        return None
    process = server["process"]
    if process.poll() is not None:
        # Processo morreu — cleanup
        _dev_servers.pop(task_id, None)
        return None
    return {
        "url": server["url"],
        "port": server["port"],
        "cwd": server["cwd"],
        "command": server["command"],
        "running": True,
    }


async def stop_dev_server(task_id: str) -> bool:
    """Para o dev server em background de um task_id."""
    server = _dev_servers.pop(task_id, None)
    if not server:
        return False
    process = server["process"]
    try:
        # Tenta matar o grupo de processo (preexec_fn=os.setsid)
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (ProcessLookupError, OSError):
        pass
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass
        process.wait()
    return True
