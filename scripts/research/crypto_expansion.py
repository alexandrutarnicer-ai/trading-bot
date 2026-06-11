"""
Crypto Expansion — ETH, SOL, XRP, LTC, ADA, BNB
=================================================
Acelasi filtru de sesiune ca BTC (skip EU mid + US prime + Sambata).
Testa daca alte crypto au edge similar cu BTC (+0.336R p=0.0075).
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

CRYPTO_SPECS_FILE = os.path.join(DATA_DIR, "crypto_specs.json")

# Incarca spec-uri din fisier daca exista
if os.path.exists(CRYPTO_SPECS_FILE):
    with open(CRYPTO_SPECS_FILE) as f:
        _specs = json.load(f)
    for sym, sp in _specs.items():
        _INDEX_PIP[sym]  = sp["tick_size"]
        _INDEX_TICK[sym] = (sp["tick_size"], sp["tick_value_usd"])
else:
    # fallback hardcodat
    for sym in ["ETHUSD","SOLUSD","XRPUSD","LTCUSD","ADAUSD","BNBUSD","BTCUSD"]:
        _INDEX_PIP[sym]  = 0.01
        _INDEX_TICK[sym] = (0.01, 0.01)

SYMBOLS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "ADAUSD", "BNBUSD"]

# Spread-uri estimate (pips = tick_size units)
SPREADS = {
    "BTCUSD":  1200,
    "ETHUSD":   500,
    "SOLUSD":   200,
    "XRPUSD":    30,
    "LTCUSD":   150,
    "ADAUSD":    10,
    "BNBUSD":   200,
}

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

def run_crypto(sym, df, cfg_base, pw, only_long, skip_hours, skip_weekdays):
    cfg = copy.deepcopy(cfg_base)
    cfg["account"]["starting_balance"] = 300
    cfg["session"]["start_hour"] = 0
    cfg["session"]["end_hour"]   = 24
    cfg["risk_management"]["max_consecutive_losses"] = 9999

    params = {
        "spread_pips":           {sym: SPREADS.get(sym, 500)},
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

# Filtre de sesiune de testat (ore UTC de SARIT)
SESSION_FILTERS = [
    # (skip_hours, skip_weekdays, label)
    ((), [],      "24/7 fara filtru"),
    ((10,11,12,13,14,19,20,21,22,23), [5], "BTC filter (skip EU mid+US prime+Sat)"),
    ((10,11,12,13,14), [5],            "skip EU mid + Sat"),
    ((19,20,21,22,23), [5],            "skip US prime + Sat"),
    ((10,11,12,13,14,19,20,21,22,23), [],  "skip EU mid + US prime (fara skip Sat)"),
]

PW_LIST = [6, 8]
DIRS    = [("BOTH", False), ("LONG", True)]

def main():
    print("=" * 76)
    print("  CRYPTO EXPANSION — ETH / SOL / XRP / LTC / ADA / BNB")
    print("  (acelasi filtru de sesiune ca BTC validat +0.336R p=0.0075)")
    print("=" * 76)

    with open(CONFIG, encoding="utf-8") as f:
        cfg_base = json.load(f)
    source = CsvDataSource(DATA_DIR)

    best_per_sym = {}
    all_candidates = []

    for sym in SYMBOLS:
        f15 = os.path.join(DATA_DIR, f"{sym}_M15.csv")
        f30 = os.path.join(DATA_DIR, f"{sym}_M30.csv")
        if not os.path.exists(f15) or not os.path.exists(f30):
            print(f"\n  {sym}: DATE LIPSA — skip")
            continue

        rows = sum(1 for _ in open(f15)) - 1
        try:
            t0 = pd.read_csv(f15, usecols=["time"], nrows=1)["time"].iloc[0]
            t1 = pd.read_csv(f15, usecols=["time"]).tail(1)["time"].iloc[0]
            yrs = (pd.Timestamp(t1) - pd.Timestamp(t0)).days / 365.25
        except Exception:
            yrs = 0

        print(f"\n{'─'*76}")
        print(f"  {sym}  ({yrs:.1f} ani, {rows:,} bare M15)  spread={SPREADS.get(sym,'?')} ticks")
        print(f"{'─'*76}")

        # prepare_symbol o singura data per simbol (costisitor)
        cfg_prep = copy.deepcopy(cfg_base)
        cfg_prep["account"]["starting_balance"] = 300
        cfg_prep["session"]["start_hour"] = 0
        cfg_prep["session"]["end_hour"] = 24
        cfg_prep["risk_management"]["max_consecutive_losses"] = 9999
        try:
            df = prepare_symbol(source, sym, cfg_prep)
        except Exception:
            print(f"  {sym}: eroare prepare_symbol — skip")
            continue
        if df is None or len(df) < 300:
            print(f"  {sym}: date insuficiente — skip")
            continue

        best = None

        for filt_hours, filt_days, filt_lbl in SESSION_FILTERS:
            for pw in PW_LIST:
                for dlbl, only_long in DIRS:
                    r = run_crypto(sym, df, cfg_base, pw, only_long,
                                   filt_hours, filt_days)
                    if r is None or r["n"] < 15: continue

                    p_s = f"{r['p_te']:.3f}{sig(r['p_te'])}" if r["p_te"] else " N/A"
                    e_s = f"{r['e_te']:+.3f}" if not np.isnan(r["e_te"]) else "  N/A"
                    e_r = f"{r['e_tr']:+.3f}" if not np.isnan(r["e_tr"]) else "  N/A"
                    flag = ""
                    if (r["p_te"] and r["p_te"] < 0.10 and
                            not np.isnan(r["e_te"]) and r["e_te"] > 0):
                        flag = "  *** EDGE" if r["p_te"] < 0.05 else "  * edge"

                    print(f"  PW={pw} {dlbl:<4} | {filt_lbl:<38} "
                          f"n={r['n']:3d} train={e_r}R test={e_s}R "
                          f"p={p_s} {r['freq']:.1f}/s DD={r['dd']:.0f}%{flag}")

                    if (r["p_te"] and r["p_te"] < 0.10 and
                            not np.isnan(r["e_te"]) and r["e_te"] > 0 and r["freq"] >= 0.5):
                        all_candidates.append(dict(
                            sym=sym, pw=pw, dir=dlbl,
                            filt_lbl=filt_lbl, filt_hours=filt_hours,
                            filt_days=filt_days, **r))

                    if best is None or (not np.isnan(r["e_te"]) and
                                        (np.isnan(best["e_te"]) or r["e_te"] > best["e_te"])):
                        best = dict(pw=pw, dir=dlbl, filt_lbl=filt_lbl, **r)

        if best and not np.isnan(best["e_te"]):
            p_s = f"{best['p_te']:.3f}{sig(best['p_te'])}" if best["p_te"] else "N/A"
            print(f"\n  >> CEL MAI BUN: PW={best['pw']} {best['dir']} | "
                  f"{best['filt_lbl']} | "
                  f"test={best['e_te']:+.3f}R p={p_s} {best['freq']:.1f}/s DD={best['dd']:.0f}%")
            best_per_sym[sym] = best

    print("\n" + "=" * 76)
    print("  SUMAR FINAL — Crypto cu edge (p_test < 0.10, exp_test > 0, >=0.5/s)")
    print("=" * 76)
    if not all_candidates:
        print("  Niciun crypto suplimentar cu edge confirmat.")
        print("\n  Cel mai bun per simbol:")
        for sym, b in best_per_sym.items():
            p_s = f"{b['p_te']:.3f}{sig(b['p_te'])}" if b["p_te"] else "N/A"
            e_s = f"{b['e_te']:+.3f}" if not np.isnan(b["e_te"]) else "N/A"
            print(f"  {sym}: PW={b['pw']} {b['dir']} | {b['filt_lbl'][:30]} | "
                  f"test={e_s}R p={p_s} {b['freq']:.1f}/s DD={b['dd']:.0f}%")
    else:
        all_candidates.sort(key=lambda x: x["e_te"], reverse=True)
        print(f"  {'Sym':<8} {'PW':>3} {'Dir':<5} {'Filtru':<38} "
              f"{'Train':>8} {'Test':>8} {'p':>8} {'Freq':>5}")
        print("  " + "-" * 76)
        for c in all_candidates:
            p_s = f"{c['p_te']:.3f}{sig(c['p_te'])}"
            print(f"  {c['sym']:<8} PW={c['pw']:2d} {c['dir']:<5} {c['filt_lbl']:<38} "
                  f"{c['e_tr']:>+8.3f}R {c['e_te']:>+8.3f}R {p_s:>8} {c['freq']:>4.1f}/s")

if __name__ == "__main__":
    main()
