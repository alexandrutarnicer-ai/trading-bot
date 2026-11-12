"""
DE40 (Daily Engine, Frankfurt 09:00, interval 5 min, breakout) — analiza de pregatire pentru LIVE (2026-11-12).
DOAR citire: CSV-ul de cercetare (tot istoricul M5) + specificatiile live din MT5 (fara ordine).

Raspunde la: rezultate istorice vs out-of-sample (train 70 / test 30, pe ani), ore de intrare, zile ale saptamanii,
sensibilitate la costuri (slippage), distributia R, frecventa, si CONSTRANGEREA CONTULUI (lot minim, risc, marja).
    python scripts/research_daily/de40_live_readiness.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from daily_engine.config import ENTRY_MODES, hm_to_min, load_config  # noqa: E402
from daily_engine.strategy import evaluate_day_multi  # noqa: E402
from daily_profit_lock import days_of  # noqa: E402

OUT = os.path.join(ROOT, "data", "research_daily", "de40_live_readiness.json")


def trades(m, extra_slip=0.0):
    rows = []
    for day, g in days_of(m):
        r = evaluate_day_multi(g.open, g.high, g.low, g.close, g.spread.to_numpy(float) * 0.01, g.mins,
                               open_min=hm_to_min(m["open"]), or_minutes=m["or_minutes"], mode=ENTRY_MODES[m["entry"]],
                               rr=m.get("rr"), slip=m["slip"] + extra_slip, comm=m["comm"], day_complete=True,
                               reentry=m.get("reentry"))
        for t in r["trades"]:
            rows.append({"day": day, "k": t.get("k", 0), "R": float(t["R"]), "risk_pts": float(t["risk"]),
                         "entry_min": int(t["entry_min"]), "reason": t["reason"]})
    return pd.DataFrame(rows)


def summ(R):
    R = np.asarray(R, float)
    if not len(R):
        return {"n": 0}
    eq = np.cumsum(R)
    w, ls = R[R > 0], R[R < 0]
    t = R.mean() / (R.std(ddof=1) / np.sqrt(len(R))) if len(R) > 2 and R.std() > 0 else None
    return {"n": int(len(R)), "exp_R": round(float(R.mean()), 4), "net_R": round(float(R.sum()), 1),
            "win_rate": round(float((R > 0).mean() * 100), 1),
            "pf": round(float(w.sum() / -ls.sum()), 3) if ls.sum() < 0 else None,
            "max_dd_R": round(float((eq - np.maximum.accumulate(eq)).min()), 1), "t": None if t is None else round(float(t), 2)}


def main():
    m = next(x for x in load_config()["markets"] if x["symbol"] == "DE40")
    df = trades(m)
    df["year"] = pd.to_datetime(df.day).dt.year
    cut = int(0.7 * len(df))
    res = {"config": {k: m.get(k) for k in ("tz", "open", "last_bar", "or_minutes", "entry", "rr", "reentry", "slip", "comm")},
           "all": summ(df.R), "train": summ(df.R[:cut]), "test": summ(df.R[cut:]),
           "test_from": str(df.day.iloc[cut].date()),
           "first_trade_only": summ(df[df.k == 0].R), "reentries_only": summ(df[df.k > 0].R),
           "by_year": {int(y): summ(g.R) for y, g in df.groupby("year")},
           "by_entry_hour_berlin": {f"{h:02d}h": summ(g.R) for h, g in df.groupby(df.entry_min // 60)},
           "by_weekday": {d: summ(g.R) for d, g in df.groupby(pd.to_datetime(df.day).dt.day_name())},
           "R_dist": {p: round(float(np.percentile(df.R, q)), 2) for p, q in (("p10", 10), ("p50", 50), ("p90", 90), ("p99", 99))},
           "exits": df.reason.value_counts().to_dict(),
           "per_week": round(len(df) / (df.day.nunique() / 5), 2)}
    # sensibilitate la costuri: slippage suplimentar pe intrare si iesire (in puncte DE40)
    res["slippage_extra"] = {f"+{s:g} pts": summ(trades(m, s).R) for s in (0.5, 1.0, 2.0)}
    # constrangerea contului: risc la lotul minim pe distanta reala a SL-ului (ultimii 2 ani)
    try:
        import MetaTrader5 as mt5
        mt5.initialize()
        info, acc, tick = mt5.symbol_info("DE40"), mt5.account_info(), mt5.symbol_info_tick("DE40")
        vpp = info.trade_tick_value / info.trade_tick_size
        rec = df[pd.to_datetime(df.day) >= pd.to_datetime(df.day).max() - pd.Timedelta(days=730)]
        risk_min = rec.risk_pts * vpp * info.volume_min
        eq = float(acc.equity)
        from live.global_guard import risk_cap_pct
        cap = risk_cap_pct() or 100.0
        res["account"] = {"equity": round(eq, 2), "volume_min": info.volume_min, "usd_per_point_per_lot": round(vpp, 4),
                          "margin_min_lot": round(mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, "DE40", info.volume_min, tick.ask), 2),
                          "spread_live_pts": round(tick.ask - tick.bid, 2), "stops_level": info.trade_stops_level,
                          "freeze_level": info.trade_freeze_level, "risk_cap_pct_global": cap,
                          "risk_min_lot_pct_of_equity": {p: round(float(np.percentile(risk_min / eq * 100, q)), 2)
                                                         for p, q in (("p25", 25), ("p50", 50), ("p75", 75), ("p90", 90))},
                          "pct_trades_blocked_by_cap": round(float((risk_min / eq * 100 > cap).mean() * 100), 1),
                          "R_of_blocked": summ(rec.R[(risk_min / eq * 100 > cap).values]),
                          "R_of_allowed": summ(rec.R[(risk_min / eq * 100 <= cap).values])}
    except Exception as e:                                # noqa: BLE001
        res["account"] = {"error": str(e)}
    # shadow
    try:
        from daily_engine.engine import load_trades
        sh = [t for t in load_trades() if t["symbol"] == "DE40"]
        res["shadow"] = {**summ([t["R"] for t in sh]), "blocked": sum(1 for t in sh if t.get("blocked"))}
    except Exception as e:                                # noqa: BLE001
        res["shadow"] = {"error": str(e)}
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=1, default=str)
    print(json.dumps(res, indent=1, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
