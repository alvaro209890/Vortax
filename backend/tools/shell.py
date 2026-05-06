import asyncio
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from config import settings


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
    is_vertex = "vertex" in executable

    env = os.environ.copy()
    if is_vertex:
        env["VERTEX_OUTPUT_DIR"] = cwd

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
        )
    except OSError as exc:
        return _shell_error(f"Erro ao executar comando: {exc}")

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    interactive_rounds = 0

    async def _publish_line(line: str, event_type: str) -> None:
        stripped = line.rstrip("\n\r")
        if not stripped:
            return
        if not bus or not task_id:
            return
        await bus.publish(task_id, event_type, {"line": stripped})

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
    stdout = "".join(stdout_lines)[:3000]
    stderr = "".join(stderr_lines)[:500]

    result = {
        "success": returncode == 0,
        "stdout": stdout,
        "stderr": stderr,
        "returncode": returncode,
    }
    if interactive_rounds > 0:
        result["interactive_rounds"] = interactive_rounds

    return result


async def run_vertex(task_description: str, task_id: str | None = None) -> dict[str, Any]:
    """Executa o Vertex CLI com uma descricao de tarefa de desenvolvimento."""
    safe_desc = str(task_description).replace("'", "'\\''")[:500]
    cmd = f"vertex '{safe_desc}'"
    return await run_shell(cmd, task_id=task_id)
