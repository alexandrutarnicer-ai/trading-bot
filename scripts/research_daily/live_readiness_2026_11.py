"""Analiza Live Readiness (20.11.2026) — Daily Engine + Special Engine, pe barele M5 REALE din MT5 (doar citire).

Pentru fiecare piata / configuratie: n, win rate, profit factor, expectancy, total R, max DD (R), frecventa,
train / test (70 / 30 pe trade-uri), ultimele 12 luni, ani pozitivi + FEZABILITATEA la capitalul real
(lotul minim al brokerului: riscul in bani al fiecarui trade la SL → ce procent din trade-uri incap sub 1 / 2 / 3 / 5 %
din capital, P&L-ul si drawdown-ul in $ la lotul minim) + comparatia backtest ↔ shadow pe ACELEASI zile.

Aceleasi functii PURE ca engine-urile (daily_engine.strategy.evaluate_day_multi + admit_session_trades;
special_engine.strategies.orb_day / noise_day). Nu plaseaza nimic, nu scrie configuratii.

    python scripts/research_daily/live_readiness_2026_11.py [--capital 300]
Rezultat: data/research_daily/live_readiness_2026_11.json + tabele in consola.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from daily_engine import config as DC                                   # noqa: E402
from daily_engine.market_tools import market_sessions, server_to_exchange   # noqa: E402
from daily_engine.config import ENTRY_MODES, hm_to_min, sanitize_sessions   # noqa: E402
from daily_engine.strategy import admit_session_trades, evaluate_day_multi  # noqa: E402
from special_engine import config as SC                                 # noqa: E402
from special_engine.data import fetch_d1, fetch_m5, nr_series, noise_days, session  # noqa: E402
from special_engine.strategies import NOISE_LOOKBACK, noise_day, orb_day     # noqa: E402

OUT = os.path.join(ROOT, "data", "research_daily", "live_readiness_2026_11.json")
SHADOW_FROM = pd.Timestamp("2026-11-02")


# ───────────────────────────── statistici ─────────────────────────────
def stats(df: pd.DataFrame, usd_pt_minlot: float, capital: float) -> dict:
    if df.empty:
        return {"n": 0}
    df = df.sort_values("entry_t").reset_index(drop=True)
    R = df["R"].to_numpy(float)
    pos, neg = R[R > 0].sum(), -R[R < 0].sum()
    cum = np.cumsum(R)
    dd = float((cum - np.maximum.accumulate(np.maximum(cum, 0))).min())
    span_w = max(1.0, (df.entry_t.iloc[-1] - df.entry_t.iloc[0]).days / 7)
    k = int(len(df) * 0.7)
    last12 = df[df.entry_t >= df.entry_t.iloc[-1] - pd.DateOffset(months=12)]
    yrs = df.groupby(df.entry_t.dt.year)["R"].mean()
    risk_usd = df["risk"].to_numpy(float) * usd_pt_minlot                 # risc la SL, lotul minim
    money = R * risk_usd
    mcum = np.cumsum(money)
    out = {
        "n": int(len(df)), "from": str(df.entry_t.iloc[0].date()), "to": str(df.entry_t.iloc[-1].date()),
        "per_week": round(len(df) / span_w, 2), "win_rate": round(float((R > 0).mean()), 3),
        "pf": round(float(pos / neg), 2) if neg > 0 else None, "exp_R": round(float(R.mean()), 3),
        "total_R": round(float(R.sum()), 1), "max_dd_R": round(dd, 1),
        "avg_win_R": round(float(R[R > 0].mean()), 2) if (R > 0).any() else None,
        "train_R": round(float(R[:k].mean()), 3), "test_R": round(float(R[k:].mean()), 3),
        "last12_R": round(float(last12.R.mean()), 3) if len(last12) else None, "last12_n": int(len(last12)),
        "years_pos": f"{int((yrs > 0).sum())}/{len(yrs)}", "by_year": {int(y): round(float(v), 3) for y, v in yrs.items()},
        "t_stat": round(float(R.mean() / (R.std(ddof=1) / np.sqrt(len(R)))), 2) if len(R) > 2 else None,
        # bani la LOTUL MINIM (contul real nu poate merge sub el)
        "minlot_risk_usd_median": round(float(np.median(risk_usd)), 2),
        "minlot_risk_usd_p90": round(float(np.percentile(risk_usd, 90)), 2),
        "minlot_pnl_usd": round(float(money.sum()), 1),
        "minlot_max_dd_usd": round(float((mcum - np.maximum.accumulate(np.maximum(mcum, 0))).min()), 1),
        "feasible": {},
    }
    for pct in (1, 2, 3, 4, 5):
        ok = risk_usd <= capital * pct / 100 + 1e-9
        sub = R[ok]
        out["feasible"][f"{pct}%"] = {"share": round(float(ok.mean()), 3), "n": int(ok.sum()),
                                      "exp_R": round(float(sub.mean()), 3) if len(sub) else None,
                                      "pnl_usd": round(float(money[ok].sum()), 1)}
    return out


# ───────────────────────────── Daily ─────────────────────────────
def daily_trades(d0: pd.DataFrame, m: dict, point: float) -> pd.DataFrame:
    """Copie a market_tools.backtest_rates care pastreaza si riscul (distanta SL) + sesiunea fiecarui trade."""
    by_day: dict = {}
    for ses in market_sessions(m):
        loc = server_to_exchange(d0["time"], ses["tz"])
        d = d0.assign(loc=loc).dropna(subset=["loc"])
        d = d[d["loc"].dt.weekday < 5]
        om, lb = hm_to_min(ses["open"]), hm_to_min(ses["last_bar"])
        d = d.assign(mins=d["loc"].dt.hour * 60 + d["loc"].dt.minute)
        d = d[(d.mins >= om) & (d.mins <= lb)]
        d = d.assign(day=d["loc"].dt.normalize())
        n_or = ses["or_minutes"] // 5
        for day, g in d.groupby("day", sort=True):
            if g.mins.iloc[0] != om or len(g) < n_or + 6 or g.high.iloc[:n_or].max() - g.low.iloc[:n_or].min() <= 0:
                continue
            r = evaluate_day_multi(g.open, g.high, g.low, g.close, g.spread.to_numpy(float) * point, g.mins, open_min=om,
                                   or_minutes=ses["or_minutes"], mode=ENTRY_MODES[ses["entry"]], rr=ses.get("rr"),
                                   slip=ses["slip"], comm=ses["comm"], day_complete=True, reentry=ses.get("reentry"),
                                   plock=ses.get("profit_lock"))
            base = datetime(day.year, day.month, day.day, tzinfo=ZoneInfo(ses["tz"]))
            by_day.setdefault(day.tz_localize(None), []).append(
                {"key": ses["_session"], "st": r,
                 "to_utc": (lambda mins, _b=base: (_b + timedelta(minutes=int(mins))).astimezone(timezone.utc))})
    max_tr = int(m.get("max_trades_per_day") or sanitize_sessions(m)[1])
    rows = []
    for day in sorted(by_day):
        comb = admit_session_trades(by_day[day], max_tr)
        for item in by_day[day]:
            for t in comb[item["key"]]["st"]["trades"]:
                rows.append({"day": day, "entry_t": day + pd.Timedelta(minutes=int(t["entry_min"])), "R": float(t["R"]),
                             "risk": float(t["risk"]), "session": item["key"]})
    return pd.DataFrame(rows)


def daily_variants(cfg: dict) -> dict:
    base = {m["symbol"]: m for m in cfg["markets"]}
    de = copy.deepcopy(base["DE40"])
    us = copy.deepcopy(base["US500"])
    re_on = {**de["reentry"], "enabled": True}
    re_off = {**de["reentry"], "enabled": False}
    v = {}
    v["DE40 · Frankfurt · fără re-intrări (inițial 03.11)"] = {**de, "sessions": ["frankfurt"], "reentry": re_off, "max_trades_per_day": 1}
    v["DE40 · Frankfurt · re-intrări max 3 (09.11)"] = {**de, "sessions": ["frankfurt"], "reentry": re_on, "max_trades_per_day": 3}
    v["DE40 · Frankfurt + NY · max 2 · re-intrări"] = {**de, "sessions": ["frankfurt", "new_york"], "reentry": re_on, "max_trades_per_day": 2}
    v["DE40 · Frankfurt + NY · max 2 · fără re-intrări"] = {**de, "sessions": ["frankfurt", "new_york"], "reentry": re_off, "max_trades_per_day": 2}
    v["DE40 · Frankfurt + NY · max 3 · re-intrări"] = {**de, "sessions": ["frankfurt", "new_york"], "reentry": re_on, "max_trades_per_day": 3}
    v["DE40 · Londra + Frankfurt + NY · max 3 (ACTUAL)"] = {**de}
    from daily_engine.market_tools import PRESETS
    ny = {k: PRESETS["new_york"][k] for k in ("tz", "open", "last_bar", "or_minutes", "entry")}
    v["DE40 · NY singur · re-intrări"] = {**de, **ny, "preset": "new_york", "sessions": ["new_york"], "reentry": re_on,
                                         "max_trades_per_day": 3}
    v["US500 · NY · fără re-intrări (inițial)"] = {**us, "reentry": {**us["reentry"], "enabled": False}, "max_trades_per_day": 1}
    v["US500 · NY · re-intrări max 3 (ACTUAL)"] = {**us}
    return v


# ───────────────────────────── Special ─────────────────────────────
def special_jp225(d: pd.DataFrame, d1: pd.DataFrame, point: float) -> pd.DataFrame:
    tz, op, last = SC.ORB_MARKETS["JP225"]
    slip, comm = SC.COSTS["JP225"]
    s, om, _ = session(d, tz, op, last, inclusive_end=True)
    nr = nr_series(d1, 4)
    rows = []
    for day, g in s.groupby("day", sort=True):
        if g.mins.iloc[0] != om or len(g) < 12:
            continue
        o, h, l, c = (g[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        if h[:1].max() - l[:1].min() <= 0:
            continue
        r = orb_day(o, h, l, c, g["spread"].to_numpy(float) * point, g["mins"].to_numpy(), open_min=om, or_minutes=5,
                    entry="direction", slip=slip, comm=comm, day_complete=True)
        if r.get("phase") != "closed":
            continue
        flag = nr.get(day)
        rows.append({"day": day, "entry_t": day + pd.Timedelta(minutes=int(r["entry_min"])), "R": float(r["R"]),
                     "risk": float(r["risk"]), "nr4": bool(flag) if flag is not None and flag == flag else False})
    return pd.DataFrame(rows)


def special_ustec(d: pd.DataFrame, point: float, stop_mult: float) -> pd.DataFrame:
    tz, op, cl = SC.NOISE_MARKETS["USTEC"]
    cost = sum(SC.COSTS["USTEC"])
    days, slots, mv, om, cm = noise_days(d, tz, op, cl)
    rows, prev = [], None
    for k, (day, g) in enumerate(days):
        if k < NOISE_LOOKBACK or prev is None:
            prev = g["close"].iat[-1]
            continue
        sig = np.nanmean(np.array(mv[k - NOISE_LOOKBACK:k]), axis=0)
        r = noise_day(g, sig=sig, slots=slots, prev_close=prev, om=om, cm=cm, point=point, cost_px=cost, day=day, sym="USTEC")
        for t in r["trades"]:
            rows.append({"day": day, "entry_t": t["entry_t"], "R": float(t["R"]), "risk": stop_mult * float(t["unit"])})
        prev = g["close"].iat[-1]
    return pd.DataFrame(rows)


# ───────────────────────────── shadow ─────────────────────────────
def shadow_daily() -> pd.DataFrame:
    from daily_engine.engine import split_valid
    rows = [json.loads(x) for x in open(os.path.join(ROOT, "data", "daily_engine", "trades.jsonl"), encoding="utf-8") if x.strip()]
    rows, bad = split_valid(rows)                      # aceleasi reguli ca statisticile engine-ului
    df = pd.DataFrame(rows)
    df["session"] = df.get("session").fillna("")
    df["k"] = df.get("k").fillna(0).astype(int)
    n0 = len(df)
    df = df.drop_duplicates(subset=["day", "symbol", "session", "k", "side", "entry"])
    return df.assign(_dups=n0 - len(df) + len(bad))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=300.0)
    a = ap.parse_args()
    import MetaTrader5 as mt5
    if not mt5.initialize():
        sys.exit("MT5 indisponibil")
    cfg = DC.load_config()
    res = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "capital": a.capital,
           "daily": {}, "special": {}, "specs": {}, "shadow": {}}
    usd_pt, bars = {}, {}
    for s in ("DE40", "US500", "JP225", "USTEC"):
        info = mt5.symbol_info(s)
        tick = mt5.symbol_info_tick(s)
        usd_pt[s] = info.trade_tick_value / info.trade_tick_size * info.volume_min
        bars[s] = fetch_m5(mt5, s)
        res["specs"][s] = {"min_lot": info.volume_min, "usd_per_point_minlot": round(usd_pt[s], 4),
                           "margin_minlot": round(mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, s, info.volume_min, tick.ask), 2),
                           "spread_pts": round(tick.ask - tick.bid, 2), "bars_from": str(bars[s].time.iloc[0].date()),
                           "bars_to": str(bars[s].time.iloc[-1])}
    pts = {s: mt5.symbol_info(s).point for s in usd_pt}
    # Daily
    sh = shadow_daily()
    res["shadow"]["daily_duplicates_ignored"] = int(sh["_dups"].iloc[0])
    for name, m in daily_variants(cfg).items():
        sym = m["symbol"]
        df = daily_trades(bars[sym], m, pts[sym])
        st = stats(df, usd_pt[sym], a.capital)
        sw = df[df.day >= SHADOW_FROM]
        st["window_shadow"] = {"n": int(len(sw)), "total_R": round(float(sw.R.sum()), 2)}
        res["daily"][name] = st
        print(f"{name:52} n={st['n']:4} wr={st['win_rate']:.2f} pf={st['pf']} exp={st['exp_R']:+.3f} "
              f"DD={st['max_dd_R']} /sapt={st['per_week']} tr/te={st['train_R']:+.3f}/{st['test_R']:+.3f} "
              f"12m={st['last12_R']} risc$ med={st['minlot_risk_usd_median']} "
              f"fez 2/3/5%={st['feasible']['2%']['share']}/{st['feasible']['3%']['share']}/{st['feasible']['5%']['share']} "
              f"shadowWin n={st['window_shadow']['n']} R={st['window_shadow']['total_R']}")
    for sym in ("DE40", "US500", "GBPUSD"):
        s_ = sh[sh.symbol == sym]
        if len(s_):
            R = s_.R.astype(float)
            res["shadow"][sym] = {"n": int(len(s_)), "from": str(s_.day.min()), "to": str(s_.day.max()),
                                  "win_rate": round(float((R > 0).mean()), 3), "total_R": round(float(R.sum()), 2),
                                  "exp_R": round(float(R.mean()), 3),
                                  "pf": round(float(R[R > 0].sum() / -R[R < 0].sum()), 2) if (R < 0).any() else None,
                                  "by_session": {k: round(float(v), 2) for k, v in s_.groupby("session")["R"].sum().items()}}
    # Special
    d1 = fetch_d1(mt5, "JP225")
    jp = special_jp225(bars["JP225"], d1, pts["JP225"])
    for name, df in (("JP225 · ORB 5 min direcție · TOATE zilele", jp),
                     ("JP225 · ORB 5 min direcție · doar NR4 (ACTUAL)", jp[jp.nr4])):
        st = stats(df, usd_pt["JP225"], a.capital)
        sw = df[df.day >= SHADOW_FROM]
        st["window_shadow"] = {"n": int(len(sw)), "total_R": round(float(sw.R.sum()), 2)}
        res["special"][name] = st
        print(f"{name:52} n={st['n']:4} wr={st['win_rate']:.2f} pf={st['pf']} exp={st['exp_R']:+.3f} DD={st['max_dd_R']} "
              f"/sapt={st['per_week']} tr/te={st['train_R']:+.3f}/{st['test_R']:+.3f} 12m={st['last12_R']} "
              f"risc$ med={st['minlot_risk_usd_median']} shadowWin n={st['window_shadow']['n']} R={st['window_shadow']['total_R']}")
    us = special_ustec(bars["USTEC"], pts["USTEC"], SC.load_config()["noise_stop_mult"] if hasattr(SC, "load_config") else 2.0)
    st = stats(us, usd_pt["USTEC"], a.capital)
    sw = us[us.day >= SHADOW_FROM]
    st["window_shadow"] = {"n": int(len(sw)), "total_R": round(float(sw.R.sum()), 2)}
    res["special"]["USTEC · NOISE (Beat the Market) (ACTUAL)"] = st
    print(f"{'USTEC · NOISE (ACTUAL)':52} n={st['n']:4} wr={st['win_rate']:.2f} pf={st['pf']} exp={st['exp_R']:+.3f} DD={st['max_dd_R']} "
          f"/sapt={st['per_week']} tr/te={st['train_R']:+.3f}/{st['test_R']:+.3f} 12m={st['last12_R']} "
          f"risc$ med={st['minlot_risk_usd_median']} fez 1/2%={st['feasible']['1%']['share']}/{st['feasible']['2%']['share']} "
          f"shadowWin n={st['window_shadow']['n']} R={st['window_shadow']['total_R']}")
    sp = [json.loads(x) for x in open(os.path.join(ROOT, "data", "special_engine", "trades.jsonl"), encoding="utf-8") if x.strip()]
    spd = pd.DataFrame(sp)
    for comp, g in spd.groupby("comp"):
        R = g.R.astype(float)
        res["shadow"][comp] = {"n": int(len(g)), "win_rate": round(float((R > 0).mean()), 3), "total_R": round(float(R.sum()), 2),
                               "exp_R": round(float(R.mean()), 3), "from": g.day.min(), "to": g.day.max()}
    res["specs"]["account"] = {"equity": mt5.account_info().equity}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
    print(json.dumps(res["shadow"], ensure_ascii=False, indent=1, default=str))
    print(json.dumps(res["specs"], ensure_ascii=False, indent=1))
    print("->", OUT)


if __name__ == "__main__":
    main()
