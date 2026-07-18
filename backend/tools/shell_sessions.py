"""Sessões de shell estilo Manus: shell_exec / shell_view / shell_write / shell_kill.

Inspirado no leak Manus (sessões interativas) e no Bash do Claude Code (timeout + background).
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from config import settings
from services.process_registry import register_pid, unregister_pid
from tools.shell import (
    BLOCKED_RM_PATTERN,
    _extract_command,
    _has_blocked_patterns,
    _is_whitelisted,
    _normalize_shell_command,
    _project_dir,
    _shell_error,
    run_shell,
)


@dataclass
class ShellSession:
    session_id: str
    task_id: str
    command: str
    process: subprocess.Popen[bytes] | None
    cwd: str
    created_at: float = field(default_factory=time.time)
    stdout_buf: bytearray = field(default_factory=bytearray)
    stderr_buf: bytearray = field(default_factory=bytearray)
    last_read_stdout: int = 0
    last_read_stderr: int = 0
    returncode: int | None = None
    background: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _drain_task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        if self.process is None:
            return False
        return self.process.poll() is None

    def snapshot_output(self, *, since_last: bool = True, max_chars: int = 12000) -> dict[str, Any]:
        with self._lock:
            if self.process is not None and self.process.poll() is not None:
                self.returncode = self.process.returncode
            out = bytes(self.stdout_buf)
            err = bytes(self.stderr_buf)
            if since_last:
                out_chunk = out[self.last_read_stdout :]
                err_chunk = err[self.last_read_stderr :]
                self.last_read_stdout = len(out)
                self.last_read_stderr = len(err)
            else:
                out_chunk, err_chunk = out, err
        def _dec(b: bytes) -> str:
            text = b.decode("utf-8", errors="replace")
            if len(text) > max_chars:
                return text[-max_chars:]
            return text

        return {
            "stdout": _dec(out_chunk),
            "stderr": _dec(err_chunk),
            "running": self.running,
            "returncode": self.returncode if not self.running else None,
            "session_id": self.session_id,
            "command": self.command,
        }


_SESSIONS: dict[str, ShellSession] = {}
_SESSIONS_LOCK = threading.Lock()


def _get(session_id: str) -> ShellSession | None:
    with _SESSIONS_LOCK:
        return _SESSIONS.get(session_id)


def _put(session: ShellSession) -> None:
    with _SESSIONS_LOCK:
        _SESSIONS[session.session_id] = session


def _drop(session_id: str) -> None:
    with _SESSIONS_LOCK:
        _SESSIONS.pop(session_id, None)


def list_task_sessions(task_id: str) -> list[str]:
    with _SESSIONS_LOCK:
        return [s.session_id for s in _SESSIONS.values() if s.task_id == task_id]


async def kill_task_sessions(task_id: str) -> int:
    ids = list_task_sessions(task_id)
    n = 0
    for sid in ids:
        result = await shell_kill(sid)
        if result.get("success"):
            n += 1
    return n


def _start_drain(session: ShellSession) -> None:
    """Thread que drena stdout/stderr do processo."""

    def _reader(pipe, is_stdout: bool) -> None:
        try:
            while True:
                chunk = pipe.read(4096)
                if not chunk:
                    break
                with session._lock:
                    if is_stdout:
                        session.stdout_buf.extend(chunk)
                        if len(session.stdout_buf) > 2_000_000:
                            session.stdout_buf = session.stdout_buf[-1_500_000:]
                            session.last_read_stdout = max(0, session.last_read_stdout - 500_000)
                    else:
                        session.stderr_buf.extend(chunk)
                        if len(session.stderr_buf) > 1_000_000:
                            session.stderr_buf = session.stderr_buf[-750_000:]
                            session.last_read_stderr = max(0, session.last_read_stderr - 250_000)
        except Exception:
            pass

    if session.process is None:
        return
    if session.process.stdout:
        threading.Thread(target=_reader, args=(session.process.stdout, True), daemon=True).start()
    if session.process.stderr:
        threading.Thread(target=_reader, args=(session.process.stderr, False), daemon=True).start()


async def shell_exec(
    command: str,
    task_id: str,
    *,
    session_id: str | None = None,
    background: bool = False,
    timeout: float | None = None,
    bus: Any = None,
) -> dict[str, Any]:
    """Executa comando no workspace. background=True → sessão Manus-style."""
    cmd = _normalize_shell_command(str(command or "").strip())
    if not cmd:
        return _shell_error("Comando vazio.")

    # Alias: sem background e sem session_id → comportamento shell_run (compat)
    if not background and not session_id:
        result = await run_shell(cmd, task_id=task_id, bus=bus)
        result["tool"] = "shell_exec"
        result["mode"] = "oneshot"
        return result

    executable = _extract_command(cmd)
    if not executable:
        return _shell_error(f"Nao foi possivel identificar o comando em: {cmd}")
    if not _is_whitelisted(executable):
        return _shell_error(f"Comando '{executable}' nao esta na whitelist do Vortax.")
    blocked = _has_blocked_patterns(cmd)
    if blocked:
        return _shell_error(blocked)
    if BLOCKED_RM_PATTERN.search(cmd):
        projects_root = str(settings.WORKSPACE_PATH.resolve())
        if projects_root not in cmd:
            return _shell_error(f"rm so e permitido dentro de {projects_root}")

    # Se session_id existente: escrever comando no stdin (pipeline interativo)
    if session_id:
        existing = _get(session_id)
        if not existing or not existing.running or not existing.process or not existing.process.stdin:
            return {"success": False, "error": f"Sessao {session_id} nao esta aberta para escrita."}
        try:
            payload = (cmd if cmd.endswith("\n") else cmd + "\n").encode()
            existing.process.stdin.write(payload)
            existing.process.stdin.flush()
            await asyncio.sleep(0.15)
            snap = existing.snapshot_output(since_last=True)
            return {"success": True, "mode": "session_command", **snap}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": f"Falha ao enviar comando: {exc}"}

    cwd_path = _project_dir(task_id)
    env = os.environ.copy()
    runtime_tmp = settings.RUNTIME_PATH / "tmp"
    runtime_tmp.mkdir(parents=True, exist_ok=True)
    env.setdefault("TMPDIR", str(runtime_tmp))
    env["CI"] = "true"
    env["FORCE_COLOR"] = "0"

    sid = f"sh_{uuid.uuid4().hex[:12]}"
    try:
        process = subprocess.Popen(
            cmd,
            shell=True,
            cwd=str(cwd_path),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
    except OSError as exc:
        return _shell_error(f"Erro ao executar: {exc}")

    register_pid(process.pid)
    session = ShellSession(
        session_id=sid,
        task_id=task_id,
        command=cmd,
        process=process,
        cwd=str(cwd_path),
        background=True,
    )
    _put(session)
    _start_drain(session)

    if background:
        await asyncio.sleep(0.2)
        snap = session.snapshot_output(since_last=True)
        return {
            "success": True,
            "mode": "background",
            "session_id": sid,
            "pid": process.pid,
            "message": "Processo em background. Use shell_view para acompanhar e shell_kill para encerrar.",
            **snap,
        }

    # Foreground com timeout: espera terminar
    timeout_s = float(timeout or settings.SHELL_TIMEOUT_SECONDS or 30)
    try:
        await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=timeout_s)
    except asyncio.TimeoutError:
        # promove a background em vez de matar (padrão Manus: observar)
        snap = session.snapshot_output(since_last=True)
        return {
            "success": True,
            "mode": "background_timeout",
            "session_id": sid,
            "pid": process.pid,
            "message": f"Timeout {timeout_s}s — processo continua. Use shell_view/shell_kill.",
            **snap,
        }

    unregister_pid(process.pid)
    session.returncode = process.returncode
    snap = session.snapshot_output(since_last=False)
    _drop(sid)
    return {
        "success": process.returncode == 0,
        "mode": "session_wait",
        "session_id": sid,
        "returncode": process.returncode,
        **snap,
    }


async def shell_view(session_id: str) -> dict[str, Any]:
    session = _get(session_id)
    if not session:
        return {"success": False, "error": f"Sessao desconhecida: {session_id}"}
    if session.process and session.process.poll() is not None:
        session.returncode = session.process.returncode
        unregister_pid(session.process.pid)
    snap = session.snapshot_output(since_last=True)
    return {"success": True, **snap}


async def shell_write(session_id: str, input_text: str, press_enter: bool = True) -> dict[str, Any]:
    session = _get(session_id)
    if not session or not session.running or not session.process or not session.process.stdin:
        return {"success": False, "error": f"Sessao {session_id} nao aceita input."}
    data = str(input_text or "")
    if press_enter and not data.endswith("\n"):
        data += "\n"
    try:
        session.process.stdin.write(data.encode())
        session.process.stdin.flush()
        await asyncio.sleep(0.2)
        snap = session.snapshot_output(since_last=True)
        return {"success": True, **snap}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc)}


async def shell_kill(session_id: str) -> dict[str, Any]:
    session = _get(session_id)
    if not session:
        return {"success": False, "error": f"Sessao desconhecida: {session_id}"}
    proc = session.process
    if proc is None:
        _drop(session_id)
        return {"success": True, "killed": False, "session_id": session_id}
    try:
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    proc.kill()
        unregister_pid(proc.pid)
        session.returncode = proc.returncode
    finally:
        _drop(session_id)
    return {"success": True, "killed": True, "session_id": session_id, "returncode": session.returncode}
