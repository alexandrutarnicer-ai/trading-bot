"""
Noisy Engine — verificarea candidatilor gasiti de edge_test (M5 mean reversion): e un edge REAL sau noroc
de cautare (72 de combinatii testate)?  t-stat, bootstrap P(edge>0), consistenta pe trimestre si
sensibilitate la costuri (slippage 25% / 50% / 100% din spread, comision Raw $7/lot).

    python scripts/research_noisy/candidate_check.py  ->  data/research_noisy/candidates.json
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd
import MetaTrader5 as mt5

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import edge_test as E  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
CANDIDATES = ["XAUUSD", "USDJPY", "EURUSD", "AUDUSD", "US30"]
N_TRIALS = 72          # combinatii incercate in edge_test (12 piete x 3 strategii x 2 TF) — pentru corectia Bonferroni


def mr_trades(sym: str, metrics: dict, slip_frac: float, raw_comm: bool) -> pd.DataFrame:
    r = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, E.START, E.END)
    df = pd.DataFrame(r)
    t = pd.to_datetime(df["time"], unit="s")
    info = mt5.symbol_info(sym)
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    hour = t.dt.hour.to_numpy()
    liquid = np.isin(hour, list(E.LIQUID_SERVER_H[E.KIND[sym]]))
    m = metrics[sym]
    by_h = {x["hour"]: x["spread_med"] for x in m.get("by_hour_ro", [])}
    med = m["spread_median"]
    sp_prof = np.array([by_h.get(int(x), med) for x in (hour - 1) % 24])
    spread = np.maximum(df["spread"].to_numpy(float) * info.point, sp_prof)
    cost = spread + m["comm_in_price"] + 2 * slip_frac * med
    if raw_comm and E.KIND[sym] in ("fx", "metal"):
        cost = cost + 7.0 / (info.trade_tick_value / info.trade_tick_size)
    a = E.atr(h, l, c)
    e20 = E.ema(c, 20)
    sig = np.where(c < e20 - 2 * a, 1, np.where(c > e20 + 2 * a, -1, 0)) * liquid
    tr = E.simulate(o, h, l, c, sig.astype(int), 1.5 * a, np.abs(e20 - c) + 1e-12, 20, cost)
    arr = np.array(tr)
    out = pd.DataFrame({"time": t.iloc[arr[:, 0].astype(int)].to_numpy(), "gross_R": arr[:, 1] / arr[:, 3],
                        "net_R": arr[:, 2] / arr[:, 3], "hold_bars": arr[:, 4]})
    return out


def stats(d: pd.DataFrame, rng: np.random.Generator) -> dict:
    x = d["net_R"].to_numpy()
    n = len(x)
    mean, sd = x.mean(), x.std(ddof=1)
    t = mean / (sd / np.sqrt(n))
    # bootstrap pe blocuri de zile (trade-urile din aceeasi zi sunt corelate)
    days = d["time"].dt.date.to_numpy()
    uniq = np.unique(days)
    by_day = {u: x[days == u] for u in uniq}
    boots = []
    for _ in range(2000):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        boots.append(np.concatenate([by_day[p] for p in pick]).mean())
    boots = np.array(boots)
    q = d.groupby(d["time"].dt.to_period("Q"))["net_R"].mean()
    eq = np.cumsum(x)
    dd = float((eq - np.maximum.accumulate(eq)).min())
    streak = cur = 0
    for v in x:
        cur = cur + 1 if v < 0 else 0
        streak = max(streak, cur)
    return {"trades": n, "per_day": n / len(uniq), "net_R": float(mean), "gross_R": float(d["gross_R"].mean()),
            "t_stat": float(t), "p_edge_pos_boot": float((boots > 0).mean()),
            "ci90": [float(np.percentile(boots, 5)), float(np.percentile(boots, 95))],
            "bonferroni_t_needed": 2.98,   # ~ p<0.05/72 unilateral
            "quarters_pos": f"{int((q > 0).sum())}/{len(q)}", "quarters": {str(k): round(float(v), 3) for k, v in q.items()},
            "win_rate": float((x > 0).mean()), "max_dd_R": dd, "max_loss_streak": int(streak),
            "avg_hold_min": float(d["hold_bars"].mean() * 5)}


def main() -> None:
    assert mt5.initialize()
    metrics = {s["symbol"]: s for s in json.load(open(os.path.join(E.OUT, "market_metrics.json"), encoding="utf-8"))["symbols"]
               if "spread_median" in s}
    rng = np.random.default_rng(7)
    res = {}
    for sym in CANDIDATES:
        res[sym] = {}
        for label, slip, raw in (("slip25", 0.25, False), ("slip50", 0.5, False), ("slip100", 1.0, False), ("raw7", 0.25, True)):
            s = stats(mr_trades(sym, metrics, slip, raw), rng)
            res[sym][label] = s
            print(f"{sym:7s} {label:7s} n={s['trades']:5d} ({s['per_day']:.1f}/zi) net={s['net_R']:+.3f}R t={s['t_stat']:+.2f} "
                  f"P(>0)={s['p_edge_pos_boot']:.2f} CI90={s['ci90'][0]:+.3f}..{s['ci90'][1]:+.3f} trim+={s['quarters_pos']} "
                  f"DD={s['max_dd_R']:.1f}R serie-={s['max_loss_streak']} hold={s['avg_hold_min']:.0f}min", flush=True)
    json.dump(res, open(os.path.join(E.OUT, "candidates.json"), "w", encoding="utf-8"), indent=1, default=str)


if __name__ == "__main__":
    main()
