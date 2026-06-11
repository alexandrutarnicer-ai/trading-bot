"""
US500 Quick Test — sesiuni NY + extins
======================================
US500 testat anterior cu index_backtest.py cu rezultate negative.
Retestam cu sesiunile NY corecte si acelasi grid ca GER40/US30.
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
from engine.portfolio import run_portfolio

SYMBOL   = "US500"
SPREAD   = 0.3     # US500 spread tipic ~0.3 puncte

# Sesiuni de testat
SESSIONS = [
    ("ny_13_22",    (13, 22)),   # NY session core
    ("ny_ext_12_23",(12, 23)),   # NY extins
    ("eu_ny_08_20", (8,  20)),   # EU+NY overlap
    ("full_eu_ny",  (7,  22)),   # London open to NY close
]
PW_LIST  = [6, 8, 10]
DIRS     = [("BOTH", False), ("LONG", True)]


def ttest_os(rs):
    if len(rs) < 10: return None
    return _stats.ttest_1samp(rs, 0).pvalue / 2


def sig(p):
    if p is None: return ""
    if p < 0.01:  return "***"
    if p < 0.05:  return "**"
    if p < 0.10:  return "*"
    return ""


def maxdd(equity):
    eq = np.array([e["balance"] for e in equity], float)
    if len(eq) < 2: return 0.0
    pk = np.maximum.accumulate(eq)
    return float(((eq - pk) / np.where(pk > 0, pk, 1)).min() * 100)


def run_one(sym, df, session, pw, only_long, cfg_base):
    cfg = copy.deepcopy(cfg_base)
    cfg["account"]["starting_balance"] = 1000
    cfg["session"]["start_hour"] = 0
    cfg["session"]["end_hour"]   = 24
    cfg["risk_management"]["max_consecutive_losses"] = 9999

    params = {
        "spread_pips":           {sym: SPREAD},
        "leverage":              20,
        "start_balance":         1000,
        "expire_bars":           4,
        "pullback_window":       pw,
        "depth_range":           None,
        "skip_monday":           False,
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
        with contextlib.redirect_stdout(io.StringIO()):
            trades, equity, balance, _, _, halted, split_time = \
                run_portfolio({sym: df}, cfg, params)
    except Exception:
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
        p_te=ttest_os(test["R"].values),
        freq=freq, dd=maxdd(equity),
        split_time=split_time,
    )


def main():
    print("=" * 72)
    print("  US500 Quick Test — sesiuni NY (8.5 ani date)")
    print(f"  spread={SPREAD}p  grid={len(SESSIONS)}sess × {len(PW_LIST)}PW × {len(DIRS)}dir")
    print("=" * 72)

    f15 = os.path.join(DATA_DIR, f"{SYMBOL}_M15.csv")
    f30 = os.path.join(DATA_DIR, f"{SYMBOL}_M30.csv")
    if not os.path.exists(f15):
        print(f"  {SYMBOL}: date lipsa — SKIP")
        return

    t0   = pd.read_csv(f15, usecols=["time"], nrows=1)["time"].iloc[0]
    t1   = pd.read_csv(f15, usecols=["time"]).tail(1)["time"].iloc[0]
    rows = sum(1 for _ in open(f15)) - 1
    yrs  = (pd.Timestamp(t1) - pd.Timestamp(t0)).days / 365.25
    print(f"\n  {SYMBOL}: {yrs:.1f} ani, {rows:,} bare M15  ({t0[:10]} -> {t1[:10]})")

    with open(CONFIG, encoding="utf-8") as f:
        cfg_base = json.load(f)
    source = CsvDataSource(DATA_DIR)

    cfg_prep = copy.deepcopy(cfg_base)
    cfg_prep["account"]["starting_balance"] = 1000
    cfg_prep["session"]["start_hour"] = 0
    cfg_prep["session"]["end_hour"]   = 24
    cfg_prep["risk_management"]["max_consecutive_losses"] = 9999
    df_sym = prepare_symbol(source, SYMBOL, cfg_prep)
    print(f"  prepare_symbol: {len(df_sym)} bare\n")

    best = None
    candidates = []

    for sess_label, session in SESSIONS:
        sess_str = f"{session[0]:02d}-{session[1]:02d}h"
        print(f"  ── {sess_label} ({sess_str})")

        for pw in PW_LIST:
            for dlbl, only_long in DIRS:
                r = run_one(SYMBOL, df_sym, session, pw, only_long, cfg_base)
                if r is None or r["n"] < 15:
                    print(f"    PW={pw} {dlbl}: n<15")
                    continue

                p_s = f"{r['p_te']:.3f}{sig(r['p_te'])}" if r["p_te"] else "  N/A"
                e_s = f"{r['e_te']:+.3f}" if not np.isnan(r["e_te"]) else "  N/A"
                e_r = f"{r['e_tr']:+.3f}" if not np.isnan(r["e_tr"]) else "  N/A"
                spl = r["split_time"].strftime("%Y-%m")

                flag = ""
                is_edge = (
                    r["p_te"] and r["p_te"] < 0.10
                    and not np.isnan(r["e_te"]) and r["e_te"] > 0
                    and not np.isnan(r["e_tr"]) and r["e_tr"] > -0.10
                    and r["freq"] >= 0.5
                )
                if is_edge:
                    flag = "  *** EDGE" if r["p_te"] < 0.05 else "  * edge"
                    candidates.append(dict(sess=sess_label, pw=pw, dir=dlbl, **r))

                print(f"    PW={pw} {dlbl:<4} | n={r['n']:4d} train={e_r}R test={e_s}R "
                      f"p={p_s} {r['freq']:.1f}/s DD={r['dd']:+.0f}% [{spl}]{flag}")

                e_te_v = r["e_te"] if not np.isnan(r["e_te"]) else float("-inf")
                if best is None or e_te_v > (
                    best["e_te"] if not np.isnan(best.get("e_te", float("nan"))) else float("-inf")
                ):
                    best = dict(sess=sess_label, pw=pw, dir=dlbl, **r)

        print()

    if best:
        p_s = f"{best['p_te']:.3f}{sig(best['p_te'])}" if best["p_te"] else "N/A"
        print(f"\n  >> US500 CEL MAI BUN: {best['sess']} PW={best['pw']} {best['dir']} "
              f"| test={best['e_te']:+.3f}R p={p_s} {best['freq']:.1f}/s DD={best['dd']:+.0f}%")

    print("\n" + "=" * 72)
    if not candidates:
        print("  US500: Niciun config cu edge confirmat.")
    else:
        print("  US500 EDGE CONFIG:")
        for c in sorted(candidates, key=lambda x: x["e_te"], reverse=True):
            p_s = f"{c['p_te']:.3f}{sig(c['p_te'])}"
            print(f"  {c['sess']} PW={c['pw']} {c['dir']}: test={c['e_te']:+.3f}R "
                  f"p={p_s} {c['freq']:.1f}/s")


if __name__ == "__main__":
    main()
