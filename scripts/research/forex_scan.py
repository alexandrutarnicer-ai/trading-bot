"""
Forex Scan — perechi netestata din /data
=========================================
EURJPY, GBPUSD, USDJPY, AUDJPY, AUDUSD, NZDJPY, NZDUSD, USDCAD, USDCHF, CHFJPY
Sesiuni targetate pe caracteristicile fiecarei perechi.
Grid: PW 4/6/8/10 × LONG/BOTH × skipMon × sesiune
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

INSTRUMENTS = [
    # sesiune(start,end), spread_pips
    ("EURJPY",  [(7,17),(7,12),(12,17)],  1.2),
    ("GBPUSD",  [(7,17),(7,12),(12,17)],  1.0),
    ("USDJPY",  [(0,9),(7,17),(12,21)],   1.0),
    ("AUDJPY",  [(0,10),(7,17)],          1.5),
    ("AUDUSD",  [(0,10),(7,17)],          1.2),
    ("NZDJPY",  [(0,10),(7,17)],          2.0),
    ("NZDUSD",  [(0,10),(7,17)],          1.5),
    ("USDCAD",  [(12,21),(7,17)],         1.5),
    ("USDCHF",  [(7,17),(12,21)],         1.2),
    ("CHFJPY",  [(7,17),(0,10)],          1.5),
]

PW_LIST = [4, 6, 8, 10]
DIRS    = [("BOTH", False), ("LONG", True)]


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


def run_one(sym, df, session, pw, only_long, skip_monday, spread, cfg_base):
    cfg = copy.deepcopy(cfg_base)
    cfg["account"]["starting_balance"] = 1000
    cfg["session"]["start_hour"] = 0
    cfg["session"]["end_hour"] = 24
    cfg["risk_management"]["max_consecutive_losses"] = 9999

    params = {
        "spread_pips":           {sym: spread},
        "leverage":              30,
        "start_balance":         1000,
        "expire_bars":           4,
        "pullback_window":       pw,
        "depth_range":           None,
        "skip_monday":           skip_monday,
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
        p_tr=ttest_os(train["R"].values),
        p_te=ttest_os(test["R"].values),
        freq=freq, dd=maxdd(equity), bal=balance,
    )


def main():
    print("=" * 76)
    print("  FOREX SCAN — perechi netestata")
    print("=" * 76)

    with open(CONFIG, encoding="utf-8") as f:
        cfg_base = json.load(f)
    source = CsvDataSource(DATA_DIR)

    all_candidates = []

    for sym, sessions, spread in INSTRUMENTS:
        f15 = os.path.join(DATA_DIR, f"{sym}_M15.csv")
        f30 = os.path.join(DATA_DIR, f"{sym}_M30.csv")
        if not os.path.exists(f15) or not os.path.exists(f30):
            print(f"\n  {sym}: date lipsa — skip")
            continue

        try:
            t0 = pd.read_csv(f15, usecols=["time"], nrows=1)["time"].iloc[0]
            t1 = pd.read_csv(f15, usecols=["time"]).tail(1)["time"].iloc[0]
            yrs = (pd.Timestamp(t1) - pd.Timestamp(t0)).days / 365.25
            rows = sum(1 for _ in open(f15)) - 1
        except Exception:
            yrs, rows = 0, 0

        print(f"\n{'─'*76}")
        print(f"  {sym}  ({yrs:.1f} ani, {rows:,} bare M15)  spread={spread}p")
        print(f"{'─'*76}")

        # prepare_symbol o singura data per pereche
        cfg_prep = copy.deepcopy(cfg_base)
        cfg_prep["account"]["starting_balance"] = 1000
        cfg_prep["session"]["start_hour"] = 0
        cfg_prep["session"]["end_hour"] = 24
        cfg_prep["risk_management"]["max_consecutive_losses"] = 9999
        try:
            df_sym = prepare_symbol(source, sym, cfg_prep)
        except Exception:
            print(f"  {sym}: eroare prepare_symbol — skip")
            continue
        if df_sym is None or len(df_sym) < 300:
            print(f"  {sym}: date insuficiente — skip")
            continue

        best = None

        for session in sessions:
            for pw in PW_LIST:
                for dlbl, only_long in DIRS:
                    for skip_mon in [True, False]:
                        r = run_one(sym, df_sym, session, pw, only_long, skip_mon,
                                    spread, cfg_base)
                        if r is None or r["n"] < 15: continue

                        sm  = "skipMon" if skip_mon else "allDay"
                        p_s = f"{r['p_te']:.3f}{sig(r['p_te'])}" if r["p_te"] else " N/A"
                        e_s = f"{r['e_te']:+.3f}" if not np.isnan(r["e_te"]) else "  N/A"
                        e_r = f"{r['e_tr']:+.3f}" if not np.isnan(r["e_tr"]) else "  N/A"
                        flag = ""
                        if (r["p_te"] and r["p_te"] < 0.10 and
                                not np.isnan(r["e_te"]) and r["e_te"] > 0):
                            flag = "  *** EDGE" if r["p_te"] < 0.05 else "  * edge"

                        print(f"  {session[0]:02d}-{session[1]:02d}h PW={pw} {dlbl:<4} {sm:<7} | "
                              f"n={r['n']:3d} train={e_r}R test={e_s}R "
                              f"p={p_s} {r['freq']:.1f}/s DD={r['dd']:.0f}%{flag}")

                        if (r["p_te"] and r["p_te"] < 0.10 and
                                not np.isnan(r["e_te"]) and r["e_te"] > 0 and r["freq"] >= 0.5):
                            all_candidates.append(dict(
                                sym=sym, session=session, pw=pw,
                                dir=dlbl, sm=skip_mon, spread=spread, **r))

                        if best is None or (not np.isnan(r["e_te"]) and
                                             (np.isnan(best.get("e_te", float("nan"))) or
                                              r["e_te"] > best["e_te"])):
                            best = dict(session=session, pw=pw, dir=dlbl,
                                        sm=skip_mon, **r)

        if best and not np.isnan(best.get("e_te", float("nan"))):
            sm = "skipMon" if best["sm"] else "allDay"
            p_s = f"{best['p_te']:.3f}{sig(best['p_te'])}" if best["p_te"] else "N/A"
            print(f"\n  >> CEL MAI BUN: {best['session'][0]:02d}-{best['session'][1]:02d}h "
                  f"PW={best['pw']} {best['dir']} {sm} | "
                  f"test={best['e_te']:+.3f}R p={p_s} {best['freq']:.1f}/s DD={best['dd']:.0f}%")

    print("\n" + "=" * 76)
    print("  SUMAR — Forex cu edge (p_test < 0.10, exp_test > 0, >=0.5/s)")
    print("=" * 76)
    if not all_candidates:
        print("  Niciun instrument cu edge confirmat.")
    else:
        all_candidates.sort(key=lambda x: x["e_te"], reverse=True)
        print(f"  {'Sym':<8} {'Sesiune':>10} {'PW':>3} {'Dir':<5} {'Sm':<8} "
              f"{'Train':>8} {'Test':>8} {'p':>8} {'Freq':>5}")
        print("  " + "-" * 70)
        for c in all_candidates:
            sm  = "skipMon" if c["sm"] else "allDay"
            p_s = f"{c['p_te']:.3f}{sig(c['p_te'])}"
            sstr= f"{c['session'][0]:02d}-{c['session'][1]:02d}h"
            print(f"  {c['sym']:<8} {sstr:>10} PW={c['pw']:2d} {c['dir']:<5} {sm:<8} "
                  f"{c['e_tr']:>+8.3f}R {c['e_te']:>+8.3f}R {p_s:>8} {c['freq']:>4.1f}/s")


if __name__ == "__main__":
    main()
