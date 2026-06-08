"""
Backtest individual indici: US500, GER40, US30, US2000, UK100
=============================================================
Fiecare indice testat separat, ONLY_LONG=True, train/test 70/30.

Specificatii reale MT5 (trade_tick_size, trade_tick_value_usd):
  US500:  tick=0.01  tv=$0.010000  pip_val=$1.00/pt  spread=0.50pt
  US30:   tick=0.01  tv=$0.010000  pip_val=$1.00/pt  spread=0.70pt
  US2000: tick=0.01  tv=$0.010000  pip_val=$1.00/pt  spread=0.26pt
  UK100:  tick=0.01  tv=$0.013334  pip_val=$1.33/pt  spread=1.00pt
  GER40:  tick=0.01  tv=$0.011519  pip_val=$1.15/pt  spread=0.80pt

Sesiuni (ora server MT5, UTC+2 vara):
  US500/US30/US2000: NYSE/Russell  15:30-22:00 -> (15, 22)
  UK100:             FTSE          08:00-16:30 -> (9, 17)
  GER40:             XETRA         09:00-17:30 -> (9, 17)

AUS200 exclus (spread 3.20pt la piata deschisa, $0.70/pt pip_val — cost prea mare).
US100 nu exista la acest broker.

Prerequizit: ruleaza mai intai scripts/descarca_indici.py
Rulare:     python index_backtest.py
"""

import os
import copy
import json
import numpy as np
import pandas as pd

from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol
from engine.single import run_symbol

# ---- Specificatii reale per indice (din MT5) --------------------------------
#   pip_val : tick_value_usd / tick_size  (pip = 1 punct index)
#   spread  : spread in puncte index (din MT5 trade_spread * tick_size)
#   session : (start_hour, end_hour) ora server MT5 (UTC+2 vara)

INDEX_SPECS = {
    "US500":  {"pip_val": 1.0000, "spread": 0.50, "session": (15, 22)},
    "US30":   {"pip_val": 1.0000, "spread": 0.70, "session": (15, 22)},
    "US2000": {"pip_val": 1.0000, "spread": 0.26, "session": (15, 22)},
    "UK100":  {"pip_val": 1.3334, "spread": 1.00, "session": (9,  17)},
    "GER40":  {"pip_val": 1.1519, "spread": 0.80, "session": (9,  17)},
}

SYMBOLS        = ["US500", "GER40", "US30", "US2000", "UK100"]
START_BALANCE  = 300
ONLY_LONG      = True
PULLBACK_WINDOW = 8


# ---- backtest per indice ----------------------------------------------------

def run_index(symbol, spec, cfg_base):
    cfg = copy.deepcopy(cfg_base)
    cfg["account"]["starting_balance"]                = START_BALANCE
    cfg["session"]["start_hour"]                      = spec["session"][0]
    cfg["session"]["end_hour"]                        = spec["session"][1]
    cfg["costs"]["commission_per_lot_round_turn_usd"] = 0.0  # CFD spread-only

    source = CsvDataSource(DATA_DIR)
    try:
        df = prepare_symbol(source, symbol, cfg)
    except FileNotFoundError:
        print(f"\n  {symbol}: LIPSESC datele — ruleaza scripts/descarca_indici.py")
        return None

    trades, equity_curve, equity_timeline, setups = run_symbol(
        df, symbol, cfg,
        spread_pips={symbol: spec["spread"]},
        pip_val_per_lot=spec["pip_val"],
        only_long=ONLY_LONG,
    )
    return trades, equity_curve, equity_timeline, setups, df


# ---- statistici -------------------------------------------------------------

def summarize(symbol, spec, trades, equity_curve, equity_timeline, df):
    n_bars = len(df)
    if not trades:
        print(f"\n  {symbol}: 0 tranzactii din {n_bars} bare")
        return

    tdf = pd.DataFrame(trades)
    tdf["R"]       = tdf["pnl_usd"] / tdf["risk_usd"]
    tdf["entry_t"] = pd.to_datetime(tdf["time"])

    wins   = (tdf["outcome"] == "win").sum()
    losses = (tdf["outcome"] == "loss").sum()

    eq   = np.array(equity_curve)
    peak = np.maximum.accumulate(eq)
    dd   = ((eq - peak) / peak).min() * 100
    ret  = (equity_curve[-1] - START_BALANCE) / START_BALANCE * 100

    split_t = tdf["entry_t"].quantile(0.7)
    train   = tdf[tdf["entry_t"] <  split_t]
    test    = tdf[tdf["entry_t"] >= split_t]

    verdict = ""
    if len(train) >= 5 and len(test) >= 5:
        if train["R"].mean() > 0 and test["R"].mean() > 0:
            verdict = "  *** POZITIV PE AMBELE ***"
        elif test["R"].mean() <= 0:
            verdict = "  (test negativ — fara edge)"

    print(f"\n{'='*56}")
    print(f"  {symbol}  |  pip_val=${spec['pip_val']:.4f}  spread={spec['spread']}pt  sesiune {spec['session'][0]}-{spec['session'][1]}h{verdict}")
    print(f"{'='*56}")
    print(f"  Balanta: {START_BALANCE} -> {equity_curve[-1]:.2f} USD  ({ret:+.1f}%)")
    print(f"  Trades        : {len(tdf)}  (W:{wins} / L:{losses})  |  Win rate: {wins/len(tdf)*100:.1f}%")
    print(f"  Expectancy    : {tdf['R'].mean():+.3f} R")
    print(f"  Drawdown max  : {dd:.1f}%")
    print(f"  TRAIN ({len(train):3d}t) : {train['R'].mean():+.3f} R")
    print(f"  TEST  ({len(test):3d}t) : {test['R'].mean():+.3f} R")

    out = os.path.join(DATA_DIR, f"trades_{symbol}.csv")
    tdf.to_csv(out, index=False)

    if equity_timeline:
        pd.DataFrame(equity_timeline).to_csv(
            os.path.join(DATA_DIR, f"equity_{symbol}.csv"), index=False)


# ---- main -------------------------------------------------------------------

def main():
    with open(CONFIG, encoding="utf-8") as f:
        cfg_base = json.load(f)

    print(f"Backtest indici individual | {START_BALANCE} USD | ONLY_LONG={ONLY_LONG}")
    print(f"Simboluri: {SYMBOLS}\n")
    print("Specificatii reale MT5 (tick_value deja in USD):")
    print(f"  {'Simbol':<8} {'pip_val':>9} {'spread':>8} {'sesiune':>10}")
    for sym in SYMBOLS:
        s = INDEX_SPECS[sym]
        print(f"  {sym:<8} ${s['pip_val']:>8.4f} {s['spread']:>7.2f}pt {str(s['session']):>10}")
    print()

    for symbol in SYMBOLS:
        spec = INDEX_SPECS[symbol]
        result = run_index(symbol, spec, cfg_base)
        if result is None:
            continue
        trades, equity_curve, equity_timeline, setups, df = result
        print(f"  {symbol}: {setups} setup-uri detectate  |  {len(trades)} trades triggerate")
        summarize(symbol, spec, trades, equity_curve, equity_timeline, df)

    print(f"\n{'='*56}")
    print("Gata. CSV salvate in data/trades_<SIMBOL>.csv")


if __name__ == "__main__":
    main()
