import re
import subprocess
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
    # Remove prefixos comuns de shell
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
    # Vertex CLI precisa de mais tempo para desenvolvimento de software.
    if "vertex" in command:
        return float(getattr(settings, "SHELL_VERTEX_TIMEOUT_SECONDS", 300) or 300)
    return float(getattr(settings, "SHELL_TIMEOUT_SECONDS", 30) or 30)


async def run_shell(command: str, task_id: str | None = None) -> dict[str, Any]:
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

    timeout = _shell_timeout(cmd)
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=str(settings.WORKSPACE_PATH),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _shell_error(f"Comando excedeu timeout de {timeout}s e foi cancelado.")
    except OSError as exc:
        return _shell_error(f"Erro ao executar comando: {exc}")

    stdout = result.stdout[:3000] if result.stdout else ""
    stderr = result.stderr[:500] if result.stderr else ""

    return {
        "success": result.returncode == 0,
        "stdout": stdout,
        "stderr": stderr,
        "returncode": result.returncode,
    }


async def run_vertex(task_description: str, task_id: str | None = None) -> dict[str, Any]:
    """Executa o Vertex CLI com uma descricao de tarefa de desenvolvimento."""
    safe_desc = str(task_description).replace("'", "'\\''")[:500]
    cmd = f"vertex '{safe_desc}'"
    return await run_shell(cmd, task_id=task_id)
