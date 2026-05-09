import asyncio
import os
import signal
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from auth import AuthUser, ensure_task_owner, require_auth
from config import settings
from services.credential_store import credential_store
from services.registry import event_bus, runner_tasks, task_store

router = APIRouter()


def _kill_process_tree(pid: int) -> None:
    """Mata o processo e todos os filhos recursivamente."""
    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        pass


def _iter_process_cmdlines() -> list[tuple[int, str]]:
    processes: list[tuple[int, str]] = []
    for proc_dir in Path("/proc").iterdir():
        if not proc_dir.name.isdigit():
            continue
        try:
            cmdline = (proc_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="ignore")
        except OSError:
            continue
        processes.append((int(proc_dir.name), cmdline))
    return processes


def _kill_runner_and_children(task_id: str) -> bool:
    """Cancela o runner asyncio e mata subprocessos shell/agente de codigo ativos."""
    stopped = False

    # Cancela o runner task
    runner = runner_tasks.pop(task_id, None)
    if runner and not runner.done():
        runner.cancel()
        stopped = True

    # Mata dev servers em background
    from tools.shell import _dev_servers, _kill_orphan_dev_processes
    stopped = _kill_orphan_dev_processes(task_id) or stopped
    dev_server = _dev_servers.pop(task_id, None)
    if dev_server:
        stopped = True
        proc = dev_server["process"]
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass

    # Mata processos associados ao task_id sem depender de psutil.
    for pid, cmdline in _iter_process_cmdlines():
        if pid == os.getpid():
            continue
        projects_root = str(settings.WORKSPACE_PATH)
        if task_id in cmdline or (settings.CODE_AGENT_COMMAND in cmdline and projects_root in cmdline):
            stopped = True
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    return stopped


@router.post("/{task_id}/confirm")
async def confirm_task(
    task_id: str,
    approved: bool = True,
    current_user: AuthUser = Depends(require_auth),
) -> dict:
    ensure_task_owner(task_store.get(task_id), current_user)
    await event_bus.publish(task_id, "confirmation_result", {"approved": approved})
    return {"ok": True, "approved": approved}


@router.post("/{task_id}/stop")
async def stop_task(task_id: str, current_user: AuthUser = Depends(require_auth)) -> dict:
    """Interrompe uma tarefa em execucao: cancela runner, mata subprocessos, limpa estado."""
    ensure_task_owner(task_store.get(task_id), current_user)

    # Marca como stopped no store (o loop do runner checa is_stopped)
    task_store.stop(task_id)

    # Forca cancelamento do runner + kill de processos
    _kill_runner_and_children(task_id)
    from tools.browser_pool import browser_pool

    await browser_pool.release(task_id)
    credential_store.revoke_task(task_id)

    # Publica status final
    await event_bus.publish(task_id, "agent_status", {"status": "stopped", "label": "Interrompido"})

    # Tenta publicar que parou (se as conexoes WS ainda estiverem abertas)
    try:
        await asyncio.wait_for(
            event_bus.close_task_connections(task_id),
            timeout=3.0,
        )
    except asyncio.TimeoutError:
        pass

    return {"ok": True, "stopped": True}
