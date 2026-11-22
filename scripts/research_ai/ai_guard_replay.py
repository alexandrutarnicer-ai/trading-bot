"""Re-simularea celor 103 trade-uri AI reale pe barele M5 MT5, cu si fara reguli IN COD (propunerea de imbunatatire):
  G1 regim: fara intrari noi in regim CHOPPY (eticheta din snapshot-ul consiliului);
  G2 SL minim 2,5 × ATR(M15) (SL-ul prea strans e largit; TP recalculat la acelasi RR);
  G1 + G2.
Baza = aceeasi simulare cu SL / TP-ul ales de consiliu (comparatie mere cu mere; nu rezultatul real MT5).
Fill: ordinul stop la intrare in max 24 h de la decizie (altfel expirat); iesire SL / TP / 48 h.

    python scripts/research_ai/ai_guard_replay.py
"""
from __future__ import annotations

import os
import sys
from datetime import timedelta

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def sim(b, side, entry, sl, tp, t0, market):
    w = b[(b.time >= t0) & (b.time <= t0 + timedelta(hours=72))]
    if w.empty:
        return None
    i0 = 0
    if not market:
        hit = np.where((w.high >= entry) if side == 1 else (w.low <= entry))[0]
        hit = hit[hit < 288]                               # 24 h de M5
        if not len(hit):
            return 0.0, "expirat"
        i0 = hit[0]
    risk = abs(entry - sl)
    for k in range(i0, min(len(w), i0 + 576)):             # 48 h
        h, l = w.high.iat[k], w.low.iat[k]
        if (l <= sl) if side == 1 else (h >= sl):
            return -1.0, "SL"
        if k > i0 and ((h >= tp) if side == 1 else (l <= tp)):
            return abs(tp - entry) / risk, "TP"
    return (w.close.iat[min(len(w), i0 + 576) - 1] - entry) * side / risk, "timp"


def main():
    import MetaTrader5 as mt5
    mt5.initialize()
    d = pd.read_csv(os.path.join(ROOT, "data", "research_ai_decisions_closed.csv"))
    d = d.dropna(subset=["entry", "sl", "tp", "atr"])
    cache, rows = {}, []
    for _, r in d.iterrows():
        sym = r.symbol
        if sym not in cache:
            mt5.symbol_select(sym, True)
            x = pd.DataFrame(mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 60000))
            x["time"] = pd.to_datetime(x.time, unit="s")
            cache[sym] = x
        b, side, t0 = cache[sym], int(r.side), pd.Timestamp(r.ts)
        market = str(r.order_type) == "market"
        rr = abs(r.tp - r.entry) / abs(r.entry - r.sl)
        base = sim(b, side, r.entry, r.sl, r.tp, t0, market)
        risk2 = max(abs(r.entry - r.sl), 2.5 * r.atr)
        g2 = sim(b, side, r.entry, r.entry - side * risk2, r.entry + side * rr * risk2, t0, market)
        if base is None or g2 is None:
            continue
        rows.append({"symbol": sym, "ts": r.ts, "regime": r.regime, "real_R": r.result_r, "base": base[0], "g2": g2[0],
                     "base_st": base[1], "g2_st": g2[1], "sl_atr": abs(r.entry - r.sl) / r.atr})
    x = pd.DataFrame(rows)
    traded = lambda s: s != "expirat"
    print(f"trade-uri re-simulate: {len(x)} (real MT5 pe aceleasi: {x.real_R.sum():+.1f}R)")
    print(f"  baza (SL/TP consiliu, simulat): {x.base.sum():+.1f}R · n {traded(x.base_st).sum()}")
    g1 = x[x.regime != "CHOPPY"]
    print(f"  G1 fara CHOPPY:                 {g1.base.sum():+.1f}R · n {traded(g1.base_st).sum()} (eliminate {len(x) - len(g1)})")
    print(f"  G2 SL minim 2,5 ATR:            {x.g2.sum():+.1f}R · n {traded(x.g2_st).sum()}")
    print(f"  G1 + G2:                        {g1.g2.sum():+.1f}R · n {traded(g1.g2_st).sum()}")
    print("\n  pe regim (baza / G2):")
    print(x.groupby("regime")[["base", "g2"]].agg(["count", "sum", "mean"]).round(2).to_string())
    k = int(len(x) * 0.5)
    x = x.sort_values("ts")
    for name, part in (("prima jumatate", x.iloc[:k]), ("a doua jumatate", x.iloc[k:])):
        p1 = part[part.regime != "CHOPPY"]
        print(f"  {name}: baza {part.base.sum():+.1f}R · G1+G2 {p1.g2.sum():+.1f}R")
    x.to_csv(os.path.join(ROOT, "data", "research_ai_guard_replay.csv"), index=False)


if __name__ == "__main__":
    sys.exit(main())
