import os
import sys
import ctypes
import subprocess
from fastapi import APIRouter, HTTPException
from api.config import ROOT, PID_FILE, SESSIONS
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


@router.post("/start")
def start_bot():
    pid = _read_pid(PID_FILE) if os.path.exists(PID_FILE) else None
    if pid and _pid_alive(pid):
        raise HTTPException(409, f"Bot-ul ruleaza deja (PID={pid})")

    script = os.path.join(ROOT, "live", "run_all.py")
    if not os.path.exists(script):
        raise HTTPException(404, "live/run_all.py nu a fost gasit")

    proc = subprocess.Popen(
        [sys.executable, script],
        cwd=ROOT,
        # Detasat complet: supravietuieste daca API-ul se opreste
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    return {"started": True, "pid": proc.pid}


@router.post("/stop")
def stop_bot():
    pid = _read_pid(PID_FILE) if os.path.exists(PID_FILE) else None
    if not pid or not _pid_alive(pid):
        raise HTTPException(409, "Bot-ul nu ruleaza")

    result = subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(pid)],
        capture_output=True, text=True,
    )
    return {"stopped": result.returncode == 0, "pid": pid}
