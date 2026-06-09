"""
Session 4 — Optimizare ore GER40 + US30 (LONG only, $400)
==========================================================
Acelasi approach ca btc_session_optimize.py:
Configuratii cu rationale economic, NU grid-search exhaustiv.

GER40 ipoteza: pullback-urile "curate" apar in fereastra EU pura,
  inainte ca fluxurile US sa deranjeze structura (dupa 14h UTC).
  Pranzul EU (12-13h) si deschiderea US (14-16h) sunt candidate de skip.

US30 ipoteza: prima ora NYSE (14-15h) si ultima ora (20-21h) au cel
  mai mult noise. Luni are gap-uri frecvente pe indici US.

Criteriu: Exp(test) maxim cu p(test) < 0.10 si DD > -60%.
Capital: $400 (verificat viabil pentru ambele instrumente la pip_val ~$1/pt/lot).

Rulare: python scripts/research/session4_optimize.py
"""

import os, sys, copy, json, math, warnings
import numpy as np
import pandas as pd
from scipy import stats as _stats
warnings.filterwarnings("ignore")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol
from engine.portfolio import run_portfolio

START_BALANCE = 400


# =============================================================================
# CONFIGURATII DE TESTAT
# =============================================================================

GER40_CONFIGS = [
    # label,               session,  skip_hours,           skip_mon
    ("Baseline 07-16h",    (7, 16),  (),                   False),
    ("Skip EU-open 08-16h",(8, 16),  (),                   False),
    ("Skip US-flow 07-14h",(7, 14),  (),                   False),
    ("EU-pura 08-14h",     (8, 14),  (),                   False),
    ("Matinal 09-14h",     (9, 14),  (),                   False),
    ("EU-pura 08-14h sMon",(8, 14),  (),                   True),
    ("08-16h skip lunch",  (8, 16),  (12, 13),             False),
    ("07-14h skip lunch",  (7, 14),  (12, 13),             False),
    ("08-14h sMon sLunch", (8, 14),  (12, 13),             True),
    ("07-13h (preNYSE)",   (7, 13),  (),                   False),
    ("08-13h strict",      (8, 13),  (),                   False),
    ("08-16h skip 14-15h", (8, 16),  (14, 15),             False),
]

US30_CONFIGS = [
    # label,               session,  skip_hours,           skip_mon
    ("Baseline 14-21h",    (14, 21), (),                   False),
    ("Skip pre-open 15-21h",(15, 21),(),                   False),
    ("Skip last-h 14-20h", (14, 20), (),                   False),
    ("Core 15-20h",        (15, 20), (),                   False),
    ("Tight 15-19h",       (15, 19), (),                   False),
    ("14-21h skipMon",     (14, 21), (),                   True),
    ("15-20h skipMon",     (15, 20), (),                   True),
    ("15-19h skipMon",     (15, 19), (),                   True),
    ("14-21h skip 20h",    (14, 21), (20,),                False),
    ("14-21h skip 14h",    (14, 21), (14,),                False),
    ("15-20h skip 19h",    (15, 20), (19,),                False),
    ("16-20h (midday US)", (16, 20), (),                   False),
]


# =============================================================================
# HELPERS
# =============================================================================

def p_onesided(arr):
    a = np.asarray(arr, float)
    n = len(a)
    if n < 10: return None
    s = a.std(ddof=1)
    if s < 1e-12: return None
    t = a.mean() / (s / math.sqrt(n))
    return round(1 - _stats.t.cdf(t, df=n - 1), 4)

def sig(p):
    if p is None: return ""
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.10 else ""

def maxdd(equity_list):
    eq = np.array([e["balance"] for e in equity_list], float)
    pk = np.maximum.accumulate(eq)
    return round(((eq - pk) / np.where(pk > 0, pk, 1)).min() * 100, 1)

def annual_breakdown(trades_df, split_time):
    lines = []
    for yr, grp in trades_df.groupby("year"):
        n  = len(grp)
        exp = grp["R"].mean()
        wr  = (grp["outcome"] == "win").sum() / n * 100
        era = "TEST" if grp["entry_t"].iloc[0] >= split_time else "train"
        lines.append(f"    {yr}: {n:4d}t  wr={wr:.0f}%  exp={exp:+.4f}R  [{era}]")
    return "\n".join(lines)


# =============================================================================
# RUN BACKTEST
# =============================================================================

def run_config(sym, spread_pips, session, skip_hours, skip_mon, pw,
               cfg_base, source):
    sh, eh = session
    cfg = copy.deepcopy(cfg_base)
    cfg["account"]["starting_balance"]               = START_BALANCE
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
        "start_balance":          START_BALANCE,
        "expire_bars":            4,
        "pullback_window":        pw,
        "depth_range":            None,
        "skip_monday":            skip_mon,
        "skip_hours":             skip_hours,
        "atr_max_pips":           {},
        "max_day_consec_losses":  3,
        "corr_pairs":             {},
        "only_long":              True,
        "max_pos_per_symbol":     1,
        "symbol_sessions":        {sym: (sh, eh)},
        "symbol_skip_hours":      {},
    }

    trades, equity, balance, _, _, _, split_time = \
        run_portfolio({sym: df}, cfg, params)

    if not trades:
        return None

    tdf = pd.DataFrame(trades)
    tdf["R"]       = tdf["pnl_usd"] / tdf["risk_usd"]
    tdf["entry_t"] = pd.to_datetime(tdf["time"])
    tdf["year"]    = tdf["entry_t"].dt.year
    span = (tdf["entry_t"].max() - tdf["entry_t"].min()).days

    train = tdf[tdf["entry_t"] <  split_time]
    test  = tdf[tdf["entry_t"] >= split_time]

    return {
        "n":         len(tdf),
        "n_train":   len(train),
        "n_test":    len(test),
        "exp_all":   round(tdf["R"].mean(), 4),
        "exp_train": round(train["R"].mean(), 4) if len(train) else 0.0,
        "exp_test":  round(test["R"].mean(),  4) if len(test)  else 0.0,
        "p_train":   p_onesided(train["R"].values) if len(train) >= 10 else None,
        "p_test":    p_onesided(test["R"].values)  if len(test)  >= 10 else None,
        "dd":        maxdd(equity),
        "freq":      round(len(tdf) / max(span / 7, 1), 1),
        "wr":        round((tdf["outcome"] == "win").sum() / len(tdf) * 100, 1),
        "bal":       round(balance, 0),
        "ret":       round((balance - START_BALANCE) / START_BALANCE * 100, 1),
        "split":     split_time,
        "tdf":       tdf,
    }


def scan_instrument(sym, spread_pips, configs, label, cfg_base, source):
    """Scaneaza toate configuratiile pentru un instrument, returneaza clasamentul."""
    sep = "=" * 76
    print(f"\n{sep}")
    print(f"  {label}  |  LONG only  |  ${START_BALANCE}  |  spread={spread_pips}pip")
    print(sep)
    print(f"  {'Config':<26} {'PW':>2}  {'N':>4}  {'Exp(tr)':>8}  {'Exp(te)':>9}  "
          f"{'p_test':>9}  {'DD':>7}  {'T/wk':>5}")
    print(f"  {'-'*74}")

    results = []
    for label_cfg, session, skip_h, skip_m in configs:
        for pw in [8, 6]:
            r = run_config(sym, spread_pips, session, skip_h, skip_m, pw, cfg_base, source)
            if r is None or r["n"] < 20:
                continue
            p_s = f"{r['p_test']:.4f}{sig(r['p_test'])}" if r["p_test"] is not None else "     N/A"
            skip_note = f"skip{list(skip_h)}" if skip_h else ""
            mon_note  = "sMon" if skip_m else ""
            tag = f"{label_cfg} {skip_note}{mon_note}".strip()
            print(f"  {tag:<26} {pw:>2}  {r['n']:>4}  {r['exp_train']:>+8.4f}  "
                  f"{r['exp_test']:>+9.4f}  {p_s:>9}  {r['dd']:>+6.1f}%  {r['freq']:>4.1f}/w")
            results.append({"label": tag, "pw": pw, "r": r,
                             "session": session, "skip_h": skip_h, "skip_m": skip_m})

    return results


def print_best(sym, results, n_best=3):
    """Afiseaza detaliat primele n_best configuratii dupa Exp(test)."""
    sorted_r = sorted(results, key=lambda x: x["r"]["exp_test"], reverse=True)[:n_best]
    sep = "-" * 64
    print(f"\n  --- TOP {n_best} configuratii {sym} (dupa Exp test) ---")
    for i, item in enumerate(sorted_r):
        r = item["r"]
        p = r["p_test"]
        p_s = f"p={p:.4f}{sig(p)}" if p is not None else "p=N/A"
        print(f"\n  #{i+1}  {item['label']}  PW={item['pw']}")
        print(f"  N={r['n']}  WR={r['wr']:.1f}%  Freq={r['freq']:.1f}/sapt  "
              f"DD={r['dd']:+.1f}%  ${START_BALANCE}->${r['bal']:.0f} ({r['ret']:+.1f}%)")
        print(f"  TRAIN ({r['n_train']}t): {r['exp_train']:+.4f}R  "
              f"p={r['p_train']:.4f}{sig(r['p_train'])}" if r["p_train"] else
              f"  TRAIN ({r['n_train']}t): {r['exp_train']:+.4f}R")
        print(f"  TEST  ({r['n_test']}t): {r['exp_test']:+.4f}R  {p_s}")
        print(f"  Split: {r['split'].date()}")
        print(f"  Annual:")
        print(annual_breakdown(r["tdf"], r["split"]))
        print(f"  {sep}")


# =============================================================================
# COMBINED SESSION TEST
# =============================================================================

def test_combined(best_ger40, best_us30, cfg_base, source):
    """Testeaza GER40 + US30 impreuna intr-o singura sesiune."""
    sep = "=" * 76
    print(f"\n{sep}")
    print(f"  COMBINED SESSION — GER40 + US30 (LONG only, ${START_BALANCE})")
    print(f"  GER40: {best_ger40['session'][0]}-{best_ger40['session'][1]}h UTC")
    print(f"  US30:  {best_us30['session'][0]}-{best_us30['session'][1]}h UTC")
    print(sep)

    cfg = copy.deepcopy(cfg_base)
    cfg["account"]["starting_balance"]               = START_BALANCE
    cfg["session"]["start_hour"]                     = 0
    cfg["session"]["end_hour"]                       = 24
    cfg["risk_management"]["max_trades_per_day"]     = 5
    cfg["risk_management"]["max_consecutive_losses"] = 9999

    data = {}
    for sym in ["GER40", "US30"]:
        try:
            data[sym] = prepare_symbol(source, sym, cfg)
        except FileNotFoundError:
            print(f"    {sym}: lipsesc datele")

    if len(data) < 2:
        return

    for pw in [8, 6]:
        params = {
            "spread_pips":  {"GER40": 1.5, "US30": 3.0},
            "leverage":     30,
            "start_balance": START_BALANCE,
            "expire_bars":  4,
            "pullback_window": pw,
            "depth_range":  None,
            "skip_monday":  best_us30["skip_m"],   # US30 skipMon
            "skip_hours":   best_ger40["skip_h"],  # GER40 skip_hours
            "atr_max_pips": {},
            "max_day_consec_losses": 3,
            "corr_pairs":   {},
            "only_long":    True,
            "max_pos_per_symbol": 1,
            "symbol_sessions": {
                "GER40": best_ger40["session"],
                "US30":  best_us30["session"],
            },
            "symbol_skip_hours": {},
        }

        trades, equity, balance, _, _, _, split = \
            run_portfolio(data, cfg, params)

        if not trades:
            print(f"  PW={pw}: 0 tranzactii")
            continue

        tdf = pd.DataFrame(trades)
        tdf["R"]       = tdf["pnl_usd"] / tdf["risk_usd"]
        tdf["entry_t"] = pd.to_datetime(tdf["time"])
        tdf["year"]    = tdf["entry_t"].dt.year
        span           = (tdf["entry_t"].max() - tdf["entry_t"].min()).days

        train = tdf[tdf["entry_t"] <  split]
        test  = tdf[tdf["entry_t"] >= split]

        p_test = p_onesided(test["R"].values)  if len(test)  >= 10 else None
        p_tr   = p_onesided(train["R"].values) if len(train) >= 10 else None
        dd     = maxdd(equity)
        freq   = round(len(tdf) / max(span / 7, 1), 1)
        p_s    = f"p={p_test:.4f}{sig(p_test)}" if p_test is not None else "p=N/A"

        wins = (tdf["outcome"] == "win").sum()
        print(f"\n  PW={pw}  N={len(tdf)}  WR={wins/len(tdf)*100:.1f}%  "
              f"freq={freq:.1f}/sapt  DD={dd:+.1f}%")
        print(f"  TRAIN ({len(train)}t): {train['R'].mean():+.4f}R  "
              f"p={p_tr:.4f}{sig(p_tr)}" if p_tr else
              f"  TRAIN: {train['R'].mean():+.4f}R  p=N/A")
        print(f"  TEST  ({len(test)}t):  {test['R'].mean():+.4f}R  {p_s}")
        print(f"  ${START_BALANCE} -> ${balance:.0f}  "
              f"({(balance-START_BALANCE)/START_BALANCE*100:+.1f}%)")
        print(f"  Split: {split.date()}")

        print(f"  Annual:")
        for yr, grp in tdf.groupby("year"):
            n_yr = len(grp)
            e_yr = grp["R"].mean()
            w_yr = (grp["outcome"] == "win").sum() / n_yr * 100
            era  = "TEST" if grp["entry_t"].iloc[0] >= split else "train"
            ger_n = len(grp[grp["symbol"]=="GER40"])
            us_n  = len(grp[grp["symbol"]=="US30"])
            print(f"    {yr}: {n_yr:4d}t (DAX:{ger_n} DOW:{us_n})  "
                  f"wr={w_yr:.0f}%  exp={e_yr:+.4f}R  [{era}]")

        print(f"\n  Per simbol:")
        for sym_ in ["GER40", "US30"]:
            sub = tdf[tdf["symbol"] == sym_]
            if len(sub):
                w_ = (sub["outcome"] == "win").sum()
                print(f"    {sym_:<8} {len(sub):4d}t  wr={w_/len(sub)*100:.0f}%  "
                      f"exp={sub['R'].mean():+.4f}R")


# =============================================================================
# MAIN
# =============================================================================

def main():
    sep = "=" * 76
    print(sep)
    print(f"  SESSION 4 OPTIMIZE — GER40 + US30, LONG only, ${START_BALANCE}")
    print(sep)
    print("  Criterii viabilitate: Exp(test)>0, p<0.10, DD>-60%\n")

    with open(CONFIG, encoding="utf-8") as f:
        cfg_base = json.load(f)
    source = CsvDataSource(DATA_DIR)

    # ── GER40 ──────────────────────────────────────────────────────────────────
    ger40_results = scan_instrument(
        "GER40", 1.5, GER40_CONFIGS,
        "DAX (GER40) — EU equity session", cfg_base, source
    )
    ger40_sorted = sorted(ger40_results, key=lambda x: x["r"]["exp_test"], reverse=True)
    print_best("GER40", ger40_results, n_best=3)

    # ── US30 ───────────────────────────────────────────────────────────────────
    us30_results = scan_instrument(
        "US30", 3.0, US30_CONFIGS,
        "Dow Jones (US30) — US equity session", cfg_base, source
    )
    us30_sorted = sorted(us30_results, key=lambda x: x["r"]["exp_test"], reverse=True)
    print_best("US30", us30_results, n_best=3)

    # ── COMBINED ───────────────────────────────────────────────────────────────
    if ger40_sorted and us30_sorted:
        best_ger40 = ger40_sorted[0]
        best_us30  = us30_sorted[0]
        test_combined(best_ger40, best_us30, cfg_base, source)

    # ── VERDICT ────────────────────────────────────────────────────────────────
    print(f"\n{sep}")
    print("  VERDICT FINAL")
    print(sep)

    # Bonferroni: nr total configuratii testate
    n_total = len(ger40_results) + len(us30_results)
    print(f"\n  Configuratii testate: {n_total}  (Bonferroni factor: {n_total})")

    viable = [r for r in ger40_results + us30_results
              if r["r"]["exp_test"] > 0
              and r["r"]["p_test"] is not None
              and r["r"]["p_test"] < 0.10
              and r["r"]["dd"] > -60]

    if viable:
        print(f"\n  VIABILE (p<0.10 inainte de Bonferroni):")
        for r in sorted(viable, key=lambda x: x["r"]["exp_test"], reverse=True):
            p = r["r"]["p_test"]
            p_corr = round(p * n_total, 4) if p else None
            corr_sig = sig(p_corr) if p_corr else ""
            print(f"    {r['label']:<30} PW={r['pw']}  "
                  f"exp_test={r['r']['exp_test']:+.4f}R  "
                  f"p={p:.4f}{sig(p)}  p_corr={p_corr:.4f}{corr_sig}")
    else:
        print("\n  Nicio configuratie nu trece pragul p<0.10.")
        # Cel mai bun per instrument
        if ger40_sorted:
            top_g = ger40_sorted[0]
            print(f"  Cel mai bun GER40: {top_g['label']} PW={top_g['pw']}  "
                  f"exp_test={top_g['r']['exp_test']:+.4f}R  p={top_g['r']['p_test']:.4f}")
        if us30_sorted:
            top_u = us30_sorted[0]
            print(f"  Cel mai bun US30:  {top_u['label']} PW={top_u['pw']}  "
                  f"exp_test={top_u['r']['exp_test']:+.4f}R  p={top_u['r']['p_test']:.4f}")

    print(f"\n{sep}\n")


if __name__ == "__main__":
    main()
