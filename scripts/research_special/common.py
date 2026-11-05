"""
Infrastructura comuna pentru cercetarea Special Engine / engine nou (2026-11-04). DOAR backtest, MT5 doar CITIRE.

- fetch(sym, tf): bare din MT5 (ora serverului), cache in data/research_special/<SYM>_<TF>.csv
- spec(sym): spread LIVE (pret), point, swap pe noapte convertit in PRET (long / short), lot minim, contract
- trades_to_R(...): R net = miscare / risc − spread / risc − nopti × swap / risc
- report(...): statistici R + verdict M0 + randament LUNAR la un risc fix pe trade (fara compunere) si riscul necesar
  pentru 3% / luna, cu drawdown-ul care vine la pachet. Asta e cifra cinstita: orice edge pozitiv „face” 3% / luna cu
  destula parghie — intrebarea e cu ce drawdown si cu ce probabilitate.
"""
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "data", "research_special")
os.makedirs(OUT, exist_ok=True)

from m0.robustness import evaluate_trades  # noqa: E402

_mt5 = None


def mt5():
    global _mt5
    if _mt5 is None:
        import MetaTrader5 as m
        assert m.initialize()
        _mt5 = m
    return _mt5


TF = {"M5": "TIMEFRAME_M5", "M15": "TIMEFRAME_M15", "M30": "TIMEFRAME_M30", "H1": "TIMEFRAME_H1",
      "H4": "TIMEFRAME_H4", "D1": "TIMEFRAME_D1"}


def fetch(sym: str, tf: str, n: int = 50000, refresh: bool = False) -> pd.DataFrame:
    p = os.path.join(OUT, f"{sym}_{tf}.csv")
    if os.path.exists(p) and not refresh:
        return pd.read_csv(p, parse_dates=["time"])
    m = mt5()
    m.symbol_select(sym, True)
    r = m.copy_rates_from_pos(sym, getattr(m, TF[tf]), 0, n)
    if r is None or not len(r):
        raise RuntimeError(f"fara bare {sym} {tf}")
    df = pd.DataFrame(r)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df[["time", "open", "high", "low", "close", "tick_volume", "spread"]]
    df.to_csv(p, index=False)
    return df


_SPEC = {}


def spec(sym: str) -> dict:
    if sym in _SPEC:
        return _SPEC[sym]
    m = mt5()
    m.symbol_select(sym, True)
    i = m.symbol_info(sym)
    t = m.symbol_info_tick(sym)
    spread = (t.ask - t.bid) if t and t.ask > 0 else i.spread * i.point
    if spread <= 0:
        spread = i.spread * i.point
    # pretul echivalent al unui $ / lot: $ = dpret / tick_size * tick_value
    per_price = i.trade_tick_value / i.trade_tick_size if i.trade_tick_size else 0
    def swap_price(v):
        if i.swap_mode == 1:                     # points
            return -v * i.point                  # cost pozitiv = pierdere
        if i.swap_mode == 2:                     # bani in valuta de baza ~ $
            return -v / per_price if per_price else 0
        if i.swap_mode == 3:                     # bani in valuta marjei ~ $
            return -v / per_price if per_price else 0
        if i.swap_mode == 5:                     # % anual din pretul curent
            return -v / 100.0 / 360.0 * (t.bid if t else i.bid)
        return 0.0
    s = {"sym": sym, "point": i.point, "digits": i.digits, "spread": float(spread),
         "swap_long": swap_price(i.swap_long), "swap_short": swap_price(i.swap_short),
         "swap_mode": i.swap_mode, "vol_min": i.volume_min, "contract": i.trade_contract_size,
         "per_price": per_price, "price": t.bid if t else None}
    _SPEC[sym] = s
    return s


def nights(t_in, t_out) -> int:
    return max(0, (pd.Timestamp(t_out).normalize() - pd.Timestamp(t_in).normalize()).days)


def trade_R(sym, d, entry, exit_, risk, t_in, t_out, slip_spreads: float = 0.25) -> float:
    """R net: spread intreg + slippage (fractie din spread) + swap pe noptile tinute."""
    sp = spec(sym)
    gross = (exit_ - entry) * d / risk
    cost = sp["spread"] * (1 + slip_spreads) / risk
    sw = (sp["swap_long"] if d == 1 else sp["swap_short"]) * nights(t_in, t_out) / risk
    return gross - cost - sw


def report(rows, risk_pct: float = 1.0, label: str = "") -> dict:
    df = pd.DataFrame(rows)
    if df.empty:
        return {"label": label, "n": 0}
    df = df.sort_values("exit_t").reset_index(drop=True)
    df["outcome"] = np.where(df["R"] > 0, "win", "loss")
    df["entry_t"] = pd.to_datetime(df["entry_t"])
    split = df["entry_t"].sort_values().iloc[int(0.7 * len(df))]
    ev = evaluate_trades(df[["R", "outcome", "entry_t"]].copy(), split_time=split, n_boot=2000)
    mon = df.groupby(pd.to_datetime(df["exit_t"]).dt.to_period("M"))["R"].sum()
    all_m = pd.period_range(mon.index.min(), mon.index.max(), freq="M")
    mon = mon.reindex(all_m, fill_value=0.0)
    eq = df["R"].cumsum()
    dd_R = float((eq - eq.cummax()).min())
    mean_m = float(mon.mean())
    years = (pd.Timestamp(df["exit_t"].max()) - pd.Timestamp(df["entry_t"].min())).days / 365.25
    res = {"label": label, "n": len(df), "per_month": round(len(df) / max(len(mon), 1), 2),
           "exp_R": round(df["R"].mean(), 4), "win_rate": round((df["R"] > 0).mean() * 100, 1),
           "total_R": round(df["R"].sum(), 1), "max_dd_R": round(dd_R, 1),
           "verdict": ev["verdict"], "p_edge": round(ev["prob_positive"], 3),
           "train": round(ev["train_exp"], 4), "test": round(ev["test_exp"], 4),
           "folds_pos": round(ev["frac_positive"], 2), "years": round(years, 1),
           "months": len(mon), "R_per_month": round(mean_m, 3),
           "pct_months_pos": round((mon > 0).mean() * 100, 1),
           "worst_month_R": round(float(mon.min()), 2),
           "from": str(pd.Timestamp(df["entry_t"].min()).date()), "to": str(pd.Timestamp(df["exit_t"].max()).date())}
    if mean_m > 0:
        r3 = 3.0 / mean_m                                   # % risc / trade pentru 3% / luna (medie)
        m_pct = mon * r3
        res["risk_for_3pct"] = round(r3, 2)
        res["dd_pct_at_3pct"] = round(dd_R * r3, 1)
        res["p_month_ge_2pct"] = round((m_pct >= 2).mean() * 100, 1)
        res["p_month_neg"] = round((m_pct < 0).mean() * 100, 1)
        res["worst_month_pct"] = round(float(m_pct.min()), 1)
        res["mar"] = round(mean_m * 12 / abs(dd_R), 2) if dd_R < 0 else None   # randament anual / DD maxim
    yr = df.groupby(pd.to_datetime(df["exit_t"]).dt.year)["R"].agg(["count", "sum"])
    res["by_year"] = {int(y): [int(r["count"]), round(float(r["sum"]), 1)] for y, r in yr.iterrows()}
    return res


def fmt(r: dict) -> str:
    if not r.get("n"):
        return f"{r.get('label')}: fara trade-uri"
    s = (f"{r['label']}: n={r['n']} ({r['per_month']}/luna, {r['years']} ani) exp={r['exp_R']:+.3f}R WR={r['win_rate']}% "
         f"DD={r['max_dd_R']}R train={r['train']:+.3f} test={r['test']:+.3f} folds+={r['folds_pos']} "
         f"p={r['p_edge']} {r['verdict']} | {r['R_per_month']:+.2f}R/luna, luni+ {r['pct_months_pos']}%")
    if "risk_for_3pct" in r:
        s += (f" | 3%/luna cere {r['risk_for_3pct']}%/trade → DD {r['dd_pct_at_3pct']}%, luni>=2% "
              f"{r['p_month_ge_2pct']}%, luni neg {r['p_month_neg']}%, MAR {r['mar']}")
    return s
