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


async def run_shell(
    command: str,
    task_id: str | None = None,
    bus: Any = None,
) -> dict[str, Any]:
    """Executa um comando shell seguro com streaming de stdout via EventBus."""
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

    # Se for vertex, injeta o output-dir via env e usa o task_id como subdiretório
    env = os.environ.copy()
    if "vertex" in executable:
        env["VERTEX_OUTPUT_DIR"] = cwd

    timeout = _shell_timeout(cmd)
    try:
        process = subprocess.Popen(
            cmd,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
    except OSError as exc:
        return _shell_error(f"Erro ao executar comando: {exc}")

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    async def _drain_stream(stream, lines_list: list[str], event_type: str) -> None:
        """Le e publica linhas de um stream ate que ele feche."""
        loop = asyncio.get_event_loop()

        while True:
            try:
                line = await asyncio.wait_for(
                    loop.run_in_executor(None, stream.readline),
                    timeout=0.3,
                )
            except asyncio.TimeoutError:
                continue

            if not line:
                break

            lines_list.append(line)
            if bus and task_id:
                stripped = line.rstrip("\n\r")
                if stripped:
                    await bus.publish(task_id, event_type, {"line": stripped})

    async def _drain_with_timeout() -> None:
        """Drena ambos os streams com timeout global."""
        drain_task = asyncio.gather(
            _drain_stream(process.stdout, stdout_lines, "shell_stdout"),
            _drain_stream(process.stderr, stderr_lines, "shell_stderr"),
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

    return {
        "success": returncode == 0,
        "stdout": stdout,
        "stderr": stderr,
        "returncode": returncode,
    }


async def run_vertex(task_description: str, task_id: str | None = None) -> dict[str, Any]:
    """Executa o Vertex CLI com uma descricao de tarefa de desenvolvimento."""
    safe_desc = str(task_description).replace("'", "'\\''")[:500]
    cmd = f"vertex '{safe_desc}'"
    return await run_shell(cmd, task_id=task_id)
