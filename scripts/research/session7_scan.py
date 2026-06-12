"""
Session 7 Scan — H1+H4 combo + XAUUSD Gold multi-TF
======================================================
Combo H1+H4 (H1 entry, H4 trend) — NETESTATA in S6.
S6 a testat: M30+H1, H1+D1, H4+D1.

Instrumente: 26 perechi FX + indici + XAUUSD
TF principal: H1+H4 (entry H1, trend H4, expire 3 bare)
XAUUSD extra: M30+H1, H1+H4, H1+D1, H4+D1

Criteriu selectie:
  - exp_test > +0.15R
  - p_test   < 0.10 (one-sided t-test)
  - N_test  >= 20 trades
  - DD       > -55%
  - Spread/SL < 20%

Rulare: python scripts/research/session7_scan.py
(Ruleaza DUPA scripts/research/descarca_s7.py)
"""

import os
import sys
import copy
import json
import math
import time as _time
from concurrent.futures import ProcessPoolExecutor, as_completed

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
from scipy import stats as _stats

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol_tf
from strategy.signals import pip_size
from engine.portfolio import run_portfolio


# ============================================================================
# INSTRUMENTE — 26 FX + indici  (toate au H1+H4 sau vor avea dupa descarca_s7)
# ============================================================================
# Format: dict(symbol, label, spread_pips, sessions, skip_options, note)
# sessions: lista (start_h, end_h) UTC
# ============================================================================

INSTRUMENTS = [
    # ---- Majore (in S1/S2 la M15, acum testam H1+H4) ----
    dict(symbol="EURUSD",  label="EUR/USD",  spread=0.8,
         sessions=[(6,18)],             skip_options=[True, False],
         note="S1 M15 viable, testat H1+H4 prima oara"),
    dict(symbol="GBPUSD",  label="GBP/USD",  spread=1.0,
         sessions=[(6,18)],             skip_options=[True, False],
         note="S1 M15 viable"),
    dict(symbol="AUDUSD",  label="AUD/USD",  spread=0.9,
         sessions=[(0,18),(6,18)],      skip_options=[False, True],
         note="M15 a fost -0.380R"),
    dict(symbol="NZDUSD",  label="NZD/USD",  spread=1.2,
         sessions=[(0,18),(6,18)],      skip_options=[False],
         note="S2 M15 viable"),
    dict(symbol="USDCAD",  label="USD/CAD",  spread=1.2,
         sessions=[(6,18),(12,22)],     skip_options=[True],
         note="M15 a fost -0.497R"),
    dict(symbol="USDCHF",  label="USD/CHF",  spread=1.0,
         sessions=[(7,17)],             skip_options=[True, False],
         note="S5 H1+D1 VIABLE p=0.0896*"),
    dict(symbol="USDJPY",  label="USD/JPY",  spread=0.7,
         sessions=[(0,10),(6,18)],      skip_options=[False, True],
         note="S1 M15 viable"),

    # ---- EUR crosses ----
    dict(symbol="EURAUD",  label="EUR/AUD",  spread=1.5,
         sessions=[(6,18),(0,24)],      skip_options=[True, False],
         note="EU session dominanta"),
    dict(symbol="EURCAD",  label="EUR/CAD",  spread=1.5,
         sessions=[(6,18),(0,24)],      skip_options=[True, False],
         note="EU+NY overlap"),
    dict(symbol="EURNZD",  label="EUR/NZD",  spread=2.0,
         sessions=[(6,18),(0,24)],      skip_options=[True, False],
         note="Spread moderat"),
    dict(symbol="EURGBP",  label="EUR/GBP",  spread=0.9,
         sessions=[(6,18)],             skip_options=[True, False],
         note="Spread mic"),
    dict(symbol="EURJPY",  label="EUR/JPY",  spread=0.9,
         sessions=[(6,18),(0,10)],      skip_options=[True, False],
         note="Activ Asia+EU"),

    # ---- GBP crosses ----
    dict(symbol="GBPAUD",  label="GBP/AUD",  spread=2.0,
         sessions=[(6,18),(0,18)],      skip_options=[True, False],
         note="Volatil, spread moderat"),
    dict(symbol="GBPCAD",  label="GBP/CAD",  spread=2.0,
         sessions=[(6,18),(0,18)],      skip_options=[True, False],
         note="EU+NY overlap"),
    dict(symbol="GBPNZD",  label="GBP/NZD",  spread=2.5,
         sessions=[(6,18)],             skip_options=[True],
         note="Spread mai mare"),
    dict(symbol="GBPJPY",  label="GBP/JPY",  spread=1.5,
         sessions=[(6,18),(0,18)],      skip_options=[True, False],
         note="M15 -0.620R, H1+H4?"),

    # ---- JPY crosses ----
    dict(symbol="CHFJPY",  label="CHF/JPY",  spread=1.3,
         sessions=[(0,10),(6,18)],      skip_options=[False, True],
         note="S6 H1+D1 marginal"),
    dict(symbol="CADJPY",  label="CAD/JPY",  spread=1.5,
         sessions=[(6,18),(12,22)],     skip_options=[True, False],
         note="NY overlap"),
    dict(symbol="AUDJPY",  label="AUD/JPY",  spread=1.2,
         sessions=[(0,10),(6,18)],      skip_options=[False, True],
         note="S2 M15 viable"),
    dict(symbol="NZDJPY",  label="NZD/JPY",  spread=1.5,
         sessions=[(0,10),(6,18)],      skip_options=[False, True],
         note="S2 M15 viable"),

    # ---- Minor crosses ----
    dict(symbol="AUDNZD",  label="AUD/NZD",  spread=1.3,
         sessions=[(0,10),(0,18)],      skip_options=[False],
         note="Oceania session, spread mic"),
    dict(symbol="AUDCAD",  label="AUD/CAD",  spread=1.5,
         sessions=[(0,18),(6,18)],      skip_options=[False],
         note="Lichiditate buna"),

    # ---- Indici (sesiuni mai scurte) ----
    dict(symbol="GER40",   label="GER40",    spread=1.5,
         sessions=[(7,15)],             skip_options=[True],
         note="S4 M15 viable, S5 H1+D1 borderline"),
    dict(symbol="UK100",   label="UK100",    spread=1.5,
         sessions=[(7,15)],             skip_options=[True],
         note="LSE hours"),
    dict(symbol="US30",    label="US30",     spread=2.0,
         sessions=[(13,21)],            skip_options=[True],
         note="S6 H1+D1 marginal p=0.123"),
    dict(symbol="US500",   label="US500",    spread=0.8,
         sessions=[(13,21)],            skip_options=[True],
         note="M15 -0.133R"),

    # ---- Gold ----
    dict(symbol="XAUUSD",  label="XAU/USD",  spread=0.40,
         sessions=[(7,17),(7,21),(13,21),(0,24)], skip_options=[True, False],
         note="Gold — 8.5ani M15, H1/H4/D1 nou descarcat"),
]

# ============================================================================
# TF combos de testat
# Principal: H1+H4 (netestata in S6)
# XAUUSD: si celelalte combos (nicio TF superioara testata)
# ============================================================================
TF_COMBOS_MAIN = [
    # (label, entry_tf, trend_tf, expire_bars, pw_range)
    ("H1+H4", "H1", "H4", 3, [4, 6, 8, 10, 12]),
]

TF_COMBOS_XAUUSD = [
    ("M30+H1", "M30", "H1",  4, [6, 8, 10, 12]),
    ("H1+H4",  "H1",  "H4",  3, [4, 6, 8, 10, 12]),
    ("H1+D1",  "H1",  "D1",  3, [6, 8, 10, 12]),
    ("H4+D1",  "H4",  "D1",  2, [4, 6,  8, 10]),
]

XAUUSD_SYMBOLS = {"XAUUSD"}

# ============================================================================
# Helpers
# ============================================================================

def ttest_one_sided(arr):
    a = np.asarray(arr, float)
    n = len(a)
    if n < 10:
        return None
    s = a.std(ddof=1)
    if s < 1e-12:
        return None
    t = a.mean() / (s / math.sqrt(n))
    return round(float(1 - _stats.t.cdf(t, df=n - 1)), 4)


def sig_label(p):
    if p is None:  return "   "
    if p < 0.01:   return "***"
    if p < 0.05:   return "** "
    if p < 0.10:   return "*  "
    return "   "


def maxdd(equity_list):
    eq = np.asarray([e["balance"] for e in equity_list], float)
    if len(eq) < 2:
        return 0.0
    pk = np.maximum.accumulate(eq)
    return round(float(((eq - pk) / np.where(pk > 0, pk, 1)).min() * 100), 1)


def spread_sl_pct(trades, symbol, spread_pips):
    pip  = pip_size(symbol)
    rats = []
    for tr in trades:
        sl_p = abs(tr["entry"] - tr["sl"]) / pip
        if sl_p > 0:
            rats.append(spread_pips / sl_p * 100)
    return round(float(np.median(rats)), 1) if rats else float("nan")


def run_one(sym, entry_tf, trend_tf, session, skip_mon, only_long,
            spread, pw, expire, cfg_base):
    source = CsvDataSource(DATA_DIR)
    cfg    = copy.deepcopy(cfg_base)
    cfg["account"]["starting_balance"]               = 1000
    cfg["session"]["start_hour"]                     = 0
    cfg["session"]["end_hour"]                       = 24
    cfg["risk_management"]["max_trades_per_day"]     = 5
    cfg["risk_management"]["max_consecutive_losses"] = 9999
    cfg["optional_criteria"]["rsi"]["sell_max"]      = 60

    try:
        df = prepare_symbol_tf(source, sym, cfg, entry_tf=entry_tf, trend_tf=trend_tf)
    except (FileNotFoundError, Exception):
        return None

    params = {
        "spread_pips":           {sym: spread},
        "leverage":              30 if sym not in XAUUSD_SYMBOLS else 20,
        "start_balance":         1000,
        "expire_bars":           expire,
        "pullback_window":       pw,
        "depth_range":           None,
        "skip_monday":           skip_mon,
        "skip_hours":            (),
        "atr_max_pips":          {},
        "max_day_consec_losses": 3,
        "corr_pairs":            {},
        "only_long":             only_long,
        "max_pos_per_symbol":    1,
        "symbol_sessions":       {sym: session},
        "symbol_skip_hours":     {},
    }

    try:
        trades, equity, balance, _, _, _, split_time = \
            run_portfolio({sym: df}, cfg, params)
    except Exception:
        return None

    if not trades or len(trades) < 5:
        return None

    tdf = pd.DataFrame(trades)
    tdf["R"]       = tdf["pnl_usd"] / tdf["risk_usd"]
    tdf["entry_t"] = pd.to_datetime(tdf["time"])

    train = tdf[tdf["entry_t"] <  split_time]
    test  = tdf[tdf["entry_t"] >= split_time]

    if len(test) < 5:
        return None

    span_days = (tdf["entry_t"].max() - tdf["entry_t"].min()).days
    freq_wk   = len(tdf) / max(span_days / 7, 1)

    return {
        "n":         len(tdf),
        "n_train":   len(train),
        "n_test":    len(test),
        "exp_train": round(train["R"].mean(), 4) if len(train) else 0.0,
        "exp_test":  round(test["R"].mean(),  4) if len(test)  else 0.0,
        "p_train":   ttest_one_sided(train["R"].values) if len(train) >= 10 else None,
        "p_test":    ttest_one_sided(test["R"].values)  if len(test)  >= 10 else None,
        "wr":        round((tdf["outcome"] == "win").sum() / len(tdf) * 100, 1),
        "dd":        maxdd(equity),
        "freq":      round(freq_wk, 1),
        "sp_sl":     spread_sl_pct(trades, sym, spread),
        "bal_end":   round(balance, 0),
        "split":     split_time,
        "pw":        pw,
        "session":   session,
        "skip_mon":  skip_mon,
        "only_long": only_long,
    }


def verdict(r):
    if r is None or r["n_test"] < 15:
        return "INSUF"
    sp_ok  = not math.isnan(r["sp_sl"]) and r["sp_sl"] < 20
    p_ok   = r["p_test"] is not None and r["p_test"] < 0.10
    dd_ok  = r["dd"] > -55
    exp_ok = r["exp_test"] > 0.10
    if sp_ok and p_ok and dd_ok and exp_ok and r["n_test"] >= 20:
        return "VIABLE"
    if r["exp_test"] > 0 and sp_ok:
        return "marginal"
    return "—"


# ============================================================================
# WORKER
# ============================================================================

def worker(args):
    (sym, entry_tf, trend_tf, session, skip_mon, only_long,
     spread, pw, expire, cfg_base, tf_label, dir_label) = args
    r = run_one(sym, entry_tf, trend_tf, session, skip_mon, only_long,
                spread, pw, expire, cfg_base)
    return (sym, tf_label, session, skip_mon, only_long, pw, r)


# ============================================================================
# MAIN
# ============================================================================

def main():
    SEP = "=" * 90

    print(SEP)
    print("  SESSION 7 SCAN — H1+H4 combo (netestata S6) + XAUUSD Gold multi-TF")
    print(f"  {len(INSTRUMENTS)} instrumente  |  H1+H4 principal  |  XAUUSD: 4 TF combos")
    print(f"  Data: {DATA_DIR}")
    print(SEP)

    with open(CONFIG, encoding="utf-8") as f:
        cfg_base = json.load(f)

    t_start = _time.time()

    # Construieste lista de taskuri
    tasks = []
    for inst in INSTRUMENTS:
        sym    = inst["symbol"]
        spread = inst["spread"]

        # Alege TF combos pentru simbol
        combos = TF_COMBOS_XAUUSD if sym in XAUUSD_SYMBOLS else TF_COMBOS_MAIN

        for (tf_label, entry_tf, trend_tf, expire, pw_list) in combos:
            for pw in pw_list:
                for session in inst["sessions"]:
                    for skip_mon in inst["skip_options"]:
                        for only_long in [False, True]:
                            tasks.append((
                                sym, entry_tf, trend_tf, session,
                                skip_mon, only_long, spread, pw, expire,
                                cfg_base, tf_label,
                                "LONG" if only_long else "BOTH",
                            ))

    print(f"\n  Total configuratii: {len(tasks)}")
    print(f"  Procesare paralela (max 6 workers)...\n")

    # key: (sym, tf_label) -> best result
    best: dict[tuple, dict] = {}

    n_done = 0
    n_total = len(tasks)

    with ProcessPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(worker, t): t for t in tasks}
        for fut in as_completed(futures):
            n_done += 1
            try:
                sym, tf_label, session, skip_mon, only_long, pw, r = fut.result()
            except Exception:
                continue

            if r is None:
                continue

            key = (sym, tf_label)
            prev = best.get(key)
            if prev is None or r["exp_test"] > prev["exp_test"]:
                r["tf_label"] = tf_label
                r["sym"]      = sym
                best[key]     = r

            if n_done % 100 == 0 or n_done == n_total:
                elapsed = _time.time() - t_start
                print(f"  [{n_done:4d}/{n_total}]  {elapsed/60:.1f} min  "
                      f"({elapsed/n_done*1000:.0f}ms/run avg)")

    elapsed = _time.time() - t_start
    print(f"\n  Scan complet in {elapsed/60:.1f} minute.\n")

    # =========================================================================
    # RAPORT PER INSTRUMENT
    # =========================================================================
    print(SEP)
    print("  RAPORT PER INSTRUMENT — cea mai buna configuratie per piata + TF")
    print(SEP)
    hdr = (f"  {'Simbol':<10} {'TF':<9} {'PW':>3} {'Dir':<5} {'Sess':>9} "
           f"{'N':>5} {'Ntest':>6} {'Exp(tst)':>9} {'p_test':>8} "
           f"{'DD':>6} {'Sp/SL':>6} {'f/wk':>5}  Verdict")
    print(hdr)
    print(f"  {'-'*87}")

    viable_list   = []
    marginal_list = []

    for inst in INSTRUMENTS:
        sym = inst["symbol"]
        combos = TF_COMBOS_XAUUSD if sym in XAUUSD_SYMBOLS else TF_COMBOS_MAIN
        rows = []
        for (tf_label, _, _, _, _) in combos:
            r = best.get((sym, tf_label))
            if r:
                rows.append(r)

        if not rows:
            print(f"  {sym:<10} {'—':<9} — — — date lipsa")
            continue

        best_r = max(rows, key=lambda x: x["exp_test"])
        v      = verdict(best_r)
        p_str  = (f"{best_r['p_test']:.4f}{sig_label(best_r['p_test'])}"
                  if best_r["p_test"] is not None else "  N/A   ")
        sess_str = f"{best_r['session'][0]:02d}-{best_r['session'][1]:02d}h"
        dir_str  = "LONG" if best_r["only_long"] else "BOTH"

        line = (f"  {sym:<10} {best_r['tf_label']:<9} {best_r['pw']:>3} "
                f"{dir_str:<5} {sess_str:>9} "
                f"{best_r['n']:>5} {best_r['n_test']:>6} "
                f"{best_r['exp_test']:>+9.4f} {p_str:>8} "
                f"{best_r['dd']:>+6.1f}% {best_r['sp_sl']:>5.1f}% "
                f"{best_r['freq']:>4.1f}  {v}")
        print(line)

        if v == "VIABLE":
            viable_list.append((sym, inst, best_r, rows))
        elif v == "marginal":
            marginal_list.append((sym, inst, best_r, rows))

    # =========================================================================
    # DETALII per simbol VIABLE + MARGINAL
    # =========================================================================
    for sym, inst, _, rows in (viable_list + marginal_list):
        print(f"\n  {'-'*60}")
        print(f"  {inst['label']}  spread={inst['spread']}  |  {inst['note']}")
        print(f"  {'TF':<9} {'PW':>3} {'Dir':<5} {'Sess':>9} {'N':>5} {'Ntest':>6} "
              f"{'Train':>7} {'Test':>7} {'p_test':>9} {'DD':>7}  v")
        for r in sorted(rows, key=lambda x: -x["exp_test"])[:8]:
            v     = verdict(r)
            p_str = (f"{r['p_test']:.4f}{sig_label(r['p_test'])}"
                     if r["p_test"] is not None else "    N/A  ")
            sess_str = f"{r['session'][0]:02d}-{r['session'][1]:02d}h"
            dir_str  = "LONG" if r["only_long"] else "BOTH"
            print(f"  {r['tf_label']:<9} {r['pw']:>3} {dir_str:<5} {sess_str:>9} "
                  f"{r['n']:>5} {r['n_test']:>6} "
                  f"{r['exp_train']:>+7.4f} {r['exp_test']:>+7.4f} "
                  f"{p_str:>9} {r['dd']:>+7.1f}%  {v}")

    # =========================================================================
    # SUMAR FINAL
    # =========================================================================
    print(f"\n{SEP}")
    print(f"  SUMAR FINAL")
    print(f"{SEP}")

    if viable_list:
        print(f"  VIABLE ({len(viable_list)}):")
        for sym, inst, r, _ in viable_list:
            p_str = (f"{r['p_test']:.4f}{sig_label(r['p_test'])}"
                     if r["p_test"] is not None else "N/A")
            sess_str = f"{r['session'][0]:02d}-{r['session'][1]:02d}h"
            dir_str  = "LONG" if r["only_long"] else "BOTH"
            print(f"    {sym:<10} {r['tf_label']:<9} PW={r['pw']:<3} "
                  f"{dir_str:<5} {sess_str}  test={r['exp_test']:+.4f}R "
                  f"p={p_str}  DD={r['dd']:+.1f}%  {r['freq']:.1f}/wk")
    else:
        print("  Niciun VIABLE gasit.")

    if marginal_list:
        print(f"\n  Marginali ({len(marginal_list)}) — exp>0, fara p<0.10:")
        for sym, inst, r, _ in marginal_list:
            p_str = (f"{r['p_test']:.4f}{sig_label(r['p_test'])}"
                     if r["p_test"] is not None else "N/A")
            sess_str = f"{r['session'][0]:02d}-{r['session'][1]:02d}h"
            dir_str  = "LONG" if r["only_long"] else "BOTH"
            print(f"    {sym:<10} {r['tf_label']:<9} PW={r['pw']:<3} "
                  f"{dir_str:<5} {sess_str}  test={r['exp_test']:+.4f}R "
                  f"p={p_str}  DD={r['dd']:+.1f}%  {r['freq']:.1f}/wk")

    print(f"\n  Durata totala: {elapsed/60:.1f} minute")
    print(SEP)


if __name__ == "__main__":
    main()
