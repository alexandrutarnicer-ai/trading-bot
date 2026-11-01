"""
Router API pentru Noisy Engine (noisy_engine/) — mean reversion (M1 implicit) pe o singura piata,
mod SHADOW (implicit) sau EXECUTIE (DEMO / REAL deblocat in Trading LIVE).

  GET  /noisy/status          — stare (cu motivul), pozitie / semnal, contoare azi, buget, scorecard
  POST /noisy/start           — porneste `python -m noisy_engine` detasat (UI-ul cere confirmare: risc HIGH)
  POST /noisy/stop            — oprire normala
  POST /noisy/emergency-stop  — oprire IMEDIATA (fara AI) + inchide pozitiile REALE Noisy + blocheaza intrarile
  POST /noisy/pause | resume  — fara intrari noi / reluare (hot, fara restart)
  POST /noisy/reset-budget    — reseteaza bugetul (dupa BUDGET LIMIT), doar manual
  GET  /noisy/trades          — trade-urile virtuale (cele mai noi primele)
  GET/PUT /noisy/config       — configurarea (hot-reload)
  GET  /noisy/logs            — ultimele N linii din engine.log
NU are autostart si NU e repornit de watchdog (decizia userului: pornire doar manuala).
"""
import json
import os
import subprocess
import sys
from datetime import datetime

from fastapi import APIRouter, HTTPException

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from noisy_engine.config import CFG_PATH, DATA_DIR, load_config, save_config, save_default_config  # noqa: E402
from noisy_engine.engine import CONTROL_FILE, STATE_FILE, STATES, load_trades, scorecard  # noqa: E402

router = APIRouter(prefix="/noisy", tags=["noisy_engine"])

PID_FILE = os.path.join(DATA_DIR, "noisy_engine.pid")
STATUS_FILE = os.path.join(DATA_DIR, "status.json")
LOG_FILE = os.path.join(DATA_DIR, "engine.log")

# Referinta backtest — ACEEASI functie ca engine-ul (scripts/research_noisy/noisy_backtest.py),
# USDJPY M5, 2025-11-01 → 2026-10-31, configurarea implicita. Shadow-ul se compara cu ea.
BACKTEST_REF_BY_TF = {
    # M1 = implicit (decizia userului: frecventa, nu profit) — ~25 trade-uri / zi in fereastra 10–20
    "M1": {"symbol": "USDJPY", "timeframe": "M1", "period": "2025-11 → 2026-10", "trades": 6510, "per_day": 25.2,
           "win_rate": 0.409, "expectancy_R": -0.010, "gross_R": 0.047, "cost_R": 0.057, "profit_factor": 0.98,
           "max_dd_R": -116.8, "max_loss_streak": 13, "avg_hold_min": 8, "t_stat": -0.66, "test_R": -0.030,
           "pass_criteria": "M1 = test de FRECVENȚĂ: backtestul e ~0 după costuri; urmărim dacă shadow-ul confirmă "
                            "costul real și ritmul (~2–3 trade-uri / oră), nu un profit"},
    "M5": {"symbol": "USDJPY", "timeframe": "M5", "period": "2025-11 → 2026-10", "trades": 1005, "per_day": 3.9,
           "win_rate": 0.441, "expectancy_R": 0.081, "gross_R": 0.102, "cost_R": 0.021, "profit_factor": 1.15,
           "max_dd_R": -31.1, "max_loss_streak": 17, "avg_hold_min": 43, "t_stat": 2.06, "test_R": 0.027,
           "pass_criteria": "≥250 trade-uri shadow, ≥ +0,04R/trade după costuri, 2/3 luni pozitive, "
                            "rezultat în intervalul de încredere 90% al backtestului"},
}


def _pid_alive(pid: int) -> bool:
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


def _read(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _tg(text: str) -> None:
    try:
        from api.telegram import send_message
        send_message(text)
    except Exception:
        pass


@router.get("/status")
def noisy_status():
    pid = _read_pid()
    running = pid is not None and _pid_alive(pid)
    st = _read(STATUS_FILE, {})
    st["running"] = running
    st["pid"] = pid if running else None
    cfg = load_config()
    if not running:
        stop = st.get("stopped_reason")
        st["state"] = "stopped"
        st["state_label"] = STATES["stopped"] + (f" – {stop}" if stop else "")
        st["scorecard"] = scorecard(load_trades())
        st.setdefault("symbol", cfg["symbol"])
    state = _read(STATE_FILE, {})
    st["budget_lock"] = state.get("budget_lock")
    st["paused"] = bool(_read(CONTROL_FILE, {}).get("paused"))
    st["backtest_ref"] = BACKTEST_REF_BY_TF.get(cfg.get("timeframe", "M1"), BACKTEST_REF_BY_TF["M1"])
    st.setdefault("mode", cfg["mode"])
    st["config"] = cfg
    return st


@router.post("/start")
def noisy_start():
    pid = _read_pid()
    if pid and _pid_alive(pid):
        raise HTTPException(409, f"Noisy Engine rulează deja (PID={pid})")
    os.makedirs(DATA_DIR, exist_ok=True)
    save_default_config()
    st = _read(STATUS_FILE, {})
    st.pop("stopped_reason", None)
    st["state"], st["state_label"] = "starting", STATES["starting"]
    _write(STATUS_FILE, st)
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    out = open(os.path.join(DATA_DIR, "stdout.log"), "a", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "noisy_engine"], cwd=ROOT, creationflags=flags,
                            stdout=out, stderr=subprocess.STDOUT, close_fds=True)
    return {"ok": True, "pid": proc.pid, "mode": load_config()["mode"]}


def _close_real(force: bool) -> str:
    """Pozitiile REALE Noisy (magic 990001) la oprire: Emergency Stop = mereu; Stop = doar in EXECUTIE
    cu on_stop = "close". Prin conexiunea MT5 a API-ului (mt5_pool), independent de procesul engine-ului."""
    cfg = load_config()
    if not force and (cfg["mode"] != "execute" or cfg.get("on_stop", "close") != "close"):
        return ""
    try:
        from api import mt5_pool
        from noisy_engine import executor as X
        with mt5_pool._LOCK:
            mt5 = mt5_pool._ensure_mt5()
            ok, bad = X.close_all(mt5, cfg["symbol"])
        if not ok and not bad:
            return ""
        return f" · {ok} poziții Noisy închise" + (f", {bad} EȘUATE — verifică MT5!" if bad else "")
    except Exception as e:
        return f" · ⚠️ închiderea pozițiilor Noisy a eșuat: {e}"


def _kill(reason: str) -> bool:
    pid = _read_pid()
    if not pid or not _pid_alive(pid):
        return False
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, text=True)
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    st = _read(STATUS_FILE, {})
    st.update(running=False, state="stopped", stopped_reason=reason, state_label=f"{STATES['stopped']} – {reason}",
              stopped_at=datetime.now().isoformat(timespec="seconds"))
    _write(STATUS_FILE, st)
    return True


@router.post("/stop")
def noisy_stop():
    if not _kill("manual"):
        raise HTTPException(409, "Noisy Engine nu rulează")
    closed = _close_real(force=False)
    _tg("⏹ <b>Noisy Engine oprit</b> (din UI)" + closed)
    return {"ok": True, "positions": closed.strip(" ·")}


@router.post("/emergency-stop")
def noisy_emergency_stop():
    """Oprire IMEDIATA, independenta de AI: oprește procesul, ÎNCHIDE pozițiile reale Noisy (mereu) și
    blochează intrările până la Resume."""
    stopped = _kill("Emergency Stop")
    _write(CONTROL_FILE, {**_read(CONTROL_FILE, {}), "paused": True})   # si la repornire: fara intrari pana la Resume
    closed = _close_real(force=True)
    _tg("🛑 <b>Noisy Engine — EMERGENCY STOP</b>" + ("" if stopped else " (nu rula)") + closed
        + "\nIntrările noi rămân blocate până la Resume.")
    return {"ok": True, "was_running": stopped, "positions": closed.strip(" ·")}


@router.post("/pause")
def noisy_pause():
    _write(CONTROL_FILE, {**_read(CONTROL_FILE, {}), "paused": True})
    _tg("⏸ <b>Noisy Engine pe pauză</b> — fără intrări noi")
    return {"ok": True, "paused": True}


@router.post("/resume")
def noisy_resume():
    _write(CONTROL_FILE, {**_read(CONTROL_FILE, {}), "paused": False})
    _tg("▶️ <b>Noisy Engine reluat</b>")
    return {"ok": True, "paused": False}


@router.post("/reset-budget")
def noisy_reset_budget():
    """Bugetul se socoteste de acum: P&L-ul trade-urilor dinainte nu mai conteaza, blocarea dispare."""
    state = _read(STATE_FILE, {})
    before = state.get("budget_lock")
    state["budget_lock"] = None
    state["budget_reset_at"] = datetime.now().isoformat(timespec="seconds")
    _write(STATE_FILE, state)
    _tg("♻️ <b>Noisy Engine — buget resetat</b>" + (" (era blocat)" if before else ""))
    return {"ok": True, "reset_at": state["budget_reset_at"]}


@router.get("/trades")
def noisy_trades(limit: int = 200):
    return list(reversed(load_trades()))[:max(1, min(limit, 5000))]


@router.get("/config")
def noisy_config():
    return load_config()


@router.put("/config")
def noisy_config_save(body: dict):
    """Merge partial peste configurarea curenta (hot-reload la iteratia urmatoare)."""
    cur = load_config()
    before = cur["mode"]

    def merge(a, b):
        for k, v in b.items():
            if isinstance(v, dict) and isinstance(a.get(k), dict):
                merge(a[k], v)
            else:
                a[k] = v
        return a
    clean = save_config(merge(cur, body or {}))
    if clean["mode"] != before:
        _tg("🟢 <b>Noisy Engine — mod EXECUȚIE</b>\nOrdine reale de la următorul semnal (DEMO, sau REAL dacă e "
            "deblocat în Settings → Trading LIVE → Noisy Engine)." if clean["mode"] == "execute" else
            "🧪 <b>Noisy Engine — mod SHADOW</b>\nFără ordine noi; trade-uri virtuale.")
    return clean


@router.get("/logs")
def noisy_logs(lines: int = 100):
    try:
        with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
            return {"lines": f.readlines()[-max(1, min(lines, 1000)):]}
    except FileNotFoundError:
        return {"lines": []}
