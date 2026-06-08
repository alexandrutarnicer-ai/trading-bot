"""
Test suite — strategie pullback in trend
==========================================
Testeaza sistematic combinatii de parametri si compara rezultatele.

Sectiuni:
  A   - Baseline (configuratie actuala: M15, ONLY_LONG, PW=8)
  1A  - ONLY_LONG=False, M15, RSI asimetric (actual) vs RSI simetric
  1B  - ONLY_LONG=False, M15, RSI simetric, variatie PULLBACK_WINDOW 4-12
  2A  - ONLY_LONG=True,  M15, variatie PW 10-20
  2B  - ONLY_LONG=False, M15, RSI simetric, variatie PW 10-20
  3A  - M5, ONLY_LONG=True,  variatie PW
  3B  - M5, ONLY_LONG=False, RSI simetric, variatie PW

Nota: M1 data nu exista in /data — testul la 1 minut nu este posibil.
RSI simetric SELL: sell_max=60 (mirror al buy 40-65 in jurul lui 50).

Rulare: python test_suite.py
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
from strategy.preparation import prepare_symbol, prepare_symbol_tf
from engine.portfolio import run_portfolio

SYMBOLS     = ["EURUSD", "GBPUSD", "EURJPY"]
SPREAD_PIPS = {"EURUSD": 0.5, "GBPUSD": 0.8, "EURJPY": 1.5}

BASE_PARAMS = {
    "spread_pips":           SPREAD_PIPS,
    "leverage":              30,
    "start_balance":         1000,
    "expire_bars":           4,
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
        return {"label": label, "trades": 0, "wr": 0.0, "exp": 0.0, "dd": 0.0,
                "test_exp": 0.0, "test_n": 0, "trades_wk": 0.0,
                "elapsed": time.time() - t0, "error": str(e)}

    elapsed = time.time() - t0

    if not trades:
        return {"label": label, "trades": 0, "wr": 0.0, "exp": 0.0, "dd": 0.0,
                "test_exp": 0.0, "test_n": 0, "trades_wk": 0.0, "elapsed": elapsed}

    df = pd.DataFrame(trades)
    df["R"]       = df["pnl_usd"] / df["risk_usd"]
    df["entry_t"] = pd.to_datetime(df["time"])

    wins = (df["outcome"] == "win").sum()
    wr   = wins / len(df) * 100
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
            "elapsed": elapsed, "balance": balance}


def _header(title):
    print(f"\n{'='*100}")
    print(f"  {title}")
    print("="*100)
    print(f"  {'Label':<50} {'Tot':>5} {'WR':>6} {'Exp/R':>7} {'TestR':>7} {'TestN':>6} {'T/wk':>6} {'DD':>7}  {'t':>4}")
    print(f"  {'-'*98}")


def _row(r):
    if r.get("error"):
        print(f"  {r['label']:<50}  EROARE: {r['error']}")
        return
    if r["trades"] == 0:
        print(f"  {r['label']:<50}   0 trades  ({r['elapsed']:.1f}s)")
        return
    print(f"  {r['label']:<50} {r['trades']:>5} {r['wr']:>5.1f}%"
          f" {r['exp']:>+7.3f} {r['test_exp']:>+7.3f} {r['test_n']:>6}"
          f" {r['trades_wk']:>5.1f}/w {r['dd']:>+6.1f}%  {r['elapsed']:>3.0f}s")


def _best(results, min_test_n=15):
    valid = [r for r in results if r.get("test_n", 0) >= min_test_n and r["trades"] > 0 and not r.get("error")]
    if not valid:
        return None
    return max(valid, key=lambda r: r["test_exp"])


def main():
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)

    source = CsvDataSource(DATA_DIR)

    # ---- incarca datele -------------------------------------------------------
    print("Incarc date M15/M30...")
    data_m15 = {}
    for s in SYMBOLS:
        try:
            data_m15[s] = prepare_symbol(source, s, cfg)
            print(f"  {s}: {len(data_m15[s])} bare M15")
        except FileNotFoundError:
            print(f"  {s}: LIPSESC datele M15/M30")

    print("\nIncarc date M5/M15...")
    data_m5 = {}
    for s in SYMBOLS:
        try:
            data_m5[s] = prepare_symbol_tf(source, s, cfg, entry_tf="M5", trend_tf="M15")
            print(f"  {s}: {len(data_m5[s])} bare M5")
        except FileNotFoundError:
            print(f"  {s}: M5 lipseste")

    # cfg cu RSI simetric pentru SELL:
    # buy  RSI: 40-65  →  sell mirror: 35-60  (100-65=35, 100-40=60)
    # Asta face strategia IDENTICA pentru ambele directii (same edge test)
    cfg_sym = copy.deepcopy(cfg)
    cfg_sym["optional_criteria"]["rsi"]["sell_max"] = 60

    all_results = []

    # =========================================================================
    # A — BASELINE
    # =========================================================================
    _header("A — BASELINE: M15, ONLY_LONG=True, PW=8, RSI_sell_max=50 (configuratie actuala)")
    r = _run(data_m15, cfg, "A0 M15 LONG PW=8 RSI_sell=50", {**BASE_PARAMS})
    _row(r)
    all_results.append(r)

    # =========================================================================
    # 1A — ONLY_LONG=False, RSI asimetric vs simetric (PW=8 fix)
    # =========================================================================
    _header("1A — ONLY_LONG=False, M15, PW=8: RSI actual vs RSI simetric (sell_max=60)")

    for label, cfg_v in [
        ("1A-1 M15 BOTH PW=8 RSI_sell=50 (actual)",   cfg),
        ("1A-2 M15 BOTH PW=8 RSI_sell=60 (simetric)",  cfg_sym),
    ]:
        r = _run(data_m15, cfg_v, label, {**BASE_PARAMS, "only_long": False})
        _row(r)
        all_results.append(r)

    # =========================================================================
    # 1B — ONLY_LONG=False, RSI simetric, variatie PW 4-12
    # =========================================================================
    _header("1B — ONLY_LONG=False, M15, RSI_sell=60 (simetric), variatie PW 4-12")

    sec1b = []
    for pw in [4, 5, 6, 7, 8, 9, 10, 12]:
        r = _run(data_m15, cfg_sym, f"1B M15 BOTH PW={pw:2d} RSI_sym",
                 {**BASE_PARAMS, "only_long": False, "pullback_window": pw})
        _row(r)
        all_results.append(r)
        sec1b.append(r)

    b = _best(sec1b)
    if b:
        print(f"\n  >>> BEST 1B: {b['label']}  "
              f"test_exp={b['test_exp']:+.3f}R  {b['trades_wk']:.1f}/wk  DD={b['dd']:+.1f}%")

    # =========================================================================
    # 2A — ONLY_LONG=True, M15, PW mare (10-20)
    # =========================================================================
    _header("2A — ONLY_LONG=True, M15, variatie PW 10-20")

    sec2a = []
    for pw in [10, 12, 13, 14, 15, 16, 18, 20]:
        r = _run(data_m15, cfg, f"2A M15 LONG PW={pw:2d}",
                 {**BASE_PARAMS, "only_long": True, "pullback_window": pw})
        _row(r)
        all_results.append(r)
        sec2a.append(r)

    b = _best(sec2a)
    if b:
        print(f"\n  >>> BEST 2A: {b['label']}  "
              f"test_exp={b['test_exp']:+.3f}R  {b['trades_wk']:.1f}/wk  DD={b['dd']:+.1f}%")

    # =========================================================================
    # 2B — ONLY_LONG=False, M15, RSI simetric, PW mare (10-20)
    # =========================================================================
    _header("2B — ONLY_LONG=False, M15, RSI_sell=60, variatie PW 10-20")

    sec2b = []
    for pw in [10, 12, 13, 14, 15, 16, 18, 20]:
        r = _run(data_m15, cfg_sym, f"2B M15 BOTH PW={pw:2d} RSI_sym",
                 {**BASE_PARAMS, "only_long": False, "pullback_window": pw})
        _row(r)
        all_results.append(r)
        sec2b.append(r)

    b = _best(sec2b)
    if b:
        print(f"\n  >>> BEST 2B: {b['label']}  "
              f"test_exp={b['test_exp']:+.3f}R  {b['trades_wk']:.1f}/wk  DD={b['dd']:+.1f}%")

    # =========================================================================
    # 3A — M5, ONLY_LONG=True, variatie PW
    # =========================================================================
    if data_m5:
        # expire_bars=12 pe M5 = 60 min = echivalent cu expire_bars=4 pe M15
        _header("3A — M5 (trend M15), ONLY_LONG=True, expire=12, variatie PW")

        sec3a = []
        for pw in [6, 8, 10, 12, 16, 20]:
            r = _run(data_m5, cfg, f"3A M5 LONG PW={pw:2d} exp=12",
                     {**BASE_PARAMS, "only_long": True,
                      "pullback_window": pw, "expire_bars": 12})
            _row(r)
            all_results.append(r)
            sec3a.append(r)

        b = _best(sec3a)
        if b:
            print(f"\n  >>> BEST 3A: {b['label']}  "
                  f"test_exp={b['test_exp']:+.3f}R  {b['trades_wk']:.1f}/wk  DD={b['dd']:+.1f}%")

        # =========================================================================
        # 3B — M5, ONLY_LONG=False, RSI simetric, variatie PW
        # =========================================================================
        _header("3B — M5 (trend M15), ONLY_LONG=False, RSI_sell=60, expire=12, variatie PW")

        sec3b = []
        for pw in [6, 8, 10, 12, 16, 20]:
            r = _run(data_m5, cfg_sym, f"3B M5 BOTH PW={pw:2d} RSI_sym exp=12",
                     {**BASE_PARAMS, "only_long": False,
                      "pullback_window": pw, "expire_bars": 12})
            _row(r)
            all_results.append(r)
            sec3b.append(r)

        b = _best(sec3b)
        if b:
            print(f"\n  >>> BEST 3B: {b['label']}  "
                  f"test_exp={b['test_exp']:+.3f}R  {b['trades_wk']:.1f}/wk  DD={b['dd']:+.1f}%")
    else:
        print("\n  (M5 data lipsa — sectiunile 3A/3B sarite)")

    # =========================================================================
    # SUMAR FINAL
    # =========================================================================
    print(f"\n\n{'='*100}")
    print("  SUMAR FINAL — toate testele")
    print("="*100)
    print(f"  {'Label':<50} {'Tot':>5} {'WR':>6} {'Exp/R':>7} {'TestR':>7} {'TestN':>6} {'T/wk':>6} {'DD':>7}")
    print(f"  {'-'*98}")
    for r in all_results:
        _row(r)

    valid = [r for r in all_results if r.get("test_n", 0) >= 15 and r["trades"] > 0 and not r.get("error")]

    if valid:
        print(f"\n\n{'='*100}")
        print("  TOP 5 dupa TEST expectancy (min 15 test trades)")
        print("="*100)
        top5_exp = sorted(valid, key=lambda r: r["test_exp"], reverse=True)[:5]
        for i, r in enumerate(top5_exp, 1):
            print(f"  {i}. {r['label']:<50}  test={r['test_exp']:+.3f}R "
                  f"| {r['trades_wk']:.1f}/wk | DD={r['dd']:+.1f}%")

        print(f"\n  TOP 5 dupa FRECVENTA (test_exp >= +0.05R, min 15 test trades)")
        print("  Target user: 5-10 trades/saptamana")
        freq = [r for r in valid if r.get("test_exp", -999) >= 0.05]
        if freq:
            top5_frq = sorted(freq, key=lambda r: r["trades_wk"], reverse=True)[:5]
            for i, r in enumerate(top5_frq, 1):
                print(f"  {i}. {r['label']:<50}  {r['trades_wk']:.1f}/wk "
                      f"| test={r['test_exp']:+.3f}R | DD={r['dd']:+.1f}%")
        else:
            print("  (niciun test cu test_exp >= +0.05R)")

    total_elapsed = sum(r["elapsed"] for r in all_results)
    print(f"\n  Total timp rulare: {total_elapsed:.0f}s ({total_elapsed/60:.1f} min)")
    print("  Nota: M1 data lipseste din /data — testele la 1 minut nu au putut fi rulate.")
    print("        M5 cu trend M15 = echivalent structural cu M15/M30 (raport 1:3).")


if __name__ == "__main__":
    main()
