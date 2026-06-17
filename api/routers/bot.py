import os
import sys
import json
import ctypes
import subprocess
from datetime import datetime
from fastapi import APIRouter, HTTPException, Body
from typing import Optional
from api.config import ROOT, DATA_DIR, PID_FILE, SESSIONS
from api.models import BotStatus

router = APIRouter(prefix="/bot", tags=["bot"])

ACTIVE_PROFILE_FILE = os.path.join(DATA_DIR, "active_profile.json")
RUN_LOG_FILE        = os.path.join(DATA_DIR, "bot_run_log.json")


def _pid_alive(pid: int) -> bool:
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259  # GetExitCodeProcess returneaza asta cat timp procesul ruleaza
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h:
            exit_code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(h)
            return exit_code.value == STILL_ACTIVE
    except Exception:
        pass
    return False


def _read_pid(path: str) -> int | None:
    try:
        return int(open(path).read().strip())
    except Exception:
        return None


def _read_active_profile() -> dict:
    try:
        with open(ACTIVE_PROFILE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"id": None, "name": None}


def _save_active_profile(profile_id: str, profile_name: str) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    now = datetime.now().isoformat()
    with open(ACTIVE_PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump({"id": profile_id, "name": profile_name, "started_at": now}, f)
    _update_run_log(last_started_at=now)


def _clear_active_profile() -> None:
    try:
        if os.path.exists(ACTIVE_PROFILE_FILE):
            os.remove(ACTIVE_PROFILE_FILE)
    except Exception:
        pass
    _update_run_log(last_stopped_at=datetime.now().isoformat())


def _read_run_log() -> dict:
    try:
        with open(RUN_LOG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_started_at": None, "last_stopped_at": None}


def _update_run_log(**kwargs) -> None:
    log = _read_run_log()
    log.update(kwargs)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(RUN_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f)


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

    ap      = _read_active_profile() if running else {"id": None, "name": None}
    run_log = _read_run_log()

    return BotStatus(
        running=running,
        pid=pid if running else None,
        sessions_active=active,
        active_profile_id=ap.get("id"),
        active_profile_name=ap.get("name"),
        last_started_at=run_log.get("last_started_at"),
        last_stopped_at=run_log.get("last_stopped_at"),
    )


@router.post("/start")
def start_bot(body: Optional[dict] = Body(default=None)):
    body = body or {}
    pid = _read_pid(PID_FILE) if os.path.exists(PID_FILE) else None
    if pid and _pid_alive(pid):
        raise HTTPException(409, f"Bot-ul ruleaza deja (PID={pid})")

    script = os.path.join(ROOT, "live", "run_all.py")
    if not os.path.exists(script):
        raise HTTPException(404, "live/run_all.py nu a fost gasit")

    proc = subprocess.Popen(
        [sys.executable, script],
        cwd=ROOT,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )

    profile_id   = body.get("profile_id")   or "standard"
    profile_name = body.get("profile_name") or "Standard"
    _save_active_profile(profile_id, profile_name)

    return {"started": True, "pid": proc.pid, "profile_id": profile_id}


@router.post("/stop")
def stop_bot():
    pid = _read_pid(PID_FILE) if os.path.exists(PID_FILE) else None
    if not pid or not _pid_alive(pid):
        raise HTTPException(409, "Bot-ul nu ruleaza")

    result = subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(pid)],
        capture_output=True, text=True,
    )
    # Sterge PID file imediat — run_all.py nu apuca cleanup la taskkill /F
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except Exception:
        pass
    _clear_active_profile()
    return {"stopped": result.returncode == 0, "pid": pid}
