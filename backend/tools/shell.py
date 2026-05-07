import asyncio
import errno
import fcntl
import os
import pty
import re
import signal
import shlex
import subprocess
import termios
from pathlib import Path
from typing import Any

from config import settings
from services.project_files import missing_local_asset_refs

# ── Dev server registry (processos em background) ──────────────────────────
# task_id -> {"process": Popen, "port": int, "url": str, "cwd": str}
_dev_servers: dict[str, dict[str, Any]] = {}

DEV_SERVER_PROCESS_RE = re.compile(
    r"\b(npm\s+run\s+dev|npm\s+start|vite|next\s+dev|nuxt\s+dev|react-scripts\s+start|"
    r"http-server|live-server|serve\b|python3?\s+-m\s+http\.server)\b",
    re.IGNORECASE,
)


SHELL_WHITELIST = {
    "python3", "python", "pip3", "pip",
    "node", "npm", "npx",
    "echo", "pwd", "ls", "cat", "mkdir", "cp", "mv", "touch",
    "curl", "wget", "git", "pandoc", "ffmpeg", "libreoffice", "convert",
    "grep", "find", "wc", "head", "tail", "sort", "uniq", "awk", "sed", "cut", "tr",
    "df", "free", "uname",
    # OpenClaude code agent
    "openclaude",
    # Node.js ecosystem (openclaude depende disso)
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

# ── Code agent progress patterns ───────────────────────────────────────────
# O OpenClaude pode emitir linhas como:
#   "Planejando a tarefa..."
#   "Criando arquivo src/index.html"
#   "Instalando dependências..."
#   "Executando testes..."
#   "Tarefa concluída"

CODE_AGENT_PROGRESS_PATTERNS = [
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

CODE_AGENT_SIMULATED_PROGRESS = [
    ("planning", "Analisando o pedido e separando as partes do projeto."),
    ("creating", "Montando a estrutura de pastas e arquivos."),
    ("writing_file", "Escrevendo os arquivos principais da interface."),
    ("editing", "Ajustando estilos, textos e interacoes."),
    ("validating", "Preparando a entrega para revisao final."),
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
LOCAL_URL_PATTERN = re.compile(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0):\d{2,5}(?:/[^\s\"'<>)]*)?", re.IGNORECASE)


def _redact_local_urls(text: str) -> str:
    return LOCAL_URL_PATTERN.sub("preview interno do Vortax", str(text or ""))
OSC_ESCAPE_PATTERN = re.compile(r"\x1B\][^\x07]*(?:\x07|\x1B\\)")
ANSI_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
SPINNER_CHARS = set("◔◐◑◕●○◌⠁⠂⠄⠈⠐⠠⠤⠦⠧⠇⠏⠋⠙⠹⠸⠼⠴⠦⠧⠇")
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
TUI_ARTIFACT_PATTERNS = [
    re.compile(r"^\??forshortcuts", re.IGNORECASE),
    re.compile(r"^esctointerrupt", re.IGNORECASE),
    re.compile(r"vertex-api\.cursar\.space.*painel", re.IGNORECASE),
    re.compile(r"^8;;", re.IGNORECASE),
    re.compile(r"^\d+;.*(?:vertex|openclaude)", re.IGNORECASE),
    re.compile(r"^;?id=", re.IGNORECASE),
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


def _extract_local_urls(output: str) -> list[str]:
    urls = []
    seen = set()
    for match in LOCAL_URL_PATTERN.finditer(output):
        url = match.group(0).rstrip(".,;").replace("://0.0.0.0:", "://127.0.0.1:")
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls[:10]


def _clean_terminal_text(text: str) -> str:
    cleaned = OSC_ESCAPE_PATTERN.sub("", text)
    cleaned = ANSI_ESCAPE_PATTERN.sub("", cleaned)
    cleaned = cleaned.replace("\x00", "").replace("\x07", "")
    return cleaned


def _clean_terminal_line(line: str) -> str:
    cleaned = _clean_terminal_text(line).replace("\xa0", " ")
    cleaned = CONTROL_CHAR_PATTERN.sub("", cleaned)
    cleaned = cleaned.rstrip()
    if any(pattern.search(cleaned.strip()) for pattern in TUI_ARTIFACT_PATTERNS):
        return ""
    return cleaned


def _display_terminal_line(line: str) -> str:
    cleaned = _clean_terminal_line(line)
    if not cleaned.strip():
        return ""
    body = cleaned.lstrip(" ")
    had_spinner = False
    while body and body[0] in SPINNER_CHARS:
        had_spinner = True
        body = body[1:].lstrip(" ")
    if had_spinner:
        return body.rstrip()
    return cleaned


def _is_spinner_noise(line: str) -> bool:
    stripped = _display_terminal_line(line).strip()
    if not stripped:
        return True
    if all((char in SPINNER_CHARS or char.isspace()) for char in stripped):
        return True
    without_spinner = "".join(char for char in stripped if char not in SPINNER_CHARS).strip()
    if not without_spinner:
        return True
    if len(without_spinner) <= 2 and any(char in SPINNER_CHARS for char in line):
        return True
    return False


def _is_duplicate_terminal_line(lines: list[dict[str, str]], line: str) -> bool:
    if not lines:
        return False
    previous = lines[-1].get("line", "")
    if previous == line:
        return True
    status_line = re.compile(r"^(aplicando|pensando|carregando|processando|executando)[. …]*$", re.IGNORECASE)
    return bool(status_line.match(previous) and status_line.match(line))


class _TerminalTextFilter:
    """Remove sequencias ANSI/OSC mesmo quando chegam quebradas em chunks do PTY."""

    def __init__(self) -> None:
        self._pending = ""

    def feed(self, text: str) -> str:
        text = self._pending + text
        self._pending = ""
        output: list[str] = []
        index = 0
        while index < len(text):
            char = text[index]
            if char != "\x1b":
                output.append(char)
                index += 1
                continue

            if index + 1 >= len(text):
                self._pending = text[index:]
                break

            next_char = text[index + 1]
            if next_char == "]":
                bell = text.find("\x07", index + 2)
                st = text.find("\x1b\\", index + 2)
                terminators = [pos for pos in (bell, st) if pos != -1]
                if not terminators:
                    self._pending = text[index:]
                    break
                end = min(terminators)
                index = end + (2 if end == st else 1)
                continue

            if next_char == "[":
                match = re.match(r"\x1B\[[0-?]*[ -/]*[@-~]", text[index:])
                if not match:
                    self._pending = text[index:]
                    break
                index += match.end()
                continue

            index += 2

        cleaned = "".join(output)
        return cleaned.replace("\x00", "").replace("\x07", "")


def _terminal_frame_interval() -> float:
    value = float(getattr(settings, "STREAM_TERMINAL_INTERVAL", 0.75) or 0.75)
    return max(value, 0.35)


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
    cmd = _normalize_shell_command(cmd)
    for prefix in ("cd workspace && ", "cd ./workspace && ", "cd /workspace && "):
        if cmd.startswith(prefix):
            cmd = cmd[len(prefix):]
    cd_match = re.match(r"^cd\s+([A-Za-z0-9_./-]+)\s*&&\s*(.+)$", cmd)
    if cd_match:
        cd_path = Path(cd_match.group(1))
        if not cd_path.is_absolute() and ".." not in cd_path.parts:
            cmd = cd_match.group(2).strip()
    return cmd.split()[0] if cmd.split() else ""


def _normalize_shell_command(cmd: str) -> str:
    """Normaliza wrappers comuns que atrapalham o executor seguro.

    O proprio run_shell mantem dev servers vivos em background. Por isso comandos
    gerados como "nohup npm run dev &" ou "cd app && python -m http.server &"
    devem virar processos foreground registrados pelo Vortax.
    """
    normalized = str(cmd or "").strip()
    if normalized.endswith("&"):
        normalized = normalized[:-1].rstrip()

    cd_match = re.match(r"^(cd\s+[A-Za-z0-9_./-]+\s*&&\s*)nohup\s+(.+)$", normalized)
    if cd_match:
        return cd_match.group(1) + cd_match.group(2).strip()

    if normalized.startswith("nohup "):
        return normalized[len("nohup ") :].strip()

    return normalized


def _is_whitelisted(executable: str) -> bool:
    return executable in SHELL_WHITELIST


def _has_blocked_patterns(command: str) -> str | None:
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, command):
            return f"Comando bloqueado por seguranca (padrao perigoso): {pattern}"
    return None


def _shell_timeout(command: str) -> float:
    if "openclaude" in command:
        return float(
            getattr(settings, "SHELL_CODE_AGENT_TIMEOUT_SECONDS", None)
            or getattr(settings, "SHELL_VERTEX_TIMEOUT_SECONDS", 300)
            or 300
        )
    return float(getattr(settings, "SHELL_TIMEOUT_SECONDS", 30) or 30)


def _is_code_agent_executable(executable: str) -> bool:
    return executable == "openclaude"


def _is_noninteractive_code_agent_command(command: str) -> bool:
    return bool(re.search(r"(^|\s)(-p|--print)(\s|$)", command))


def _project_dir(task_id: str | None) -> Path:
    """Retorna o diretório persistente de projetos para um task_id."""
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


async def _publish_ai_exchange(
    task_id: str | None,
    bus: Any,
    *,
    actor: str,
    target: str,
    message: str,
    kind: str,
) -> None:
    if not bus or not task_id:
        return
    await bus.publish(
        task_id,
        "ai_exchange",
        {
            "actor": actor,
            "target": target,
            "message": message[:500],
            "kind": kind,
        },
    )


async def _publish_code_agent_terminal_frame(
    task_id: str,
    bus: Any,
    terminal_lines: list[dict[str, str]],
    *,
    status: str = "running",
    current_stage: str | None = None,
    files: list[str] | None = None,
) -> None:
    if not bus or not task_id:
        return
    await bus.publish(
        task_id,
        "vertex_progress",
        {
            "stage": current_stage or ("done" if status == "done" else "executing"),
            "message": (
                "Entrega pronta."
                if status == "done"
                else "OpenClaude encontrou um erro."
                if status == "error"
                else "OpenClaude esta executando a tarefa."
            ),
            "status": status,
            "current_stage": current_stage,
            "line_count": len(terminal_lines),
            "files": files or [],
        },
    )


def _set_pty_size(fd: int, rows: int = 32, cols: int = 120) -> None:
    try:
        import struct

        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    except OSError:
        pass


def _make_code_agent_preexec(slave_fd: int):
    def _preexec() -> None:
        os.setsid()
        try:
            fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
        except OSError:
            pass

    return _preexec


def _process_group_commands(pgid: int) -> list[str]:
    try:
        output = subprocess.check_output(["ps", "-eo", "pid,pgid,cmd"], text=True, timeout=1.5)
    except (OSError, subprocess.SubprocessError):
        return []
    commands: list[str] = []
    for line in output.splitlines()[1:]:
        parts = line.strip().split(maxsplit=2)
        if len(parts) == 3 and parts[1].isdigit() and int(parts[1]) == pgid:
            commands.append(parts[2])
    return commands


def _read_process_cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()


def _process_cwd_under(pid: int, root: Path) -> bool:
    try:
        cwd = Path(os.readlink(f"/proc/{pid}/cwd")).resolve()
        root_resolved = root.resolve()
    except OSError:
        return False
    return cwd == root_resolved or root_resolved in cwd.parents


def _terminate_pid_group(pid: int, *, sig: int = signal.SIGTERM) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        os.killpg(os.getpgid(pid), sig)
        return True
    except (ProcessLookupError, OSError):
        try:
            os.kill(pid, sig)
            return True
        except (ProcessLookupError, OSError):
            return False


def _kill_orphan_dev_processes(task_id: str) -> bool:
    project_dir = _project_dir(task_id).resolve()
    killed = False
    proc_root = Path("/proc")
    if not proc_root.exists():
        return False
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == os.getpid():
            continue
        cmdline = _read_process_cmdline(pid)
        if not cmdline or not DEV_SERVER_PROCESS_RE.search(cmdline):
            continue
        if str(project_dir) not in cmdline and not _process_cwd_under(pid, project_dir):
            continue
        killed = _terminate_pid_group(pid) or killed
    return killed


def _looks_like_foreground_dev_server(command: str) -> bool:
    lowered = command.lower()
    return any(
        marker in lowered
        for marker in (
            "python3 -m http.server",
            "python -m http.server",
            "vite --",
            "vite ",
            "npm run dev",
            "npm start",
            "next dev",
        )
    )


def _parse_code_agent_progress(line: str) -> dict[str, Any] | None:
    """Tenta extrair progresso estruturado de uma linha de stdout do agente de codigo."""
    stripped = line.strip()
    if not stripped:
        return None

    for pattern, stage in CODE_AGENT_PROGRESS_PATTERNS:
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
            await _publish_ai_exchange(
                task_id,
                bus,
                actor="deepseek",
                target="openclaude",
                message=f"DeepSeek respondeu ao prompt interativo do OpenClaude: {content}",
                kind="auto_response",
            )
        return content[:500]
    except Exception:
        return None


async def _run_code_agent_pty(
    cmd: str,
    *,
    cwd_path: Path,
    env: dict[str, str],
    timeout: float,
    task_id: str | None,
    bus: Any,
    max_interactive_rounds: int,
) -> dict[str, Any]:
    master_fd, slave_fd = pty.openpty()
    _set_pty_size(slave_fd)
    env = dict(env)
    env.setdefault("TERM", "xterm-256color")
    env.setdefault("COLORTERM", "truecolor")
    env.setdefault("COLUMNS", "120")
    env.setdefault("LINES", "32")

    try:
        process = subprocess.Popen(
            cmd,
            shell=True,
            cwd=str(cwd_path),
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            text=False,
            env=env,
            preexec_fn=_make_code_agent_preexec(slave_fd),
            close_fds=True,
        )
    except OSError as exc:
        os.close(master_fd)
        os.close(slave_fd)
        return _shell_error(f"Erro ao executar comando: {exc}")

    os.close(slave_fd)
    flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    terminal_lines: list[dict[str, str]] = []
    stdout_lines: list[str] = []
    latest_code_agent_stage: str | None = None
    interactive_rounds = 0
    current_line = ""
    recent_text = ""
    stopped = False
    server_detected_success = False
    static_project_detected_success = False
    static_project_incomplete = False
    static_missing_assets: list[str] = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    last_terminal_frame_at = 0.0
    last_server_check_at = 0.0
    last_simulated_progress_at = 0.0
    simulated_progress_index = -1
    last_output_at = loop.time()
    last_file_summary: dict[str, Any] = {}
    static_snapshot: tuple[int, int] | None = None
    static_snapshot_since: float | None = None
    terminal_filter = _TerminalTextFilter()

    if bus and task_id:
        await _publish_ai_exchange(
            task_id,
            bus,
            actor="openclaude",
            target="deepseek",
            message="OpenClaude iniciou em uma CLI com TTY real.",
            kind="start",
        )
        await _publish_code_agent_terminal_frame(task_id, bus, terminal_lines, status="running")

    def _check_stopped() -> bool:
        nonlocal stopped
        if stopped:
            return True
        if task_id:
            from services.registry import task_store

            if task_store.is_stopped(task_id):
                stopped = True
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except OSError:
                    pass
                return True
        return False

    def _frame_lines() -> list[dict[str, str]]:
        display_line = _display_terminal_line(current_line)
        if display_line and not _is_spinner_noise(display_line):
            return [*terminal_lines, {"stream": "stdout", "line": display_line}]
        return terminal_lines

    async def _publish_terminal_frame(*, force: bool = False, status: str = "running") -> None:
        nonlocal last_terminal_frame_at
        if status == "running":
            return
        now = loop.time()
        if not force and now - last_terminal_frame_at < _terminal_frame_interval():
            return
        last_terminal_frame_at = now
        await _publish_code_agent_terminal_frame(
            task_id or "",
            bus,
            _frame_lines(),
            status=status,
            current_stage=latest_code_agent_stage,
            files=last_file_summary.get("root_files") or [],
        )

    async def _publish_terminal_line(line: str) -> None:
        nonlocal latest_code_agent_stage, last_output_at
        stripped = _display_terminal_line(line)
        if not stripped or _is_spinner_noise(stripped):
            return
        display = _redact_local_urls(stripped)
        if _is_duplicate_terminal_line(terminal_lines, display):
            return
        last_output_at = loop.time()
        stdout_lines.append(display + "\n")
        terminal_lines.append({"stream": "stdout", "line": display})
        if bus and task_id:
            await bus.publish(task_id, "shell_stdout", {"line": display})
            progress = _parse_code_agent_progress(stripped)
            if progress:
                latest_code_agent_stage = str(progress.get("stage") or "")
                await bus.publish(task_id, "vertex_progress", progress)
                await _publish_ai_exchange(
                    task_id,
                    bus,
                    actor="openclaude",
                    target="deepseek",
                    message=progress["message"],
                    kind="progress",
                )
            await _publish_terminal_frame(force=False)

    async def _publish_simulated_progress(*, force: bool = False) -> None:
        nonlocal latest_code_agent_stage, last_simulated_progress_at, simulated_progress_index
        if not bus or not task_id:
            return
        now = loop.time()
        if not force and now - last_simulated_progress_at < 3.0:
            return
        last_simulated_progress_at = now
        elapsed = max(0, int(now - (deadline - timeout)))
        target_index = min(elapsed // 8, len(CODE_AGENT_SIMULATED_PROGRESS) - 1)
        if target_index <= simulated_progress_index and not force:
            return
        simulated_progress_index = target_index
        stage, message = CODE_AGENT_SIMULATED_PROGRESS[target_index]
        latest_code_agent_stage = stage
        await bus.publish(
            task_id,
            "vertex_progress",
            {
                "stage": stage,
                "message": message,
                "status": "running",
                "simulated": True,
            },
        )

    async def _consume_terminal_chunk(chunk: str) -> None:
        nonlocal current_line
        for char in chunk:
            if char == "\r":
                if current_line.strip():
                    await _publish_terminal_line(current_line)
                current_line = ""
                continue
            if char == "\n":
                await _publish_terminal_line(current_line)
                current_line = ""
                continue
            if char == "\b":
                current_line = current_line[:-1]
                continue
            current_line += char
            if len(current_line) > 400:
                current_line = current_line[-400:]

    async def _interrupt_code_agent_group(pgid: int) -> None:
        try:
            os.write(master_fd, b"\x03")
        except OSError:
            pass
        await asyncio.sleep(0.2)
        if process.poll() is not None:
            return
        try:
            os.killpg(pgid, signal.SIGINT)
        except OSError:
            pass

    try:
        while process.poll() is None:
            if _check_stopped():
                break
            if loop.time() > deadline:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except OSError:
                    process.kill()
                break

            now = loop.time()
            await _publish_simulated_progress()
            if now - last_server_check_at >= 1.0:
                last_server_check_at = now
                try:
                    pgid = os.getpgid(process.pid)
                except OSError:
                    pgid = -1
                last_file_summary = _build_file_summary(cwd_path)
                file_summary = last_file_summary
                if pgid > 0 and file_summary.get("has_index_html"):
                    commands = _process_group_commands(pgid)
                    if any(_looks_like_foreground_dev_server(command) for command in commands):
                        server_detected_success = True
                        await _publish_terminal_line(
                            "Servidor local em foreground detectado; Vortax encerrou o processo e usara o preview interno."
                        )
                        await _interrupt_code_agent_group(pgid)
                        break
                    if not file_summary.get("has_package_json"):
                        snapshot = (
                            int(file_summary.get("file_count") or 0),
                            int(file_summary.get("total_size") or 0),
                        )
                        if snapshot != static_snapshot:
                            static_snapshot = snapshot
                            static_snapshot_since = now
                        stable_for = now - (static_snapshot_since or now)
                        quiet_for = now - last_output_at
                        ready_seconds = float(
                            getattr(settings, "CODE_AGENT_STATIC_READY_SECONDS", None)
                            or getattr(settings, "VERTEX_STATIC_READY_SECONDS", 4.0)
                            or 4.0
                        )
                        incomplete_seconds = float(
                            getattr(settings, "CODE_AGENT_STATIC_INCOMPLETE_SECONDS", None)
                            or getattr(settings, "VERTEX_STATIC_INCOMPLETE_SECONDS", 45.0)
                            or 45.0
                        )
                        if stable_for >= ready_seconds and quiet_for >= min(ready_seconds, 2.0):
                            static_missing_assets = missing_local_asset_refs(cwd_path)
                            if static_missing_assets and stable_for < incomplete_seconds:
                                await _publish_simulated_progress(force=True)
                                continue
                            if static_missing_assets:
                                static_project_incomplete = True
                                await _publish_terminal_line(
                                    "Projeto estatico incompleto: ha referencias locais sem arquivo. Vortax pedira correcao ao OpenClaude."
                                )
                                await _interrupt_code_agent_group(pgid)
                                break
                            static_project_detected_success = True
                            await _publish_terminal_line(
                                "Projeto estatico detectado; Vortax encerrou o OpenClaude e iniciara a revisao no Chrome."
                            )
                            await _interrupt_code_agent_group(pgid)
                            break

            try:
                data = os.read(master_fd, 4096)
            except BlockingIOError:
                await asyncio.sleep(0.05)
                continue
            except OSError as exc:
                if exc.errno == errno.EIO:
                    break
                raise

            if not data:
                await asyncio.sleep(0.05)
                continue

            chunk = terminal_filter.feed(data.decode("utf-8", errors="replace"))
            if not chunk:
                continue
            recent_text = (recent_text + chunk)[-4000:]
            await _consume_terminal_chunk(chunk)
            await _publish_terminal_frame(force=False)

            if interactive_rounds < max_interactive_rounds and _detect_interactive_prompt(recent_text):
                interactive_rounds += 1
                prompt_snapshot = "\n".join([line for line in recent_text.split("\n") if line.strip()][-5:])
                if bus and task_id:
                    await bus.publish(
                        task_id,
                        "shell_interactive_prompt",
                        {"prompt": prompt_snapshot[:500], "round": interactive_rounds},
                    )
                    await _publish_ai_exchange(
                        task_id,
                        bus,
                        actor="openclaude",
                        target="deepseek",
                        message=prompt_snapshot,
                        kind="prompt",
                    )
                response = await _ask_deepseek_for_response(prompt_snapshot, cmd, task_id or "", bus)
                if response and process.poll() is None:
                    os.write(master_fd, (response + "\n").encode("utf-8"))
                    recent_text = ""

        if current_line.strip():
            await _publish_terminal_line(current_line)

        try:
            await asyncio.wait_for(asyncio.get_event_loop().run_in_executor(None, process.wait), timeout=5.0)
        except asyncio.TimeoutError:
            process.kill()
            await asyncio.get_event_loop().run_in_executor(None, process.wait)
    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass

    returncode = process.returncode if process.returncode is not None else -1
    if bus and task_id:
        await _publish_code_agent_terminal_frame(
            task_id,
            bus,
            _frame_lines(),
            status="done" if returncode == 0 or server_detected_success or static_project_detected_success else "error",
            current_stage=latest_code_agent_stage,
            files=last_file_summary.get("root_files") or [],
        )

    stdout_full = "".join(stdout_lines)
    file_summary = _build_file_summary(cwd_path)
    static_missing_assets = static_missing_assets or missing_local_asset_refs(cwd_path)
    success = (
        not static_project_incomplete
        and not static_missing_assets
        and (
            returncode == 0
            or ((server_detected_success or static_project_detected_success) and bool(file_summary.get("has_index_html")))
        )
    )
    result = {
        "success": success,
        "stdout": stdout_full[:3000],
        "stderr": "",
        "returncode": 0 if (server_detected_success or static_project_detected_success) and success else returncode,
        "stdout_truncated": len(stdout_full) > 3000,
        "stderr_truncated": False,
        "local_urls": _extract_local_urls(stdout_full),
        "file_summary": file_summary,
        "tty": True,
    }
    if server_detected_success:
        result["foreground_server_detected"] = True
    if static_project_detected_success:
        result["static_project_detected"] = True
    if static_missing_assets:
        result["missing_assets"] = static_missing_assets
        result["stderr"] = "Referencias locais ausentes: " + ", ".join(static_missing_assets)
    if interactive_rounds > 0:
        result["interactive_rounds"] = interactive_rounds
    return result


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
    3. Parse de progresso do OpenClaude → eventos vertex_progress (nome legado)
    4. Detecção de prompts interativos → consulta DeepSeek para auto-resposta
    5. Listagem de arquivos criados
    """
    cmd = str(command).strip()
    if not cmd:
        return _shell_error("Comando vazio.")
    cmd = _normalize_shell_command(cmd)

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
        projects_root = str(settings.WORKSPACE_PATH.resolve())
        if projects_root not in cmd:
            return _shell_error(
                "rm so e permitido dentro da pasta de projetos. "
                f"Use caminhos dentro de {projects_root}"
            )

    cwd = str(_project_dir(task_id))
    cwd_path = _project_dir(task_id)
    is_code_agent = _is_code_agent_executable(executable)
    is_dev_server = False if is_code_agent else _is_dev_server_command(cmd)

    env = os.environ.copy()
    runtime_tmp = settings.RUNTIME_PATH / "tmp"
    runtime_tmp.mkdir(parents=True, exist_ok=True)
    env.setdefault("TMPDIR", str(runtime_tmp))
    env.setdefault("TEMP", str(runtime_tmp))
    env.setdefault("TMP", str(runtime_tmp))
    if is_code_agent:
        env["OPENCLAUDE_OUTPUT_DIR"] = cwd
    # Para dev servers, adiciona CI=true e FORCE_COLOR=0 para evitar prompts
    if is_dev_server:
        env["CI"] = "true"
        env["FORCE_COLOR"] = "0"
        env["BROWSER"] = "none"  # Evita abrir navegador automatico (create-react-app etc)

    timeout = _shell_timeout(cmd)
    if is_code_agent:
        return await _run_code_agent_pty(
            cmd,
            cwd_path=cwd_path,
            env=env,
            timeout=timeout,
            task_id=task_id,
            bus=bus,
            max_interactive_rounds=max_interactive_rounds,
        )

    if is_dev_server and task_id:
        await stop_dev_server(task_id)

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

    terminal_lines: list[dict[str, str]] = []
    latest_code_agent_stage: str | None = None
    if is_code_agent and bus and task_id:
        await _publish_ai_exchange(
            task_id,
            bus,
            actor="openclaude",
            target="deepseek",
            message="OpenClaude iniciou a execucao local da tarefa.",
            kind="start",
        )
        await _publish_code_agent_terminal_frame(task_id, bus, terminal_lines, status="running")

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    interactive_rounds = 0
    detected_port: int | None = None
    stopped = False  # flag local para interrupcao

    def _check_stopped() -> bool:
        """Verifica se a task foi interrompida e mata o processo se necessario."""
        nonlocal stopped
        if stopped:
            return True
        if task_id:
            from services.registry import task_store
            if task_store.is_stopped(task_id):
                stopped = True
                try:
                    if is_dev_server:
                        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    else:
                        process.kill()
                except OSError:
                    pass
                return True
        return False

    async def _publish_line(line: str, event_type: str) -> None:
        nonlocal detected_port, latest_code_agent_stage
        stripped = line.rstrip("\n\r")
        if not stripped:
            return
        if not bus or not task_id:
            return
        display = _redact_local_urls(stripped)
        await bus.publish(task_id, event_type, {"line": display})
        if is_code_agent:
            stream = "stderr" if event_type == "shell_stderr" else "stdout"
            terminal_lines.append({"stream": stream, "line": display})

        # Detecta porta do dev server
        if is_dev_server and detected_port is None and event_type == "shell_stdout":
            detected_port = _extract_port_from_output(stripped)

        if is_code_agent and event_type == "shell_stdout":
            progress = _parse_code_agent_progress(stripped)
            if progress:
                latest_code_agent_stage = str(progress.get("stage") or "")
                await bus.publish(task_id, "vertex_progress", progress)
                await _publish_ai_exchange(
                    task_id,
                    bus,
                    actor="openclaude",
                    target="deepseek",
                    message=progress["message"],
                    kind="progress",
                )
        if is_code_agent:
            await _publish_code_agent_terminal_frame(task_id, bus, terminal_lines, status="running", current_stage=latest_code_agent_stage)

    async def _drain_and_interact(stream, lines_list: list[str], event_type: str) -> None:
        """Le um stream com detecção de prompts interativos e auto-resposta."""
        nonlocal interactive_rounds
        loop = asyncio.get_event_loop()

        accumulated = ""
        while True:
            # Verifica interrupcao a cada iteracao
            if _check_stopped():
                break

            try:
                line = await asyncio.wait_for(
                    loop.run_in_executor(None, stream.readline),
                    timeout=0.3,
                )
            except asyncio.TimeoutError:
                # Verifica se o processo ainda está rodando e pode estar esperando input
                if process.poll() is None and event_type == "shell_stdout":
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
                        if is_code_agent:
                            await _publish_ai_exchange(
                                task_id,
                                bus,
                                actor="openclaude",
                                target="deepseek",
                                message=prompt_snapshot,
                                kind="prompt",
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
                "port": detected_port,
                "task_id": task_id,
                "internal": True,
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
            "local_urls": _extract_local_urls("".join(stdout_lines + stderr_lines) + "\n" + dev_url),
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
    if is_code_agent and bus and task_id:
        await _publish_code_agent_terminal_frame(
            task_id,
            bus,
            terminal_lines,
            status="done" if returncode == 0 else "error",
            current_stage=latest_code_agent_stage,
        )
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
        "local_urls": _extract_local_urls(stdout_full + "\n" + stderr_full),
        "file_summary": file_summary,
    }
    if interactive_rounds > 0:
        result["interactive_rounds"] = interactive_rounds

    return result


async def run_code_agent(task_description: str, task_id: str | None = None) -> dict[str, Any]:
    """Executa o OpenClaude com uma descricao de tarefa de desenvolvimento."""
    safe_desc = shlex.quote(str(task_description)[:500])
    cmd = (
        "openclaude -p --permission-mode bypassPermissions "
        "--dangerously-skip-permissions --no-session-persistence "
        f"{safe_desc}"
    )
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
    stopped = _kill_orphan_dev_processes(task_id)
    if not server:
        return stopped
    process = server["process"]
    try:
        # Tenta matar o grupo de processo (preexec_fn=os.setsid)
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        stopped = True
    except (ProcessLookupError, OSError):
        pass
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            stopped = True
        except (ProcessLookupError, OSError):
            pass
        process.wait()
    return stopped
