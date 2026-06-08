"""
Backtest Session 2 — M15, BOTH, 6 piete (EUR + JPY), sesiuni separate
=======================================================================
Echivalentul portfolio_backtest.py pentru Session 2 live.

Rezultate validate (2026-06-08):
  TEST set (30%): 435 trades, +0.142R expectancy, DD -52.9%
  Frecventa:      3.2 trades/saptamana

Rulare: python session2_backtest.py
"""

import os
import json
import numpy as np
import pandas as pd

from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol
from engine.portfolio import run_portfolio

# ---- parametri Session 2 ---------------------------------------------------
SYMBOLS      = ["EURUSD", "GBPUSD", "EURJPY", "USDJPY", "AUDJPY", "NZDJPY"]
SPREAD_PIPS  = {
    "EURUSD": 0.5, "GBPUSD": 0.8, "EURJPY": 1.5,
    "USDJPY": 0.5, "AUDJPY": 1.5, "NZDJPY": 1.5,
}
START_BALANCE         = 300
LEVERAGE              = 30
EXPIRE_BARS           = 4
PULLBACK_WINDOW       = 6
SKIP_MONDAY           = False   # luni activa (+0.6/sapt)
SKIP_HOURS            = (15, 16)
ATR_MAX_PIPS          = {"EURUSD": 7.5}
MAX_DAY_CONSEC_LOSSES = 3
CORR_PAIRS            = {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD"}
ONLY_LONG             = False   # BOTH: long + short
MAX_POS_PER_SYMBOL    = 1

# Sesiuni separate: EUR in Europa, JPY in Tokyo
SYMBOL_SESSIONS = {
    "EURUSD": (10, 18), "GBPUSD": (10, 18), "EURJPY": (10, 18),
    "USDJPY": (2, 10),  "AUDJPY": (2, 10),  "NZDJPY": (2, 10),
}
SYMBOL_SKIP_HOURS = {}


# ---- statistici + salvare CSV ----------------------------------------------
def summarize(trades, equity, balance, max_concurrent, skipped_margin, split_time):
    if not trades:
        print("\nNicio tranzactie.")
        return
    df = pd.DataFrame(trades)
    df["R_realizat"] = df["pnl_usd"] / df["risk_usd"]
    df["entry_t"]    = pd.to_datetime(df["time"])
    wins   = (df["outcome"] == "win").sum()
    losses = (df["outcome"] == "loss").sum()

    eqdf = pd.DataFrame(equity).sort_values("time")
    b    = eqdf["balance"].values
    peak = np.maximum.accumulate(b)
    dd   = ((b - peak) / peak).min() * 100
    ret  = (balance - START_BALANCE) / START_BALANCE * 100
    swap_total = df["swap"].sum() if "swap" in df else 0.0

    span_days = (df["entry_t"].max() - df["entry_t"].min()).days
    trades_wk = len(df) / max(span_days / 7, 1)

    print("\n===== SESSION 2 (M15 BOTH, 6 piete, sesiuni separate) =====")
    print(f"  Balanta: {START_BALANCE} -> {balance:.2f} USD   ({ret:+.1f}%)")
    print(f"  Tranzactii          : {len(df)}  (W:{wins} / L:{losses})")
    print(f"  Rata de castig      : {wins/len(df)*100:.1f}%")
    print(f"  Expectancy/trade    : {df['R_realizat'].mean():+.3f} R")
    print(f"  Drawdown maxim      : {dd:.1f}%")
    print(f"  Frecventa           : {trades_wk:.1f} trades/saptamana")
    print(f"  Swap platit total   : {swap_total:.2f} USD")
    print(f"  Maxim pozitii simultane : {max_concurrent}")
    print(f"  Ratate (fonduri insuficiente): {skipped_margin}")

    print("\n  --- VALIDARE: train vs test nevazut ---")
    for name, d in [("TRAIN (primele 70%)", df[df["entry_t"] < split_time]),
                    ("TEST  (ultimele 30%, nevazut)", df[df["entry_t"] >= split_time])]:
        if len(d):
            w = (d["outcome"] == "win").sum()
            print(f"  {name}: {len(d):4d} trades | win {w/len(d)*100:.1f}% | "
                  f"expectancy {d['R_realizat'].mean():+.3f} R")

    print("\n  --- pe pereche ---")
    for s in df["symbol"].unique():
        sub = df[df["symbol"] == s]
        w   = (sub["outcome"] == "win").sum()
        print(f"  {s}: {len(sub):4d} trades | win {w/len(sub)*100:.1f}% | "
              f"expectancy {sub['R_realizat'].mean():+.3f} R | pnl {sub['pnl_usd'].sum():+.1f} USD")

    print("\n  --- per directie ---")
    for d_label, d_val in [("LONG (+1)", 1), ("SHORT (-1)", -1)]:
        sub = df[df["direction"] == d_val] if "direction" in df.columns else pd.DataFrame()
        if len(sub):
            w = (sub["outcome"] == "win").sum()
            print(f"  {d_label}: {len(sub):4d} trades | win {w/len(sub)*100:.1f}% | "
                  f"expectancy {sub['R_realizat'].mean():+.3f} R")

    out_trades = os.path.join(DATA_DIR, "session2_trades.csv")
    out_equity = os.path.join(DATA_DIR, "session2_equity.csv")
    df.to_csv(out_trades, index=False)
    eqdf.to_csv(out_equity, index=False)
    print(f"\n  Salvat: session2_trades.csv si session2_equity.csv in {DATA_DIR}")


# ---- main ------------------------------------------------------------------
def main():
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)

    # RSI simetric pentru SELL (validat: identic cu sell_max=50)
    cfg["optional_criteria"]["rsi"]["sell_max"] = 60

    print(f"Backtest Session 2 | BOTH | PW={PULLBACK_WINDOW} | "
          f"skip_mon={SKIP_MONDAY} | {len(SYMBOLS)} piete | {START_BALANCE} USD")

    source = CsvDataSource(DATA_DIR)
    data = {}
    for s in SYMBOLS:
        try:
            data[s] = prepare_symbol(source, s, cfg)
            print(f"  {s}: {len(data[s])} bare M15")
        except FileNotFoundError:
            print(f"  {s}: lipsesc datele (M15/M30) — sare peste")
    if not data:
        print("Nu am date pentru nicio pereche.")
        return

    params = {
        "spread_pips":           SPREAD_PIPS,
        "leverage":              LEVERAGE,
        "start_balance":         START_BALANCE,
        "expire_bars":           EXPIRE_BARS,
        "pullback_window":       PULLBACK_WINDOW,
        "depth_range":           None,
        "skip_monday":           SKIP_MONDAY,
        "skip_hours":            SKIP_HOURS,
        "atr_max_pips":          ATR_MAX_PIPS,
        "max_day_consec_losses": MAX_DAY_CONSEC_LOSSES,
        "corr_pairs":            CORR_PAIRS,
        "only_long":             ONLY_LONG,
        "max_pos_per_symbol":    MAX_POS_PER_SYMBOL,
        "symbol_sessions":       SYMBOL_SESSIONS,
        "symbol_skip_hours":     SYMBOL_SKIP_HOURS,
    }

    trades, equity, balance, max_concurrent, skipped_margin, halted_days, split_time = \
        run_portfolio(data, cfg, params)

    print(f"\n  Circuit breaker activat in {halted_days} zile "
          f"(stop dupa {MAX_DAY_CONSEC_LOSSES} pierderi consecutive)")
    summarize(trades, equity, balance, max_concurrent, skipped_margin, split_time)


if __name__ == "__main__":
    main()
