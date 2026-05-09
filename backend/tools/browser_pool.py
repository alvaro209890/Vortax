import asyncio
import logging
import os
import re
import signal
import shutil
import time
from pathlib import Path
from typing import Callable

from config import settings
from services.credential_store import credential_store
from tools.browser import BrowserTool

logger = logging.getLogger(__name__)


class BrowserPoolError(RuntimeError):
    pass


BrowserToolFactory = Callable[[int, Path], BrowserTool]


def _profile_root() -> Path:
    if Path("/dev/shm").exists():
        return Path("/dev/shm/vortax-profiles")
    return settings.RUNTIME_PATH / "browser-profiles"


def _safe_profile_name(task_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(task_id or "").strip())
    return safe.strip("._-") or "task"


class BrowserPool:
    def __init__(
        self,
        *,
        max_instances: int = 4,
        port_start: int = 9223,
        port_end: int = 9240,
        profile_root: Path | None = None,
        tool_factory: BrowserToolFactory = BrowserTool,
    ) -> None:
        ports = list(range(int(port_end), int(port_start) - 1, -1))
        if not ports:
            raise ValueError("BrowserPool precisa de pelo menos uma porta disponivel")
        self._instances: dict[str, BrowserTool] = {}
        self._ports_by_task: dict[str, int] = {}
        self._profile_dirs_by_task: dict[str, Path] = {}
        self._available_ports = ports
        self._semaphore = asyncio.BoundedSemaphore(max(1, min(int(max_instances), len(ports))))
        self._lock = asyncio.Lock()
        self._profile_root = Path(profile_root) if profile_root else _profile_root()
        self._tool_factory = tool_factory
        # Hibernacao de browsers ociosos
        self._last_activity: dict[str, float] = {}
        self._hibernation_task: asyncio.Task | None = None
        self._idle_timeout = getattr(settings, "BROWSER_IDLE_TIMEOUT_SECONDS", 600)

    @property
    def profile_root(self) -> Path:
        return self._profile_root

    async def initialize(self) -> None:
        """Remove perfis antigos antes do backend aceitar novas tarefas."""
        self._kill_orphan_chrome_processes()
        await self._remove_path(self._profile_root)
        self._profile_root.mkdir(parents=True, exist_ok=True)
        self._start_hibernation()

    def _start_hibernation(self) -> None:
        if self._hibernation_task is not None:
            return
        self._hibernation_task = asyncio.ensure_future(self._hibernation_loop())

    def _stop_hibernation(self) -> None:
        if self._hibernation_task is None:
            return
        self._hibernation_task.cancel()
        self._hibernation_task = None

    async def _hibernation_loop(self) -> None:
        """Fecha browsers ociosos apos IDLE_TIMEOUT segundos sem atividade."""
        while True:
            try:
                await asyncio.sleep(60)
                now = time.time()
                to_release: list[str] = []
                async with self._lock:
                    for task_id, last_used in list(self._last_activity.items()):
                        if task_id in self._instances and (now - last_used) >= self._idle_timeout:
                            to_release.append(task_id)
                for task_id in to_release:
                    logger.info(
                        "Hibernando browser ocioso task=%s apos %ds inativo",
                        task_id,
                        int(now - self._last_activity.get(task_id, now)),
                    )
                    await self.release(task_id)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Erro no loop de hibernacao de browsers")

    async def acquire(self, task_id: str, timeout: float = 30.0) -> BrowserTool:
        key = str(task_id or "").strip()
        if not key:
            raise BrowserPoolError("task_id obrigatorio para abrir navegador isolado")

        async with self._lock:
            existing = self._instances.get(key)
            if existing is not None:
                self._last_activity[key] = time.time()
                return existing

        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=float(timeout))
        except asyncio.TimeoutError as exc:
            raise BrowserPoolError("Limite de navegadores ativos atingido; tente novamente em instantes.") from exc

        semaphore_acquired = True
        reserved_port: int | None = None
        try:
            async with self._lock:
                existing = self._instances.get(key)
                if existing is not None:
                    self._semaphore.release()
                    semaphore_acquired = False
                    return existing

                if not self._available_ports:
                    raise BrowserPoolError("Nenhuma porta CDP disponivel para abrir navegador.")

                port = self._available_ports.pop()
                reserved_port = port
                profile_dir = self._profile_root / _safe_profile_name(key)
                await self._remove_path(profile_dir)
                profile_dir.mkdir(parents=True, exist_ok=True)

                tool = self._tool_factory(port, profile_dir)
                self._instances[key] = tool
                self._ports_by_task[key] = port
                self._profile_dirs_by_task[key] = profile_dir
                self._last_activity[key] = time.time()
                return tool
        except Exception:
            async with self._lock:
                if reserved_port is not None and reserved_port not in self._available_ports:
                    self._available_ports.append(reserved_port)
            if semaphore_acquired:
                self._semaphore.release()
            raise

    async def get_existing(self, task_id: str) -> BrowserTool:
        key = str(task_id or "").strip()
        async with self._lock:
            tool = self._instances.get(key)
        if tool is None:
            raise BrowserPoolError("Nenhum navegador ativo para esta tarefa.")
        return tool

    async def get_tool_method(self, task_id: str, method_name: str):
        tool = await self.acquire(task_id)
        method = getattr(tool, method_name, None)
        if method is None:
            raise BrowserPoolError(f"Metodo de navegador desconhecido: {method_name}")
        return method

    async def release(self, task_id: str) -> bool:
        key = str(task_id or "").strip()
        async with self._lock:
            tool = self._instances.pop(key, None)
            port = self._ports_by_task.pop(key, None)
            profile_dir = self._profile_dirs_by_task.pop(key, None)
            self._last_activity.pop(key, None)

        if tool is None:
            if profile_dir is not None:
                await self._remove_path(profile_dir)
            return False

        try:
            await tool.close()
        finally:
            if profile_dir is not None:
                await self._remove_path(profile_dir)
            credential_store.revoke_task(key)
            async with self._lock:
                if port is not None and port not in self._available_ports:
                    self._available_ports.append(port)
            self._semaphore.release()
        return True

    async def shutdown(self) -> None:
        self._stop_hibernation()
        async with self._lock:
            task_ids = list(self._instances.keys())
        for task_id in task_ids:
            await self.release(task_id)
        await self._remove_path(self._profile_root)

    @staticmethod
    async def _remove_path(path: Path) -> None:
        if not path.exists() and not path.is_symlink():
            return
        try:
            if path.is_symlink() or path.is_file():
                path.unlink(missing_ok=True)
            else:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass

    def _kill_orphan_chrome_processes(self) -> None:
        proc_root = Path("/proc")
        if not proc_root.exists():
            return
        profile_root = str(self._profile_root)
        for proc_dir in proc_root.iterdir():
            if not proc_dir.name.isdigit() or int(proc_dir.name) == os.getpid():
                continue
            try:
                cmdline = (proc_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="ignore")
            except OSError:
                continue
            lowered = cmdline.lower()
            if profile_root not in cmdline or ("chrome" not in lowered and "chromium" not in lowered):
                continue
            try:
                os.kill(int(proc_dir.name), signal.SIGTERM)
            except OSError:
                pass


browser_pool = BrowserPool(max_instances=settings.BROWSER_POOL_MAX_INSTANCES)
