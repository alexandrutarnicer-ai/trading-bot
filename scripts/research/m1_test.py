"""
Backtest M1 — strategie pullback pe 1 minut
=============================================
Entry timeframe: M1, trend timeframe: M5.
Structura identica cu M5/M15 (raport 1:5), dar la granularitate mai mica.

CERINTE: ruleaza intai scripts/descarca_m1.py pentru a descarca datele M1.
         Necesita si datele M5 existente (EURUSD_M5.csv etc.)

Testam:
  - ONLY_LONG=True si False
  - PULLBACK_WINDOW 4, 6, 8, 12
  - expire_bars=20 pe M1 = 20 minute (echivalent cu 4 bare M5 = 20 min)

Rulare: python m1_test.py
"""

import json
import copy
import contextlib
import io
import time
import os
import numpy as np
import pandas as pd

from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol_tf
from engine.portfolio import run_portfolio

SYMBOLS     = ["EURUSD", "GBPUSD", "EURJPY"]
SPREAD_PIPS = {"EURUSD": 0.5, "GBPUSD": 0.8, "EURJPY": 1.5}

BASE_PARAMS = {
    "spread_pips":           SPREAD_PIPS,
    "leverage":              30,
    "start_balance":         1000,
    "expire_bars":           20,          # 20 bare M1 = 20 min (vs 4 bare M15 = 60 min)
    "pullback_window":       8,
    "depth_range":           None,
    "skip_monday":           True,
    "skip_hours":            (15, 16),
    "atr_max_pips":          {"EURUSD": 7.5},
    "max_day_consec_losses": 3,
    "corr_pairs":            {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD"},
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
        print(f"  {r['label']:<48}   0 trades")
        return
    print(f"  {r['label']:<48} {r['trades']:>5} {r['wr']:>5.1f}%"
          f" {r['exp']:>+7.3f} {r['test_exp']:>+7.3f} {r['test_n']:>6}"
          f" {r['trades_wk']:>5.1f}/w {r['dd']:>+6.1f}%  ({r['elapsed']:.0f}s)")


def main():
    # Verifica daca datele M1 exista
    missing = [s for s in SYMBOLS
               if not os.path.exists(os.path.join(DATA_DIR, f"{s}_M1.csv"))]
    if missing:
        print(f"EROARE: Lipsesc fisierele M1 pentru: {missing}")
        print("Ruleaza intai:  python scripts/descarca_m1.py")
        return

    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)

    cfg_sym = copy.deepcopy(cfg)
    cfg_sym["optional_criteria"]["rsi"]["sell_max"] = 60

    source = CsvDataSource(DATA_DIR)

    print("Incarc date M1/M5 (poate dura 1-2 minute)...")
    data_m1 = {}
    for s in SYMBOLS:
        try:
            data_m1[s] = prepare_symbol_tf(source, s, cfg, entry_tf="M1", trend_tf="M5")
            print(f"  {s}: {len(data_m1[s]):,} bare M1")
        except FileNotFoundError as e:
            print(f"  {s}: EROARE — {e}")

    if not data_m1:
        print("Nu am date. Abort.")
        return

    results = []

    # =========================================================================
    # ONLY_LONG=True
    # =========================================================================
    _header("M1 (trend M5), ONLY_LONG=True, variatie PW si expire_bars")

    for pw, exp_bars in [(4, 20), (6, 20), (8, 20), (8, 30), (12, 20)]:
        r = _run(data_m1, cfg,
                 f"M1 LONG PW={pw} exp={exp_bars}",
                 {**BASE_PARAMS, "only_long": True,
                  "pullback_window": pw, "expire_bars": exp_bars})
        _row(r)
        results.append(r)

    # =========================================================================
    # ONLY_LONG=False
    # =========================================================================
    _header("M1 (trend M5), ONLY_LONG=False, RSI_sym, variatie PW")

    for pw, exp_bars in [(4, 20), (6, 20), (8, 20), (12, 20)]:
        r = _run(data_m1, cfg_sym,
                 f"M1 BOTH PW={pw} exp={exp_bars} RSI_sym",
                 {**BASE_PARAMS, "only_long": False,
                  "pullback_window": pw, "expire_bars": exp_bars})
        _row(r)
        results.append(r)

    # =========================================================================
    # SUMAR
    # =========================================================================
    _header("SUMAR FINAL M1")
    for r in sorted([r for r in results if r["trades"] > 0],
                    key=lambda r: r["test_exp"], reverse=True):
        _row(r)

    valid = [r for r in results if r.get("test_n", 0) >= 15 and not r.get("error")]
    if valid:
        best = max(valid, key=lambda r: r["test_exp"])
        print(f"\n  >>> BEST M1: {best['label']}")
        print(f"      test={best['test_exp']:+.3f}R | {best['trades_wk']:.1f}/wk | DD={best['dd']:+.1f}%")

    print("\n  Referinta (M15 LONG PW=8, validat): test=+0.375R, 0.9/wk, DD=-50.6%")
    print("  Referinta (M5  LONG PW=6, negativ): test=-0.263R, 2.5/wk, DD=-57.8%")
    print("  Interpretare: daca M1 are test_exp negativ la fel ca M5, timeframe-ul")
    print("  este prea mic pentru aceasta strategie de pullback structural.")


if __name__ == "__main__":
    main()
