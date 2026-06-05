"""
Motor de backtest v1 - strategie pullback in trend (buy/sell stop)
==================================================================
Entry-point pentru backtestul single-symbol. Incarca CSV-urile, ruleaza
motorul din engine/single.py si afiseaza statisticile.

Cerinte:  pip install pandas numpy
Rulare:   python backtest.py
"""

import os
import json
import numpy as np
import pandas as pd

from strategy.indicators import ema, rsi, atr
from strategy.structure import mark_swings
from engine.single import run_symbol

# ---- cai (relative la radacina proiectului) -------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.isdir(os.path.join(_HERE, "config")):
    ROOT = _HERE
elif os.path.isdir(os.path.join(os.path.dirname(_HERE), "config")):
    ROOT = os.path.dirname(_HERE)
else:
    ROOT = _HERE
CONFIG   = os.path.join(ROOT, "config", "standard_profile.json")
DATA_DIR = os.path.join(ROOT, "data")

# ---- parametri de cost ----------------------------------------------------
SPREAD_PIPS = {"EURUSD": 0.5, "GBPUSD": 0.8}
PIP_VALUE_PER_LOT_USD = 10.0                   # pt perechi cotate in USD, 1 lot
SYMBOLS_V1 = ["EURUSD", "GBPUSD"]


# ---- incarcare + pregatire date (va deveni CsvDataSource in Pas 3) --------
def load_symbol(symbol, cfg):
    m15 = pd.read_csv(os.path.join(DATA_DIR, f"{symbol}_M15.csv"), parse_dates=["time"])
    m30 = pd.read_csv(os.path.join(DATA_DIR, f"{symbol}_M30.csv"), parse_dates=["time"])

    m30["ema_trend"] = ema(m30["close"], cfg["trend_filter"]["ema_trend_period"])
    m30["trend"] = np.where(m30["close"] > m30["ema_trend"], 1,
                    np.where(m30["close"] < m30["ema_trend"], -1, 0))

    per = cfg["optional_criteria"]["ema_alignment"]["periods"]
    m15["ema_fast"] = ema(m15["close"], per[0])
    m15["ema_mid"]  = ema(m15["close"], per[1])
    m15["ema_slow"] = ema(m15["close"], per[2])
    m15["rsi"]      = rsi(m15["close"], cfg["optional_criteria"]["rsi"]["period"])
    m15["atr"]      = atr(m15, 14)
    m15 = mark_swings(m15, cfg["structure"]["swing_lookback_N"])

    m15 = pd.merge_asof(m15.sort_values("time"),
                        m30[["time", "trend"]].sort_values("time"),
                        on="time", direction="backward")
    return m15.reset_index(drop=True)


# ---- backtest single-symbol: incarca + ruleaza motor + afiseaza -----------
def backtest_symbol(symbol, cfg):
    df = load_symbol(symbol, cfg)
    trades, equity_curve, equity_timeline, setups = run_symbol(
        df, symbol, cfg, SPREAD_PIPS, PIP_VALUE_PER_LOT_USD
    )
    summarize(symbol, trades, equity_curve, equity_timeline, setups)


# ---- statistici + salvare CSV ---------------------------------------------
def summarize(symbol, trades, equity, equity_timeline, setups):
    if not trades:
        print(f"\n=== {symbol} ===")
        print(f"  Setup-uri detectate: {setups} | Tranzactii: 0")
        return
    df = pd.DataFrame(trades)
    wins   = (df["outcome"] == "win").sum()
    losses = (df["outcome"] == "loss").sum()
    wr     = wins / len(df) * 100
    start, end = equity[0], equity[-1]
    ret = (end - start) / start * 100
    eq  = np.array(equity)
    dd  = ((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq)).min() * 100

    df["R_realizat"] = df["pnl_usd"] / df["risk_usd"]
    expectancy = df["R_realizat"].mean()
    avg_win  = df.loc[df["outcome"] == "win",  "R_realizat"].mean()
    avg_loss = df.loc[df["outcome"] == "loss", "R_realizat"].mean()

    print(f"\n=== {symbol} ===")
    print(f"  Setup-uri detectate : {setups}")
    print(f"  Tranzactii          : {len(df)}  (W:{wins} / L:{losses})")
    print(f"  Rata de castig      : {wr:.1f}%")
    print(f"  Expectancy/trade    : {expectancy:+.3f} R")
    print(f"  Castig mediu        : {avg_win:+.2f} R | Pierdere medie: {avg_loss:+.2f} R")
    print(f"  Balanta finala      : {end:.2f} USD  (start {start})")
    print(f"  Randament total     : {ret:+.1f}%")
    print(f"  Drawdown maxim      : {dd:.1f}%")

    out = os.path.join(DATA_DIR, f"trades_{symbol}.csv")
    df.to_csv(out, index=False)
    print(f"  Tranzactii salvate  : {out}")
    if equity_timeline:
        eqout = os.path.join(DATA_DIR, f"equity_{symbol}.csv")
        pd.DataFrame(equity_timeline).to_csv(eqout, index=False)
        print(f"  Curba de capital    : {eqout}")


# ---- main ------------------------------------------------------------------
def main():
    if not os.path.isfile(CONFIG):
        print("Nu gasesc fisierul de config:", CONFIG)
        return
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    if not os.path.isdir(DATA_DIR):
        print("Atentie: folderul data/ nu exista la:", DATA_DIR)
    print("Backtest v1 - strategie pullback in trend")
    for sym in SYMBOLS_V1:
        try:
            backtest_symbol(sym, cfg)
        except FileNotFoundError as e:
            print(f"\n{sym}: lipseste fisierul de date -> {e}")
        except Exception as e:
            print(f"\n{sym}: eroare -> {type(e).__name__}: {e}")

if __name__ == "__main__":
    main()
