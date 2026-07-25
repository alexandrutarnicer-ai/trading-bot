"""
Router API pentru EMA — asistentul vocal (voice_bridge/) — daemon STANDALONE, optional.

Endpoints (mirror al /telegram-bridge/*):
  GET  /voice-bridge/status   — running/pid/paused/mode + heartbeat
  POST /voice-bridge/start    — porneste `python -m voice_bridge` detasat
  POST /voice-bridge/stop     — taskkill pe PID-ul lui EMA
  POST /voice-bridge/pause    — pune EMA pe pauza/mut (microfon oprit; ex: pe Discord)
  POST /voice-bridge/resume   — scoate EMA din pauza

IZOLARE: EMA e un proces separat, aditiv, READ-ONLY — nu atinge botul/motorul/MT5.
Acest router doar o porneste/opreste/mut + citeste starea ei din fisiere. Pauza se
face scriind un flag (data/voice_bridge_control.json), pe care bucla lui EMA il
citeste la fiecare iteratie (efect in ~1s, fara restart).
"""

import os
import sys
import json
import subprocess
from datetime import datetime

from fastapi import APIRouter, HTTPException, Body

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(ROOT, "data")

router = APIRouter(prefix="/voice-bridge", tags=["voice_bridge"])

PID_FILE     = os.path.join(DATA_DIR, "voice_bridge.pid")
STATUS_FILE  = os.path.join(DATA_DIR, "voice_bridge_status.json")
CONTROL_FILE = os.path.join(DATA_DIR, "voice_bridge_control.json")


def _pid_alive(pid: int) -> bool:
    """GetExitCodeProcess (STILL_ACTIVE=259) — identic cu bot.py/telegram_bridge.py."""
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


def _read_control() -> dict:
    try:
        with open(CONTROL_FILE, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _write_control(d: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = CONTROL_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, CONTROL_FILE)


@router.get("/status")
def voice_status():
    pid = _read_pid()
    running = bool(pid and _pid_alive(pid))
    st = {}
    if os.path.isfile(STATUS_FILE):
        try:
            with open(STATUS_FILE, encoding="utf-8") as f:
                st = json.load(f)
        except Exception:
            st = {}
    if not running:
        st["running"] = False
    return {
        "running":        running,
        "pid":            pid if running else None,
        "paused":         bool(_read_control().get("paused")),
        "assistant_name": st.get("assistant_name", "EMA"),
        "mode":           st.get("mode"),            # "wake" / "ptt"
        "listening":      st.get("listening", False),
        "voice_style":    st.get("voice_style"),
        "stt_model":      st.get("stt_model"),
        "read_only":      True,
        "ts":             st.get("ts"),
    }


@router.post("/start")
def voice_start():
    pid = _read_pid()
    if pid and _pid_alive(pid):
        raise HTTPException(409, f"EMA ruleaza deja (PID={pid})")
    # porneste curata (scoate un eventual flag de pauza vechi)
    _write_control({"paused": False})
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        [sys.executable, "-m", "voice_bridge"], cwd=ROOT, creationflags=flags,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    return {"ok": True, "pid": proc.pid,
            "note": "EMA porneste. Daca dependintele lipsesc, ruleaza setup_voice_bridge.bat."}


@router.post("/stop")
def voice_stop():
    pid = _read_pid()
    if not pid or not _pid_alive(pid):
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        raise HTTPException(409, "EMA nu ruleaza")
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


CFG_FILE = os.path.join(DATA_DIR, "voice_bridge.json")
_ALLOWED_WAKE = {"openwakeword", "ptt", "name"}
_ALLOWED_LANG = {"en", "ro"}


def _read_cfg_file() -> dict:
    try:
        with open(CFG_FILE, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


@router.get("/config")
def voice_config_get():
    """Setari editabile din UI (restul raman default in cod)."""
    c = _read_cfg_file()
    return {
        "wake_mode": c.get("wake_mode", "openwakeword"),
        "language":  c.get("language", "en"),
    }


@router.put("/config")
def voice_config_put(body: dict = Body(...)):
    """Salveaza wake_mode / language in data/voice_bridge.json. Se aplica la
    urmatoarea pornire a lui Jarvis (Stop -> Start)."""
    c = _read_cfg_file()
    wake = (body.get("wake_mode") or "").strip().lower()
    lang = (body.get("language") or "").strip().lower()
    if wake:
        if wake not in _ALLOWED_WAKE:
            raise HTTPException(400, f"wake_mode invalid (permise: {sorted(_ALLOWED_WAKE)})")
        c["wake_mode"] = wake
    if lang:
        if lang not in _ALLOWED_LANG:
            raise HTTPException(400, "language trebuie sa fie 'en' sau 'ro'")
        c["language"] = lang
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = CFG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CFG_FILE)
    pid = _read_pid()
    return {"ok": True, "wake_mode": c.get("wake_mode"), "language": c.get("language"),
            "restart_needed": bool(pid and _pid_alive(pid)),
            "note": "Se aplica la urmatoarea pornire (Stop -> Start)."}


@router.post("/pause")
def voice_pause():
    """Mut EMA fara sa opresti procesul (microfon oprit) — ex: cand esti pe Discord."""
    d = _read_control()
    d["paused"] = True
    _write_control(d)
    return {"ok": True, "paused": True,
            "note": "EMA nu mai asculta. Efect in ~1s (fara restart)."}


@router.post("/resume")
def voice_resume():
    d = _read_control()
    d["paused"] = False
    _write_control(d)
    return {"ok": True, "paused": False, "note": "EMA asculta din nou."}


# ── Autostart Windows (Task Scheduler) — mirror al /telegram-bridge/autostart/* ──

@router.get("/autostart/status")
def voice_autostart_status():
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "if (Get-ScheduledTask -TaskName 'TradingBot-VoiceEMA' "
             "-ErrorAction SilentlyContinue) { 'true' } else { 'false' }"],
            capture_output=True, text=True, timeout=10)
        enabled = r.stdout.strip().lower() == "true"
    except Exception:
        enabled = False
    return {"enabled": enabled}


@router.post("/autostart/enable")
def voice_autostart_enable():
    script = os.path.join(ROOT, "scripts", "setup_autostart_voice.ps1")
    if not os.path.exists(script):
        raise HTTPException(404, "scripts/setup_autostart_voice.ps1 nu a fost gasit")
    subprocess.Popen([
        "powershell", "-Command",
        f'Start-Process powershell -Verb RunAs -ArgumentList \'-NoExit -ExecutionPolicy Bypass -File "{script}"\''
    ])
    return {"started": True}


@router.post("/autostart/disable")
def voice_autostart_disable():
    script = os.path.join(ROOT, "scripts", "remove_autostart_voice.ps1")
    if not os.path.exists(script):
        raise HTTPException(404, "scripts/remove_autostart_voice.ps1 nu a fost gasit")
    subprocess.Popen([
        "powershell", "-Command",
        f'Start-Process powershell -Verb RunAs -ArgumentList \'-NoExit -ExecutionPolicy Bypass -File "{script}"\''
    ])
    return {"started": True}
