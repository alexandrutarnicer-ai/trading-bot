"""
Noisy Engine — research: exista edge pe termen foarte scurt (M1) DUPA costurile reale?

Strategii-tip FIXATE dinainte (nu optimizate — evitam „data mining”), cate o varianta:
  MOM  — breakout Donchian 20 bare M1 (momentum de scurta durata), SL 1×ATR14, TP 1.5×ATR, stop de timp 30 min
  MR   — mean reversion: inchidere dincolo de EMA20 ± 2×ATR14 → contra, TP la EMA20, SL 1.5×ATR, stop de timp 20 min
  TRD  — continuare pe trend: EMA20 > EMA100 (M1) + pullback la EMA20 si redresare → pe directia trendului,
         SL 1×ATR, TP 2×ATR, stop de timp 45 min
Toate: maximum o pozitie, fara suprapuneri, doar in orele lichide ale pietei, intrare la DESCHIDEREA barei
urmatoare semnalului (fara lookahead), iesire pe high/low al barei (SL inaintea TP in aceeasi bara = conservator).

Costuri pe trade (din tick-urile reale, scripts/research_noisy/measure_markets.py):
  spread median al orei (sau spread-ul barei, care e mai mare) + comision real dus-intors + slippage
  = 25% din spread median la intrare si la iesire (ipoteza prudenta, de verificat pe demo).

Iesire: pe piata × strategie — trade-uri/zi, castig BRUT mediu (inainte de costuri) in unitati de cost,
expectancy NET in R, profit factor net, split 70/30 (train/test). Verdict: edge brut / cost.

    python scripts/research_noisy/edge_test.py  ->  data/research_noisy/edge_results.json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import MetaTrader5 as mt5

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "research_noisy")
sys.stdout.reconfigure(encoding="utf-8")

START = datetime(2025, 11, 1, tzinfo=timezone.utc)
END = datetime(2026, 10, 31, tzinfo=timezone.utc)
SLIP_FRAC = 0.25
COST_SCENARIO = os.environ.get("COST", "A")
TF = os.environ.get("TF", "M1")              # M1 (implicit) sau M5 — aceleasi reguli, bare mai mari
# ore lichide (ora serverului ICMarkets; server ≈ RO + 1h vara SUA / RO + 0h iarna) — fereastra larga
LIQUID_SERVER_H = {
    "fx": range(10, 20),        # ~ 09-19 RO: Londra + suprapunerea cu NY
    "metal": range(10, 21),
    "index_us": range(17, 23),  # ~ 16:30-22 RO: sesiunea cash NY
    "index_eu": range(10, 18),
    "crypto": range(10, 23),
}
KIND = {"EURUSD": "fx", "GBPUSD": "fx", "USDJPY": "fx", "AUDUSD": "fx", "XAUUSD": "metal", "XAGUSD": "metal",
        "USTEC": "index_us", "US500": "index_us", "US30": "index_us", "DE40": "index_eu",
        "BTCUSD": "crypto", "ETHUSD": "crypto", "XRPUSD": "crypto",
        "USDCAD": "fx", "USDCHF": "fx", "NZDUSD": "fx", "EURJPY": "fx", "GBPJPY": "fx", "CHFJPY": "fx",
        "NZDJPY": "fx", "AUDJPY": "fx", "EURGBP": "fx", "EURCHF": "fx"}


def ema(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def atr(h, l, c, n=14):
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    return pd.Series(tr).rolling(n).mean().to_numpy()


def simulate(o, h, l, c, sig, sl_d, tp_d, tmax, cost):
    """sig[i] = +1/-1 semnal la inchiderea barei i → intrare la o[i+1]. Rezultat in unitati de pret, brut si net."""
    n = len(o)
    trades = []
    i = 0
    while i < n - 2:
        d = sig[i]
        if d == 0 or not np.isfinite(sl_d[i]) or sl_d[i] <= 0:
            i += 1
            continue
        e = o[i + 1]
        sl = e - d * sl_d[i]
        tp = e + d * tp_d[i]
        exit_p, j = None, i + 1
        for j in range(i + 1, min(n, i + 1 + tmax)):
            if d > 0:
                if l[j] <= sl:
                    exit_p = sl; break
                if h[j] >= tp:
                    exit_p = tp; break
            else:
                if h[j] >= sl:
                    exit_p = sl; break
                if l[j] <= tp:
                    exit_p = tp; break
        if exit_p is None:
            exit_p = c[j]
        gross = d * (exit_p - e)
        trades.append((i, gross, gross - cost[i + 1], sl_d[i], j - i))
        i = j + 1                                   # o singura pozitie odata
    return trades


def run_symbol(sym: str, metrics: dict) -> dict:
    mt5.symbol_select(sym, True)
    r = mt5.copy_rates_range(sym, getattr(mt5, f"TIMEFRAME_{TF}"), START, END)
    if r is None or len(r) < (50_000 if TF == "M1" else 10_000):
        return {"symbol": sym, "error": f"bare M1 insuficiente ({0 if r is None else len(r)})"}
    df = pd.DataFrame(r)
    t = pd.to_datetime(df["time"], unit="s")
    info = mt5.symbol_info(sym)
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    hour = t.dt.hour.to_numpy()
    liquid = np.isin(hour, list(LIQUID_SERVER_H[KIND[sym]]))

    # cost dus-intors in pret: max(spread bara, spread median al orei RO) + comision + slippage
    m = metrics[sym]
    by_h = {x["hour"]: x["spread_med"] for x in m.get("by_hour_ro", [])}
    med = m["spread_median"]
    hour_ro = (hour - 1) % 24                            # aproximare server -> RO pentru profilul orar
    sp_prof = np.array([by_h.get(int(x), med) for x in hour_ro])
    sp_bar = df["spread"].to_numpy(float) * info.point
    spread = np.maximum(sp_bar, sp_prof)
    cost = spread + m["comm_in_price"] + 2 * SLIP_FRAC * med
    if COST_SCENARIO == "B" and KIND[sym] in ("fx", "metal"):
        # prudent: comisionul public ICMarkets Raw $7 / lot dus-intors (in istoricul contului apare 0)
        cost = cost + 7.0 / (info.trade_tick_value / info.trade_tick_size)

    a = atr(h, l, c)
    e20, e100 = ema(c, 20), ema(c, 100)
    don_h = pd.Series(h).rolling(20).max().shift(1).to_numpy()
    don_l = pd.Series(l).rolling(20).min().shift(1).to_numpy()

    sig_mom = np.where(c > don_h, 1, np.where(c < don_l, -1, 0)) * liquid
    sig_mr = np.where(c < e20 - 2 * a, 1, np.where(c > e20 + 2 * a, -1, 0)) * liquid
    up = (e20 > e100)
    dn = (e20 < e100)
    prev_l = np.r_[l[0], l[:-1]]
    prev_h = np.r_[h[0], h[:-1]]
    sig_trd = (np.where(up & (prev_l <= e20) & (c > e20) & (c > o), 1, 0)
               + np.where(dn & (prev_h >= e20) & (c < e20) & (c < o), -1, 0)) * liquid

    days = max(1, t.dt.date.nunique())
    split = int(len(o) * 0.7)
    out = {"symbol": sym, "bars": len(o), "days": days,
           "median_cost_price": float(np.median(cost[liquid])), "median_atr_price": float(np.nanmedian(a[liquid]))}
    out["atr_over_cost"] = out["median_atr_price"] / out["median_cost_price"]
    for name, sig, sl_k, tp_k, tmax in (("MOM", sig_mom, 1.0, 1.5, 30), ("MR", sig_mr, 1.5, None, 20),
                                         ("TRD", sig_trd, 1.0, 2.0, 45)):
        sl_d = sl_k * a
        tp_d = (tp_k * a) if tp_k else np.abs(e20 - c) + 1e-12      # MR: tinta = revenirea la EMA20
        tr = simulate(o, h, l, c, sig.astype(int), sl_d, tp_d, tmax, cost)
        if len(tr) < 30:
            out[name] = {"trades": len(tr)}
            continue
        arr = np.array(tr)
        idx, gross, net, risk, hold = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3], arr[:, 4]
        cst = gross - net

        def stats(mask):
            g, nt, rk, cs = gross[mask], net[mask], risk[mask], cst[mask]
            wins = nt[nt > 0].sum()
            loss = -nt[nt < 0].sum()
            return {"trades": int(mask.sum()),
                    "gross_R": float(np.mean(g / rk)), "net_R": float(np.mean(nt / rk)),
                    "cost_R": float(np.mean(cs / rk)),
                    "gross_over_cost": float(np.mean(g) / np.mean(cs)) if np.mean(cs) else None,
                    "pf_net": float(wins / loss) if loss else None,
                    "win_rate_net": float((nt > 0).mean())}
        all_m = np.ones(len(arr), bool)
        out[name] = {**stats(all_m), "per_day": len(arr) / days, "avg_hold_min": float(hold.mean()),
                     "train": stats(idx < split), "test": stats(idx >= split)}
    return out


def main() -> None:
    assert mt5.initialize(), mt5.last_error()
    metrics = {s["symbol"]: s for s in json.load(open(os.path.join(OUT, os.environ.get("METRICS", "market_metrics.json")),
                                                      encoding="utf-8"))["symbols"] if "spread_median" in s}
    res = []
    for sym in metrics:
        r = run_symbol(sym, metrics)
        res.append(r)
        line = f"{sym:7s} ATR/cost={r.get('atr_over_cost', 0):.2f} "
        for k in ("MOM", "MR", "TRD"):
            s = r.get(k) or {}
            if "net_R" in s:
                line += (f"| {k}: {s['per_day']:.1f}/zi brut {s['gross_R']:+.3f}R cost {s['cost_R']:.3f}R "
                         f"net {s['net_R']:+.3f}R (test {s['test']['net_R']:+.3f}) ")
        print(line, flush=True)
    with open(os.path.join(OUT, f"edge_results_{TF}_{COST_SCENARIO}{os.environ.get('TAG', '')}.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, default=str)


if __name__ == "__main__":
    main()
