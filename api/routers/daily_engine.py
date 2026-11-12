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
# Starea DORITA: scrisa de engine la pornire (orice cale: UI, autostart, manual), stearsa DOAR de
# Stop-ul din UI. Watchdog-ul API (api/watchdog.py) reporneste engine-ul daca procesul moare
# fara Stop. Tinut sincron cu daily_engine/engine.py::DESIRED_FILE.
DESIRED_FILE = os.path.join(DATA_DIR, "desired_running.json")

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
    st["backtest_ref"] = BACKTEST_REF            # referinta istorica din cercetare (doc) — doar pentru pietele ei
    _cfg = load_config()
    try:                                          # backtest legat de configuratia EXACTA (porneste singur daca lipseste)
        from api.backtest_refresh import daily_ensure
        st["backtest_auto"] = daily_ensure(_cfg)
    except Exception as e:                        # noqa: BLE001 — statusul nu cade din cauza backtestului
        st["backtest_auto"] = [{"status": "failed", "error": f"{type(e).__name__}: {e}"}]
    st.setdefault("mode", _cfg["mode"])
    st.setdefault("sizing", _cfg.get("sizing"))
    return st


# ── schimbarea pietei unui slot (dimineata / dupa-amiaza) ─────────────────────────────────────────────────────

def _mt5_read():
    """MT5 din pool-ul API-ului (doar CITIRE, lock global)."""
    from api import mt5_pool
    return mt5_pool._LOCK, mt5_pool._ensure_mt5


def _proposed_market(slot_m: dict, body: dict) -> dict:
    """Piata propusa pentru slot: sablonul bursei (ora / interval / mod testate) + simbolul; restul (rr, re-intrari)
    raman ale slotului daca nu sunt trimise."""
    from daily_engine.market_tools import PRESETS
    from daily_engine.config import sanitize_reentry, sanitize_rr
    preset = body.get("preset") or slot_m.get("preset")
    if preset not in PRESETS:
        raise HTTPException(400, f"bursă necunoscută: {preset} (una din {list(PRESETS)})")
    p = PRESETS[preset]
    sym = str(body.get("symbol") or slot_m["symbol"]).strip().upper()
    m = {**slot_m, "symbol": sym, "preset": preset, "tz": p["tz"], "open": p["open"], "last_bar": p["last_bar"],
         "or_minutes": int(body.get("or_minutes") or p["or_minutes"]), "entry": body.get("entry") or p["entry"],
         "label": f"{'Dimineața' if p['tz'] != 'America/New_York' else 'După-amiaza'} — {p['label']}"}
    if m["entry"] not in ("breakout", "direction") or m["or_minutes"] % 5 or not 5 <= m["or_minutes"] <= 120:
        raise HTTPException(400, "interval de deschidere 5–120 min (multiplu de 5) și mod breakout / direction")
    if "rr" in body:
        m["rr"] = sanitize_rr(body["rr"])
    if "reentry" in body:
        m["reentry"] = sanitize_reentry(body["reentry"])
    return m


def _market_check(mt5, m: dict, costs_mode: str, slip=None, comm=None) -> dict:
    """Simbol existent + tranzactionabil, costuri (auto din MT5 sau manuale), marja la lotul minim."""
    from daily_engine.market_tools import estimate_costs
    sym = m["symbol"]
    if not mt5.symbol_select(sym, True) or mt5.symbol_info(sym) is None:
        raise HTTPException(400, f"simbolul {sym} nu există în contul MT5 curent")
    info, tick = mt5.symbol_info(sym), mt5.symbol_info_tick(sym)
    if getattr(info, "trade_mode", 4) != getattr(mt5, "SYMBOL_TRADE_MODE_FULL", 4):
        raise HTTPException(400, f"{sym} nu e tranzacționabil (dezactivat / doar închidere)")
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 20000)
    import pandas as _pd
    costs = estimate_costs(mt5, sym, _pd.DataFrame(rates)["spread"] if rates is not None and len(rates) else None)
    if not costs.get("ok"):
        raise HTTPException(400, costs.get("detail"))
    if costs_mode == "manual":
        costs = {**costs, "slip": float(slip if slip is not None else m.get("slip", costs["slip"])),
                 "comm": float(comm if comm is not None else m.get("comm", costs["comm"]))}
    margin = None
    try:
        margin = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, sym, info.volume_min, tick.ask)
    except Exception:
        pass
    return {"costs": costs, "costs_mode": costs_mode, "volume_min": info.volume_min,
            "margin_min_lot": None if margin is None else round(margin, 2),
            "description": getattr(info, "description", "")}


def _slot_busy(symbol: str) -> str | None:
    """Slotul are o pozitie (virtuala sau reala) deschisa azi → nu se schimba piata."""
    pid = _read_pid()
    if pid is None or not _pid_alive(pid):
        return None
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        return None
    for m in st.get("markets", []):
        if m.get("symbol") == symbol and m.get("phase") in ("in_position", "waiting_entry"):
            return f"{symbol} are azi o poziție / un ordin în curs ({m.get('phase')}) — schimbă piața după închidere sau oprește engine-ul"
    return None


@router.get("/presets")
def daily_presets():
    from daily_engine.market_tools import PRESETS, SLOTS
    return {"presets": PRESETS, "slots": list(SLOTS)}


@router.post("/market-preview")
def daily_market_preview(body: dict):
    """Ce ar insemna piata propusa pentru slot: costuri auto, marja la lotul minim si backtest rapid (~3 ani, MT5,
    aceeasi functie ca engine-ul). Nu salveaza nimic."""
    from daily_engine.market_tools import backtest_rates
    cfg = load_config()
    slot = int(body.get("slot", 0))
    if not 0 <= slot < len(cfg["markets"]):
        raise HTTPException(400, "slot invalid")
    m = _proposed_market(cfg["markets"][slot], body)
    lock, ensure = _mt5_read()
    with lock:
        try:
            mt5 = ensure()
        except Exception as e:
            raise HTTPException(503, f"MT5 indisponibil: {e}")
        chk = _market_check(mt5, m, body.get("costs_mode") or "auto", body.get("slip"), body.get("comm"))
        m.update(slip=chk["costs"]["slip"], comm=chk["costs"]["comm"])
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        end = _dt.now(_tz.utc)
        rates = mt5.copy_rates_range(m["symbol"], mt5.TIMEFRAME_M5, end - _td(days=3 * 365), end)
        point = float(mt5.symbol_info(m["symbol"]).point)
    bt = backtest_rates(rates, m, point) if rates is not None and len(rates) else {"ok": False, "detail": "fără bare M5"}
    return {"market": m, **chk, "backtest": bt}


@router.post("/backtest/refresh")
def daily_backtest_refresh(body: dict | None = None):
    """Reporneste backtestul unui slot (dupa „failed” / la cerere). Nu blocheaza."""
    from api.backtest_refresh import daily_ensure
    slot = int((body or {}).get("slot", 0))
    return {"backtest_auto": daily_ensure(load_config(), force_slots=(slot,))}


@router.post("/markets/{slot}/pause")
def daily_market_pause(slot: int):
    """Pune piata slotului pe PAUZA: fara intrari noi (shadow si executie); pozitiile deschise raman gestionate
    (SL, inchiderea la final de fereastra). Persistat in config.json — supravietuieste restartului."""
    return _set_pause(slot, True)


@router.post("/markets/{slot}/resume")
def daily_market_resume(slot: int):
    return _set_pause(slot, False)


@router.post("/markets/{slot}/mode")
def daily_market_mode(slot: int, body: dict):
    """Modul PIETEI din slot: live (ordine reale — DOAR daca Trading LIVE e deblocat pentru Daily pe cont real) /
    shadow (virtual) / pause (fara intrari noi; pozitiile existente raman gestionate). Persistat in config,
    hot-reload; cealalta piata nu e atinsa."""
    mode = str((body or {}).get("mode") or "").lower()
    if mode not in ("live", "shadow", "pause"):
        raise HTTPException(400, "mode: una din live / shadow / pause")
    if mode == "pause":
        return {**_set_pause(slot, True), "mode": "pause"}
    from daily_engine.config import CFG_PATH, market_mode
    import json as _json
    with open(CFG_PATH, encoding="utf-8") as f:
        raw = _json.load(f)
    mk = raw.get("markets") or []
    if not 0 <= slot < len(mk):
        raise HTTPException(400, "slot invalid")
    m = mk[slot]
    before = market_mode({**m, "exec_mode": m.get("exec_mode") or ("live" if raw.get("mode") == "execute" else "shadow")})
    for m_ in mk:                                   # fiecare piata cu modul ei scris explicit
        m_.setdefault("exec_mode", "live" if raw.get("mode") == "execute" else "shadow")
    if m.get("paused"):
        _set_pause(slot, False)                     # iesirea din pauza (Telegram + moment)
        with open(CFG_PATH, encoding="utf-8") as f:
            raw = _json.load(f)
        mk = raw["markets"]
        m = mk[slot]
        for m_ in mk:
            m_.setdefault("exec_mode", "live" if raw.get("mode") == "execute" else "shadow")
    m["exec_mode"] = mode
    raw["mode"] = "execute" if any(x.get("exec_mode") == "live" for x in mk) else "shadow"
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        _json.dump(raw, f, indent=2, ensure_ascii=False)
    changed = before != mode
    if changed:
        try:
            from api import audit_log
            audit_log.record("daily", "mode", f"{m.get('symbol')}: {before} → {mode}", market=m.get("symbol"),
                             before=before, after=mode)
        except Exception:
            pass
        try:
            from api.telegram import send_message
            send_message((f"🟢 <b>Daily Engine — {m.get('symbol')} pe LIVE</b>\nOrdine reale de la următoarea fereastră "
                          "(dacă Trading LIVE e deblocat pentru Daily; altfel rămâne fără ordine)." if mode == "live" else
                          f"🧪 <b>Daily Engine — {m.get('symbol')} pe SHADOW</b>\nFără ordine noi; o poziție reală deschisă azi "
                          "rămâne gestionată până la SL / finalul ferestrei."))
        except Exception:
            pass
    return {"ok": True, "slot": slot, "symbol": m.get("symbol"), "mode": mode, "changed": changed}


def _set_pause(slot: int, paused: bool) -> dict:
    from datetime import datetime as _dt, timezone as _tz
    from daily_engine.config import CFG_PATH
    import json as _json
    with open(CFG_PATH, encoding="utf-8") as f:
        raw = _json.load(f)
    mk = raw.get("markets") or []
    if not 0 <= slot < len(mk):
        raise HTTPException(400, "slot invalid")
    m = mk[slot]
    was = bool(m.get("paused"))
    m["paused"] = paused
    m["paused_at"] = _dt.now(_tz.utc).isoformat(timespec="seconds") if paused else None
    if was == paused:
        return {"ok": True, "slot": slot, "symbol": m.get("symbol"), "paused": paused, "changed": False}
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        _json.dump(raw, f, indent=2, ensure_ascii=False)
    try:
        from api import audit_log
        audit_log.record("daily", "pause" if paused else "resume", f"{m.get('symbol')} {'pe pauză' if paused else 'reluat'}",
                         market=m.get("symbol"))
    except Exception:
        pass
    try:
        from api.telegram import send_message
        send_message(f"{'⏸' if paused else '▶️'} <b>Daily Engine — {m.get('symbol')} {'PE PAUZĂ' if paused else 'reluat'}</b>\n"
                     + ("Fără intrări noi; pozițiile deschise rămân gestionate (SL, închidere la final de fereastră)."
                        if paused else "Piața poate deschide din nou trade-uri (de la următoarea fereastră / bară)."))
    except Exception:
        pass
    return {"ok": True, "slot": slot, "symbol": m.get("symbol"), "paused": paused, "changed": True,
            "paused_at": m["paused_at"]}


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
    try:
        from api import audit_log
        audit_log.record("daily", "start", f"pornit (PID {proc.pid})")
    except Exception:
        pass
    return {"ok": True, "pid": proc.pid, "note": "modul fiecărei piețe se vede pe card (Live / Shadow / Pauză)"}


@router.post("/stop")
def daily_stop():
    pid = _read_pid()
    if not pid or not _pid_alive(pid):
        raise HTTPException(409, "Daily Engine nu ruleaza")
    # INTAI starea dorita — altfel watchdog-ul ar putea reporni engine-ul imediat dupa kill
    try:
        os.remove(DESIRED_FILE)
    except OSError:
        pass
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, text=True)
    try:
        os.remove(PID_FILE)
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
    try:
        from api import audit_log
        audit_log.record("daily", "stop", "oprit din UI")
    except Exception:
        pass
    return {"ok": True}


@router.get("/trades")
def daily_trades(limit: int = 200):
    return list(reversed(load_trades()))[:max(1, min(limit, 2000))]


@router.get("/config")
def daily_config():
    return load_config()


@router.put("/config")
def daily_config_save(body: dict):
    """Schimba modul: {"mode": "shadow" | "execute"} (+ optional "sizing"). Hot-reload — engine-ul il
    citeste la iteratia urmatoare. Executia reala porneste abia de la urmatoarea fereastra (ziua
    trebuie armata inainte de formarea intervalului); pe cont REAL cere si deblocarea din Trading LIVE."""
    from daily_engine.config import CFG_PATH, MODES, _sanitize
    import json as _json
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            raw = _json.load(f)
    except Exception:
        raw = load_config()
    before = raw.get("mode", "shadow")
    if "mode" in body:
        if body["mode"] not in MODES:
            raise HTTPException(400, f"mode: una din {list(MODES)}")
        raw["mode"] = body["mode"]
        for m_ in raw.get("markets") or []:              # compat: modul global = acelasi mod pe fiecare piata
            m_["exec_mode"] = "live" if body["mode"] == "execute" else "shadow"
    if isinstance(body.get("sizing"), dict):
        raw["sizing"] = {**(raw.get("sizing") or {}), **body["sizing"]}
    changes = []
    if isinstance(body.get("markets"), list):
        # per piata se pot schimba DOAR R:R si re-intrarile (restul regulilor = varianta testata, din config.json)
        from daily_engine.config import sanitize_reentry, sanitize_rr
        raw_mk = raw.get("markets") or [dict(m) for m in load_config()["markets"]]
        by = {m.get("symbol"): m for m in raw_mk}
        for upd in body["markets"]:
            upd = upd or {}
            if "slot" in upd:                                    # schimbarea PIETEI unui slot (sablon + simbol + costuri)
                slot = int(upd["slot"])
                if not 0 <= slot < len(raw_mk):
                    raise HTTPException(400, "slot invalid")
                old = {**load_config()["markets"][slot], **raw_mk[slot]}
                new = _proposed_market(old, upd)
                if new["symbol"] != old["symbol"] or new.get("preset") != old.get("preset"):
                    busy = _slot_busy(old["symbol"])
                    if busy:
                        raise HTTPException(409, busy)
                lock, ensure = _mt5_read()
                with lock:
                    try:
                        mt5 = ensure()
                    except Exception as e:
                        raise HTTPException(503, f"MT5 indisponibil: {e}")
                    chk = _market_check(mt5, new, upd.get("costs_mode") or "auto", upd.get("slip"), upd.get("comm"))
                    new.update(slip=chk["costs"]["slip"], comm=chk["costs"]["comm"])
                new["costs_mode"] = chk["costs_mode"]
                new.pop("backtest", None)              # backtestul vechi NU mai e valabil — refresh automat (backtest_auto)
                for k_ in ("label", "role"):
                    new.setdefault(k_, old.get(k_))
                if new["symbol"] != old["symbol"] or new["preset"] != old.get("preset"):
                    changes.append(f"slot {slot + 1}: {old['symbol']} ({old.get('preset') or old.get('tz')}) → "
                                   f"{new['symbol']} ({new['preset']}) · costuri {chk['costs_mode']}: slip {new['slip']:g}, "
                                   f"comision {new['comm']:g}")
                if new["symbol"] != old["symbol"]:
                    new["exec_mode"] = "shadow"          # o piata noua intra mereu in SHADOW (Live = decizia ta)
                raw_mk[slot] = {k_: v for k_, v in new.items() if k_ in (
                    "symbol", "enabled", "label", "tz", "open", "last_bar", "or_minutes", "entry", "rr", "slip", "comm",
                    "role", "reentry", "preset", "costs_mode", "paused", "paused_at", "exec_mode", "profit_lock")}
                continue
            m = by.get(upd.get("symbol"))
            if m is None:
                raise HTTPException(400, f"piață necunoscută în Daily: {upd.get('symbol')}")
            if "rr" in upd:
                new_rr = sanitize_rr(upd["rr"])
                if new_rr != m.get("rr"):
                    changes.append(f"{m['symbol']}: R:R {m.get('rr') or 'fără TP'} → {new_rr or 'fără TP'}")
                m["rr"] = new_rr
            if "reentry" in upd:
                new_re = sanitize_reentry(upd["reentry"])
                old_on = bool((m.get("reentry") or {}).get("enabled"))
                if new_re["enabled"] != old_on:
                    changes.append(f"{m['symbol']}: re-intrări {'PORNITE' if new_re['enabled'] else 'oprite'}"
                                   + (f" ({new_re['window_min']} min, max {new_re['max_trades']}, stop la "
                                      f"{new_re['max_consec_losses']} pierderi)" if new_re["enabled"] else ""))
                m["reentry"] = new_re
            if "profit_lock" in upd:
                from daily_engine.config import sanitize_plock
                new_pl = sanitize_plock(upd["profit_lock"])
                old_pl = sanitize_plock(m.get("profit_lock"))
                if new_pl != old_pl:
                    changes.append(f"{m['symbol']}: Profit Lock " + (
                        f"PORNIT — la {new_pl['trigger_R']:g}R SL → +{new_pl['lock_R']:g}R" if new_pl["enabled"]
                        else "oprit"))
                m["profit_lock"] = new_pl
        syms = [m_.get("symbol") for m_ in raw_mk]
        if len(set(syms)) != len(syms):
            raise HTTPException(400, f"aceeași piață în ambele sloturi ({syms}) — alege simboluri diferite")
        raw["markets"] = raw_mk
    clean = _sanitize(raw)
    for m_, c_ in zip(raw.get("markets") or [], clean["markets"]):
        m_["exec_mode"] = c_["exec_mode"]
    raw["mode"], raw["sizing"] = clean["mode"], clean["sizing"]
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        _json.dump(raw, f, indent=2, ensure_ascii=False)
    try:
        from api.backtest_refresh import daily_ensure
        daily_ensure(load_config())                # fingerprint nou → rezultatul vechi devine „outdated”, job nou
    except Exception:
        pass
    if changes:
        try:
            from api import audit_log
            for ch in changes:
                audit_log.record("daily", "config", ch)
        except Exception:
            pass
        try:
            from api.telegram import send_message
            send_message("⚙️ <b>Daily Engine — configurare</b>\n" + "\n".join(changes)
                         + "\nSe aplică de la următoarea iterație (fără restart).")
        except Exception:
            pass
    if before != raw["mode"]:
        try:
            from api.telegram import send_message
            send_message("🟢 <b>Daily Engine — mod EXECUȚIE</b>\nOrdine reale de la următoarea fereastră "
                         "(DEMO, sau REAL dacă e deblocat în Trading LIVE)." if raw["mode"] == "execute" else
                         "🧪 <b>Daily Engine — mod SHADOW</b>\nFără ordine noi; pozițiile reale deschise azi sunt "
                         "închise la finalul ferestrei.")
        except Exception:
            pass
    return clean


@router.get("/logs")
def daily_logs(lines: int = 100):
    try:
        with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
            return {"lines": f.readlines()[-max(1, min(lines, 1000)):]}
    except FileNotFoundError:
        return {"lines": []}
