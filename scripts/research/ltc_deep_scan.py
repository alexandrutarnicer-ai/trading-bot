"""
LTC (LTCUSD) — scan profund pe 14.6 ani de date
================================================
Cel mai lung dataset crypto. Testeaza sesiuni proprii, nu doar filtrul BTC.
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
from strategy.signals import _INDEX_PIP
from strategy.costs import _INDEX_TICK
from engine.portfolio import run_portfolio

# LTC specs din crypto_specs.json
import json as _json
_specs = _json.load(open(os.path.join(DATA_DIR, "crypto_specs.json")))
_sp = _specs["LTCUSD"]
_INDEX_PIP["LTCUSD"]  = _sp["tick_size"]
_INDEX_TICK["LTCUSD"] = (_sp["tick_size"], _sp["tick_value_usd"])

SPREAD_PIPS = int(_sp.get("spread_ticks", 150))

SESSION_FILTERS = [
    ((), [],       "24/7"),
    ((10,11,12,13,14,19,20,21,22,23), [5], "BTC filter"),
    ((10,11,12,13,14), [5],            "skip EU mid+Sat"),
    ((19,20,21,22,23), [5],            "skip US prime+Sat"),
    ((0,1,2,3,4,5,6),  [],             "skip Asia night"),
    ((10,11,12,13,14), [],             "skip EU mid only"),
    ((19,20,21,22,23), [],             "skip US prime only"),
    ((10,11,12,13,14,19,20,21,22,23), [], "skip EU+US (no Sat skip)"),
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


def run_ltc(df, cfg_base, pw, only_long, skip_hours, skip_weekdays):
    cfg = copy.deepcopy(cfg_base)
    cfg["account"]["starting_balance"] = 300
    cfg["session"]["start_hour"] = 0
    cfg["session"]["end_hour"] = 24
    cfg["risk_management"]["max_consecutive_losses"] = 9999

    params = {
        "spread_pips":           {"LTCUSD": SPREAD_PIPS},
        "leverage":              30,
        "start_balance":         300,
        "expire_bars":           4,
        "pullback_window":       pw,
        "depth_range":           None,
        "skip_monday":           False,
        "skip_hours":            skip_hours,
        "skip_weekdays":         skip_weekdays,
        "atr_max_pips":          {},
        "max_day_consec_losses": 3,
        "corr_pairs":            {},
        "only_long":             only_long,
        "max_pos_per_symbol":    1,
        "symbol_sessions":       {},
        "symbol_skip_hours":     {},
    }

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            trades, equity, balance, _, _, halted, split_time = \
                run_portfolio({"LTCUSD": df}, cfg, params)
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
    print("  LTCUSD — scan profund  (14.6 ani de date)")
    print(f"  Spread: {SPREAD_PIPS} ticks")
    print("=" * 76)

    with open(CONFIG, encoding="utf-8") as f:
        cfg_base = json.load(f)
    source = CsvDataSource(DATA_DIR)

    # prepare_symbol o singura data (evita reloading 64x)
    cfg_prep = copy.deepcopy(cfg_base)
    cfg_prep["account"]["starting_balance"] = 300
    cfg_prep["session"]["start_hour"] = 0
    cfg_prep["session"]["end_hour"] = 24
    cfg_prep["risk_management"]["max_consecutive_losses"] = 9999
    try:
        df = prepare_symbol(source, "LTCUSD", cfg_prep)
    except Exception as e:
        print(f"EROARE prepare_symbol: {e}"); return
    if df is None or len(df) < 500:
        print("Date insuficiente LTCUSD"); return
    print(f"  Date incarcate: {len(df)} bare")

    best = None
    candidates = []

    for filt_hours, filt_days, filt_lbl in SESSION_FILTERS:
        print(f"\n  Filtru: {filt_lbl}")
        print(f"  {'Config':<26} {'n':>4} {'train':>8} {'test':>8} {'p_test':>8} {'freq':>5} {'DD':>6}")

        for pw in PW_LIST:
            for dlbl, only_long in DIRS:
                r = run_ltc(df, cfg_base, pw, only_long, filt_hours, filt_days)
                if r is None or r["n"] < 15: continue

                lbl = f"PW={pw} {dlbl:<4}"
                p_s = f"{r['p_te']:.3f}{sig(r['p_te'])}" if r["p_te"] else "N/A"
                e_s = f"{r['e_te']:+.3f}" if not np.isnan(r["e_te"]) else " N/A"
                e_r = f"{r['e_tr']:+.3f}" if not np.isnan(r["e_tr"]) else " N/A"
                flag = ""
                if r["p_te"] and r["p_te"] < 0.05 and not np.isnan(r["e_te"]) and r["e_te"] > 0:
                    flag = "  *** EDGE"
                elif r["p_te"] and r["p_te"] < 0.10 and not np.isnan(r["e_te"]) and r["e_te"] > 0:
                    flag = "  * edge"

                print(f"  {lbl:<26} {r['n']:>4} {e_r:>8}R {e_s:>8}R {p_s:>8} "
                      f"{r['freq']:>4.1f}/s {r['dd']:>5.0f}%{flag}")

                if (r["p_te"] and r["p_te"] < 0.10 and
                        not np.isnan(r["e_te"]) and r["e_te"] > 0 and r["freq"] >= 0.5):
                    candidates.append(dict(
                        pw=pw, dir=dlbl, filt_lbl=filt_lbl,
                        filt_hours=filt_hours, filt_days=filt_days, **r))

                if best is None or (not np.isnan(r["e_te"]) and
                                     (np.isnan(best["e_te"]) or r["e_te"] > best["e_te"])):
                    best = dict(pw=pw, dir=dlbl, filt_lbl=filt_lbl, **r)

    print("\n" + "=" * 76)
    print("  SUMAR LTCUSD — configuratii cu edge")
    print("=" * 76)
    if not candidates:
        print("  Niciun config cu edge confirmat.")
        if best:
            p_s = f"{best['p_te']:.3f}{sig(best['p_te'])}" if best["p_te"] else "N/A"
            print(f"\n  Cel mai bun totusi: PW={best['pw']} {best['dir']} "
                  f"{best['filt_lbl']} | "
                  f"test={best['e_te']:+.3f}R p={p_s} {best['freq']:.1f}/s DD={best['dd']:.0f}%")
    else:
        candidates.sort(key=lambda x: x["e_te"], reverse=True)
        for c in candidates:
            p_s = f"{c['p_te']:.3f}{sig(c['p_te'])}"
            print(f"  PW={c['pw']} {c['dir']:<4} | {c['filt_lbl']:<35} | "
                  f"train={c['e_tr']:+.3f}R test={c['e_te']:+.3f}R "
                  f"p={p_s} {c['freq']:.1f}/s DD={c['dd']:.0f}%")


if __name__ == "__main__":
    main()
