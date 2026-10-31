"""
Router API pentru Daily Engine (daily_engine/) — motor intraday ORB, mod SHADOW.

  GET  /daily/status   — running/pid/heartbeat + piete (faza zilei) + scorecard
  POST /daily/start    — porneste `python -m daily_engine` detasat
  POST /daily/stop     — taskkill pe PID
  GET  /daily/trades   — trade-urile virtuale inregistrate (cele mai noi primele)
  GET  /daily/config   — configurarea curenta
  GET  /daily/logs     — ultimele N linii din engine.log
"""
import os
import sys
import json
import subprocess

from fastapi import APIRouter, HTTPException

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from daily_engine.config import DATA_DIR, load_config, save_default_config  # noqa: E402
from daily_engine.engine import load_trades, scorecard  # noqa: E402

router = APIRouter(prefix="/daily", tags=["daily_engine"])

PID_FILE = os.path.join(DATA_DIR, "daily_engine.pid")
STATUS_FILE = os.path.join(DATA_DIR, "status.json")
LOG_FILE = os.path.join(DATA_DIR, "engine.log")

# Referinta backtest (docs/DAILY_ENGINE_PLAN.md sect. 8) — afisata langa rezultatele shadow
BACKTEST_REF = {
    "GBPUSD": {"trades": 3974, "expectancy_R": 0.075, "period": "2010–2026", "verdict": "OBSERVE"},
    "US500": {"trades": 2464, "expectancy_R": 0.059, "period": "2017–2026", "verdict": "KEEP"},
}


def _pid_alive(pid: int) -> bool:
    """GetExitCodeProcess — identic cu bot.py / ai_engine.py (OpenProcess singur minte)."""
    try:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok) and code.value == 259
    except Exception:
        return False


def _read_pid() -> int | None:
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return None


@router.get("/status")
def daily_status():
    pid = _read_pid()
    running = pid is not None and _pid_alive(pid)
    st: dict = {}
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        pass
    st["running"] = running
    st["pid"] = pid if running else None
    if not running:
        st["scorecard"] = scorecard(load_trades())   # disponibil si cu motorul oprit
    st["backtest_ref"] = BACKTEST_REF
    st.setdefault("mode", load_config()["mode"])
    return st


@router.post("/start")
def daily_start():
    pid = _read_pid()
    if pid and _pid_alive(pid):
        raise HTTPException(409, f"Daily Engine ruleaza deja (PID={pid})")
    os.makedirs(DATA_DIR, exist_ok=True)
    save_default_config()
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    # stdout/stderr in fisier: o eroare inainte de logging (import, crash) ramane vizibila
    out = open(os.path.join(DATA_DIR, "stdout.log"), "a", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "daily_engine"], cwd=ROOT, creationflags=flags,
                            stdout=out, stderr=subprocess.STDOUT, close_fds=True)
    return {"ok": True, "pid": proc.pid, "note": "Mod SHADOW — trade-uri virtuale, zero ordine reale"}


@router.post("/stop")
def daily_stop():
    pid = _read_pid()
    if not pid or not _pid_alive(pid):
        raise HTTPException(409, "Daily Engine nu ruleaza")
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, text=True)
    for path in (PID_FILE,):
        try:
            os.remove(path)
        except OSError:
            pass
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            st = json.load(f)
        st["running"] = False
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    try:
        from api.telegram import send_message
        send_message("⏹ <b>Daily Engine oprit</b> (din UI)")
    except Exception:
        pass
    return {"ok": True}


@router.get("/trades")
def daily_trades(limit: int = 200):
    return list(reversed(load_trades()))[:max(1, min(limit, 2000))]


@router.get("/config")
def daily_config():
    return load_config()


@router.get("/logs")
def daily_logs(lines: int = 100):
    try:
        with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
            return {"lines": f.readlines()[-max(1, min(lines, 1000)):]}
    except FileNotFoundError:
        return {"lines": []}
