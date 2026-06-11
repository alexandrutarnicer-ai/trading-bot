"""
Gold (XAUUSD) — test sistematic M15 pullback
=============================================
8.5 ani de date, acelasi API ca session4_scan.py
"""
import os, sys, copy, json, contextlib, io
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd
from scipy import stats as _stats

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol
from strategy.signals import pip_size, _INDEX_PIP
from engine.portfolio import run_portfolio

_INDEX_PIP["XAUUSD"] = 0.01

def ttest_os(rs):
    if len(rs) < 10: return None
    return _stats.ttest_1samp(rs, 0).pvalue / 2

def sig(p):
    if p is None: return ""
    if p < 0.01: return "***"
    if p < 0.05: return "**"
    if p < 0.10: return "*"
    return ""

def maxdd(equity):
    eq = np.array([e["balance"] for e in equity], float)
    if len(eq) < 2: return 0.0
    pk = np.maximum.accumulate(eq)
    return float(((eq - pk) / np.where(pk > 0, pk, 1)).min() * 100)

def run_one(df, cfg_base, session, pw, only_long, skip_monday, skip_hours=()):
    cfg = copy.deepcopy(cfg_base)
    cfg["account"]["starting_balance"] = 1000
    cfg["session"]["start_hour"] = 0
    cfg["session"]["end_hour"] = 24
    cfg["risk_management"]["max_consecutive_losses"] = 9999

    params = {
        "spread_pips": {"XAUUSD": 0.3},
        "leverage": 30,
        "start_balance": 1000,
        "expire_bars": 4,
        "pullback_window": pw,
        "depth_range": None,
        "skip_monday": skip_monday,
        "skip_hours": skip_hours,
        "atr_max_pips": {},
        "max_day_consec_losses": 3,
        "corr_pairs": {},
        "only_long": only_long,
        "max_pos_per_symbol": 1,
        "symbol_sessions": {"XAUUSD": session},
        "symbol_skip_hours": {},
    }

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            trades, equity, balance, _, _, halted, split_time = \
                run_portfolio({"XAUUSD": df}, cfg, params)
    except Exception as e:
        return None

    if not trades:
        return None

    tdf = pd.DataFrame(trades)
    tdf["R"]  = tdf["pnl_usd"] / tdf["risk_usd"]
    tdf["et"] = pd.to_datetime(tdf["time"])

    train = tdf[tdf["et"] <  split_time]
    test  = tdf[tdf["et"] >= split_time]
    freq  = len(tdf) / max((tdf["et"].max() - tdf["et"].min()).days / 7, 1)

    return dict(
        n=len(tdf), n_tr=len(train), n_te=len(test),
        e_tr=train["R"].mean() if len(train) >= 5 else float("nan"),
        e_te=test["R"].mean()  if len(test)  >= 5 else float("nan"),
        p_tr=ttest_os(train["R"].values),
        p_te=ttest_os(test["R"].values),
        freq=freq, dd=maxdd(equity), bal=balance,
    )

def main():
    print("=" * 72)
    print("  XAUUSD (Gold) — research M15 pullback  (8.5 ani date)")
    print("=" * 72)

    with open(CONFIG, encoding="utf-8") as f:
        cfg_base = json.load(f)
    source = CsvDataSource(DATA_DIR)

    # prepare_symbol o singura data — costisitor pe 200k bare
    cfg_prep = copy.deepcopy(cfg_base)
    cfg_prep["account"]["starting_balance"] = 1000
    cfg_prep["session"]["start_hour"] = 0
    cfg_prep["session"]["end_hour"] = 24
    cfg_prep["risk_management"]["max_consecutive_losses"] = 9999
    try:
        df = prepare_symbol(source, "XAUUSD", cfg_prep)
    except Exception as e:
        print(f"EROARE prepare_symbol: {e}")
        return
    if df is None or len(df) < 500:
        print("Date insuficiente XAUUSD")
        return
    print(f"  Date incarcate: {len(df)} bare")

    SESSIONS = [
        (7, 17,  "London+NY"),
        (7, 20,  "London+NY ext"),
        (8, 17,  "London core"),
        (13, 20, "NY only"),
        (6, 20,  "full day"),
    ]
    PW_LIST   = [4, 6, 8, 10]
    DIRS      = [("LONG", True), ("BOTH", False)]
    SKIP_MONS = [False, True]

    best = None
    candidates = []

    for sh, eh, slabel in SESSIONS:
        print(f"\n  Sesiune {sh:02d}-{eh:02d}h UTC  ({slabel})")
        print(f"  {'Config':<28} {'n':>4} {'train':>8} {'test':>8} {'p_test':>8} {'freq':>5} {'DD':>6}")
        for pw in PW_LIST:
            for dlbl, only_long in DIRS:
                for skip_mon in SKIP_MONS:
                    r = run_one(df, cfg_base, (sh, eh), pw, only_long, skip_mon)
                    if r is None or r["n"] < 20: continue
                    sm  = "skipMon" if skip_mon else "allDay"
                    lbl = f"PW={pw} {dlbl:<4} {sm}"
                    p_s = f"{r['p_te']:.3f}{sig(r['p_te'])}" if r["p_te"] else "N/A"
                    e_s = f"{r['e_te']:+.3f}" if not np.isnan(r["e_te"]) else " N/A"
                    e_r = f"{r['e_tr']:+.3f}" if not np.isnan(r["e_tr"]) else " N/A"
                    flag = ""
                    if r["p_te"] and r["p_te"] < 0.05 and not np.isnan(r["e_te"]) and r["e_te"] > 0:
                        flag = "  *** EDGE"
                    print(f"  {lbl:<28} {r['n']:>4} {e_r:>8}R {e_s:>8}R {p_s:>8} {r['freq']:>4.1f}/s {r['dd']:>5.0f}%{flag}")

                    if (r["p_te"] and r["p_te"] < 0.10 and
                            not np.isnan(r["e_te"]) and r["e_te"] > 0):
                        candidates.append(dict(session=(sh,eh), slabel=slabel,
                                               pw=pw, dir=dlbl, sm=skip_mon, **r))
                    if best is None or (not np.isnan(r["e_te"]) and
                                        (np.isnan(best["e_te"]) or r["e_te"] > best["e_te"])):
                        best = dict(sh=sh, eh=eh, slabel=slabel, pw=pw, dir=dlbl, sm=skip_mon, **r)

    print("\n" + "=" * 72)
    print("  SUMAR — configuratii XAUUSD cu edge (p_test < 0.10, exp_test > 0)")
    print("=" * 72)
    if not candidates:
        print("  Niciun config cu edge confirmat statistic.")
        if best:
            sm = "skipMon" if best["sm"] else "allDay"
            p_s = f"{best['p_te']:.3f}{sig(best['p_te'])}" if best["p_te"] else "N/A"
            print(f"\n  Cel mai bun totusi: {best['sh']:02d}-{best['eh']:02d}h "
                  f"PW={best['pw']} {best['dir']} {sm} | "
                  f"test={best['e_te']:+.3f}R {p_s} {best['freq']:.1f}/s DD={best['dd']:.0f}%")
    else:
        candidates.sort(key=lambda x: x["e_te"], reverse=True)
        for c in candidates:
            sm  = "skipMon" if c["sm"] else "allDay"
            p_s = f"{c['p_te']:.3f}{sig(c['p_te'])}"
            print(f"  {c['slabel']:<18} PW={c['pw']} {c['dir']:<4} {sm:<7} | "
                  f"train={c['e_tr']:+.3f}R test={c['e_te']:+.3f}R "
                  f"p={p_s} {c['freq']:.1f}/s DD={c['dd']:.0f}%")

if __name__ == "__main__":
    main()
