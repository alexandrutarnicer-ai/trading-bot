"""
Motor de backtest DE PORTOFOLIU
================================
Entry-point pentru backtestul multi-symbol pe cont comun.
Foloseste CsvDataSource + strategy.preparation pentru a pregati datele,
apoi deleaga simularea la engine/portfolio.py.

Cerinte:  pip install pandas numpy
Rulare:   python portfolio_backtest.py
"""

import os
import json
import numpy as np
import pandas as pd

from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol
from engine.portfolio import run_portfolio

# ---- parametri portofoliu --------------------------------------------------
SYMBOLS               = ["EURUSD", "GBPUSD", "USDJPY"]
SPREAD_PIPS           = {"EURUSD": 0.5, "GBPUSD": 0.8, "USDJPY": 0.7}
START_BALANCE         = 1000
LEVERAGE              = 30
EXPIRE_BARS           = 4
DEPTH_RANGE           = None
PULLBACK_WINDOW       = 8
SKIP_MONDAY           = True
SKIP_HOURS            = (15, 16)
ATR_MAX_PIPS          = {"EURUSD": 7.5}
MAX_DAY_CONSEC_LOSSES = 3
CORR_PAIRS            = {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD"}


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

    print("\n===== PORTOFOLIU (cont comun, swap inclus) =====")
    print(f"  Balanta: {START_BALANCE} -> {balance:.2f} USD   ({ret:+.1f}%)")
    print(f"  Tranzactii          : {len(df)}  (W:{wins} / L:{losses})")
    print(f"  Rata de castig      : {wins/len(df)*100:.1f}%")
    print(f"  Expectancy/trade    : {df['R_realizat'].mean():+.3f} R")
    print(f"  Drawdown maxim      : {dd:.1f}%")
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

    df.to_csv(os.path.join(DATA_DIR, "portfolio_trades.csv"), index=False)
    eqdf.to_csv(os.path.join(DATA_DIR, "portfolio_equity.csv"), index=False)
    print(f"\n  Salvat: portfolio_trades.csv si portfolio_equity.csv in {DATA_DIR}")


# ---- main ------------------------------------------------------------------
def main():
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    print(f"Backtest de portofoliu | balanta simulata {START_BALANCE} USD | levier 1:{LEVERAGE}")

    source = CsvDataSource(DATA_DIR)
    data = {}
    for s in SYMBOLS:
        try:
            data[s] = prepare_symbol(source, s, cfg)
            print(f"  {s}: {len(data[s])} bare M15")
        except FileNotFoundError:
            print(f"  {s}: LIPSESC datele (M15/M30) - sare peste")
    if not data:
        print("Nu am date pentru nicio pereche.")
        return

    params = {
        "spread_pips":           SPREAD_PIPS,
        "leverage":              LEVERAGE,
        "start_balance":         START_BALANCE,
        "expire_bars":           EXPIRE_BARS,
        "pullback_window":       PULLBACK_WINDOW,
        "depth_range":           DEPTH_RANGE,
        "skip_monday":           SKIP_MONDAY,
        "skip_hours":            SKIP_HOURS,
        "atr_max_pips":          ATR_MAX_PIPS,
        "max_day_consec_losses": MAX_DAY_CONSEC_LOSSES,
        "corr_pairs":            CORR_PAIRS,
    }

    trades, equity, balance, max_concurrent, skipped_margin, halted_days, split_time = \
        run_portfolio(data, cfg, params)

    print(f"\n  Circuit breaker activat in {halted_days} zile "
          f"(stop dupa {MAX_DAY_CONSEC_LOSSES} pierderi consecutive)")
    summarize(trades, equity, balance, max_concurrent, skipped_margin, split_time)


if __name__ == "__main__":
    main()
