"""
Test sesiune asiatica — USDJPY, AUDJPY, NZDJPY
================================================
Testeaza perechile JPY cross/major cu sesiune Tokyo (02:00-10:00 EET).
Date M15 disponibile, swap estimat.

Idee: aceasta sesiune are trendul sau propriu (risk-on/off pe JPY)
si nu se suprapune cu sesiunea EUR (10-18h) deja testata.
Asta ar adauga ~0.5-1.0 trades/saptamana per pereche, complet independent.

Rulare: python asian_session_test.py
"""

import json
import copy
import contextlib
import io
import time
import numpy as np
import pandas as pd

from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol
from engine.portfolio import run_portfolio

# Core forex (sesiune europeana, validat)
CORE_SYMBOLS = ["EURUSD", "GBPUSD", "EURJPY"]
CORE_SESSION = (10, 18)

# Perechi asiatice de testat
ASIAN_SYMBOLS = ["USDJPY", "AUDJPY", "NZDJPY"]
ASIAN_SESSION = (2, 10)   # 02:00-10:00 EET = sesiunea Tokyo

SPREAD_PIPS = {
    "EURUSD": 0.5, "GBPUSD": 0.8, "EURJPY": 1.5,
    "USDJPY": 0.5, "AUDJPY": 1.5, "NZDJPY": 1.5,
}

BASE_PARAMS = {
    "spread_pips":           SPREAD_PIPS,
    "leverage":              30,
    "start_balance":         1000,
    "expire_bars":           4,
    "pullback_window":       8,
    "depth_range":           None,
    "skip_monday":           True,
    "skip_hours":            (),           # sesiunile sunt pe simbol, nu global
    "atr_max_pips":          {"EURUSD": 7.5},
    "max_day_consec_losses": 3,
    "corr_pairs":            {},
    "only_long":             True,
    "max_pos_per_symbol":    1,
    "symbol_sessions":       {},
    "symbol_skip_hours":     {},
}


@contextlib.contextmanager
def _quiet():
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _run(data, cfg, label, params):
    t0 = time.time()
    try:
        with _quiet():
            trades, equity, balance, _, _, _, split_time = run_portfolio(data, cfg, params)
    except Exception as e:
        return {"label": label, "trades": 0, "exp": 0.0, "test_exp": 0.0,
                "test_n": 0, "trades_wk": 0.0, "dd": 0.0,
                "elapsed": time.time() - t0, "error": str(e)}

    elapsed = time.time() - t0
    if not trades:
        return {"label": label, "trades": 0, "exp": 0.0, "test_exp": 0.0,
                "test_n": 0, "trades_wk": 0.0, "dd": 0.0, "elapsed": elapsed}

    df = pd.DataFrame(trades)
    df["R"]       = df["pnl_usd"] / df["risk_usd"]
    df["entry_t"] = pd.to_datetime(df["time"])

    wr   = (df["outcome"] == "win").sum() / len(df) * 100
    exp  = df["R"].mean()

    eqdf = pd.DataFrame(equity).sort_values("time")
    b    = eqdf["balance"].values
    peak = np.maximum.accumulate(b)
    dd   = ((b - peak) / peak).min() * 100

    test_df  = df[df["entry_t"] >= split_time]
    test_exp = test_df["R"].mean() if len(test_df) else 0.0
    test_n   = len(test_df)

    span_days = (df["entry_t"].max() - df["entry_t"].min()).days
    trades_wk = len(df) / max(span_days / 7, 1)

    return {"label": label, "trades": len(df), "wr": wr, "exp": exp, "dd": dd,
            "test_exp": test_exp, "test_n": test_n, "trades_wk": trades_wk,
            "elapsed": elapsed}


def _header(title):
    print(f"\n{'='*100}")
    print(f"  {title}")
    print("="*100)
    print(f"  {'Label':<48} {'Tot':>5} {'WR':>6} {'Exp/R':>7} {'TestR':>7} {'TestN':>6} {'T/wk':>6} {'DD':>7}")
    print(f"  {'-'*98}")


def _row(r):
    if r.get("error"):
        print(f"  {r['label']:<48}  EROARE: {r['error']}")
        return
    if r["trades"] == 0:
        print(f"  {r['label']:<48}   0 trades  ({r['elapsed']:.1f}s)")
        return
    print(f"  {r['label']:<48} {r['trades']:>5} {r['wr']:>5.1f}%"
          f" {r['exp']:>+7.3f} {r['test_exp']:>+7.3f} {r['test_n']:>6}"
          f" {r['trades_wk']:>5.1f}/w {r['dd']:>+6.1f}%")


def main():
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)

    cfg_sym = copy.deepcopy(cfg)
    cfg_sym["optional_criteria"]["rsi"]["sell_max"] = 60

    source = CsvDataSource(DATA_DIR)

    print("Incarc date M15/M30...")
    all_data = {}
    for s in CORE_SYMBOLS + ASIAN_SYMBOLS:
        try:
            all_data[s] = prepare_symbol(source, s, cfg)
            print(f"  {s}: {len(all_data[s])} bare M15")
        except FileNotFoundError:
            print(f"  {s}: LIPSESC datele")

    asian_avail = [s for s in ASIAN_SYMBOLS if s in all_data]
    core_avail  = [s for s in CORE_SYMBOLS  if s in all_data]

    results = []

    # =========================================================================
    # 1. ASIAN individual — ONLY_LONG=True
    # =========================================================================
    _header("1 — INDIVIDUAL ASIAN LONG, sesiune 02-10h EET, PW=8")
    for s in asian_avail:
        r = _run({s: all_data[s]}, cfg, f"{s} LONG asian-session",
                 {**BASE_PARAMS, "only_long": True,
                  "symbol_sessions": {s: ASIAN_SESSION}})
        _row(r)
        results.append(r)

    # =========================================================================
    # 2. ASIAN individual — ONLY_LONG=False
    # =========================================================================
    _header("2 — INDIVIDUAL ASIAN BOTH, sesiune 02-10h EET, PW=8, RSI_sym")
    for s in asian_avail:
        r = _run({s: all_data[s]}, cfg_sym, f"{s} BOTH asian-session",
                 {**BASE_PARAMS, "only_long": False,
                  "symbol_sessions": {s: ASIAN_SESSION}})
        _row(r)
        results.append(r)

    # =========================================================================
    # 3. CORE EUR (european) + ASIAN JPY (Tokyo) — sesiuni separate, fara overlap
    # =========================================================================
    _header("3 — COMBINAT: core EUR sesiune 10-18h + asian JPY sesiune 02-10h")

    combo_results = []
    sym_sessions_combined = {s: CORE_SESSION for s in core_avail}

    # Referinta: core EUR singur (sesiune 10-18)
    r = _run({s: all_data[s] for s in core_avail}, cfg,
             f"CORE EUR only LONG",
             {**BASE_PARAMS, "only_long": True,
              "symbol_sessions": sym_sessions_combined,
              "corr_pairs": {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD"}})
    _row(r)
    combo_results.append(r)

    # Core EUR LONG + fiecare asiatic individual
    for s in asian_avail:
        data_combo = {x: all_data[x] for x in core_avail + [s] if x in all_data}
        sessions = {**sym_sessions_combined, s: ASIAN_SESSION}
        r = _run(data_combo, cfg,
                 f"CORE EUR + {s} LONG",
                 {**BASE_PARAMS, "only_long": True, "symbol_sessions": sessions,
                  "corr_pairs": {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD"}})
        _row(r)
        combo_results.append(r)

    # Core EUR LONG + toate asiaticele
    if len(asian_avail) >= 2:
        data_combo = {s: all_data[s] for s in core_avail + asian_avail if s in all_data}
        sessions = {**sym_sessions_combined,
                    **{s: ASIAN_SESSION for s in asian_avail}}
        r = _run(data_combo, cfg,
                 f"CORE EUR + ALL ASIAN LONG",
                 {**BASE_PARAMS, "only_long": True, "symbol_sessions": sessions,
                  "corr_pairs": {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD"}})
        _row(r)
        combo_results.append(r)

    # =========================================================================
    # 4. COMBINAT BOTH — core EUR BOTH + asian JPY BOTH
    # =========================================================================
    _header("4 — COMBINAT BOTH: core EUR 10-18h + asian JPY 02-10h, RSI_sym")

    # Core BOTH
    r = _run({s: all_data[s] for s in core_avail}, cfg_sym,
             f"CORE EUR only BOTH",
             {**BASE_PARAMS, "only_long": False,
              "symbol_sessions": sym_sessions_combined,
              "corr_pairs": {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD"}})
    _row(r)
    combo_results.append(r)

    # Core BOTH + fiecare asiatic BOTH
    for s in asian_avail:
        data_combo = {x: all_data[x] for x in core_avail + [s] if x in all_data}
        sessions = {**sym_sessions_combined, s: ASIAN_SESSION}
        r = _run(data_combo, cfg_sym,
                 f"CORE EUR + {s} BOTH",
                 {**BASE_PARAMS, "only_long": False, "symbol_sessions": sessions,
                  "corr_pairs": {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD"}})
        _row(r)
        combo_results.append(r)

    # Core BOTH + toate asiaticele BOTH
    if len(asian_avail) >= 2:
        data_combo = {s: all_data[s] for s in core_avail + asian_avail if s in all_data}
        sessions = {**sym_sessions_combined,
                    **{s: ASIAN_SESSION for s in asian_avail}}
        r = _run(data_combo, cfg_sym,
                 f"CORE EUR + ALL ASIAN BOTH",
                 {**BASE_PARAMS, "only_long": False, "symbol_sessions": sessions,
                  "corr_pairs": {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD"}})
        _row(r)
        combo_results.append(r)

    # =========================================================================
    # 5. VARIATIE PW pentru cele mai bune combos
    # =========================================================================
    # Testam PW=4 (cel mai bun pe BOTH din test_suite) pe combinatia completa
    _header("5 — COMBINAT BOTH, PW=4 (best din test_suite): core EUR + all asian")
    if len(asian_avail) >= 2:
        data_combo = {s: all_data[s] for s in core_avail + asian_avail if s in all_data}
        sessions = {**sym_sessions_combined,
                    **{s: ASIAN_SESSION for s in asian_avail}}
        for pw in [4, 6, 8]:
            r = _run(data_combo, cfg_sym,
                     f"ALL BOTH PW={pw}",
                     {**BASE_PARAMS, "only_long": False, "pullback_window": pw,
                      "symbol_sessions": sessions,
                      "corr_pairs": {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD"}})
            _row(r)
            combo_results.append(r)

    # =========================================================================
    # SUMAR
    # =========================================================================
    all_r = results + combo_results
    _header("SUMAR FINAL — sortate dupa trades/saptamana")

    sorted_r = sorted([r for r in all_r if r["trades"] > 0 and not r.get("error")],
                      key=lambda r: r["trades_wk"], reverse=True)
    for r in sorted_r:
        _row(r)

    valid = [r for r in all_r if r.get("test_n", 0) >= 10 and r["trades"] > 0 and not r.get("error")]
    if valid:
        best_exp  = max(valid, key=lambda r: r["test_exp"])
        print(f"\n  >>> BEST test_exp : {best_exp['label']}")
        print(f"      {best_exp['test_exp']:+.3f}R | {best_exp['trades_wk']:.1f}/wk | DD={best_exp['dd']:+.1f}%")

        best_freq = max([r for r in valid if r.get("test_exp", -999) > 0],
                        key=lambda r: r["trades_wk"], default=None)
        if best_freq and best_freq["label"] != best_exp["label"]:
            print(f"\n  >>> BEST frecventa (test_exp>0): {best_freq['label']}")
            print(f"      {best_freq['test_exp']:+.3f}R | {best_freq['trades_wk']:.1f}/wk | DD={best_freq['dd']:+.1f}%")

    elapsed_total = sum(r["elapsed"] for r in all_r)
    print(f"\n  Total timp: {elapsed_total:.0f}s ({elapsed_total/60:.1f} min)")
    print("  Nota: swap-urile AUDJPY/NZDJPY sunt estimate. USDJPY=10.0 validat.")


if __name__ == "__main__":
    main()
