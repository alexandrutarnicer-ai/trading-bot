"""Special Engine — API (DOAR shadow). Mirror al /daily/*: status / start / stop / trades / selection / config / logs."""
from __future__ import annotations

import json
import os
import subprocess
import sys

from fastapi import APIRouter, HTTPException

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from special_engine.config import DATA_DIR, load_config, save_config  # noqa: E402

router = APIRouter(prefix="/special", tags=["special-engine"])
PID_FILE = os.path.join(DATA_DIR, "special_engine.pid")
STATUS_FILE = os.path.join(DATA_DIR, "status.json")
TRADES_FILE = os.path.join(DATA_DIR, "trades.jsonl")
SELECTION_FILE = os.path.join(DATA_DIR, "selection.json")
LOG_FILE = os.path.join(DATA_DIR, "engine.log")
DESIRED_FILE = os.path.join(DATA_DIR, "desired_running.json")   # = special_engine/engine.py::DESIRED_FILE


def _audit(action: str, detail: str, **kw) -> None:
    try:
        from api import audit_log
        audit_log.record("special", action, detail, **kw)
    except Exception:
        pass


def _tg(text: str) -> None:
    try:
        from api.telegram import send_message
        import threading
        threading.Thread(target=send_message, args=(text,), daemon=True).start()
    except Exception:
        pass

# Validarea din cercetare (scripts/research_special/validate_special.py, walk-forward out-of-sample, costuri incluse)
RESEARCH_REF = {
    "A": {"label": "Adaptiv NR4 (walk-forward 36 luni, t ≥ 1,5)", "trades_per_month": 13.6, "expectancy_R": 0.101,
          "test_R": 0.129, "max_dd_R": -34.5, "pct_months_pos": 56.0, "month_pct_at_05": 0.69, "dd_pct_at_05": -13.7,
          "verdict": "KEEP", "period": "2018–2026"},
    "B": {"label": "Noise area USTEC (Zarattini 2024)", "trades_per_month": 20.0, "expectancy_R": 0.064, "test_R": 0.022,
          "max_dd_R": -25.6, "pct_months_pos": 60.3, "month_pct_at_05": 0.64, "dd_pct_at_05": -11.7, "verdict": "KEEP",
          "period": "2021–2026", "note": "cost de cercetare pesimist (spread de seară); la spread-ul sesiunii NY ≈ +0,084R"},
    "AB": {"label": "A + B", "trades_per_month": 27.0, "expectancy_R": 0.083, "test_R": 0.048, "max_dd_R": -40.5,
           "pct_months_pos": 58.4, "month_pct_at_05": 1.12, "dd_pct_at_05": -16.0, "verdict": "KEEP", "period": "2018–2026",
           "mc_year_median_pct": 13.1, "mc_p_year_negative": 18.3},
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


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


@router.get("/status")
def special_status():
    from special_engine.engine import load_trades, scorecard
    pid = _read_pid()
    running = pid is not None and _pid_alive(pid)
    st = _read(STATUS_FILE, {})
    st["running"] = running
    st["pid"] = pid if running else None
    if not running:
        st["scorecard"] = scorecard(load_trades())
        st["selection"] = _read(SELECTION_FILE, {})
    st["research"] = RESEARCH_REF
    cfg = st["config"] = load_config()
    if not running or not st.get("markets"):
        from special_engine.config import market_mode
        syms = {c.split(":")[1] for c in ((st.get("selection") or {}).get("components") or [])}
        if cfg["strategy_b"]["enabled"]:
            syms.add(cfg["strategy_b"]["symbol"])
        syms |= set(cfg.get("markets") or {})
        st["markets"] = {s: market_mode(cfg, s) for s in sorted(syms)}
    return st


@router.post("/start")
def special_start():
    pid = _read_pid()
    if pid and _pid_alive(pid):
        raise HTTPException(409, f"Special Engine rulează deja (PID={pid})")
    os.makedirs(DATA_DIR, exist_ok=True)
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    out = open(os.path.join(DATA_DIR, "stdout.log"), "a", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "special_engine"], cwd=ROOT, creationflags=flags,
                            stdout=out, stderr=subprocess.STDOUT, close_fds=True)
    _audit("start", f"pornit (PID {proc.pid})")
    return {"ok": True, "pid": proc.pid, "note": "modul fiecărei piețe: Live / Shadow / Pauză (implicit Shadow)"}


@router.post("/stop")
def special_stop():
    pid = _read_pid()
    if not pid or not _pid_alive(pid):
        raise HTTPException(409, "Special Engine nu rulează")
    try:
        os.remove(DESIRED_FILE)            # INAINTE de kill: watchdog-ul nu-l reporneste (oprire voita)
    except OSError:
        pass
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, text=True)
    _audit("stop", "oprit din UI")
    _tg("⏹ <b>Special Engine oprit</b> (din UI). Pozițiile reale deschise (dacă există) rămân cu SL-ul lor; "
        "la repornire se închid la finalul sesiunii / dacă sunt din altă zi.")
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    return {"ok": True}


@router.get("/trades")
def special_trades(limit: int = 300):
    """Trade-urile + momentele in ora bursei SI in fusul aplicatiei + observat live / reconstituit (doar afisare)."""
    from special_engine.engine import annotate_trade, load_trades
    try:
        from tz_helper import get_configured_tz_name
        app_tz = get_configured_tz_name()
    except Exception:
        app_tz = "Europe/Bucharest"
    return {"trades": [annotate_trade(t, app_tz) for t in load_trades()[-max(1, min(limit, 5000)):][::-1]]}


@router.get("/selection")
def special_selection():
    return _read(SELECTION_FILE, {})


@router.post("/selection/refresh")
def special_selection_refresh():
    """Recalculeaza selectia trimestrului curent la urmatoarea iteratie (sterge cache-ul; engine-ul o reface ~30 s)."""
    sel = _read(SELECTION_FILE, {})
    if sel:
        sel["quarter"] = None
        with open(SELECTION_FILE, "w", encoding="utf-8") as f:
            json.dump(sel, f, indent=1)
    return {"ok": True, "note": "selecția se recalculează la următoarea iterație (engine pornit)"}


_SETTING_LABELS = {"risk_pct": ("risc / trade", 100, "%"), "max_open_risk_pct": ("risc total deschis", 100, "%"),
                   "max_positions": ("poziții simultane", 1, ""), "max_margin_pct": ("marjă maximă", 1, "% din equity"),
                   "noise_stop_mult": ("SL de protecție B", 1, "× unitatea R")}


@router.put("/config")
def special_config(body: dict):
    """Setarile PROPRII ale Special Engine (capital, risc, limite, notificari, strategii). Setarile Globale nu se
    modifica de aici — se aplica peste acestea („cea mai stricta castiga”)."""
    body = body or {}
    cur = load_config()
    before = dict(cur)
    for k in ("notify_telegram", "notify_trades", "risk_pct", "poll_seconds", "max_open_risk_pct", "max_positions",
              "max_margin_pct", "noise_stop_mult"):
        if k in body:
            cur[k] = body[k]
    if isinstance(body.get("capital"), dict):
        cur["capital"] = {**cur["capital"], **body["capital"]}
    for sec in ("strategy_a", "strategy_b"):
        if isinstance(body.get(sec), dict):
            cur[sec] = {**cur[sec], **body[sec]}
    clean = save_config(cur)
    changes = []
    for k, (lbl, mul, unit) in _SETTING_LABELS.items():
        if before.get(k) != clean.get(k):
            changes.append(f"{lbl}: {before.get(k) * mul:g}{unit} → {clean.get(k) * mul:g}{unit}")
    if before.get("capital") != clean.get("capital"):
        c = clean["capital"]
        changes.append("capital: " + ("equity MT5" if c["capital_sync_mt5"] else f"fix {c['capital_usd']} $")
                       + f" × {c['fraction'] * 100:.0f}%")
    if changes:
        for ch in changes:
            _audit("config", ch)
        _tg("⚙️ <b>Special Engine — configurare</b>\n" + "\n".join(changes) + "\nSe aplică de la următoarea iterație.")
    return clean


@router.post("/markets/{symbol}/mode")
def special_market_mode(symbol: str, body: dict):
    """Modul unei PIETE: live (ordine reale — pe cont real doar cu Special Engine deblocat in Trading LIVE) /
    shadow (virtual) / pause (fara intrari noi; pozitiile existente raman gestionate). Cealalta piata nu e atinsa."""
    from datetime import datetime as _dt, timezone as _tz
    from special_engine.config import NOISE_MARKETS, ORB_MARKETS, market_mode
    sym = str(symbol or "").upper()
    if sym not in set(ORB_MARKETS) | set(NOISE_MARKETS):
        raise HTTPException(400, f"piață necunoscută în Special Engine: {sym}")
    mode = str((body or {}).get("mode") or "").lower()
    if mode not in ("live", "shadow", "pause"):
        raise HTTPException(400, "mode: una din live / shadow / pause")
    cur = load_config()
    before = market_mode(cur, sym)
    if before == mode:
        return {"ok": True, "symbol": sym, "mode": mode, "changed": False}
    cur["markets"] = {**cur.get("markets", {}), sym: {
        "mode": mode, "paused_at": _dt.now(_tz.utc).isoformat(timespec="seconds") if mode == "pause" else None}}
    save_config(cur)
    _audit("mode", f"{sym}: {before} → {mode}", market=sym, before=before, after=mode)
    _tg({"live": f"🟢 <b>Special Engine — {sym} pe LIVE</b>\nOrdine reale de la următorul semnal (dacă Trading LIVE e "
                 "deblocat pentru Special Engine; altfel rămâne fără ordine).",
         "shadow": f"🧪 <b>Special Engine — {sym} pe SHADOW</b>\nFără ordine noi; o poziție reală deschisă rămâne "
                   "gestionată până la ieșirea strategiei / finalul sesiunii.",
         "pause": f"⏸ <b>Special Engine — {sym} PE PAUZĂ</b>\nFără intrări noi; pozițiile deschise rămân gestionate."}[mode])
    return {"ok": True, "symbol": sym, "mode": mode, "changed": True}


@router.get("/logs")
def special_logs(lines: int = 150):
    try:
        with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
            return {"lines": f.readlines()[-max(1, min(lines, 1000)):]}
    except FileNotFoundError:
        return {"lines": []}
