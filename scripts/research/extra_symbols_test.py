"""
Test simboluri extra — extindere portofoliu pentru 5-10 trades/saptamana
=========================================================================
Testeaza individual 9 perechi suplimentare, apoi combina cele mai bune
intr-un portofoliu extins alaturi de EURUSD+GBPUSD+EURJPY.

Logica: fiecare pereche adauga ~0.5-1.0 trades/saptamana.
Target: 5-10/saptamana = necesita 7-14 perechi (sau M5 + BOTH directii).

Swap-urile forex extra sunt ESTIMATE — de verificat in MT5 inainte de live.

Rulare: python extra_symbols_test.py
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

# Perechi de baza (validate)
CORE_SYMBOLS = ["EURUSD", "GBPUSD", "EURJPY"]

# Perechi extra de testat (toate au M15+M30 in /data)
EXTRA_SYMBOLS = ["AUDUSD", "NZDUSD", "USDCAD", "USDCHF",
                 "AUDJPY", "GBPJPY", "CADJPY", "CHFJPY", "NZDJPY"]

# Spread-uri estimate ECN (pips)
SPREAD_PIPS = {
    "EURUSD": 0.5, "GBPUSD": 0.8, "EURJPY": 1.5,
    "AUDUSD": 0.8, "NZDUSD": 1.0, "USDCAD": 0.8, "USDCHF": 0.8,
    "AUDJPY": 1.5, "GBPJPY": 2.0, "CADJPY": 1.5, "CHFJPY": 1.5, "NZDJPY": 1.5,
}

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
    "corr_pairs":            {},          # se seteaza per-test
    "only_long":             True,
    "max_pos_per_symbol":    1,
    "symbol_sessions":       {},
    "symbol_skip_hours":     {},
}

# Perechi corelate (pentru filtrul de corr in portofoliu combinat)
# Nu luam pozitii in aceeasi directie pe perechi puternic corelate
CORR_PAIRS_EXTENDED = {
    "EURUSD": "GBPUSD", "GBPUSD": "EURUSD",
    "AUDUSD": "NZDUSD", "NZDUSD": "AUDUSD",
    "AUDJPY": "NZDJPY", "NZDJPY": "AUDJPY",
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

    # swap impact
    swap_total = df["swap"].sum() if "swap" in df.columns else 0.0
    swap_r     = swap_total / (df["risk_usd"].mean() * max(len(df), 1))

    return {"label": label, "trades": len(df), "wr": wr, "exp": exp, "dd": dd,
            "test_exp": test_exp, "test_n": test_n, "trades_wk": trades_wk,
            "elapsed": elapsed, "balance": balance,
            "swap_total": swap_total, "swap_r": swap_r}


def _header(title):
    print(f"\n{'='*105}")
    print(f"  {title}")
    print("="*105)
    print(f"  {'Label':<45} {'Tot':>5} {'WR':>6} {'Exp/R':>7} {'TestR':>7} {'TestN':>6} "
          f"{'T/wk':>6} {'DD':>7} {'SwapR':>7}")
    print(f"  {'-'*103}")


def _row(r):
    if r.get("error"):
        print(f"  {r['label']:<45}  EROARE: {r['error']}")
        return
    if r["trades"] == 0:
        print(f"  {r['label']:<45}   0 trades  ({r['elapsed']:.1f}s)")
        return
    swap_r = r.get("swap_r", 0.0)
    print(f"  {r['label']:<45} {r['trades']:>5} {r['wr']:>5.1f}%"
          f" {r['exp']:>+7.3f} {r['test_exp']:>+7.3f} {r['test_n']:>6}"
          f" {r['trades_wk']:>5.1f}/w {r['dd']:>+6.1f}% {swap_r:>+7.3f}R")


def _best_symbols(ind_results, direction="LONG"):
    """Returneaza simbolurile cu test_exp > 0 si min 5 test trades."""
    return [r for r in ind_results
            if r.get("test_exp", -999) > 0
            and r.get("test_n", 0) >= 5
            and direction in r["label"]
            and not r.get("error")]


def main():
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)

    # cfg cu RSI simetric pentru SELL
    cfg_sym = copy.deepcopy(cfg)
    cfg_sym["optional_criteria"]["rsi"]["sell_max"] = 60

    source = CsvDataSource(DATA_DIR)

    print("Incarc date M15/M30 pentru toate perechile...")
    all_data = {}
    for s in CORE_SYMBOLS + EXTRA_SYMBOLS:
        try:
            all_data[s] = prepare_symbol(source, s, cfg)
            print(f"  {s}: {len(all_data[s])} bare M15")
        except FileNotFoundError:
            print(f"  {s}: LIPSESC datele — sare peste")

    available = list(all_data.keys())
    extra_avail = [s for s in EXTRA_SYMBOLS if s in all_data]
    core_avail  = [s for s in CORE_SYMBOLS  if s in all_data]

    ind_results = []

    # =========================================================================
    # 1. TEST INDIVIDUAL — fiecare pereche extra, ONLY_LONG=True, PW=8
    # =========================================================================
    _header("1 — INDIVIDUAL: ONLY_LONG=True, M15, PW=8 (swap inclus)")
    for s in extra_avail:
        data_single = {s: all_data[s]}
        r = _run(data_single, cfg, f"{s} LONG PW=8",
                 {**BASE_PARAMS, "only_long": True, "corr_pairs": {}})
        _row(r)
        ind_results.append(r)

    # =========================================================================
    # 2. TEST INDIVIDUAL — fiecare pereche extra, ONLY_LONG=False, RSI sim
    # =========================================================================
    _header("2 — INDIVIDUAL: ONLY_LONG=False, M15, PW=8, RSI_sell=60")
    for s in extra_avail:
        data_single = {s: all_data[s]}
        r = _run(data_single, cfg_sym, f"{s} BOTH PW=8",
                 {**BASE_PARAMS, "only_long": False, "corr_pairs": {}})
        _row(r)
        ind_results.append(r)

    # Selectam perechile cu edge pozitiv
    good_long = [r["label"].split()[0] for r in _best_symbols(ind_results, "LONG")]
    good_both = [r["label"].split()[0] for r in _best_symbols(ind_results, "BOTH")]

    print(f"\n  Perechi cu edge pozitiv (LONG): {good_long}")
    print(f"  Perechi cu edge pozitiv (BOTH): {good_both}")

    # =========================================================================
    # 3. CORE + BEST EXTRA — portofoliu combinat, ONLY_LONG=True
    # =========================================================================
    _header("3 — PORTOFOLIU COMBINAT: core + extra cu edge, ONLY_LONG=True, PW=8")

    combo_results_long = []

    # Baseline core (referinta)
    r = _run({s: all_data[s] for s in core_avail}, cfg,
             f"CORE only ({'+'.join(core_avail)}) LONG",
             {**BASE_PARAMS, "only_long": True,
              "corr_pairs": {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD"}})
    _row(r)
    combo_results_long.append(r)

    # Combina core + fiecare extra individual
    for s in good_long:
        if s in all_data:
            symbols_combo = core_avail + [s]
            data_combo = {x: all_data[x] for x in symbols_combo}
            corr = {k: v for k, v in CORR_PAIRS_EXTENDED.items()
                    if k in symbols_combo and v in symbols_combo}
            r = _run(data_combo, cfg,
                     f"CORE+{s} LONG",
                     {**BASE_PARAMS, "only_long": True, "corr_pairs": corr})
            _row(r)
            combo_results_long.append(r)

    # Adauga top 3 extra simultan
    top3_long = good_long[:3]
    if len(top3_long) >= 2:
        symbols_combo = core_avail + top3_long
        data_combo = {s: all_data[s] for s in symbols_combo if s in all_data}
        corr = {k: v for k, v in CORR_PAIRS_EXTENDED.items()
                if k in data_combo and v in data_combo}
        r = _run(data_combo, cfg,
                 f"CORE+{'+'.join(top3_long)} LONG",
                 {**BASE_PARAMS, "only_long": True, "corr_pairs": corr})
        _row(r)
        combo_results_long.append(r)

    # =========================================================================
    # 4. PORTOFOLIU COMBINAT — ONLY_LONG=False, RSI simetric
    # =========================================================================
    _header("4 — PORTOFOLIU COMBINAT: core + extra cu edge, ONLY_LONG=False, RSI_sym, PW=8")

    combo_results_both = []

    # Baseline core
    r = _run({s: all_data[s] for s in core_avail}, cfg_sym,
             f"CORE only ({'+'.join(core_avail)}) BOTH",
             {**BASE_PARAMS, "only_long": False,
              "corr_pairs": {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD"}})
    _row(r)
    combo_results_both.append(r)

    for s in good_both:
        if s in all_data:
            symbols_combo = core_avail + [s]
            data_combo = {x: all_data[x] for x in symbols_combo}
            corr = {k: v for k, v in CORR_PAIRS_EXTENDED.items()
                    if k in symbols_combo and v in symbols_combo}
            r = _run(data_combo, cfg_sym,
                     f"CORE+{s} BOTH",
                     {**BASE_PARAMS, "only_long": False, "corr_pairs": corr})
            _row(r)
            combo_results_both.append(r)

    # Top 3 extra simultan
    top3_both = good_both[:3]
    if len(top3_both) >= 2:
        symbols_combo = core_avail + top3_both
        data_combo = {s: all_data[s] for s in symbols_combo if s in all_data}
        corr = {k: v for k, v in CORR_PAIRS_EXTENDED.items()
                if k in data_combo and v in data_combo}
        r = _run(data_combo, cfg_sym,
                 f"CORE+{'+'.join(top3_both)} BOTH",
                 {**BASE_PARAMS, "only_long": False, "corr_pairs": corr})
        _row(r)
        combo_results_both.append(r)

    # =========================================================================
    # 5. SUMAR + RECOMANDARE
    # =========================================================================
    all_combo = combo_results_long + combo_results_both
    print(f"\n\n{'='*105}")
    print("  SUMAR — portofolii combinate sortate dupa trades/saptamana")
    print("="*105)
    print(f"  {'Label':<45} {'Tot':>5} {'WR':>6} {'Exp/R':>7} {'TestR':>7} {'TestN':>6} "
          f"{'T/wk':>6} {'DD':>7}")
    print(f"  {'-'*103}")

    sorted_r = sorted([r for r in all_combo if r["trades"] > 0],
                      key=lambda r: r["trades_wk"], reverse=True)
    for r in sorted_r:
        _row(r)

    # Recomandare
    valid = [r for r in all_combo if r.get("test_n", 0) >= 10 and r["trades"] > 0
             and not r.get("error")]
    if valid:
        best_exp  = max(valid, key=lambda r: r["test_exp"])
        best_freq = max([r for r in valid if r.get("test_exp", -999) > 0],
                        key=lambda r: r["trades_wk"], default=None)

        print(f"\n  >>> BEST test_exp : {best_exp['label']}")
        print(f"      {best_exp['test_exp']:+.3f}R test | {best_exp['trades_wk']:.1f}/wk | DD={best_exp['dd']:+.1f}%")
        if best_freq:
            print(f"\n  >>> BEST frecventa: {best_freq['label']}")
            print(f"      {best_freq['test_exp']:+.3f}R test | {best_freq['trades_wk']:.1f}/wk | DD={best_freq['dd']:+.1f}%")

    total_elapsed = sum(r["elapsed"] for r in ind_results + all_combo)
    print(f"\n  Total timp: {total_elapsed:.0f}s ({total_elapsed/60:.1f} min)")
    print("  ATENTIE: swap-urile perechilor extra sunt ESTIMATE.")
    print("           Verifica valorile reale in MT5 inainte de orice decizie live.")


if __name__ == "__main__":
    main()
