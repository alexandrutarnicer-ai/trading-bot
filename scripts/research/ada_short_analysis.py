"""
ADAUSD -- deep-dive short-only edge analysis
============================================
1. Obtine spread real din MT5 (ADA tranzactionat 24/7)
2. Ruleaza ADA ONLY_SHORT cu spread real
3. Train/test 70/30 + p-value one-sided + CI 95% pe test
4. Expectancy per nivel R (2.5 / 3.5 / 4.5) -- unde e concentrat edge-ul?
5. Expectancy per an cu swap (2021-2026) -- robustete la regimuri
6. Swap ca % din gross PnL short

Rulare:  python scripts/research/ada_short_analysis.py
"""

import os
import sys
import copy
import json
import math
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol
from strategy import signals as _sig
from scripts.research.crypto_backtest import (
    run_crypto, SWAP_DAYS_PER_YEAR, nights_units,
)

SYMBOL        = "ADAUSD"
START_BALANCE = 300
SPECS_FILE    = os.path.join(DATA_DIR, "crypto_specs.json")


# ---- Step 1: obtine spread real din MT5 --------------------------------------

def get_real_spread():
    """
    Conecteaza MT5, citeste spread ADAUSD in timp real.
    Returneaza (spread_price, spread_ticks) sau (None, None) daca MT5 e down.
    """
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("  MetaTrader5 nu e instalat.")
        return None, None

    if not mt5.initialize():
        print(f"  MT5 offline: {mt5.last_error()}")
        return None, None

    if not mt5.symbol_select(SYMBOL, True):
        mt5.shutdown()
        print(f"  {SYMBOL} nu exista la broker.")
        return None, None

    info = mt5.symbol_info(SYMBOL)
    mt5.shutdown()

    if info is None:
        return None, None

    spread_ticks = info.spread
    spread_price = spread_ticks * info.trade_tick_size
    return spread_price, spread_ticks


# ---- utilitare statistice ---------------------------------------------------

def ttest_one_sided(R_values):
    """
    H0: mean(R) <= 0  vs  H1: mean(R) > 0.
    Returneaza (t_stat, p_value) -- aproximare normala, valida pt n >= 30.
    """
    n = len(R_values)
    if n < 5:
        return None, None
    arr = np.asarray(R_values, dtype=float)
    m, s = arr.mean(), arr.std(ddof=1)
    if s < 1e-12:
        return None, None
    t = m / (s / math.sqrt(n))
    p = 0.5 * math.erfc(t / math.sqrt(2))
    return round(t, 3), round(p, 4)


def ci_95(R_values):
    """
    IC 95% pe media lui R. Foloseste t_critical(n-1) aproximat.
    Returneaza (lower, upper) sau (None, None).
    """
    n = len(R_values)
    if n < 2:
        return None, None
    arr  = np.asarray(R_values, dtype=float)
    m    = arr.mean()
    se   = arr.std(ddof=1) / math.sqrt(n)

    # t_critical aproximat pentru 95% two-sided (alpha=0.025 per coada)
    # Valori tabelate pentru df mici, aproximare 1.96 pentru df >= 120
    _t_table = {1: 12.71, 2: 4.30, 3: 3.18, 4: 2.78, 5: 2.57,
                6: 2.45,  7: 2.36, 8: 2.31, 9: 2.26, 10: 2.23,
                15: 2.13, 20: 2.09, 30: 2.04, 60: 2.00, 120: 1.98}
    df = n - 1
    tc = next((v for k, v in sorted(_t_table.items()) if k >= df), 1.96)

    return round(m - tc * se, 4), round(m + tc * se, 4)


def print_section(title):
    print(f"\n{'='*62}")
    print(f"  {title}")
    print(f"{'='*62}")


# ---- analiza completa -------------------------------------------------------

def main():
    # --- specs ---
    with open(SPECS_FILE, encoding="utf-8") as f:
        specs_all = json.load(f)
    if SYMBOL not in specs_all:
        print(f"EROARE: {SYMBOL} nu e in crypto_specs.json")
        return
    spec = specs_all[SYMBOL]

    # --- spread real ---
    print_section(f"STEP 1 -- Spread real ADAUSD din MT5")
    spread_price, spread_ticks = get_real_spread()
    if spread_price is not None and spread_price > 0:
        print(f"  Spread real: {spread_ticks} ticks = {spread_price:.6f} pret")
        tick_size = spec["tick_size"]
        print(f"  ({spread_ticks} x tick_size {tick_size} = {spread_price})")
        spec = dict(spec)                    # copie locala
        spec["spread_price"]  = spread_price
        spec["spread_ticks"]  = spread_ticks
        # salveaza in JSON ca referinta
        specs_all[SYMBOL]["spread_price"]  = spread_price
        specs_all[SYMBOL]["spread_ticks"]  = spread_ticks
        with open(SPECS_FILE, "w", encoding="utf-8") as f:
            json.dump(specs_all, f, indent=2)
        print(f"  Salvat in crypto_specs.json.")
    else:
        print(f"  AVERTISMENT: spread = 0 sau MT5 indisponibil.")
        print(f"  Continuam cu spread = {spec['spread_price']} din specs.json.")
        if spec["spread_price"] == 0:
            print(f"  ** REZULTATELE VOR FI OPTIMISTE (spread 0) **")

    # Patch pip_size
    _sig._INDEX_PIP[SYMBOL] = spec["tick_size"]

    # --- config ---
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["account"]["starting_balance"]              = START_BALANCE
    cfg["session"]["start_hour"]                    = 0
    cfg["session"]["end_hour"]                      = 24
    cfg["risk_management"]["max_trades_per_day"]     = 9999
    cfg["risk_management"]["max_consecutive_losses"]  = 9999
    cfg["costs"]["commission_per_lot_round_turn_usd"] = 0.0
    cfg["optional_criteria"]["rsi"]["sell_max"]      = 60

    # --- date ---
    print_section("STEP 2 -- Date ADAUSD")
    source = CsvDataSource(DATA_DIR)
    df_ada = prepare_symbol(source, SYMBOL, cfg)
    print(f"  {len(df_ada)} bare M15  "
          f"[{df_ada['time'].min().date()} ... {df_ada['time'].max().date()}]")

    # --- backtest ONLY_SHORT ---
    print_section("STEP 3 -- Backtest ONLY_SHORT")
    print(f"  Spread folosit: {spec['spread_price']:.6f}  "
          f"(mode={spec['swap_mode']}, swap_long={spec['swap_long']}%/an)")

    trades, equity_curve, _, skipped = run_crypto(
        df_ada, SYMBOL, spec, cfg,
        only_short=True,
        spread_override=spec["spread_price"],
    )
    print(f"  Trades triggerate: {len(trades)}  |  Sarite min-lot: {skipped}")

    if not trades:
        print("  0 trades -- date insuficiente sau spread prea mare.")
        return

    tdf = pd.DataFrame(trades)
    tdf = tdf[tdf["risk_usd"] > 0].copy()
    tdf["R_real"]  = tdf["pnl_usd"] / tdf["risk_usd"]
    tdf["entry_t"] = pd.to_datetime(tdf["time"])
    tdf["year"]    = tdf["entry_t"].dt.year
    tdf["R_tgt"]   = tdf["R"].round(1)   # 2.5 / 3.5 / 4.5

    eq   = np.asarray(equity_curve, dtype=float)
    peak = np.maximum.accumulate(eq)
    dd   = ((eq - peak) / peak).min() * 100
    ret  = (equity_curve[-1] - START_BALANCE) / START_BALANCE * 100

    n    = len(tdf)
    wins = (tdf["outcome"] == "win").sum()

    swap_paid = tdf["swap"].sum()
    net_pnl   = tdf["pnl_usd"].sum()
    gross_pnl = net_pnl + swap_paid
    swap_gross_pct = swap_paid / gross_pnl * 100 if gross_pnl > 0 else float("inf")

    span_days = (tdf["entry_t"].max() - tdf["entry_t"].min()).days
    freq_wk   = n / max(span_days / 7, 1)

    print(f"\n  Balanta: {START_BALANCE} -> {equity_curve[-1]:.2f}  ({ret:+.1f}%)")
    print(f"  Trades  : {n}  |  Win: {wins/n*100:.1f}%  |  Expectancy: {tdf['R_real'].mean():+.4f} R")
    print(f"  DD max  : {dd:.1f}%  |  Frecventa: {freq_wk:.1f} trades/sapt")

    # ---- STEP 4: Train / Test + p-value + CI ---------------------------------
    print_section("STEP 4 -- Train / Test 70/30 + p-value + CI 95%")

    split_t = tdf["entry_t"].quantile(0.70)
    train   = tdf[tdf["entry_t"] <  split_t]
    test    = tdf[tdf["entry_t"] >= split_t]

    print(f"  Split la: {split_t.date()}")
    for label, d_set in [("TRAIN", train), ("TEST ", test)]:
        if len(d_set) == 0:
            print(f"  {label}: gol")
            continue
        w    = (d_set["outcome"] == "win").sum()
        m    = d_set["R_real"].mean()
        ts, pv = ttest_one_sided(d_set["R_real"].values)
        lo, hi = ci_95(d_set["R_real"].values)
        sig  = "  *** SEMNIFICATIV p<0.05 ***" if (pv and pv < 0.05) else \
               "  (* marginal p<0.10)"          if (pv and pv < 0.10) else \
               "  (nesemnificativ)"              if pv else ""
        ci_str = f"IC 95%: [{lo:+.4f}, {hi:+.4f}]" if lo is not None else ""
        print(f"\n  {label} ({len(d_set)} trades):")
        print(f"    Win rate   : {w/len(d_set)*100:.1f}%")
        print(f"    Expectancy : {m:+.4f} R    {ci_str}")
        if ts is not None:
            print(f"    t-stat={ts:.3f}  p={pv:.4f}{sig}")

    # ---- STEP 5: Edge per nivel R -------------------------------------------
    print_section("STEP 5 -- Edge per nivel R (2.5 / 3.5 / 4.5)")

    print(f"  {'R target':>9} {'trades':>7} {'win%':>7} {'exp R':>9} "
          f"{'BE win%':>9} {'above BE':>9}")
    print(f"  {'-'*60}")
    breakeven = {2.5: 1/(1+2.5), 3.5: 1/(1+3.5), 4.5: 1/(1+4.5)}
    for r_val in sorted(tdf["R_tgt"].unique()):
        sub = tdf[tdf["R_tgt"] == r_val]
        w   = (sub["outcome"] == "win").sum()
        wr  = w / len(sub)
        exp = sub["R_real"].mean()
        be  = breakeven.get(r_val, float("nan"))
        above = "DA" if wr > be else "NU"
        print(f"  R={r_val:.1f}:   {len(sub):>7} {wr*100:>6.1f}% {exp:>+9.4f} "
              f"{be*100:>8.1f}% {above:>9}")

    # separat pe train/test per R
    print(f"\n  Detaliu per R pe TEST ({len(test)} trades):")
    print(f"  {'R target':>9} {'trades':>7} {'win%':>7} {'exp R':>9} {'p-val':>8}")
    print(f"  {'-'*50}")
    for r_val in sorted(test["R_tgt"].unique()):
        sub  = test[test["R_tgt"] == r_val]
        w    = (sub["outcome"] == "win").sum()
        exp  = sub["R_real"].mean()
        ts, pv = ttest_one_sided(sub["R_real"].values)
        pv_str = f"{pv:.4f}" if pv is not None else "--"
        print(f"  R={r_val:.1f}:   {len(sub):>7} {w/len(sub)*100:>6.1f}% "
              f"{exp:>+9.4f} {pv_str:>8}")

    # ---- STEP 6: Annual breakdown cu swap -----------------------------------
    print_section("STEP 6 -- Expectancy per an (2021-2026) cu swap real")

    annual = tdf.groupby("year").agg(
        trades   = ("R_real",  "count"),
        exp_R    = ("R_real",  "mean"),
        win_n    = ("outcome", lambda x: (x == "win").sum()),
        swap_paid= ("swap",    "sum"),
        net_pnl  = ("pnl_usd", "sum"),
    ).reset_index()
    annual["win_pct"]    = annual["win_n"] / annual["trades"] * 100
    annual["gross_pnl"]  = annual["net_pnl"] + annual["swap_paid"]
    annual["swap_gpct"]  = annual.apply(
        lambda r: r["swap_paid"] / r["gross_pnl"] * 100 if r["gross_pnl"] > 0 else float("inf"),
        axis=1
    )

    print(f"  {'An':>5} {'trades':>7} {'win%':>6} {'exp R':>8} "
          f"{'net PnL':>9} {'swap':>8} {'gross':>9} {'swap/gr':>9}")
    print(f"  {'-'*72}")
    for _, row_a in annual.iterrows():
        yr    = int(row_a["year"])
        sg    = f"{row_a['swap_gpct']:.0f}%" if math.isfinite(row_a["swap_gpct"]) else "inf%"
        print(f"  {yr:>5} {int(row_a['trades']):>7} {row_a['win_pct']:>5.1f}% "
              f"{row_a['exp_R']:>+8.4f} {row_a['net_pnl']:>+9.2f}$ "
              f"{row_a['swap_paid']:>7.2f}$ {row_a['gross_pnl']:>+8.2f}$ {sg:>9}")

    # ---- STEP 7: Swap global -------------------------------------------------
    print_section("STEP 7 -- Swap ca % din gross PnL (global, short-only)")
    print(f"  Gross PnL (fara swap) : {gross_pnl:+.2f}$")
    print(f"  Swap total platit     : {swap_paid:.2f}$")
    print(f"  Net PnL (cu swap)     : {net_pnl:+.2f}$")
    sg_str = f"{swap_gross_pct:.1f}%" if math.isfinite(swap_gross_pct) else "N/A (gross<=0)"
    print(f"  Swap / Gross PnL      : {sg_str}")

    mode_note = "(mode 5: dobanda % anuala pe notional)"
    print(f"  swap_long={spec['swap_long']}%/an  {mode_note}")

    # ---- Concluzie rapida ---------------------------------------------------
    print_section("CONCLUZIE RAPIDA")
    test_exp = test["R_real"].mean() if len(test) else float("nan")
    _, test_p = ttest_one_sided(test["R_real"].values if len(test) >= 5 else [])
    spread_note = "REAL" if spec["spread_price"] > 0 else "ZERO (optimist!)"
    print(f"  Spread folosit: {spread_note} ({spec['spread_price']:.6f})")
    print(f"  Expectancy global short: {tdf['R_real'].mean():+.4f} R")
    print(f"  Expectancy TEST short  : {test_exp:+.4f} R  "
          + (f"p={test_p:.4f}" if test_p else "(n<5)"))
    r_biggest = tdf.groupby("R_tgt")["R_real"].mean().idxmax()
    print(f"  Edge concentrat la R={r_biggest:.1f}  "
          f"({(tdf['R_tgt']==r_biggest).sum()} trades, "
          f"{(tdf['R_tgt']==r_biggest).sum()/n*100:.0f}% din total)")
    print(f"  Swap/gross (short): {sg_str}")
    pozitiv_ani = (annual["exp_R"] > 0).sum()
    total_ani   = len(annual)
    print(f"  Ani pozitivi: {pozitiv_ani}/{total_ani} "
          f"({'inclusiv 2022' if (annual[annual['year']==2022]['exp_R'].values[0] > 0 if 2022 in annual['year'].values else False) else '2022 negativ sau absent'})")

    # --- salveaza CSV ---------------------------------------------------------
    out = os.path.join(DATA_DIR, f"ada_short_trades.csv")
    tdf.to_csv(out, index=False)
    print(f"\n  CSV salvat: {out}")


if __name__ == "__main__":
    main()
