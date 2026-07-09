"""
Router API pentru AI Engine — motorul de trading autonom AI (ai_engine/).

Endpoints:
  GET  /ai/status      — running/pid/heartbeat + scorecard + erori recente
  POST /ai/start       — porneste `python -m ai_engine` ca proces detasat
  POST /ai/stop        — taskkill pe PID-ul motorului
  GET  /ai/decisions   — ultimele decizii (cu rationale)
  GET  /ai/council/{decision_id} — transcriptul complet al consiliului
  GET  /ai/outcomes    — rezultatele deciziilor executate
  GET  /ai/config      — configurarea curenta (piete, model, mode, risc)
  PUT  /ai/config      — actualizeaza pietele/mode (validate contra MT5)
  GET  /ai/logs        — ultimele N linii din engine.log

Cititul din ledger foloseste conexiuni SQLite proprii per-request (read-only),
ca sa nu tina lock pe DB-ul motorului.
"""

import os
import sys
import json
import sqlite3
import subprocess
import threading
from datetime import datetime

from fastapi import APIRouter, HTTPException, Body

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from ai_engine.config import CFG_PATH, AI_DATA, load_config, save_default_config

router = APIRouter(prefix="/ai", tags=["ai_engine"])

PID_FILE    = os.path.join(AI_DATA, "ai_engine.pid")
WD_PID_FILE = os.path.join(AI_DATA, "watchdog.pid")
STATUS_FILE = os.path.join(AI_DATA, "status.json")
LOG_FILE    = os.path.join(AI_DATA, "engine.log")
DB_FILE     = os.path.join(AI_DATA, "ledger.db")


def _pid_alive(pid: int) -> bool:
    """GetExitCodeProcess — identic cu bot.py (OpenProcess singur minte)."""
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
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return None


def _db() -> sqlite3.Connection:
    if not os.path.isfile(DB_FILE):
        raise HTTPException(404, "Ledger-ul AI nu exista inca (motorul nu a rulat)")
    return sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)


# ── Status / Start / Stop ─────────────────────────────────────────────────────

@router.get("/status")
def ai_status():
    pid = _read_pid()
    running = pid is not None and _pid_alive(pid)
    status: dict = {}
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            status = json.load(f)
    except Exception:
        pass
    # PID-ul e sursa de adevar pentru running (status.json poate fi stale la crash)
    status["running"] = running
    status["pid"] = pid if running else None
    if not running and status.get("scorecard") is None and os.path.isfile(DB_FILE):
        # scorecard disponibil si cu motorul oprit
        try:
            con = _db()
            row = con.execute(
                "SELECT COUNT(*), COALESCE(SUM(result_r),0), COALESCE(AVG(result_r),0), "
                "SUM(CASE WHEN result_r>0 THEN 1 ELSE 0 END) FROM outcomes "
                "WHERE result_r IS NOT NULL").fetchone()
            n, tot, avg, w = row
            n_dec = con.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
            n_wait = con.execute("SELECT COUNT(*) FROM decisions WHERE action='WAIT'").fetchone()[0]
            status["scorecard"] = {
                "decisions": n_dec, "waits": n_wait, "closed_trades": n,
                "total_R": round(tot, 2), "expectancy_R": round(avg, 3),
                "win_rate": round(w / n, 3) if n else None}
            con.close()
        except HTTPException:
            pass
    return status


def _read_wd_pid() -> int | None:
    try:
        with open(WD_PID_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return None


@router.post("/start")
def ai_start():
    pid = _read_pid()
    if pid and _pid_alive(pid):
        raise HTTPException(409, f"AI Engine ruleaza deja (PID={pid})")
    save_default_config()
    _flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        [sys.executable, "-m", "ai_engine"], cwd=ROOT, creationflags=_flags,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    # porneste si watchdog-ul (anti-crash overnight) — idempotent, iese daca exista
    wd = _read_wd_pid()
    if not (wd and _pid_alive(wd)):
        subprocess.Popen(
            [sys.executable, "-m", "ai_engine.watchdog"], cwd=ROOT, creationflags=_flags,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    return {"ok": True, "pid": proc.pid,
            "note": "Motorul verifica singur DEMO + Ollama la pornire; vezi /ai/logs"}


@router.post("/stop")
def ai_stop():
    pid = _read_pid()
    if not pid or not _pid_alive(pid):
        raise HTTPException(409, "AI Engine nu ruleaza")
    # INTAI watchdog-ul — altfel reporneste motorul in ≤5 min dupa stop
    wd = _read_wd_pid()
    if wd and _pid_alive(wd):
        subprocess.run(["taskkill", "/F", "/PID", str(wd)], capture_output=True, text=True)
        try:
            os.remove(WD_PID_FILE)
        except OSError:
            pass
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                   capture_output=True, text=True)
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    # taskkill /F nu lasa procesul sa-si scrie status-ul de oprire — o facem noi
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

    def _notify():
        try:
            from api.telegram import send_message
            send_message("🤖 AI Engine <b>oprit</b> din dashboard.")
        except Exception:
            pass
    threading.Thread(target=_notify, daemon=True).start()
    return {"ok": True}


# ── Date din ledger ───────────────────────────────────────────────────────────

@router.get("/decisions")
def ai_decisions(limit: int = 30):
    con = _db()
    rows = con.execute(
        "SELECT id, ts, symbol, action, order_type, entry, sl, tp, risk_pct, "
        "confidence, rationale, exec_status, exec_detail, ticket, council_id "
        "FROM decisions ORDER BY id DESC LIMIT ?", (min(limit, 200),)).fetchall()
    cols = ["id", "ts", "symbol", "action", "order_type", "entry", "sl", "tp",
            "risk_pct", "confidence", "rationale", "exec_status", "exec_detail",
            "ticket", "council_id"]
    out = [dict(zip(cols, r)) for r in rows]
    # ataseaza outcome-ul daca exista
    for d in out:
        o = con.execute(
            "SELECT status, exit_price, result_r, pnl_usd FROM outcomes "
            "WHERE decision_id=? ORDER BY id DESC LIMIT 1", (d["id"],)).fetchone()
        d["outcome"] = (dict(zip(["status", "exit_price", "result_r", "pnl_usd"], o))
                        if o else None)
    con.close()
    return out


@router.get("/council/{decision_id}")
def ai_council(decision_id: int):
    con = _db()
    row = con.execute(
        "SELECT c.id, c.ts, c.symbol, c.trigger, c.transcript, c.duration_s "
        "FROM councils c JOIN decisions d ON d.council_id = c.id WHERE d.id=?",
        (decision_id,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(404, "Consiliu negasit pentru decizia data")
    cid, ts, sym, trig, transcript, dur = row
    try:
        transcript = json.loads(transcript)
    except Exception:
        pass
    return {"council_id": cid, "ts": ts, "symbol": sym, "trigger": trig,
            "duration_s": dur, "transcript": transcript}


@router.get("/outcomes")
def ai_outcomes(limit: int = 50):
    con = _db()
    rows = con.execute(
        "SELECT o.ts, o.symbol, o.status, o.exit_price, o.result_r, o.pnl_usd, "
        "o.decision_id FROM outcomes o ORDER BY o.id DESC LIMIT ?",
        (min(limit, 200),)).fetchall()
    con.close()
    cols = ["ts", "symbol", "status", "exit_price", "result_r", "pnl_usd", "decision_id"]
    return [dict(zip(cols, r)) for r in rows]


# ── Config ────────────────────────────────────────────────────────────────────

@router.get("/config")
def ai_get_config():
    return load_config()


@router.put("/config")
def ai_put_config(body: dict = Body(...)):
    """Actualizeaza doar campurile editabile din UI. Pietele se valideaza in MT5."""
    editable = {"markets", "mode", "model", "risk_pct_default",
                "heartbeat_hours", "council_cooldown_min"}
    updates = {k: v for k, v in (body or {}).items() if k in editable}
    if not updates:
        raise HTTPException(400, "Niciun camp editabil in body")

    if "markets" in updates:
        mkts = updates["markets"]
        if not isinstance(mkts, list) or not (1 <= len(mkts) <= 10):
            raise HTTPException(400, "markets: lista de 1-10 simboluri")
        mkts = [str(m).strip().upper() for m in mkts if str(m).strip()]
        # validare contra MT5 (daca terminalul e disponibil)
        invalid = []
        try:
            import MetaTrader5 as mt5
            if mt5.initialize():
                for m in mkts:
                    if not mt5.symbol_select(m, True):
                        invalid.append(m)
                mt5.shutdown()
        except Exception:
            pass   # MT5 inchis — acceptam, motorul valideaza la pornire
        if invalid:
            raise HTTPException(400, f"Simboluri inexistente in MT5: {', '.join(invalid)}")
        updates["markets"] = mkts

    if "mode" in updates and updates["mode"] not in ("demo", "shadow"):
        raise HTTPException(400, "mode: 'demo' sau 'shadow'")

    save_default_config()
    with open(CFG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.update(updates)
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

    pid = _read_pid()
    restart_needed = pid is not None and _pid_alive(pid)
    return {"ok": True, "config": load_config(),
            "restart_needed": restart_needed,
            "note": "Motorul citeste config la pornire — restart necesar" if restart_needed else ""}


@router.get("/logs")
def ai_logs(lines: int = 100):
    if not os.path.isfile(LOG_FILE):
        return {"lines": []}
    try:
        with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        return {"lines": [ln.rstrip() for ln in all_lines[-min(lines, 500):]]}
    except Exception as e:
        raise HTTPException(500, f"Nu pot citi log-ul: {e}")
