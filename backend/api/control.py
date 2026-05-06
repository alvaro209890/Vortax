import asyncio
import os
import signal
import subprocess

from fastapi import APIRouter, HTTPException

from services.registry import event_bus, runner_tasks, task_store

router = APIRouter()


def _kill_process_tree(pid: int) -> None:
    """Mata o processo e todos os filhos recursivamente."""
    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        pass


def _kill_runner_and_children(task_id: str) -> bool:
    """Cancela o runner asyncio e mata subprocessos shell/vertex ativos."""
    stopped = False

    # Cancela o runner task
    runner = runner_tasks.pop(task_id, None)
    if runner and not runner.done():
        runner.cancel()
        stopped = True

    # Mata dev servers em background
    from tools.shell import _dev_servers
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

    # Mata qualquer processo "vertex" ou "shell" filho do runner
    import psutil
    try:
        current = psutil.Process()
        for child in current.children(recursive=True):
            cmdline = " ".join(child.cmdline()) if child.cmdline() else ""
            if "vertex" in cmdline or task_id in cmdline:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
    except Exception:
        pass

    return stopped


@router.post("/{task_id}/confirm")
async def confirm_task(task_id: str, approved: bool = True) -> dict:
    if not task_store.get(task_id):
        raise HTTPException(status_code=404, detail="Task nao encontrada")
    await event_bus.publish(task_id, "confirmation_result", {"approved": approved})
    return {"ok": True, "approved": approved}


@router.post("/{task_id}/stop")
async def stop_task(task_id: str) -> dict:
    """Interrompe uma tarefa em execucao: cancela runner, mata subprocessos, limpa estado."""
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task nao encontrada")

    # Marca como stopped no store (o loop do runner checa is_stopped)
    task_store.stop(task_id)

    # Forca cancelamento do runner + kill de processos
    _kill_runner_and_children(task_id)

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
