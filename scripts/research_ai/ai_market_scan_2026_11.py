"""Scanare piete noi pentru AI Engine (22.11.2026) — proxy mecanic al SINGURULUI declansator profitabil din ledger.

Ledger real (103 trade-uri, iul–nov 2026): toate pietele negative (−28R); singurul declansator pozitiv = regime_flip
pe M30 (EMA200, n=14, +4,9R). Consiliul pune tipic un ordin stop, SL ~2,8×ATR(M15), TP 2R, tine cateva ore.

Proxy (fara LLM): la inchiderea unei bare M15 in care trendul M30 (semnul close − EMA200 al ultimei bare M30 INCHISE —
echivalent live, fara lookahead) isi schimba semnul → intrare la deschiderea barei urmatoare in directia noului trend,
SL 2,5×ATR14(M15), TP 2R, iesire fortata dupa 48 de bare (12 h), o pozitie odata, pauza 120 min intre declansari (ca
cooldown-ul motorului). Costuri: spread-ul barei + markup-ul contului Standard pe FX (0,8 pip) + slippage 0,1×spread.
E o LIMITA SUPERIOARA mecanica: consiliul filtreaza (din 217 declansari a deschis 65) — rezultatul real depinde de el.

Fezabilitate 300 $: risc 1% (3 $) la SL tipic cu lotul minim, marja lotului ≤ 40% din marja libera (rail-ul AI).

    python scripts/research_ai/ai_market_scan_2026_11.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "research_ai_scan_2026_11.json")

FX = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY",
      "CHFJPY", "NZDJPY", "EURGBP", "EURAUD", "EURCAD", "EURCHF", "GBPAUD", "GBPCAD", "GBPCHF", "AUDCAD", "AUDNZD",
      "AUDCHF", "NZDCAD", "CADCHF"]
OTHER = ["XAUUSD", "XAGUSD", "US500", "JP225", "AUS200", "STOXX50", "UK100"]
SL_ATR, RR, MAX_BARS, COOLDOWN_BARS = 2.5, 2.0, 48, 8


def bars(mt5, sym, tf, n):
    mt5.symbol_select(sym, True)
    r = mt5.copy_rates_from_pos(sym, tf, 0, n)
    if r is None or not len(r):
        return None
    d = pd.DataFrame(r)
    d["time"] = pd.to_datetime(d["time"], unit="s")
    return d


def trades_for(m15, m30, point, markup):
    m30 = m30.copy()
    m30["ema"] = m30["close"].ewm(span=200, adjust=False).mean()
    m30["closed_at"] = m30["time"] + pd.Timedelta(minutes=30)
    m15 = m15.copy()
    m15["close_t"] = m15["time"] + pd.Timedelta(minutes=15)
    m = pd.merge_asof(m15.sort_values("close_t"), m30[["closed_at", "ema"]].sort_values("closed_at"),
                      left_on="close_t", right_on="closed_at", direction="backward")
    m = m.dropna(subset=["ema"]).reset_index(drop=True)
    tr = np.sign(m["close"] - m["ema"]).to_numpy()
    h, l, c, o = (m[k].to_numpy(float) for k in ("high", "low", "close", "open"))
    pc = np.r_[c[0], c[:-1]]
    atr = pd.Series(np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))).rolling(14).mean().to_numpy()
    spr = m["spread"].to_numpy(float) * point + markup
    rows, i, last_trig, n = [], 1, -10**9, len(m)
    while i < n - 2:
        if tr[i] != 0 and tr[i] != tr[i - 1] and tr[i - 1] != 0 and i - last_trig >= COOLDOWN_BARS and atr[i] > 0:
            last_trig = i
            side = int(tr[i])
            j = i + 1
            cost = spr[j] * 1.1
            entry = o[j] + side * cost / 2
            risk = SL_ATR * atr[i]
            sl, tp = entry - side * risk, entry + side * RR * risk
            out, k = None, j
            for k in range(j, min(n, j + MAX_BARS)):
                hit_sl = (l[k] <= sl) if side == 1 else (h[k] >= sl)
                hit_tp = (h[k] >= tp) if side == 1 else (l[k] <= tp)
                if hit_sl:
                    out = -1.0 - (cost / 2) / risk
                    break
                if hit_tp:
                    out = RR - (cost / 2) / risk
                    break
            if out is None:
                out = (c[k] - entry) * side / risk - (cost / 2) / risk
            rows.append({"t": m["time"].iat[j], "R": out, "risk_px": risk, "side": side})
            i = k + 1
            continue
        i += 1
    return pd.DataFrame(rows)


def stats(df):
    if len(df) < 30:
        return None
    df = df.sort_values("t").reset_index(drop=True)
    R = df.R.to_numpy()
    k = int(len(R) * 0.7)
    cum = np.cumsum(R)
    yrs = df.groupby(df.t.dt.year).R.mean()
    last12 = df[df.t >= df.t.iloc[-1] - pd.DateOffset(months=12)].R
    last3 = df[df.t >= df.t.iloc[-1] - pd.DateOffset(months=3)].R
    span_w = max(1.0, (df.t.iloc[-1] - df.t.iloc[0]).days / 7)
    return {"n": len(R), "from": str(df.t.iloc[0].date()), "per_week": round(len(R) / span_w, 2),
            "exp": round(R.mean(), 3), "wr": round((R > 0).mean(), 3),
            "pf": round(R[R > 0].sum() / -R[R < 0].sum(), 2) if (R < 0).any() else None,
            "t": round(R.mean() / (R.std(ddof=1) / np.sqrt(len(R))), 2), "dd": round(float((cum - np.maximum.accumulate(np.maximum(cum, 0))).min()), 1),
            "train": round(R[:k].mean(), 3), "test": round(R[k:].mean(), 3),
            "last12": round(last12.mean(), 3), "last12_n": int(len(last12)), "last3": round(last3.mean(), 3) if len(last3) else None,
            "years_pos": f"{int((yrs > 0).sum())}/{len(yrs)}", "by_year": {int(a): round(b, 3) for a, b in yrs.items()},
            "risk_px_median": float(df.risk_px.median())}


def main():
    import MetaTrader5 as mt5
    if not mt5.initialize():
        sys.exit("MT5 indisponibil")
    acc = mt5.account_info()
    eq, free = acc.equity, acc.margin_free
    res = {}
    for sym in FX + OTHER:
        info, tick = mt5.symbol_info(sym), mt5.symbol_info_tick(sym)
        if info is None or tick is None or info.trade_mode != 4:
            print(f"{sym:8} indisponibil")
            continue
        m15, m30 = bars(mt5, sym, mt5.TIMEFRAME_M15, 200000), bars(mt5, sym, mt5.TIMEFRAME_M30, 100000)
        if m15 is None or m30 is None:
            continue
        is_fx = sym in FX
        pip = 0.01 if sym.endswith("JPY") else 0.0001
        markup = 0.8 * pip if is_fx else 0.0
        df = trades_for(m15, m30, info.point, markup)
        st = stats(df)
        if st is None:
            continue
        vpu = info.trade_tick_value / info.trade_tick_size
        minlot_risk = st["risk_px_median"] * vpu * info.volume_min
        margin_min = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, sym, info.volume_min, tick.ask) or 0
        lots_1pct = max(info.volume_min, np.floor(eq * 0.01 / (st["risk_px_median"] * vpu) / info.volume_step) * info.volume_step)
        margin_1pct = margin_min / info.volume_min * lots_1pct
        st.update(minlot_risk_usd=round(minlot_risk, 2), minlot_risk_pct=round(100 * minlot_risk / eq, 2),
                  margin_minlot=round(margin_min, 2), lots_1pct=round(float(lots_1pct), 2), margin_1pct=round(margin_1pct, 2),
                  fits=bool(minlot_risk <= eq * 0.01 + 1e-9 and margin_1pct <= 0.40 * free),
                  spread_pts=int(info.spread), current_ai=sym in ("CHFJPY", "GBPUSD"))
        robust = st["exp"] > 0 and st["train"] > 0 and st["test"] > 0 and st["t"] >= 1.5 and st["last12"] > 0
        st["robust"] = bool(robust)
        res[sym] = st
        print(f"{sym:8} n={st['n']:5} {st['per_week']:4}/s exp={st['exp']:+.3f} t={st['t']:5} pf={st['pf']} dd={st['dd']:7} "
              f"tr/te={st['train']:+.3f}/{st['test']:+.3f} 12m={st['last12']:+.3f} 3m={st['last3']} ani={st['years_pos']} "
              f"risc_minlot={st['minlot_risk_usd']}$ marja1%={st['margin_1pct']}$ fits={st['fits']} {'ROBUST' if robust else ''}")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"equity": eq, "free_margin": free, "params": {"sl_atr": SL_ATR, "rr": RR, "max_bars": MAX_BARS,
                   "cooldown_bars": COOLDOWN_BARS}, "markets": res}, f, ensure_ascii=False, indent=1)
    print("->", OUT)


if __name__ == "__main__":
    main()
