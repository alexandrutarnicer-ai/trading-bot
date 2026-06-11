"""
NZD/AUD Deep Scan cu 8 ani date (2018-2026)
===========================================
Testam NZDUSD, NZDJPY, AUDUSD si CHFJPY cu datele complete (200k bare = 8 ani).
Accent pe sesiunea 00-10h UTC (Asia) si 07-17h UTC (EU) — ambele directii.
Grid: PW 4/6/8/10 × BOTH/LONG × skipMon True/False = 16 combos/simbol/sesiune

Rezultate precedente (doar 2.4 ani):
  NZDUSD 00-10h PW=4 LONG skipMon: test=+0.884R p=0.098* (n=53, 14 teste)
  AUDJPY 00-10h PW=8 LONG allDay:  test=+1.169R p=0.058* (1.4 ani numai)
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

# Perechi, sesiuni, spread
INSTRUMENTS = [
    ("NZDUSD", [(0, 10), (7, 17)], 1.5),
    ("NZDJPY", [(0, 10), (7, 17)], 2.0),
    ("AUDUSD", [(0, 10), (7, 17)], 1.2),
    ("CHFJPY", [(0, 10), (7, 17)], 1.5),
    ("USDCHF", [(7, 17), (0, 10)], 1.2),
]

PW_LIST  = [4, 6, 8, 10]
DIRS     = [("BOTH", False), ("LONG", True)]
SKIP_MON = [False, True]


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


def run_one(sym, df, session, pw, only_long, skip_monday, spread, cfg_base):
    cfg = copy.deepcopy(cfg_base)
    cfg["account"]["starting_balance"] = 1000
    cfg["session"]["start_hour"] = 0
    cfg["session"]["end_hour"]   = 24
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

    # Analiza anuala — semn de consistenta
    tdf["yr"] = tdf["et"].dt.year
    annual = tdf.groupby("yr")["R"].mean()
    pos_yrs = (annual > 0).sum()
    total_yrs = len(annual)

    return dict(
        n=len(tdf), n_tr=len(train), n_te=len(test),
        e_tr=train["R"].mean() if len(train) >= 5 else float("nan"),
        e_te=test["R"].mean()  if len(test)  >= 5 else float("nan"),
        p_te=ttest_os(test["R"].values),
        freq=freq, dd=maxdd(equity),
        split_time=split_time,
        pos_yrs=pos_yrs, total_yrs=total_yrs,
    )


def main():
    print("=" * 80)
    print("  NZD/AUD DEEP SCAN — 8 ani date (2018-2026)")
    print("  Grid: PW 4/6/8/10 × BOTH/LONG × skipMon × sesiune = 32/simbol")
    print("=" * 80)

    with open(CONFIG, encoding="utf-8") as f:
        cfg_base = json.load(f)
    source = CsvDataSource(DATA_DIR)

    all_candidates = []

    for sym, sessions, spread in INSTRUMENTS:
        f15 = os.path.join(DATA_DIR, f"{sym}_M15.csv")
        f30 = os.path.join(DATA_DIR, f"{sym}_M30.csv")
        if not os.path.exists(f15) or not os.path.exists(f30):
            print(f"\n  {sym}: date lipsa — SKIP")
            continue

        try:
            t0   = pd.read_csv(f15, usecols=["time"], nrows=1)["time"].iloc[0]
            t1   = pd.read_csv(f15, usecols=["time"]).tail(1)["time"].iloc[0]
            rows = sum(1 for _ in open(f15)) - 1
            yrs  = (pd.Timestamp(t1) - pd.Timestamp(t0)).days / 365.25
        except Exception:
            yrs, rows = 0, 0

        print(f"\n{'─'*80}")
        print(f"  {sym}  ({yrs:.1f} ani, {rows:,} bare M15)  spread={spread}p")
        print(f"{'─'*80}")

        cfg_prep = copy.deepcopy(cfg_base)
        cfg_prep["account"]["starting_balance"] = 1000
        cfg_prep["session"]["start_hour"] = 0
        cfg_prep["session"]["end_hour"]   = 24
        cfg_prep["risk_management"]["max_consecutive_losses"] = 9999
        try:
            df_sym = prepare_symbol(source, sym, cfg_prep)
        except Exception as e:
            print(f"  {sym}: eroare prepare_symbol — SKIP")
            continue

        if df_sym is None or len(df_sym) < 300:
            print(f"  {sym}: date insuficiente — SKIP")
            continue

        best = None

        for sess in sessions:
            sess_str = f"{sess[0]:02d}-{sess[1]:02d}h"
            print(f"\n  Sesiune: {sess_str}")

            for pw in PW_LIST:
                for dlbl, only_long in DIRS:
                    for sm in SKIP_MON:
                        sm_s = "skipMon" if sm else "allDay"
                        r = run_one(sym, df_sym, sess, pw, only_long, sm, spread, cfg_base)
                        if r is None or r["n"] < 20:
                            continue

                        p_s  = f"{r['p_te']:.3f}{sig(r['p_te'])}" if r["p_te"] else "  N/A"
                        e_s  = f"{r['e_te']:+.3f}" if not np.isnan(r["e_te"]) else "  N/A"
                        e_r  = f"{r['e_tr']:+.3f}" if not np.isnan(r["e_tr"]) else "  N/A"
                        spl  = r["split_time"].strftime("%Y-%m")
                        ann  = f"{r['pos_yrs']}/{r['total_yrs']}yr+"

                        flag = ""
                        is_edge = (
                            r["p_te"] and r["p_te"] < 0.10
                            and not np.isnan(r["e_te"]) and r["e_te"] > 0
                            and not np.isnan(r["e_tr"]) and r["e_tr"] > -0.05
                            and r["freq"] >= 0.4
                        )
                        if is_edge:
                            flag = "  *** EDGE" if r["p_te"] < 0.05 else "  * edge"

                        print(f"    PW={pw:2d} {dlbl:<4} {sm_s:<8} | "
                              f"n={r['n']:4d} train={e_r}R test={e_s}R "
                              f"p={p_s} {r['freq']:.1f}/s DD={r['dd']:+.0f}% "
                              f"[{spl}] {ann}{flag}")

                        if is_edge:
                            all_candidates.append(dict(
                                sym=sym, sess=sess_str, pw=pw, dir=dlbl,
                                skip_mon=sm, **r
                            ))

                        e_te_v = r["e_te"] if not np.isnan(r["e_te"]) else float("-inf")
                        if best is None or e_te_v > (
                            best["e_te"] if not np.isnan(best.get("e_te", float("nan"))) else float("-inf")
                        ):
                            best = dict(sess=sess_str, pw=pw, dir=dlbl, skip_mon=sm, **r)

        if best and not np.isnan(best.get("e_te", float("nan"))):
            sm_s = "skipMon" if best["skip_mon"] else "allDay"
            p_s  = f"{best['p_te']:.3f}{sig(best['p_te'])}" if best["p_te"] else "N/A"
            print(f"\n  >> {sym} CEL MAI BUN: {best['sess']} PW={best['pw']} "
                  f"{best['dir']} {sm_s} | test={best['e_te']:+.3f}R "
                  f"p={p_s} {best['freq']:.1f}/s DD={best['dd']:+.0f}%")

    print("\n" + "=" * 80)
    print("  SUMAR — NZD/AUD cu edge (p<0.10, exp>0, train>-0.05, >=0.4/s)")
    print("=" * 80)
    if not all_candidates:
        print("  Niciun instrument cu edge confirmat.")
    else:
        all_candidates.sort(key=lambda x: x["e_te"], reverse=True)
        print(f"  {'Sym':<8} {'Ses':>6} {'PW':>3} {'Dir':<5} {'SkipM':>6} "
              f"{'Train':>8} {'Test':>8} {'p':>8} {'Freq':>5} {'Ann':>8}")
        print("  " + "-" * 72)
        for c in all_candidates:
            p_s  = f"{c['p_te']:.3f}{sig(c['p_te'])}"
            e_tr = f"{c['e_tr']:>+8.3f}R" if not np.isnan(c["e_tr"]) else "     N/A"
            sm_s = "skipMon" if c["skip_mon"] else "allDay"
            print(f"  {c['sym']:<8} {c['sess']:>6} PW={c['pw']:2d} {c['dir']:<5} {sm_s:<8} "
                  f"{e_tr} {c['e_te']:>+8.3f}R {p_s:>8} {c['freq']:>4.1f}/s "
                  f"{c['pos_yrs']}/{c['total_yrs']}yr+")


if __name__ == "__main__":
    main()
