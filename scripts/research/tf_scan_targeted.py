"""
TF Scan Targeted — Retest USDCAD, USDCHF, AUDJPY, CADJPY
==========================================================
Dupa ce ai rulat scripts/descarca_h1_extra.py si ai date noi, ruleaza
acesta pentru a vedea rezultatele actualizate pe toate TF-urile.

Include si M15 (care poate nu a fost testat cu date suficiente anterior).

TF-uri testate per simbol:
  M15 + M30  — comparatie cu sesiunile existente
  M30 + H1   — unul sus fata de M15
  H1  + D1   — cel mai promitator din tf_scan general

Rulare: python scripts/research/tf_scan_targeted.py
"""

import os, sys, copy, json, math, time as _time

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
from strategy.costs import pip_value_usd
from engine.portfolio import run_portfolio


# ============================================================================
# INSTRUMENTE TESTATE
# ============================================================================

INSTRUMENTS = [
    dict(symbol="USDCAD", label="USD/CAD", spread=1.2,
         sess_eu=(7, 17), sess_d1=(0, 24), skip_mon=True,  bal=1000,
         note="London+NY 07-17h UTC"),
    dict(symbol="USDCHF", label="USD/CHF", spread=1.2,
         sess_eu=(7, 17), sess_d1=(0, 24), skip_mon=True,  bal=1000,
         note="London+NY 07-17h UTC"),
    dict(symbol="AUDJPY", label="AUD/JPY", spread=1.5,
         sess_eu=(0, 10), sess_d1=(0, 24), skip_mon=False, bal=1000,
         note="Tokyo 00-10h UTC"),
    dict(symbol="CADJPY", label="CAD/JPY", spread=1.5,
         sess_eu=(0, 10), sess_d1=(0, 24), skip_mon=False, bal=1000,
         note="Tokyo 00-10h UTC"),
]

# (label, entry_tf, trend_tf, session_key, expire_bars, pw_list)
TF_CFGS = [
    ("M15+M30", "M15", "M30", "sess_eu", 4, [6, 8]),
    ("M30+H1",  "M30", "H1",  "sess_eu", 4, [6, 8]),
    ("H1+D1",   "H1",  "D1",  "sess_eu", 4, [6, 8]),
    ("D1+D1",   "D1",  "D1",  "sess_d1", 2, [4, 6]),
]


# ============================================================================
# HELPERS
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
    if p is None:  return ""
    if p < 0.01:   return "***"
    if p < 0.05:   return "**"
    if p < 0.10:   return "*"
    return ""


def maxdd(equity_list):
    eq = np.asarray([e["balance"] for e in equity_list], float)
    if len(eq) < 2:
        return 0.0
    pk = np.maximum.accumulate(eq)
    return round(float(((eq - pk) / np.where(pk > 0, pk, 1)).min() * 100), 1)


def spread_sl_pct(trades, symbol, spread_pips):
    pip = pip_size(symbol)
    ratios = []
    for tr in trades:
        sl_pips = abs(tr["entry"] - tr["sl"]) / pip
        if sl_pips > 0:
            ratios.append(spread_pips / sl_pips * 100)
    return round(float(np.median(ratios)), 1) if ratios else float("nan")


def run_one(sym, entry_tf, trend_tf, session, skip_mon, spread, bal, pw,
            expire, cfg_base, source):
    cfg = copy.deepcopy(cfg_base)
    cfg["account"]["starting_balance"]            = bal
    cfg["session"]["start_hour"]                  = 0
    cfg["session"]["end_hour"]                    = 24
    cfg["risk_management"]["max_trades_per_day"]  = 5
    cfg["risk_management"]["max_consecutive_losses"] = 9999
    cfg["optional_criteria"]["rsi"]["sell_max"]   = 60

    try:
        df = prepare_symbol_tf(source, sym, cfg, entry_tf=entry_tf, trend_tf=trend_tf)
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"    PREP ERR {sym}: {e}")
        return None

    params = {
        "spread_pips":            {sym: spread},
        "leverage":               30,
        "start_balance":          bal,
        "expire_bars":            expire,
        "pullback_window":        pw,
        "depth_range":            None,
        "skip_monday":            skip_mon,
        "skip_hours":             (),
        "atr_max_pips":           {},
        "max_day_consec_losses":  3,
        "corr_pairs":             {},
        "only_long":              False,
        "max_pos_per_symbol":     1,
        "symbol_sessions":        {sym: session},
        "symbol_skip_hours":      {},
    }

    try:
        trades, equity, balance, _, _, halted, split_time = \
            run_portfolio({sym: df}, cfg, params)
    except Exception as e:
        print(f"    RUN ERR {sym}: {e}")
        return None

    if not trades:
        return None

    tdf = pd.DataFrame(trades)
    tdf["R"]       = tdf["pnl_usd"] / tdf["risk_usd"]
    tdf["entry_t"] = pd.to_datetime(tdf["time"])

    span_days = (tdf["entry_t"].max() - tdf["entry_t"].min()).days
    freq_wk   = len(tdf) / max(span_days / 7, 1)

    train = tdf[tdf["entry_t"] <  split_time]
    test  = tdf[tdf["entry_t"] >= split_time]

    return {
        "n":          len(tdf),
        "n_train":    len(train),
        "n_test":     len(test),
        "exp_all":    round(tdf["R"].mean(), 4),
        "exp_train":  round(train["R"].mean(), 4) if len(train) else 0.0,
        "exp_test":   round(test["R"].mean(),  4) if len(test)  else 0.0,
        "wr":         round((tdf["outcome"] == "win").sum() / len(tdf) * 100, 1),
        "p_train":    ttest_one_sided(train["R"].values) if len(train) >= 10 else None,
        "p_test":     ttest_one_sided(test["R"].values)  if len(test)  >= 10 else None,
        "dd":         maxdd(equity),
        "freq":       round(freq_wk, 1),
        "sp_sl":      spread_sl_pct(trades, sym, spread),
        "bal_end":    round(balance, 0),
        "ret_pct":    round((balance - bal) / bal * 100, 1),
        "split":      split_time,
    }


def verdict_str(r):
    if r is None or r["n"] < 20:
        return "INSUF"
    sp_ok  = not math.isnan(r["sp_sl"]) and r["sp_sl"] < 25
    p_ok   = r["p_test"] is not None and r["p_test"] < 0.10
    dd_ok  = r["dd"] > -60
    exp_ok = r["exp_test"] > 0
    if sp_ok and p_ok and dd_ok and exp_ok:
        return "VIABLE **"
    elif exp_ok and sp_ok:
        return "MARGINAL"
    return "REJECTAT"


# ============================================================================
# MAIN
# ============================================================================

def main():
    SEP = "=" * 88

    print(SEP)
    print("  TF SCAN TARGETED — USDCAD / USDCF / AUDJPY / CADJPY")
    print("  M15+M30 / M30+H1 / H1+D1 (+ D1+D1 daca exista date)")
    print("  Ruleaza dupa scripts/descarca_h1_extra.py")
    print(SEP)

    with open(CONFIG, encoding="utf-8") as f:
        cfg_base = json.load(f)

    source   = CsvDataSource(DATA_DIR)
    t_start  = _time.time()

    all_results = {}   # symbol -> {tf_label -> best_result_dict}

    for inst in INSTRUMENTS:
        sym = inst["symbol"]
        print(f"\n{'-'*60}")
        print(f"  {inst['label']}  spread={inst['spread']}pip  {inst['note']}")
        print(f"  sess_eu={inst['sess_eu']}  skip_mon={inst['skip_mon']}")

        sym_res = {}

        for (tf_label, entry_tf, trend_tf, sess_key, expire, pw_list) in TF_CFGS:
            session = inst[sess_key]
            best    = None

            for pw in pw_list:
                print(f"    {tf_label}  PW={pw}  ", end="", flush=True)
                r = run_one(sym, entry_tf, trend_tf, session, inst["skip_mon"],
                            inst["spread"], inst["bal"], pw, expire, cfg_base, source)

                if r is None:
                    print("date lipsa / N=0")
                    break

                if r["n"] < 5:
                    print(f"N={r['n']} insuf")
                    continue

                p_s = (f"p_test={r['p_test']:.4f}{sig_label(r['p_test'])}"
                       if r["p_test"] is not None else "p_test=N/A")
                print(f"N={r['n']:4d}  exp_test={r['exp_test']:+.4f}R  "
                      f"{p_s}  sp/SL={r['sp_sl']:.1f}%  DD={r['dd']:+.1f}%  "
                      f"{r['freq']:.1f}/wk  [{r['split'].date()}]")

                r["pw"] = pw
                if best is None or r["exp_test"] > best["exp_test"]:
                    best = r

            sym_res[tf_label] = best

        all_results[sym] = (inst, sym_res)

    elapsed = _time.time() - t_start
    print(f"\nScan complet in {elapsed/60:.1f} minute.\n")

    # =========================================================================
    # RAPORT CONSOLIDAT
    # =========================================================================
    print(SEP)
    print("  RAPORT CONSOLIDAT — cel mai bun TF per simbol")
    print(SEP)
    print(f"  {'Simbol':<10} {'TF':<10} {'PW':>3} {'N':>5} {'Exp(test)':>10} "
          f"{'p_test':>9} {'Sp/SL':>7} {'DD':>7} {'T/wk':>6} {'Ret%':>6}  Verdict")
    print(f"  {'-'*86}")

    viable   = []
    marginal = []

    for inst in INSTRUMENTS:
        sym     = inst["symbol"]
        sym_res = all_results[sym][1]

        # Alege best global per simbol
        best_r = None; best_tf = None
        for tf_label, r in sym_res.items():
            if r is None or r["n"] < 20:
                continue
            if best_r is None or r["exp_test"] > best_r["exp_test"]:
                best_r = r; best_tf = tf_label

        if best_r is None:
            print(f"  {inst['label']:<10} —           toate date lipsa / N insuf")
            continue

        p_s = (f"{best_r['p_test']:.4f}{sig_label(best_r['p_test'])}"
               if best_r["p_test"] is not None else "   N/A")
        verd = verdict_str(best_r)
        sp_s = f"{best_r['sp_sl']:.1f}%" if not math.isnan(best_r["sp_sl"]) else "  N/A"

        print(f"  {inst['label']:<10} {best_tf:<10} {best_r['pw']:>3} "
              f"{best_r['n']:>5} {best_r['exp_test']:>+10.4f} "
              f"{p_s:>9} {sp_s:>7} {best_r['dd']:>+7.1f}% "
              f"{best_r['freq']:>5.1f}/w {best_r['ret_pct']:>+6.1f}%  {verd}")

        if "VIABLE" in verd:
            viable.append((sym, best_tf, best_r))
        elif "MARGINAL" in verd:
            marginal.append((sym, best_tf, best_r))

    # =========================================================================
    # DETALIU TF COMPLET PER SIMBOL
    # =========================================================================
    print(f"\n\n{SEP}")
    print("  DETALIU COMPLET — toate TF per simbol")
    print(SEP)

    for inst in INSTRUMENTS:
        sym     = inst["symbol"]
        sym_res = all_results[sym][1]
        print(f"\n  {inst['label']}  [{inst['note']}]")
        print(f"  {'TF':<10} {'PW':>3} {'N':>5} {'E(train)':>9} {'E(test)':>9} "
              f"{'p_tr':>7} {'p_test':>9} {'DD':>7} {'T/wk':>6}  Verdict")

        for (tf_label, _, _, _, _, _) in TF_CFGS:
            r = sym_res.get(tf_label)
            if r is None:
                print(f"  {tf_label:<10}  —  N/A")
                continue
            if r["n"] < 5:
                print(f"  {tf_label:<10}  N={r['n']} insuf")
                continue

            p_tr_s = (f"{r['p_train']:.4f}{sig_label(r['p_train'])}"
                      if r["p_train"] is not None else "   N/A")
            p_te_s = (f"{r['p_test']:.4f}{sig_label(r['p_test'])}"
                      if r["p_test"] is not None else "   N/A")
            verd   = verdict_str(r)

            print(f"  {tf_label:<10} {r['pw']:>3} {r['n']:>5} "
                  f"{r['exp_train']:>+9.4f} {r['exp_test']:>+9.4f} "
                  f"{p_tr_s:>7} {p_te_s:>9} {r['dd']:>+7.1f}% "
                  f"{r['freq']:>5.1f}/w  {verd}")

    # =========================================================================
    # VERDICT FINAL
    # =========================================================================
    print(f"\n\n{SEP}")
    print("  VERDICT FINAL")
    print(SEP)
    print(f"\n  VIABLE    ({len(viable)}):   "
          f"{[(s, tf) for s, tf, _ in viable] if viable else '—'}")
    print(f"  MARGINALE ({len(marginal)}):  "
          f"{[(s, tf) for s, tf, _ in marginal] if marginal else '—'}")

    if viable:
        print(f"\n  Recomandare implementare:")
        for sym, tf, r in viable:
            inst = next(i for i in INSTRUMENTS if i["symbol"] == sym)
            print(f"    {sym} {tf}: PW={r['pw']}, sesiune={inst['sess_eu']}h UTC, "
                  f"exp_test={r['exp_test']:+.4f}R, p={r['p_test']:.4f}, "
                  f"DD={r['dd']:.1f}%, {r['freq']:.1f}/sapt")

    if marginal:
        print(f"\n  Candidati marginali (pot deveni viabile cu mai multa data):")
        for sym, tf, r in marginal:
            inst = next(i for i in INSTRUMENTS if i["symbol"] == sym)
            p_s = f"{r['p_test']:.4f}" if r["p_test"] is not None else "N/A"
            print(f"    {sym} {tf}: p={p_s}, exp_test={r['exp_test']:+.4f}R, "
                  f"N={r['n']} (test={r['n_test']}), split={r['split'].date()}")

    if not viable and not marginal:
        print("\n  Niciun semnal robust. Descarca mai multa data si reincearca.")

    print(f"\n{SEP}\n")


if __name__ == "__main__":
    main()
