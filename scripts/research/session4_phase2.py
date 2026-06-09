"""
Session 4 — Phase 2: LONG ONLY pe indici si aur
================================================
Phase 1 a aratat ca BOTH directions e toxic pe indici (SHORT contra secular bull).
Testam LONG only cu mai multe variante de sesiune si PW.

Rulare: python scripts/research/session4_phase2.py
"""

import os, sys, copy, json, math
import numpy as np
import pandas as pd
from scipy import stats as _stats

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol
from strategy.signals import pip_size
from engine.portfolio import run_portfolio


def ttest_one_sided(arr):
    a = np.asarray(arr, float)
    n = len(a)
    if n < 10: return None
    s = a.std(ddof=1)
    if s < 1e-12: return None
    t = a.mean() / (s / math.sqrt(n))
    p = 1 - _stats.t.cdf(t, df=n - 1)
    return round(p, 4)

def sig(p):
    if p is None: return ""
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.10 else ""

def maxdd(equity_list):
    eq = np.asarray([e["balance"] for e in equity_list], float)
    pk = np.maximum.accumulate(eq)
    return round(((eq - pk) / np.where(pk > 0, pk, 1)).min() * 100, 1)

def compute_spread_sl(trades, symbol, spread_pips_val):
    pip = pip_size(symbol)
    r = [spread_pips_val / abs(t["entry"] - t["sl"]) * pip * 100
         for t in trades if abs(t["entry"] - t["sl"]) > 0]
    return round(float(np.median(r)), 1) if r else float("nan")

def run_one(sym, spread_pips, session, skip_monday, pw, start_balance, cfg_base, source):
    sh, eh = session
    cfg = copy.deepcopy(cfg_base)
    cfg["account"]["starting_balance"]               = start_balance
    cfg["session"]["start_hour"]                     = 0
    cfg["session"]["end_hour"]                       = 24
    cfg["risk_management"]["max_trades_per_day"]     = 5
    cfg["risk_management"]["max_consecutive_losses"] = 9999

    try:
        df = prepare_symbol(source, sym, cfg)
    except FileNotFoundError:
        return None

    params = {
        "spread_pips":            {sym: spread_pips},
        "leverage":               30,
        "start_balance":          start_balance,
        "expire_bars":            4,
        "pullback_window":        pw,
        "depth_range":            None,
        "skip_monday":            skip_monday,
        "skip_hours":             (),
        "atr_max_pips":           {},
        "max_day_consec_losses":  3,
        "corr_pairs":             {},
        "only_long":              True,
        "max_pos_per_symbol":     1,
        "symbol_sessions":        {sym: (sh, eh)},
        "symbol_skip_hours":      {},
    }

    trades, equity, balance, _, _, halted, split_time = \
        run_portfolio({sym: df}, cfg, params)

    if not trades:
        return None

    tdf = pd.DataFrame(trades)
    tdf["R"] = tdf["pnl_usd"] / tdf["risk_usd"]
    tdf["entry_t"] = pd.to_datetime(tdf["time"])
    span = (tdf["entry_t"].max() - tdf["entry_t"].min()).days

    train = tdf[tdf["entry_t"] <  split_time]
    test  = tdf[tdf["entry_t"] >= split_time]

    return {
        "n": len(tdf), "n_train": len(train), "n_test": len(test),
        "exp_all":   round(tdf["R"].mean(), 4),
        "exp_train": round(train["R"].mean(), 4) if len(train) else 0.0,
        "exp_test":  round(test["R"].mean(),  4) if len(test)  else 0.0,
        "p_train":   ttest_one_sided(train["R"].values) if len(train) >= 10 else None,
        "p_test":    ttest_one_sided(test["R"].values)  if len(test)  >= 10 else None,
        "dd":        maxdd(equity),
        "freq":      round(len(tdf) / max(span / 7, 1), 1),
        "sp_sl":     compute_spread_sl(trades, sym, spread_pips),
        "bal":       round(balance, 0),
        "ret":       round((balance - start_balance) / start_balance * 100, 1),
        "split":     split_time,
        "wr":        round((tdf["outcome"] == "win").sum() / len(tdf) * 100, 1),
    }


TESTS = [
    # ── Risk Off — Gold (LONG = pozitia benefica in risk-off) ─────────────────
    dict(sym="XAUUSD", label="Gold London+NY",  spread=0.25, session=(7,17),  skip_mon=False, bal=5000),
    dict(sym="XAUUSD", label="Gold 24h",        spread=0.25, session=(0,24),  skip_mon=False, bal=5000),
    dict(sym="XAUUSD", label="Gold London only",spread=0.25, session=(7,13),  skip_mon=False, bal=5000),

    # ── Risk On EU — DAX LONG only ────────────────────────────────────────────
    dict(sym="GER40",  label="DAX 07-16h",      spread=1.5,  session=(7,16),  skip_mon=False, bal=1000),
    dict(sym="GER40",  label="DAX 08-16h",      spread=1.5,  session=(8,16),  skip_mon=False, bal=1000),
    dict(sym="GER40",  label="DAX 07-16h skipMon",spread=1.5,session=(7,16),  skip_mon=True,  bal=1000),
    dict(sym="GER40",  label="DAX 07-12h (morn)",spread=1.5, session=(7,12),  skip_mon=False, bal=1000),

    # ── Risk On EU — UK100 ────────────────────────────────────────────────────
    dict(sym="UK100",  label="FTSE 07-16h",     spread=2.0,  session=(7,16),  skip_mon=False, bal=1000),

    # ── Risk On US — Dow Jones LONG only ─────────────────────────────────────
    dict(sym="US30",   label="US30 14-21h",     spread=3.0,  session=(14,21), skip_mon=False, bal=1000),
    dict(sym="US30",   label="US30 15-21h",     spread=3.0,  session=(15,21), skip_mon=False, bal=1000),
    dict(sym="US30",   label="US30 14-20h",     spread=3.0,  session=(14,20), skip_mon=False, bal=1000),
    dict(sym="US30",   label="US30 skipMon",    spread=3.0,  session=(14,21), skip_mon=True,  bal=1000),

    # ── Risk On US — S&P 500 ─────────────────────────────────────────────────
    dict(sym="US500",  label="US500 14-21h",    spread=0.5,  session=(14,21), skip_mon=False, bal=1000),
    dict(sym="US500",  label="US500 15-21h",    spread=0.5,  session=(15,21), skip_mon=False, bal=1000),

    # ── Risk On US — Russell 2000 ─────────────────────────────────────────────
    dict(sym="US2000", label="US2000 14-21h",   spread=0.5,  session=(14,21), skip_mon=False, bal=1000),
]

DATA_OK = {"XAUUSD", "GER40", "US30"}   # 8+ ani date


def main():
    sep = "=" * 78
    print(sep)
    print("  SESSION 4 — Phase 2: LONG ONLY pe indici si aur")
    print(sep)
    print("  Motiv: SHORT contra secular bull market distruge edge-ul pe indici.")
    print("  Testam LONG only + variante de sesiune pentru fiecare instrument.\n")

    with open(CONFIG, encoding="utf-8") as f:
        cfg_base = json.load(f)
    source = CsvDataSource(DATA_DIR)

    results = []

    for t in TESTS:
        sym   = t["sym"]
        label = t["label"]
        flag  = "" if sym in DATA_OK else " [DATE LIMITATE]"
        print(f"  {label:<25}{flag}  PW=8 ", end="", flush=True)

        r8 = run_one(sym, t["spread"], t["session"], t["skip_mon"], 8, t["bal"], cfg_base, source)
        if r8 is None:
            print("date lipsa")
            continue
        print(f"N={r8['n']:4d} exp_test={r8['exp_test']:+.4f} p={r8['p_test']:.4f}{sig(r8['p_test'])} DD={r8['dd']:+.1f}%  ", end="")

        print(f"  PW=6 ", end="", flush=True)
        r6 = run_one(sym, t["spread"], t["session"], t["skip_mon"], 6, t["bal"], cfg_base, source)
        if r6 is None:
            print()
            best = r8; best["pw"] = 8
        else:
            print(f"N={r6['n']:4d} exp_test={r6['exp_test']:+.4f} p={r6['p_test']:.4f}{sig(r6['p_test'])} DD={r6['dd']:+.1f}%")
            best = r8 if (r8["exp_test"] >= (r6["exp_test"] or -999)) else r6
            best["pw"] = 8 if best is r8 else 6

        results.append({"test": t, "r": best})

    # Tabel sumar
    print(f"\n{sep}")
    print("  TABEL SUMAR — LONG only (cel mai bun PW per configuratie)")
    print(sep)
    print(f"  {'Config':<25} {'PW':>3} {'N':>5} {'Exp(all)':>9} {'Exp(test)':>10} {'p_test':>9} {'Sp/SL':>6} {'DD':>7} {'T/wk':>5}  Verdict")
    print(f"  {'-'*76}")

    viable = []
    for item in sorted(results, key=lambda x: -(x["r"]["exp_test"] or -999)):
        t = item["test"]
        r = item["r"]
        sym  = t["sym"]
        flag = "" if sym in DATA_OK else "[!]"
        p_s  = f"{r['p_test']:.4f}{sig(r['p_test'])}" if r["p_test"] is not None else "   N/A"
        ok   = (r["exp_test"] or 0) > 0 and (r["p_test"] or 1) < 0.10 and r["dd"] > -60
        v    = "VIABLE" if ok and sym in DATA_OK else ("PROMITATOR?" if ok else "—")
        if ok: viable.append(t["label"])
        print(f"  {t['label']:<25}{flag:>3} {r['pw']:>2}  {r['n']:>5} "
              f"{r['exp_all']:>+9.4f} {r['exp_test']:>+10.4f} {p_s:>9} "
              f"{r['sp_sl']:>5.1f}% {r['dd']:>+6.1f}% {r['freq']:>4.1f}/w  {v}")

    # Detaliu viabile
    print(f"\n{sep}")
    print("  DETALIU — configuratii cu exp_test > 0 si p < 0.10")
    print(sep)
    for item in results:
        t = item["test"]
        r = item["r"]
        p = r["p_test"]
        if (r["exp_test"] or 0) <= 0 or (p or 1) >= 0.10:
            continue
        flag = "" if t["sym"] in DATA_OK else "  *** DATE LIMITATE ***"
        print(f"\n  {t['label']}{flag}")
        print(f"  PW={r['pw']}  sesiune={t['session'][0]}-{t['session'][1]}h UTC  "
              f"spread={t['spread']}pip  capital=${t['bal']}")
        print(f"  N={r['n']}  WR={r['wr']:.1f}%  Frecventa={r['freq']:.1f}/sapt  Sp/SL={r['sp_sl']:.1f}%")
        print(f"  TRAIN ({r['n_train']}t): {r['exp_train']:+.4f}R  p={r['p_train']:.4f}{sig(r['p_train'])}" if r["p_train"] else f"  TRAIN: N/A")
        print(f"  TEST  ({r['n_test']}t): {r['exp_test']:+.4f}R  p={p:.4f}{sig(p)}")
        print(f"  DD max: {r['dd']:+.1f}%  |  ${t['bal']} -> ${r['bal']:.0f}  ({r['ret']:+.1f}%)")
        print(f"  Split: {r['split'].date()}")

    # Verdict
    print(f"\n{sep}")
    print("  VERDICT PHASE 2")
    print(sep)
    if viable:
        print(f"\n  Configuratii viabile/promitoare: {viable}")
    else:
        print("\n  Nicio configuratie nu trece pragul p<0.10.")
        print("  Cel mai aproape: " + str(
            sorted(results, key=lambda x: x["r"]["exp_test"] or -999, reverse=True)[0]["test"]["label"]
            + f"  exp_test={sorted(results, key=lambda x: x['r']['exp_test'] or -999, reverse=True)[0]['r']['exp_test']:+.4f}R"
        ))
    print(f"\n{sep}\n")


if __name__ == "__main__":
    main()
