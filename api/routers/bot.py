import os
import ctypes
from fastapi import APIRouter
from api.config import PID_FILE, SESSIONS
from api.models import BotStatus

router = APIRouter(prefix="/bot", tags=["bot"])


def _pid_alive(pid: int) -> bool:
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
    except Exception:
        pass
    return False


def _read_pid(path: str) -> int | None:
    try:
        return int(open(path).read().strip())
    except Exception:
        return None


@router.get("/status", response_model=BotStatus)
def bot_status():
    pid = _read_pid(PID_FILE) if os.path.exists(PID_FILE) else None
    running = pid is not None and _pid_alive(pid)

    active = 0
    if running:
        for s in SESSIONS:
            lock = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "data", "live_signals", s["id"], "session.lock",
            )
            if os.path.exists(lock):
                spid = _read_pid(lock)
                if spid and _pid_alive(spid):
                    active += 1

    return BotStatus(running=running, pid=pid if running else None, sessions_active=active)
