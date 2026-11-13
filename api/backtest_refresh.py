"""
Backtest legat de CONFIGURATIA EXACTA (Daily + Noisy) — refresh automat la salvare (2026-11-05).

Problema: piata se schimba din UI, dar backtestul afisat ramanea cel vechi (referinte scrise in cod / rezultat salvat
doar la schimbarea slotului). Acum:
  - fingerprint(config relevanta) = sha1 pe JSON canonic (piata, timeframe, reguli, R:R, re-intrari, costuri, ...)
  - fiecare rezultat e salvat CU fingerprint-ul configuratiei din care a rezultat (data/<engine>/backtest_auto.json)
  - la salvare (sau la prima citire fara rezultat) → job in fundal: pending → running → completed / failed
  - rezultatul unui job e scris DOAR daca fingerprint-ul e inca cel curent; altfel e aruncat (niciun rezultat vechi)
  - fara dubluri: acelasi (engine, cheie, fingerprint) nu porneste de doua ori; un job pornit inainte de un restart
    al API-ului ramane „running” pe disc → tratat ca intrerupt si repornit la urmatoarea citire
Statusuri afisate: pending / running / completed / failed / outdated (rezultat existent, dar pentru alta configuratie).
Teste: python scripts/test_backtest_refresh.py
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import traceback
from datetime import datetime, timezone
from typing import Callable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOCK = threading.RLock()
_RUNNING: set[tuple[str, str, str]] = set()           # (engine, key, fingerprint) cu thread viu in ACEST proces
STORE_PATHS = {"daily": os.path.join(ROOT, "data", "daily_engine", "backtest_auto.json"),
               "noisy": os.path.join(ROOT, "data", "noisy_engine", "backtest_auto.json")}


def fingerprint(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load(engine: str) -> dict:
    try:
        with open(STORE_PATHS[engine], encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(engine: str, d: dict) -> None:
    from safe_io import write_json_atomic
    write_json_atomic(STORE_PATHS[engine], d, critical=False)


def view(engine: str, key: str, fp: str) -> dict:
    """Ce vede UI-ul pentru (engine, cheie) la configuratia curenta `fp`."""
    with _LOCK:
        rec = (_load(engine).get(key) or {})
    if not rec:
        return {"status": "outdated", "fingerprint": fp, "result": None, "note": "niciun backtest încă pentru această configurație"}
    same = rec.get("fingerprint") == fp
    st = rec.get("status")
    if not same:
        # rezultatul existent (daca exista) e pentru ALTA configuratie
        return {"status": "outdated", "fingerprint": fp, "stale_fingerprint": rec.get("fingerprint"),
                "result": None, "stale_result_summary": (rec.get("result") or {}).get("summary") if rec.get("result") else None,
                "note": "configurația s-a schimbat — backtestul vechi nu mai e valabil"}
    if st in ("pending", "running") and (engine, key, fp) not in _RUNNING:
        st = "interrupted"                        # job pornit inainte de un restart al API-ului
    return {**rec, "status": st}


def request(engine: str, key: str, fp: str, fn: Callable[[], dict], summary: dict | None = None,
            force: bool = False) -> dict:
    """Porneste (o singura data) backtestul pentru configuratia `fp`. Nu blocheaza: thread daemon."""
    with _LOCK:
        cur = view(engine, key, fp)
        if not force and cur.get("status") in ("pending", "running", "completed"):
            return cur
        if (engine, key, fp) in _RUNNING:
            return cur
        d = _load(engine)
        d[key] = {"fingerprint": fp, "status": "pending", "requested_at": _now(), "config": summary or {},
                  "result": None, "error": None}
        _save(engine, d)
        _RUNNING.add((engine, key, fp))

    def _job():
        try:
            with _LOCK:
                d = _load(engine)
                if (d.get(key) or {}).get("fingerprint") != fp:
                    return                         # deja inlocuit de o configuratie mai noua
                d[key]["status"], d[key]["started_at"] = "running", _now()
                _save(engine, d)
            res, err = None, None
            try:
                res = fn()
                if not isinstance(res, dict) or res.get("ok") is False:
                    err = (res or {}).get("detail") or "backtest fără rezultat"
            except Exception as e:                 # noqa: BLE001
                err = f"{type(e).__name__}: {e}"
                traceback.print_exc()
            with _LOCK:
                d = _load(engine)
                rec = d.get(key) or {}
                if rec.get("fingerprint") != fp:
                    return                         # configuratia s-a schimbat in timpul rularii → rezultat ARUNCAT
                rec.update(status="failed" if err else "completed", finished_at=_now(), error=err,
                           result=None if err else res)
                d[key] = rec
                _save(engine, d)
        finally:
            with _LOCK:
                _RUNNING.discard((engine, key, fp))

    threading.Thread(target=_job, daemon=True, name=f"bt-{engine}-{key}").start()
    return view(engine, key, fp)


# ── Daily ─────────────────────────────────────────────────────────────────────────────────────────────────────

DAILY_FIELDS = ("symbol", "tz", "open", "last_bar", "or_minutes", "entry", "rr", "reentry", "slip", "comm")
DAILY_VERSION = "daily-orb-v1|3y-M5"


def daily_fp(m: dict) -> str:
    fp = {"v": DAILY_VERSION, **{k: m.get(k) for k in DAILY_FIELDS}}
    # sesiuni multiple / limita de trade-uri diferita de cea implicita → alt rezultat; o sesiune cu limita implicita =
    # amprenta de dinainte (fara recalculari inutile)
    from daily_engine.config import sanitize_sessions
    legacy_mt = sanitize_sessions({k: v for k, v in m.items() if k != "max_trades_per_day"})[1]
    if len(m.get("sessions") or []) > 1:
        fp["sessions"] = list(m["sessions"])
    if len(m.get("sessions") or []) > 1 or (m.get("max_trades_per_day") or legacy_mt) != legacy_mt:
        fp["max_trades_per_day"] = m.get("max_trades_per_day")
    pl = m.get("profit_lock") or {}
    if pl.get("enabled"):                     # oprit = amprenta de dinainte (fara recalculari inutile)
        fp["profit_lock"] = {"t": pl.get("trigger_R"), "l": pl.get("lock_R")}
    return fingerprint(fp)


def daily_job(m: dict) -> Callable[[], dict]:
    def fn():
        from datetime import timedelta
        from api import mt5_pool
        from daily_engine.market_tools import backtest_rates
        with mt5_pool._LOCK:                       # doar CITIRE MT5, cat mai scurt (calculul e in afara lock-ului)
            mt5 = mt5_pool._ensure_mt5()
            if not mt5.symbol_select(m["symbol"], True):
                return {"ok": False, "detail": f"simbolul {m['symbol']} nu există în MT5"}
            end = datetime.now(timezone.utc)
            rates = mt5.copy_rates_range(m["symbol"], mt5.TIMEFRAME_M5, end - timedelta(days=3 * 365), end)
            info = mt5.symbol_info(m["symbol"])
            point = float(info.point) if info else 0.0
        if rates is None or not len(rates):
            return {"ok": False, "detail": "MT5 nu a întors bare M5 (deschide graficul M5 al pieței)"}
        out = backtest_rates(rates, m, point)
        out["summary"] = f"{m['symbol']} · {out.get('trades')} trade-uri · {out.get('expectancy_R')}R/trade · {out.get('verdict')}"
        return out
    return fn


def daily_ensure(cfg: dict, force_slots=()) -> list[dict]:
    """Pentru fiecare slot: statusul la configuratia curenta; porneste backtestul daca lipseste / e invechit."""
    out = []
    for i, m in enumerate(cfg.get("markets") or []):
        fp = daily_fp(m)
        v = view("daily", f"slot{i}", fp)
        if v["status"] in ("outdated", "interrupted") or i in force_slots:
            v = request("daily", f"slot{i}", fp, daily_job(m),
                        summary={k: m.get(k) for k in DAILY_FIELDS}, force=i in force_slots)
        out.append({"slot": i, "symbol": m.get("symbol"), **{k: v.get(k) for k in (
            "status", "fingerprint", "requested_at", "started_at", "finished_at", "error", "result", "note",
            "stale_result_summary")}})
    return out


# ── Noisy ─────────────────────────────────────────────────────────────────────────────────────────────────────

NOISY_FIELDS = ("symbol", "timeframe", "strategy", "window", "break_even", "overlap", "limits", "tf_profiles", "spread", "news")
NOISY_VERSION = "noisy-v1|12m"


def noisy_fp(cfg: dict) -> str:
    return fingerprint({"v": NOISY_VERSION, **{k: cfg.get(k) for k in NOISY_FIELDS}})


def noisy_job(cfg: dict) -> Callable[[], dict]:
    def fn():
        import copy
        import sys
        from datetime import timedelta
        from api import mt5_pool
        from noisy_engine.config import resolve_spread
        from noisy_engine.engine import rates_to_bars
        sys.path.insert(0, os.path.join(ROOT, "scripts", "research_noisy"))
        from noisy_backtest import backtest, stats
        c = copy.deepcopy(cfg)
        tf = c.get("timeframe", "M1")
        with mt5_pool._LOCK:
            mt5 = mt5_pool._ensure_mt5()
            sym = c["symbol"]
            if not mt5.symbol_select(sym, True):
                return {"ok": False, "detail": f"simbolul {sym} nu există în MT5"}
            info, tick = mt5.symbol_info(sym), mt5.symbol_info_tick(sym)
            end = datetime.now(timezone.utc)
            rates = mt5.copy_rates_range(sym, getattr(mt5, f"TIMEFRAME_{tf}"), end - timedelta(days=365), end)
        if rates is None or not len(rates) or info is None:
            return {"ok": False, "detail": f"MT5 nu a întors bare {tf} pentru {sym}"}
        live_pts = ((tick.ask - tick.bid) / info.point) if tick and tick.ask and tick.bid else None
        sp = resolve_spread(c, float(info.point), live_pts, int(info.digits))
        bars = rates_to_bars(rates, None, float(info.point), tf_min=1 if tf == "M1" else 5)
        trades = backtest(c, bars)
        sc = stats(trades) if trades else {"trades": 0}
        days = len({t.date() for t in bars["t"] if t.weekday() < 5})
        sc.update(ok=True, symbol=sym, timeframe=tf, per_day=round(len(trades) / max(1, days), 2),
                  period=f"{bars['t'].iloc[0]:%Y-%m-%d} → {bars['t'].iloc[-1]:%Y-%m-%d}",
                  spread=sp, summary=f"{sym} {tf} · {len(trades)} trade-uri · {sc.get('expectancy_R')}R/trade")
        return sc
    return fn


def noisy_ensure(cfg: dict, force: bool = False) -> dict:
    fp = noisy_fp(cfg)
    v = view("noisy", "main", fp)
    if v["status"] in ("outdated", "interrupted") or force:
        v = request("noisy", "main", fp, noisy_job(cfg), summary={k: cfg.get(k) for k in ("symbol", "timeframe")},
                    force=force)
    return v
