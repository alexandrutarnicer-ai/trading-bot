"""Daily Engine — schimbarea pietei unui slot: sabloane de bursa, costuri AUTO din MT5, backtest rapid.

Folosit de API (`/daily/presets`, `/daily/market-preview`, `PUT /daily/config`) — DOAR CITIRE MT5, fara ordine.
  - PRESETS: bursa urmarita (ora locala de deschidere, ultima bara, intervalul de deschidere si modul TESTATE)
  - estimate_costs: slippage + „comision” in unitati de pret, din spread-ul LIVE vs spread-ul ISTORIC al barelor
      slip = 25% din spread-ul live (min 1 point) — slippage-ul presupus la ordinele stop / la piata
      comm = max(0, spread live − mediana spread-ului din bare): markup-ul contului (Standard FX ~0,8 pip), pe care
             barele istorice NU il contin; pe indici / cripto ~0
  - quick_backtest: ~3 ani de bare M5 din MT5, ACEEASI functie ca engine-ul (strategy.evaluate_day_multi), verdict M0
Conversia orei: serverul ICMarkets = New York + 7h (aceeasi regula ca scripts/research_daily/orb_m5.load).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from daily_engine.config import ENTRY_MODES, hm_to_min
from daily_engine.strategy import admit_session_trades, evaluate_day_multi

# Bursa urmarita de un slot. or_minutes / entry = varianta TESTATA pe acea deschidere (docs/DAILY_ENGINE_PLAN.md §8, §10)
PRESETS: dict[str, dict] = {
    "london":    {"label": "Deschiderea Londrei", "tz": "Europe/London", "open": "08:00", "last_bar": "14:25",
                  "or_minutes": 5, "entry": "breakout"},
    "frankfurt": {"label": "Deschiderea Frankfurt (Xetra)", "tz": "Europe/Berlin", "open": "09:00", "last_bar": "17:25",
                  "or_minutes": 5, "entry": "breakout"},
    "new_york":  {"label": "Deschiderea New York", "tz": "America/New_York", "open": "09:30", "last_bar": "15:55",
                  "or_minutes": 30, "entry": "direction"},
}
SLOTS = ("dimineata", "dupa-amiaza")


SESSION_LETTER = {"london": "L", "frankfurt": "F", "new_york": "N", "custom": "C"}
SESSION_LABEL = {"london": "Londra", "frankfurt": "Frankfurt", "new_york": "New York", "custom": "fereastra proprie"}
_WINDOW_KEYS = ("tz", "open", "last_bar", "or_minutes", "entry")


def market_sessions(m: dict) -> list[dict]:
    """Sesiunile pietei ca dict-uri „piata + fereastra sesiunii” (2026-11-13). Sesiunea PRIMARA (bursa pietei din
    config, `preset`) pastreaza fereastra si cheile / comment-urile de dinainte (`_sfx` = "", `_letter` = "") → o piata
    cu o singura sesiune se comporta EXACT ca inainte; celelalte primesc fereastra testata din market_tools.PRESETS,
    cheile `day|SIM@sesiune` si comment-ul `D-SIM-MMDD<litera>`."""
    ses = list(m.get("sessions") or [])
    primary = m.get("preset") if m.get("preset") in ses else (ses[0] if ses else "custom")
    if not ses:
        ses = [primary]
    out = []
    for sid in ses:
        if sid == primary or sid not in PRESETS:
            win = {k: m[k] for k in _WINDOW_KEYS}
        else:
            win = {k: PRESETS[sid][k] for k in _WINDOW_KEYS}
        is_p = sid == primary
        out.append({**m, **win, "_session": sid, "_primary": is_p,
                    "_sfx": "" if is_p else f"@{sid}", "_letter": "" if is_p else SESSION_LETTER.get(sid, "X")})
    return out



def preset_for(m: dict) -> str | None:
    for k, p in PRESETS.items():
        if p["tz"] == m.get("tz") and p["open"] == m.get("open"):
            return k
    return None


def estimate_costs(mt5, symbol: str, bars_spread_points=None) -> dict:
    """Costurile unui trade in unitati de pret (slip + comm), din MT5. bars_spread_points = spread-ul barelor
    istorice (points); lipsa → doar spread-ul live (comm = 0)."""
    info, tick = mt5.symbol_info(symbol), mt5.symbol_info_tick(symbol)
    if info is None or tick is None or not tick.ask or not tick.bid:
        return {"ok": False, "detail": f"{symbol}: symbol_info / tick indisponibil"}
    point = float(info.point)
    live = float(tick.ask - tick.bid)
    hist = None
    if bars_spread_points is not None and len(bars_spread_points):
        hist = float(np.median(np.asarray(bars_spread_points, float)[-20000:])) * point
    slip = max(point, 0.25 * live)
    comm = max(0.0, live - hist) if hist is not None else 0.0
    comm = round(comm / point) * point                                   # multiplu de point (fara zgomot float)
    sig = lambda v: float(f"{v:.6g}")                                   # noqa: E731
    return {"ok": True, "point": point, "digits": int(info.digits), "spread_live": sig(live),
            "spread_hist": None if hist is None else sig(hist), "slip": sig(slip), "comm": sig(comm),
            "spread_live_points": round(live / point, 1), "markup_points": round(comm / point, 1)}


def server_to_exchange(times_server: pd.Series, tz: str) -> pd.Series:
    """Ora serverului MT5 (naiva) → ora locala a bursei (naiva). ICMarkets: server = New York + 7h."""
    ny = times_server - pd.Timedelta(hours=7)
    if tz == "America/New_York":
        return ny
    return (ny.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
              .dt.tz_convert(tz).dt.tz_localize(None))


def backtest_rates(rates, m: dict, point: float, years: float = 3.0) -> dict:
    """Backtest pe barele M5 date (array MT5 sau DataFrame cu time=epoch server), regulile pietei `m`
    (inclusiv rr / reentry). Intoarce rezumatul + verdictul M0."""
    d0 = pd.DataFrame(rates)
    if d0.empty:
        return {"ok": False, "detail": "fara bare M5"}
    d0["time"] = pd.to_datetime(d0["time"], unit="s") if np.issubdtype(d0["time"].dtype, np.number) else pd.to_datetime(d0["time"])
    # fiecare SESIUNE a pietei (Londra / Frankfurt / New York) pe zilele ei; apoi aceeasi admitere ca engine-ul
    # (strategy.admit_session_trades: max trade-uri / zi pe piata, fara pozitii simultane). O sesiune = ca inainte.
    by_day: dict = {}
    days_set = set()
    for ses in market_sessions(m):
        loc = server_to_exchange(d0["time"], ses["tz"])
        d = d0.assign(loc=loc).dropna(subset=["loc"])
        d = d[d["loc"].dt.weekday < 5]
        om, lb = hm_to_min(ses["open"]), hm_to_min(ses["last_bar"])
        d = d.assign(mins=d["loc"].dt.hour * 60 + d["loc"].dt.minute)
        d = d[(d.mins >= om) & (d.mins <= lb)]
        d = d.assign(day=d["loc"].dt.normalize())
        n_or = ses["or_minutes"] // 5
        tzinfo = ZoneInfo(ses["tz"])
        for day, g in d.groupby("day", sort=True):
            if g.mins.iloc[0] != om or len(g) < n_or + 6 or g.high.iloc[:n_or].max() - g.low.iloc[:n_or].min() <= 0:
                continue
            days_set.add(day)
            r = evaluate_day_multi(g.open, g.high, g.low, g.close, g.spread.to_numpy(float) * point, g.mins, open_min=om,
                                   or_minutes=ses["or_minutes"], mode=ENTRY_MODES[ses["entry"]], rr=ses.get("rr"),
                                   slip=ses["slip"], comm=ses["comm"], day_complete=True, reentry=ses.get("reentry"),
                                   plock=ses.get("profit_lock"))
            base = datetime(day.year, day.month, day.day, tzinfo=tzinfo)
            by_day.setdefault(day, []).append(
                {"key": ses["_session"], "st": r, "day": day,
                 "to_utc": (lambda mins, _b=base: (_b + timedelta(minutes=int(mins))).astimezone(timezone.utc))})
    from daily_engine.config import sanitize_sessions
    max_tr = int(m.get("max_trades_per_day") or sanitize_sessions(m)[1])
    rows = []
    for day in sorted(by_day):
        comb = admit_session_trades(by_day[day], max_tr)
        for item in by_day[day]:
            for t in comb[item["key"]]["st"]["trades"]:
                rows.append({"entry_t": item["to_utc"](int(t["entry_min"])).replace(tzinfo=None), "R": float(t["R"]),
                             "session": item["key"]})
    rows.sort(key=lambda x: x["entry_t"])
    days = len(days_set)
    if not rows:
        return {"ok": True, "trades": 0, "days": days, "detail": "niciun trade in perioada (zile sarite / costuri prea mari)"}
    t = pd.DataFrame(rows)
    R = t.R.to_numpy()
    eq = np.cumsum(R)
    out = {"ok": True, "trades": int(len(R)), "days": int(days), "per_week": round(len(R) / max(1, days) * 5, 1),
           "expectancy_R": round(float(R.mean()), 3), "win_rate": round(float((R > 0).mean()), 3),
           "total_R": round(float(R.sum()), 1), "max_dd_R": round(float((eq - np.maximum.accumulate(eq)).min()), 1),
           "period": f"{t.entry_t.min():%Y-%m} → {t.entry_t.max():%Y-%m}"}
    try:
        from m0.robustness import evaluate_trades
        split = t.entry_t.iloc[int(len(t) * 0.7)] if len(t) > 10 else t.entry_t.iloc[-1]
        ev = evaluate_trades(t.assign(outcome=np.where(t.R > 0, "TP", "SL")), split_time=split, n_boot=500)
        out.update(verdict=ev["verdict"], train_R=round(ev["train_exp"], 3), test_R=round(ev["test_exp"], 3))
    except Exception:
        out["verdict"] = None
    return out


def quick_backtest(mt5, m: dict, years: float = 3.0) -> dict:
    """~`years` ani de bare M5 din MT5 (doar citire) → backtest_rates."""
    if not mt5.symbol_select(m["symbol"], True):
        return {"ok": False, "detail": f"simbolul {m['symbol']} nu exista in MT5"}
    end = datetime.now(timezone.utc)
    rates = mt5.copy_rates_range(m["symbol"], mt5.TIMEFRAME_M5, end - timedelta(days=int(365 * years)), end)
    if rates is None or len(rates) == 0:
        return {"ok": False, "detail": "MT5 nu a intors bare M5 (deschide graficul M5 al pietei ca sa se descarce istoricul)"}
    info = mt5.symbol_info(m["symbol"])
    return backtest_rates(rates, m, float(info.point))
