"""
Scan AUDNZD + AUDCAD — M15+M30
================================
Testeaza M15+M30 pentru AUDNZD si AUDCAD dupa ce s-a descarcat M15.
Sesiuni: Asia (00-10h), Oceania+EU (00-18h), EU (06-18h).

Rulare: python scripts/research/scan_audcross.py
(Ruleaza DUPA scripts/research/descarca_audcross_m15.py)
"""

import os, sys, copy, json, math, time as _time
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

INSTRUMENTS = [
    dict(symbol="AUDNZD", label="AUD/NZD", spread=1.3,
         sessions=[(0,10),(0,18),(6,18),(0,24)],
         skip_options=[False, True],
         note="Oceania session, spread mic — Oceania/Asia/EU"),
    dict(symbol="AUDCAD", label="AUD/CAD", spread=1.5,
         sessions=[(0,10),(0,18),(6,18),(12,22)],
         skip_options=[False, True],
         note="AUD activ Asia, CAD activ NY — testeaza ambele"),
]

COMBOS = [("M15+M30", "M15", "M30", 4, [4, 6, 8, 10, 12])]


def ttest_one_sided(arr):
    a = np.asarray(arr, float)
    n = len(a)
    if n < 10: return None
    s = a.std(ddof=1)
    if s < 1e-12: return None
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
    if len(eq) < 2: return 0.0
    pk = np.maximum.accumulate(eq)
    return round(float(((eq - pk) / np.where(pk > 0, pk, 1)).min() * 100), 1)


def spread_sl_pct(trades, symbol, spread_pips):
    pip  = pip_size(symbol)
    rats = [spread_pips / (abs(t["entry"] - t["sl"]) / pip) * 100
            for t in trades if abs(t["entry"] - t["sl"]) > 0]
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
    except Exception:
        return None
    params = {
        "spread_pips":           {sym: spread},
        "leverage":              30,
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
    tdf["yr"]  = tdf["entry_t"].dt.year
    ann        = tdf.groupby("yr")["R"].mean()
    return {
        "n":         len(tdf),
        "n_train":   len(train),
        "n_test":    len(test),
        "exp_train": round(train["R"].mean(), 4) if len(train) else 0.0,
        "exp_test":  round(test["R"].mean(),  4) if len(test)  else 0.0,
        "p_test":    ttest_one_sided(test["R"].values) if len(test) >= 10 else None,
        "wr":        round((tdf["outcome"] == "win").sum() / len(tdf) * 100, 1),
        "dd":        maxdd(equity),
        "freq":      round(len(tdf) / max(span_days / 7, 1), 2),
        "sp_sl":     spread_sl_pct(trades, sym, spread),
        "pos_yrs":   int((ann > 0).sum()),
        "tot_yrs":   int(len(ann)),
        "split":     split_time,
        "pw": pw, "session": session, "skip_mon": skip_mon, "only_long": only_long,
    }


def verdict(r):
    if r is None or r["n_test"] < 15: return "INSUF"
    sp_ok  = not math.isnan(r["sp_sl"]) and r["sp_sl"] < 20
    p_ok   = r["p_test"] is not None and r["p_test"] < 0.10
    dd_ok  = r["dd"] > -55
    exp_ok = r["exp_test"] > 0.10
    if sp_ok and p_ok and dd_ok and exp_ok and r["n_test"] >= 20:
        return "VIABLE"
    if r["exp_test"] > 0 and sp_ok:
        return "marginal"
    return "—"


def worker(args):
    sym, entry_tf, trend_tf, session, skip_mon, only_long, spread, pw, expire, cfg_base, tf_label = args
    r = run_one(sym, entry_tf, trend_tf, session, skip_mon, only_long, spread, pw, expire, cfg_base)
    return (sym, tf_label, r)


def main():
    SEP = "=" * 80
    print(SEP)
    print("  SCAN AUDNZD + AUDCAD — M15+M30  |  sesiuni Asia/Oceania/EU")
    print(SEP)

    with open(CONFIG, encoding="utf-8") as f:
        cfg_base = json.load(f)

    t_start = _time.time()
    tasks = []
    for inst in INSTRUMENTS:
        sym, spread = inst["symbol"], inst["spread"]
        for (tf_label, entry_tf, trend_tf, expire, pw_list) in COMBOS:
            for pw in pw_list:
                for session in inst["sessions"]:
                    for skip_mon in inst["skip_options"]:
                        for only_long in [False, True]:
                            tasks.append((sym, entry_tf, trend_tf, session,
                                          skip_mon, only_long, spread, pw, expire,
                                          cfg_base, tf_label))

    print(f"\n  {len(tasks)} configuratii, 6 workers...\n")

    best: dict[str, dict] = {}

    with ProcessPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(worker, t): t for t in tasks}
        for fut in as_completed(futures):
            try:
                sym, tf_label, r = fut.result()
            except Exception:
                continue
            if r is None:
                continue
            prev = best.get(sym)
            if prev is None or r["exp_test"] > prev["exp_test"]:
                best[sym] = r

    elapsed = _time.time() - t_start
    print(f"  Complet in {elapsed/60:.1f} min\n")

    print(SEP)
    print(f"  {'Simbol':<10} {'PW':>3} {'Dir':<5} {'Sess':>9} {'N':>5} {'Ntest':>6} "
          f"{'Train':>7} {'Test':>7} {'p_test':>9} {'DD':>7} {'f/wk':>5} {'Yrs+':>5}  Verdict")
    print(f"  {'-'*77}")

    viable = []
    marginal = []
    for inst in INSTRUMENTS:
        sym = inst["symbol"]
        r   = best.get(sym)
        if r is None:
            print(f"  {sym:<10} — date lipsa sau niciun rezultat")
            continue
        v       = verdict(r)
        p_str   = f"{r['p_test']:.4f}{sig_label(r['p_test'])}" if r["p_test"] is not None else "  N/A   "
        s_str   = f"{r['session'][0]:02d}-{r['session'][1]:02d}h"
        d_str   = "LONG" if r["only_long"] else "BOTH"
        yrs_str = f"{r['pos_yrs']}/{r['tot_yrs']}"
        print(f"  {sym:<10} {r['pw']:>3} {d_str:<5} {s_str:>9} {r['n']:>5} {r['n_test']:>6} "
              f"{r['exp_train']:>+7.4f} {r['exp_test']:>+7.4f} {p_str:>9} "
              f"{r['dd']:>+7.1f}% {r['freq']:>5.2f} {yrs_str:>5}  {v}")
        if v == "VIABLE":   viable.append((sym, r))
        elif v == "marginal": marginal.append((sym, r))

    print(f"\n{SEP}")
    if viable:
        print(f"  VIABLE ({len(viable)}):")
        for sym, r in viable:
            p_str = f"{r['p_test']:.4f}{sig_label(r['p_test'])}" if r["p_test"] else "N/A"
            print(f"    {sym} PW={r['pw']} {'LONG' if r['only_long'] else 'BOTH'} "
                  f"{r['session'][0]:02d}-{r['session'][1]:02d}h  "
                  f"test={r['exp_test']:+.4f}R  p={p_str}  "
                  f"DD={r['dd']:+.1f}%  {r['freq']:.2f}/wk  {r['pos_yrs']}/{r['tot_yrs']}yr+")
    else:
        print("  Niciun VIABLE.")
    if marginal:
        print(f"  Marginali ({len(marginal)}):")
        for sym, r in marginal:
            p_str = f"{r['p_test']:.4f}{sig_label(r['p_test'])}" if r["p_test"] else "N/A"
            print(f"    {sym} PW={r['pw']} {'LONG' if r['only_long'] else 'BOTH'} "
                  f"{r['session'][0]:02d}-{r['session'][1]:02d}h  "
                  f"test={r['exp_test']:+.4f}R  p={p_str}  "
                  f"DD={r['dd']:+.1f}%  {r['freq']:.2f}/wk  {r['pos_yrs']}/{r['tot_yrs']}yr+")
    print(SEP)


if __name__ == "__main__":
    main()
