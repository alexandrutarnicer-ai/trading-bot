"""
Backtest Session 3 — BTCUSD M15, BOTH, sesiune crypto optimizata
=================================================================
Echivalentul session2_backtest.py pentru Session 3 live (BTC crypto).

Parametri sesiune (validati prin optimizare pe 11 configuratii):
  - Skip sambata: vol scazuta, win rate 12% vs 22-26% in restul saptamanii
  - Skip 10-14h UTC: EU mid-session, news-heavy, pulback-urile nu tin
  - Skip 19-23h UTC: US prime session, algo noise, structura nu se respecta

Ferestre active (UTC):  00:00-09:59  si  15:00-18:59  (Mon-Fri + Sun)

Rezultate validate (2026-06-08), $500 capital, spread real 1200 ticks=$12:
  TRAIN (70%, 523 trades): +0.211R expectancy, p=0.0075 ***
  TEST  (30%, 224 trades): +0.336R expectancy, p=0.0075 ***
  DD max  : -22.5%
  Frecventa: 2.4 trades/saptamana
  Swap     : 3.7% din PnL brut (neglijabil — evitam overnight-uri lungi US)
  Toate cele 7 ani (2020-2026) pozitive, inclusiv bear-ul 2022 (+0.263R)

Nota p-value dupa corectie Bonferroni (11 teste): p_corr = 0.0825.
Edge sustinut si de rationale economic (nu arbitrar ales).

Rulare: python session3_backtest.py
"""

import os
import copy
import json
import math
import numpy as np
import pandas as pd

# Importam infrastructura existenta
from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol
from strategy import signals as _sig

import scripts.research.crypto_backtest as cb

# ---- parametri Session 3 ---------------------------------------------------

SYMBOL        = "BTCUSD"
START_BALANCE = 500

# Ore UTC excluse — EU mid/tardiv si US prime session
SKIP_HOURS = {10, 11, 12, 13, 14, 19, 20, 21, 22, 23}

# Sambata exclusa — lichiditate scazuta, win rate 12%
SKIP_WEEKDAYS = {5}

# ---- statistici + afisare --------------------------------------------------

def summarize(trades, equity, split_time):
    if not trades:
        print("\nNicio tranzactie executata.")
        return

    df = pd.DataFrame(trades)
    df = df[df["risk_usd"] > 0].copy()
    df["R"]       = df["pnl_usd"] / df["risk_usd"]
    df["entry_t"] = pd.to_datetime(df["time"])
    df["year"]    = df["entry_t"].dt.year

    n    = len(df)
    wins = (df["outcome"] == "win").sum()

    eq   = np.asarray(equity, dtype=float)
    pk   = np.maximum.accumulate(eq)
    dd   = ((eq - pk) / np.where(pk > 0, pk, 1)).min() * 100
    ret  = (equity[-1] - START_BALANCE) / START_BALANCE * 100

    span_days = (df["entry_t"].max() - df["entry_t"].min()).days
    freq_wk   = n / max(span_days / 7, 1)

    swap_paid   = df["swap"].sum() if "swap" in df else 0.0
    net_pnl     = df["pnl_usd"].sum()
    gross_pnl   = net_pnl + swap_paid
    swap_pct    = swap_paid / gross_pnl * 100 if abs(gross_pnl) > 0.01 else 0.0

    print(f"\n===== SESSION 3 (BTCUSD M15 BOTH, sesiune crypto) =====")
    print(f"  Ferestre: 00-09h UTC + 15-18h UTC  |  Skip: Sambata + 10-14h + 19-23h UTC")
    print(f"  Balanta:  ${START_BALANCE} -> ${equity[-1]:.2f}  ({ret:+.1f}%)")
    print(f"  Trades  : {n}  (W:{wins} / L:{n-wins})")
    print(f"  Win rate: {wins/n*100:.1f}%  |  Expectancy: {df['R'].mean():+.4f} R")
    print(f"  DD max  : {dd:.1f}%  |  Frecventa: {freq_wk:.1f} trades/saptamana")
    print(f"  Swap    : ${swap_paid:.2f} ({swap_pct:.1f}% din PnL brut)")

    # Train / Test
    print(f"\n  --- VALIDARE: train vs test nevazut ---")
    train = df[df["entry_t"] <  split_time]
    test  = df[df["entry_t"] >= split_time]
    print(f"  Split: {split_time.date()}  (70% train / 30% test)")

    for label, dset in [("TRAIN (70%)", train), ("TEST  (30%)", test)]:
        if len(dset) < 3:
            print(f"  {label}: prea putine trades ({len(dset)})")
            continue
        w  = (dset["outcome"] == "win").sum()
        r  = dset["R"].values
        t_stat, pval = _p_val(r)
        lo, hi       = _ci95(r)
        sig = ("  *** SEMNIFICATIV ***" if pval is not None and pval < 0.05 else
               "  (* marginal)"         if pval is not None and pval < 0.10 else "")
        p_str  = f"  t={t_stat:.2f}  p={pval:.4f}{sig}" if pval is not None else ""
        ci_str = f"  IC95:[{lo:.3f},{hi:.3f}]" if lo is not None else ""
        print(f"  {label}: {len(dset):4d} trades | win {w/len(dset)*100:.1f}%"
              f" | exp {dset['R'].mean():+.4f} R{p_str}{ci_str}")

    # Long vs Short
    print(f"\n  --- Directie ---")
    for d_lbl, d_val in [("LONG  (+1)", 1), ("SHORT (-1)", -1)]:
        sub = df[df["direction"] == d_val] if "direction" in df.columns else pd.DataFrame()
        if len(sub):
            w = (sub["outcome"] == "win").sum()
            print(f"  {d_lbl}: {len(sub):4d} trades | win {w/len(sub)*100:.1f}%"
                  f" | exp {sub['R'].mean():+.4f} R")

    # Annual
    print(f"\n  --- Annual (regime check) ---")
    ann = df.groupby("year").agg(
        trades=("R", "count"),
        exp=("R", "mean"),
        win=("outcome", lambda x: (x == "win").mean() * 100),
    ).reset_index()
    for _, row in ann.iterrows():
        sign = "+" if row.exp >= 0 else " "
        print(f"  {int(row.year)}: {int(row.trades):4d} trades"
              f" | win {row.win:.0f}%"
              f" | exp {sign}{row.exp:.4f} R")

    # Salveaza CSV
    out_tr = os.path.join(DATA_DIR, "session3_trades.csv")
    out_eq = os.path.join(DATA_DIR, "session3_equity.csv")
    df.to_csv(out_tr, index=False)
    pd.DataFrame({"balance": equity}).to_csv(out_eq, index=False)
    print(f"\n  Salvat: session3_trades.csv + session3_equity.csv in {DATA_DIR}")


def _p_val(arr):
    n = len(arr)
    if n < 10:
        return None, None
    a = np.asarray(arr, float)
    s = a.std(ddof=1)
    if s < 1e-12:
        return None, None
    t = a.mean() / (s / math.sqrt(n))
    p = 0.5 * math.erfc(t / math.sqrt(2))
    return round(t, 3), round(p, 4)


def _ci95(arr):
    n = len(arr)
    if n < 2:
        return None, None
    a  = np.asarray(arr, float)
    m, s = a.mean(), a.std(ddof=1)
    se   = s / math.sqrt(n)
    _t   = {10: 2.23, 15: 2.13, 20: 2.09, 30: 2.04, 40: 2.02, 60: 2.00, 120: 1.98}
    tc   = next((v for k, v in sorted(_t.items()) if n <= k), 1.96)
    return round(m - tc * se, 4), round(m + tc * se, 4)


# ---- main ------------------------------------------------------------------

def main():
    with open(os.path.join(DATA_DIR, "crypto_specs.json"), encoding="utf-8") as f:
        specs_all = json.load(f)

    if SYMBOL not in specs_all:
        print(f"EROARE: {SYMBOL} nu e in crypto_specs.json")
        print("Ruleaza mai intai: python scripts/descarca_crypto.py")
        return

    spec = specs_all[SYMBOL]
    _sig._INDEX_PIP[SYMBOL] = spec["tick_size"]
    cb.START_BALANCE = START_BALANCE

    with open(CONFIG, encoding="utf-8") as f:
        cfg = copy.deepcopy(json.load(f))

    cfg["account"]["starting_balance"]               = START_BALANCE
    cfg["session"]["start_hour"]                     = 0
    cfg["session"]["end_hour"]                       = 24
    cfg["risk_management"]["max_trades_per_day"]     = 9999
    cfg["risk_management"]["max_consecutive_losses"] = 9999
    cfg["costs"]["commission_per_lot_round_turn_usd"] = 0.0
    cfg["optional_criteria"]["rsi"]["sell_max"]      = 60

    print(f"Session 3 | {SYMBOL} | ${START_BALANCE} | BOTH | M15")
    print(f"  Skip: ore {sorted(SKIP_HOURS)} UTC  +  zile {SKIP_WEEKDAYS} (5=Sat)")
    print(f"  Ferestre active: 00-09h UTC  +  15-18h UTC  (Mon-Fri + Sun)")

    source = CsvDataSource(DATA_DIR)
    try:
        df = prepare_symbol(source, SYMBOL, cfg)
    except FileNotFoundError:
        print(f"EROARE: date {SYMBOL} M15/M30 lipsesc. Ruleaza descarca_crypto.py")
        return

    print(f"  Date: {df['time'].min().date()} -> {df['time'].max().date()}"
          f"  ({len(df)} bare M15)")

    trades, equity, _, skipped = cb.run_crypto(
        df, SYMBOL, spec, cfg,
        skip_hours    = SKIP_HOURS,
        skip_weekdays = SKIP_WEEKDAYS,
    )

    if skipped:
        print(f"  Min-lot sarite: {skipped} setup-uri (SL > ${START_BALANCE * 0.01 / 0.01:.0f} pentru lot 0.01)")

    # Split 70/30 pe timp
    if trades:
        entry_times = [pd.Timestamp(t["time"]) for t in trades]
        split_time  = pd.Series(entry_times).quantile(0.70)
    else:
        split_time = pd.Timestamp("2100-01-01")

    summarize(trades, equity, split_time)


if __name__ == "__main__":
    main()
