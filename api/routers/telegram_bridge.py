"""
Router API pentru Puntea Telegram (telegram_bridge/) — daemon STANDALONE, optional.

Endpoints (mirror al /ai/*):
  GET  /telegram-bridge/status            — running/pid/heartbeat + configured + edit mode
  POST /telegram-bridge/start             — porneste `python -m telegram_bridge` detasat
  POST /telegram-bridge/stop              — taskkill pe PID-ul puntii
  GET  /telegram-bridge/autostart/status  — task-ul TradingBot-TelegramBridge exista?
  POST /telegram-bridge/autostart/enable  — ruleaza setup_autostart_bridge.ps1 (UAC)
  POST /telegram-bridge/autostart/disable — ruleaza remove_autostart_bridge.ps1 (UAC)

IZOLARE: puntea e un proces separat, aditiv — nu atinge botul/motorul/MT5. Acest
router doar o porneste/opreste + citeste starea ei din fisiere (status.json/pid).
"""

import os
import sys
import json
import subprocess
from datetime import datetime

from fastapi import APIRouter, HTTPException, Body

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(ROOT, "data")

router = APIRouter(prefix="/telegram-bridge", tags=["telegram_bridge"])

PID_FILE    = os.path.join(DATA_DIR, "telegram_bridge.pid")
STATUS_FILE = os.path.join(DATA_DIR, "telegram_bridge_status.json")
TG_CFG      = os.path.join(DATA_DIR, "telegram_config.json")
BRIDGE_CFG  = os.path.join(DATA_DIR, "telegram_bridge.json")
MATRIX_CFG  = os.path.join(DATA_DIR, "matrix_config.json")


def _pid_alive(pid: int) -> bool:
    """GetExitCodeProcess (STILL_ACTIVE=259) — identic cu bot.py/ai_engine.py."""
    try:
        import ctypes
        STILL_ACTIVE = 259
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok) and code.value == STILL_ACTIVE
    except Exception:
        return False


def _read_pid() -> int | None:
    try:
        with open(PID_FILE, encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


def _is_configured() -> bool:
    """Puntea are nevoie de token + chat_id Telegram ca sa poata porni."""
    try:
        with open(TG_CFG, encoding="utf-8") as f:
            c = json.load(f)
        return bool((c.get("token") or "").strip() and str(c.get("chat_id") or "").strip())
    except Exception:
        return bool(os.environ.get("TELEGRAM_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


@router.get("/status")
def bridge_status():
    pid = _read_pid()
    running = bool(pid and _pid_alive(pid))
    st = {}
    if os.path.isfile(STATUS_FILE):
        try:
            with open(STATUS_FILE, encoding="utf-8") as f:
                st = json.load(f)
        except Exception:
            st = {}
    # daca fisierul zice running dar pid-ul e mort → reflecta realitatea
    if not running:
        st["running"] = False
    return {
        "running":       running,
        "pid":           pid if running else None,
        "configured":    _is_configured(),
        "ts":            st.get("ts"),
        "idle":          st.get("idle", False),
        "allow_writes":  st.get("allow_writes", False),
        "last_message_ts": st.get("last_message_ts"),
        "level_ai":      st.get("level_ai"),
        "level_claude":  st.get("level_claude"),
        "claude_detected": st.get("claude_detected"),
        "matrix_enabled": st.get("matrix_enabled", False),
    }


@router.post("/start")
def bridge_start():
    if not _is_configured():
        raise HTTPException(400, "Telegram nu e configurat (token + Chat ID). "
                                 "Salveaza-le mai intai in setarile Telegram.")
    pid = _read_pid()
    if pid and _pid_alive(pid):
        raise HTTPException(409, f"Puntea ruleaza deja (PID={pid})")
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        [sys.executable, "-m", "telegram_bridge"], cwd=ROOT, creationflags=flags,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    return {"ok": True, "pid": proc.pid,
            "note": "Puntea porneste; iti trimite un mesaj de start pe Telegram."}


@router.post("/stop")
def bridge_stop():
    pid = _read_pid()
    if not pid or not _pid_alive(pid):
        # curata pid stale + status
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        raise HTTPException(409, "Puntea nu ruleaza")
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                   capture_output=True, text=True)
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    # taskkill /F nu lasa procesul sa scrie status-ul de oprire — o facem noi
    try:
        st = {}
        if os.path.isfile(STATUS_FILE):
            with open(STATUS_FILE, encoding="utf-8") as f:
                st = json.load(f)
        st["running"] = False
        st["ts"] = datetime.now().isoformat(timespec="seconds")
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    return {"ok": True}


# ── Autostart Windows (Task Scheduler) — mirror al /ai/autostart/* ────────────

@router.get("/autostart/status")
def bridge_autostart_status():
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "if (Get-ScheduledTask -TaskName 'TradingBot-TelegramBridge' "
             "-ErrorAction SilentlyContinue) { 'true' } else { 'false' }"],
            capture_output=True, text=True, timeout=10)
        enabled = r.stdout.strip().lower() == "true"
    except Exception:
        enabled = False
    return {"enabled": enabled}


@router.post("/autostart/enable")
def bridge_autostart_enable():
    script = os.path.join(ROOT, "scripts", "setup_autostart_bridge.ps1")
    if not os.path.exists(script):
        raise HTTPException(404, "scripts/setup_autostart_bridge.ps1 nu a fost gasit")
    subprocess.Popen([
        "powershell", "-Command",
        f'Start-Process powershell -Verb RunAs -ArgumentList \'-NoExit -ExecutionPolicy Bypass -File "{script}"\''
    ])
    return {"started": True}


@router.post("/autostart/disable")
def bridge_autostart_disable():
    script = os.path.join(ROOT, "scripts", "remove_autostart_bridge.ps1")
    if not os.path.exists(script):
        raise HTTPException(404, "scripts/remove_autostart_bridge.ps1 nu a fost gasit")
    subprocess.Popen([
        "powershell", "-Command",
        f'Start-Process powershell -Verb RunAs -ArgumentList \'-NoExit -ExecutionPolicy Bypass -File "{script}"\''
    ])
    return {"started": True}


# ── Al doilea canal Matrix — configurare din UI ───────────────────────────────

def _load_bridge_cfg() -> dict:
    try:
        with open(BRIDGE_CFG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _matrix_token() -> str:
    try:
        with open(MATRIX_CFG, encoding="utf-8") as f:
            return (json.load(f).get("access_token") or "").strip()
    except Exception:
        return ""


@router.get("/matrix-config")
def matrix_config_get():
    """Config Matrix curent (token NU e returnat — doar daca e setat)."""
    cfg = _load_bridge_cfg()
    return {
        "enabled":       bool(cfg.get("matrix_enabled")),
        "homeserver":    cfg.get("matrix_homeserver", "https://matrix.org"),
        "room_id":       cfg.get("matrix_room_id", ""),
        "allowed_users": cfg.get("matrix_allowed_users", []),
        "token_set":     bool(_matrix_token()),
    }


@router.put("/matrix-config")
def matrix_config_put(body: dict = Body(...)):
    """
    Salveaza config Matrix: campurile non-secrete in data/telegram_bridge.json,
    access_token in data/matrix_config.json (gitignored). Reporneste puntea manual
    ca sa se aplice. Validare de baza (room_id !camera:homeserver).
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    cfg = _load_bridge_cfg()

    enabled    = bool(body.get("enabled"))
    homeserver = (body.get("homeserver") or "").strip().rstrip("/")
    room_id    = (body.get("room_id") or "").strip()
    allowed    = body.get("allowed_users") or []
    token      = (body.get("access_token") or "").strip()   # gol = pastreaza tokenul existent

    if enabled:
        if not homeserver.startswith("http"):
            raise HTTPException(400, "homeserver trebuie sa fie o adresa http(s) (ex: https://matrix.org)")
        if not room_id.startswith("!"):
            raise HTTPException(400, "room_id trebuie sa fie ID intern de camera (ex: !AbC:matrix.org), NU alias #...")
        if not (token or _matrix_token()):
            raise HTTPException(400, "access_token lipseste (necesar la activare)")

    if isinstance(allowed, str):
        allowed = [x.strip() for x in allowed.split(",") if x.strip()]
    allowed = [str(u).strip() for u in allowed if str(u).strip()]

    cfg["matrix_enabled"]       = enabled
    if homeserver: cfg["matrix_homeserver"] = homeserver
    cfg["matrix_room_id"]       = room_id
    cfg["matrix_allowed_users"] = allowed
    tmp = BRIDGE_CFG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    os.replace(tmp, BRIDGE_CFG)

    if token:
        with open(MATRIX_CFG, "w", encoding="utf-8") as f:
            json.dump({"access_token": token}, f, indent=2)

    pid = _read_pid()
    return {"ok": True, "token_set": bool(token or _matrix_token()),
            "restart_needed": bool(pid and _pid_alive(pid)),
            "note": "Reporneste puntea (Stop -> Start) ca al doilea canal sa se aplice."}
