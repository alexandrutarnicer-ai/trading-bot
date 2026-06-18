import os
import sys
import json
import ctypes
import subprocess
import threading
from datetime import datetime
from fastapi import APIRouter, HTTPException, Body
from typing import Optional
from api.config import ROOT, DATA_DIR, PID_FILE, SESSIONS
from api.models import BotStatus
from api import telegram as tg

router = APIRouter(prefix="/bot", tags=["bot"])

ACTIVE_PROFILE_FILE   = os.path.join(DATA_DIR, "active_profile.json")
RUNTIME_PROFILE_FILE  = os.path.join(DATA_DIR, "active_profile_runtime.json")
RUN_LOG_FILE          = os.path.join(DATA_DIR, "bot_run_log.json")
PROFILES_DIR          = os.path.join(ROOT, "data", "profiles")


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
    # Scrie profilul complet in fisierul runtime pe care il citesc sesiunile live
    profile_path = os.path.join(PROFILES_DIR, f"{profile_id}.json")
    if os.path.exists(profile_path):
        try:
            with open(profile_path, encoding="utf-8") as f:
                profile_data = json.load(f)
            with open(RUNTIME_PROFILE_FILE, "w", encoding="utf-8") as f:
                json.dump(profile_data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass


def _clear_active_profile() -> None:
    try:
        if os.path.exists(ACTIVE_PROFILE_FILE):
            os.remove(ACTIVE_PROFILE_FILE)
    except Exception:
        pass
    try:
        if os.path.exists(RUNTIME_PROFILE_FILE):
            os.remove(RUNTIME_PROFILE_FILE)
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

    env = os.environ.copy()
    env["BOT_API_START"] = "1"   # semnalizeaza run_all.py sa nu trimita propriul mesaj de start
    proc = subprocess.Popen(
        [sys.executable, script],
        cwd=ROOT,
        env=env,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )

    profile_id   = body.get("profile_id")   or "standard"
    profile_name = body.get("profile_name") or "Standard"
    _save_active_profile(profile_id, profile_name)

    # Trimite notificare Telegram cu profilul si sesiunile active
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    def _notify_start():
        lines = [f"Bot Trading <b>pornit</b>  {now_str}", f"Profil: <b>{profile_name}</b>"]
        try:
            with open(RUNTIME_PROFILE_FILE, encoding="utf-8") as f:
                profile_data = json.load(f)
            sessions = profile_data.get("sessions", [])
            if sessions:
                lines.append("")
                for s in sessions:
                    sid       = s.get("id", "?")
                    markets   = ", ".join(s.get("markets", []))
                    direction = s.get("direction", "?")
                    etf       = s.get("entry_tf", "?")
                    label     = s.get("label", "")
                    name_part = f"{label} " if label else ""
                    lines.append(f"• <b>{sid}</b> {name_part}— {markets} | {etf} | {direction}")
        except Exception:
            pass
        tg.send_message("\n".join(lines))
    threading.Thread(target=_notify_start, daemon=True).start()

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

    ap = _read_active_profile()
    profile_name = ap.get("name") or "necunoscut"
    _clear_active_profile()

    # Trimite notificare Telegram in background (run_all.py nu a apucat sa trimita)
    stopped_ok = result.returncode == 0
    if stopped_ok:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        def _notify():
            tg.send_message(
                f"Bot Trading <b>oprit</b>  {now_str}\n"
                f"Profil: {profile_name}\n"
                f"Oprit manual din interfata web."
            )
        threading.Thread(target=_notify, daemon=True).start()

    return {"stopped": stopped_ok, "pid": pid}


# ─── Autostart Windows ────────────────────────────────────────────────────────

@router.get("/autostart/status")
def autostart_status():
    try:
        r = subprocess.run(
            ["powershell", "-Command",
             "if (Get-ScheduledTask -TaskName 'TradingBot-RunAll' -ErrorAction SilentlyContinue) { 'true' } else { 'false' }"],
            capture_output=True, text=True, timeout=10
        )
        enabled = r.stdout.strip().lower() == "true"
    except Exception:
        enabled = False
    return {"enabled": enabled}


@router.post("/autostart/enable")
def autostart_enable():
    script = os.path.join(ROOT, "scripts", "setup_autostart.ps1")
    if not os.path.exists(script):
        raise HTTPException(404, "scripts/setup_autostart.ps1 nu a fost gasit")
    subprocess.Popen([
        "powershell", "-Command",
        f'Start-Process powershell -Verb RunAs -ArgumentList \'-ExecutionPolicy Bypass -File "{script}"\''
    ])
    return {"started": True}


@router.post("/autostart/disable")
def autostart_disable():
    script = os.path.join(ROOT, "scripts", "remove_autostart.ps1")
    if not os.path.exists(script):
        raise HTTPException(404, "scripts/remove_autostart.ps1 nu a fost gasit")
    subprocess.Popen([
        "powershell", "-Command",
        f'Start-Process powershell -Verb RunAs -ArgumentList \'-ExecutionPolicy Bypass -File "{script}"\''
    ])
    return {"started": True}
