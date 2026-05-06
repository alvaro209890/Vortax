import atexit
import os
import subprocess
import threading


_lock = threading.Lock()
_pids: set[int] = set()
_atexit_registered = False


def ensure_atexit_registered() -> None:
    global _atexit_registered
    with _lock:
        if _atexit_registered:
            return
        atexit.register(kill_all_best_effort)
        _atexit_registered = True


def register_pid(pid: int) -> None:
    if not pid:
        return
    ensure_atexit_registered()
    with _lock:
        _pids.add(int(pid))


def unregister_pid(pid: int) -> None:
    if not pid:
        return
    with _lock:
        _pids.discard(int(pid))


def kill_all_best_effort() -> None:
    with _lock:
        pids = list(_pids)
        _pids.clear()

    for pid in pids:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                os.kill(pid, 9)
        except Exception:
            pass
