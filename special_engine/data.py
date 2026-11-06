"""Special Engine — barele pe sesiune + istoricul componentelor + selectia trimestriala (PURE peste DataFrame-uri;
MT5 doar in fetch_m5 / fetch_d1, doar CITIRE). Aceleasi reguli ca cercetarea (intraday_orb / noise_area / walkforward)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from daily_engine.config import hm_to_min
from daily_engine.market_tools import server_to_exchange
from special_engine.strategies import NOISE_LOOKBACK, ORB_VARIANTS, noise_day, noise_moves, nr_flag, orb_day


def rates_df(rates) -> pd.DataFrame:
    d = pd.DataFrame(rates)
    if d.empty:
        return d
    if np.issubdtype(d["time"].dtype, np.number):
        d["time"] = pd.to_datetime(d["time"], unit="s")
    return d[["time", "open", "high", "low", "close", "tick_volume", "spread"]]


def fetch_m5(mt5, sym: str, n: int = 400000) -> pd.DataFrame:
    mt5.symbol_select(sym, True)
    r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, n)
    return rates_df(r) if r is not None and len(r) else pd.DataFrame()


def fetch_d1(mt5, sym: str, n: int = 3000) -> pd.DataFrame:
    mt5.symbol_select(sym, True)
    r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, n)
    return rates_df(r) if r is not None and len(r) else pd.DataFrame()


def session(d: pd.DataFrame, tz: str, op: str, end: str, inclusive_end: bool) -> tuple[pd.DataFrame, int, int]:
    """Barele in fereastra bursei (ora LOCALA), zile lucratoare; `day` = ziua bursei (naiva)."""
    loc = server_to_exchange(d["time"], tz)
    d = d.assign(loc=loc).dropna(subset=["loc"])
    d = d[d["loc"].dt.weekday < 5].copy()
    om, em = hm_to_min(op), hm_to_min(end)
    d["mins"] = d["loc"].dt.hour * 60 + d["loc"].dt.minute
    d = d[(d.mins >= om) & ((d.mins <= em) if inclusive_end else (d.mins < em))]
    d["day"] = d["loc"].dt.normalize().dt.tz_localize(None)
    return d, om, em


def orb_history(d: pd.DataFrame, sym: str, tz: str, op: str, last: str, slip: float, comm: float, point: float) -> list[dict]:
    """Toate trade-urile ORB (6 variante) pe istoric — ca intraday_orb.run_market."""
    s, om, _ = session(d, tz, op, last, inclusive_end=True)
    rows = []
    for day, g in s.groupby("day", sort=True):
        if g.mins.iloc[0] != om or len(g) < 12:
            continue
        o, h, l, c = (g[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        spr = g["spread"].to_numpy(float) * point
        mins = g["mins"].to_numpy()
        for orm, ent in ORB_VARIANTS:
            n_or = orm // 5
            if h[:n_or].max() - l[:n_or].min() <= 0:
                continue
            r = orb_day(o, h, l, c, spr, mins, open_min=om, or_minutes=orm, entry=ent, slip=slip, comm=comm,
                        day_complete=True)
            if r.get("phase") == "closed":
                et = day + pd.Timedelta(minutes=int(r["entry_min"]))
                rows.append({"comp": f"ORB:{sym}:{orm}/{ent}", "sym": sym, "entry_t": et,
                             "exit_t": day + pd.Timedelta(minutes=int(r["exit_min"])), "R": float(r["R"])})
    return rows


def noise_days(d: pd.DataFrame, tz: str, op: str, cl: str):
    """Zilele complete NOISE (ca noise_area.run): lista (day, g) + sloturile + matricea |close/open − 1|."""
    s, om, cm = session(d, tz, op, cl, inclusive_end=False)
    days = [(day, g.reset_index(drop=True)) for day, g in s.groupby("day", sort=True)
            if g.mins.iloc[0] == om and len(g) >= (cm - om) // 5 * 0.9]
    slots = list(range(om, cm, 5))
    mv = [noise_moves(g["open"].iat[0], g["close"], g["mins"], slots) for _, g in days]
    return days, slots, mv, om, cm


def noise_history(d: pd.DataFrame, sym: str, tz: str, op: str, cl: str, cost_px: float, point: float) -> list[dict]:
    days, slots, mv, om, cm = noise_days(d, tz, op, cl)
    rows, prev_close = [], None
    for k, (day, g) in enumerate(days):
        if k < NOISE_LOOKBACK or prev_close is None:
            prev_close = g["close"].iat[-1]
            continue
        sig = np.nanmean(np.array(mv[k - NOISE_LOOKBACK:k]), axis=0)
        r = noise_day(g, sig=sig, slots=slots, prev_close=prev_close, om=om, cm=cm, point=point, cost_px=cost_px,
                      day=day, sym=sym, day_complete=True)
        rows += [{"comp": f"NOISE:{sym}", "sym": sym, "entry_t": t["entry_t"], "exit_t": t["exit_t"], "R": t["R"]}
                 for t in r["trades"]]
        prev_close = g["close"].iat[-1]
    return rows


def nr_series(d1: pd.DataFrame, n: int) -> pd.Series:
    """Indicator NR-n pe ziua serverului (din bara D1 ANTERIOARA) — identic validate_special.nr_flags."""
    d = d1.copy()
    d["rng"] = d.high - d.low
    d["flag"] = (d.rng <= d.rng.rolling(n).min()).shift(1) if n else True
    d["day"] = d.time.dt.normalize()
    return d.set_index("day")["flag"]


def select(trades: pd.DataFrame, q_start: pd.Timestamp, a: dict) -> tuple[list[str], pd.DataFrame]:
    """Selectia trimestrului care incepe la `q_start` — DOAR trade-uri intrate inainte de q_start (anti look-ahead).
    `trades` are deja filtrul NR aplicat. Intoarce (componente, tabelul de statistici)."""
    hist = trades[(trades.entry_t >= q_start - pd.DateOffset(months=a["lookback_months"])) & (trades.entry_t < q_start)]
    assert hist.empty or hist.entry_t.max() < q_start
    g = hist.groupby("comp")["R"].agg(["count", "mean", "std"])
    g = g[g["count"] >= a["min_trades"]].copy()
    g["t"] = g["mean"] / (g["std"] / np.sqrt(g["count"]))
    g["sym"] = [c.split(":")[1] for c in g.index]
    ok = g[(g["t"] >= a["t_min"]) & (g["mean"] >= a["min_mean_R"])].sort_values("t", ascending=False)
    sel = ok.drop_duplicates("sym").head(a["max_components"])
    return list(sel.index), g.sort_values("t", ascending=False)


def today_nr(d1: pd.DataFrame, day: pd.Timestamp, n: int) -> bool | None:
    return True if not n else nr_flag(d1, day, n)
