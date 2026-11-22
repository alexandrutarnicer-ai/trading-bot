"""Variante de context peste proxy-ul regime_flip (ai_market_scan_2026_11.py) — DOAR doua, ca sa nu fie data-mining:
  (a) flip M30 DOAR in directia trendului D1 (EMA200 D1 al ultimei bare inchise) — cum confirma consiliul contextul;
  (b) (a) + regim TRENDING (Efficiency Ratio 20 bare M15 ≥ 0,35, eticheta din briefing-ul consiliului) + tinere 48 h.
Aceleasi costuri / SL 2,5×ATR / TP 2R / cooldown 120 min. Robust = medie > 0 pe train SI test SI ultimele 12 luni, t ≥ 1,5.

    python scripts/research_ai/ai_market_scan_variants.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ai_market_scan_2026_11 import FX, OTHER, bars, stats  # noqa: E402

OUT = os.path.join(ROOT, "data", "research_ai_scan_variants_2026_11.json")


def run(m15, m30, d1, point, markup, need_trend_er: bool, max_bars: int):
    m30 = m30.assign(ema=m30.close.ewm(span=200, adjust=False).mean(), closed_at=m30.time + pd.Timedelta(minutes=30))
    d1 = d1.assign(ema_d=d1.close.ewm(span=200, adjust=False).mean(), closed_at=d1.time + pd.Timedelta(days=1))
    m = m15.assign(close_t=m15.time + pd.Timedelta(minutes=15)).sort_values("close_t")
    m = pd.merge_asof(m, m30[["closed_at", "ema"]].sort_values("closed_at"), left_on="close_t", right_on="closed_at")
    m = pd.merge_asof(m.drop(columns="closed_at"), d1[["closed_at", "ema_d", "close"]].rename(columns={"close": "d_close"})
                      .sort_values("closed_at"), left_on="close_t", right_on="closed_at")
    m = m.dropna(subset=["ema", "ema_d"]).reset_index(drop=True)
    tr = np.sign(m.close - m.ema).to_numpy()
    trd = np.sign(m.d_close - m.ema_d).to_numpy()
    h, l, c, o = (m[k].to_numpy(float) for k in ("high", "low", "close", "open"))
    pc = np.r_[c[0], c[:-1]]
    atr = pd.Series(np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))).rolling(14).mean().to_numpy()
    path = pd.Series(np.abs(np.diff(c, prepend=c[0]))).rolling(20).sum().to_numpy()
    er = np.abs(c - np.r_[np.full(20, np.nan), c[:-20]]) / np.where(path > 0, path, np.nan)
    spr = m.spread.to_numpy(float) * point + markup
    rows, i, last, n = [], 1, -10**9, len(m)
    while i < n - 2:
        ok = tr[i] != 0 and tr[i - 1] != 0 and tr[i] != tr[i - 1] and i - last >= 8 and atr[i] > 0 and tr[i] == trd[i]
        if ok and need_trend_er:
            ok = er[i] >= 0.35
        if ok:
            last, side, j = i, int(tr[i]), i + 1
            cost = spr[j] * 1.1
            entry = o[j] + side * cost / 2
            risk = 2.5 * atr[i]
            sl, tp, out, k = entry - side * risk, entry + side * 2 * risk, None, j
            for k in range(j, min(n, j + max_bars)):
                if (l[k] <= sl) if side == 1 else (h[k] >= sl):
                    out = -1 - cost / 2 / risk
                    break
                if (h[k] >= tp) if side == 1 else (l[k] <= tp):
                    out = 2 - cost / 2 / risk
                    break
            if out is None:
                out = (c[k] - entry) * side / risk - cost / 2 / risk
            rows.append({"t": m.time.iat[j], "R": out, "risk_px": risk, "side": side})
            i = k + 1
            continue
        i += 1
    return pd.DataFrame(rows)


def main():
    import MetaTrader5 as mt5
    mt5.initialize()
    res = {}
    for sym in FX + OTHER:
        info = mt5.symbol_info(sym)
        if info is None or info.trade_mode != 4:
            continue
        m15, m30, d1 = (bars(mt5, sym, tf, n) for tf, n in ((mt5.TIMEFRAME_M15, 200000), (mt5.TIMEFRAME_M30, 100000),
                                                              (mt5.TIMEFRAME_D1, 5000)))
        if m15 is None or m30 is None or d1 is None:
            continue
        pip = 0.01 if sym.endswith("JPY") else 0.0001
        markup = 0.8 * pip if sym in FX else 0.0
        res[sym] = {}
        for name, er_on, mb in (("a_d1", False, 48), ("b_d1_trend_48h", True, 192)):
            st = stats(run(m15, m30, d1, info.point, markup, er_on, mb))
            if st is None:
                continue
            st["robust"] = bool(st["exp"] > 0 and st["train"] > 0 and st["test"] > 0 and st["last12"] > 0 and st["t"] >= 1.5)
            res[sym][name] = st
            print(f"{sym:8} {name:15} n={st['n']:5} {st['per_week']:4}/s exp={st['exp']:+.3f} t={st['t']:5} pf={st['pf']} "
                  f"tr/te={st['train']:+.3f}/{st['test']:+.3f} 12m={st['last12']:+.3f}({st['last12_n']}) 3m={st['last3']} "
                  f"ani={st['years_pos']} {'ROBUST' if st['robust'] else ''}")
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("->", OUT)


if __name__ == "__main__":
    main()
