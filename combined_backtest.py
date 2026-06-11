"""
Backtest combinat — toate sesiunile live
=========================================
Ruleaza fiecare sesiune independent (capital separat) si afiseaza
un sumar global comparabil.

Adaugare sesiune noua: adauga un dict in SESSIONS si gata.

Rulare: python combined_backtest.py
"""

import os
import json
import numpy as np
import pandas as pd

from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol
from engine.portfolio import run_portfolio

# =============================================================================
# DEFINITIA SESIUNILOR
# Adauga sesiuni noi in aceasta lista — restul se face automat.
# =============================================================================

SESSIONS = [
    # -------------------------------------------------------------------------
    # Session 1 — M15, LONG, 3 piete EUR
    # Backtest ref: TEST +0.375R | 0.9/sapt | DD -50.6%
    # -------------------------------------------------------------------------
    {
        "id":          "S1-M15-LONG",
        "label":       "Session 1 — M15 LONG, 3 piete EUR",
        "symbols":     ["EURUSD", "GBPUSD", "EURJPY"],
        "spread_pips": {"EURUSD": 0.5, "GBPUSD": 0.8, "EURJPY": 1.5},
        "start_balance":         300,
        "leverage":              30,
        "expire_bars":           4,
        "pullback_window":       8,
        "skip_monday":           True,
        "skip_hours":            (15, 16),
        "atr_max_pips":          {"EURUSD": 7.5},
        "max_day_consec_losses": 3,
        "corr_pairs":            {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD"},
        "only_long":             True,
        "max_pos_per_symbol":    1,
        "symbol_sessions":       {},
        "symbol_skip_hours":     {},
        "rsi_sell_max":          50,    # nu e relevant (LONG only)
        "ref_test_exp":          0.375,
        "ref_trades_wk":         0.9,
    },

    # -------------------------------------------------------------------------
    # Session 2 — M15, BOTH, 6 piete EUR + JPY, sesiuni separate
    # Backtest ref: TEST +0.142R | 3.2/sapt | DD -52.9%
    # -------------------------------------------------------------------------
    {
        "id":          "S2-M15-BOTH",
        "label":       "Session 2 — M15 BOTH, 6 piete EUR+JPY",
        "symbols":     ["EURUSD", "GBPUSD", "EURJPY", "USDJPY", "AUDJPY", "NZDJPY"],
        "spread_pips": {
            "EURUSD": 0.5, "GBPUSD": 0.8, "EURJPY": 1.5,
            "USDJPY": 0.5, "AUDJPY": 1.5, "NZDJPY": 1.5,
        },
        "start_balance":         300,
        "leverage":              30,
        "expire_bars":           4,
        "pullback_window":       6,
        "skip_monday":           False,
        "skip_hours":            (15, 16),
        "atr_max_pips":          {"EURUSD": 7.5},
        "max_day_consec_losses": 3,
        "corr_pairs":            {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD"},
        "only_long":             False,
        "max_pos_per_symbol":    1,
        "symbol_sessions": {
            "EURUSD": (10, 18), "GBPUSD": (10, 18), "EURJPY": (10, 18),
            "USDJPY": (2, 10),  "AUDJPY": (2, 10),  "NZDJPY": (2, 10),
        },
        "symbol_skip_hours":     {},
        "rsi_sell_max":          60,    # RSI simetric pentru SELL
        "ref_test_exp":          0.142,
        "ref_trades_wk":         3.2,
    },

    # -------------------------------------------------------------------------
    # Session 3 — adauga aici cand e gata
    # -------------------------------------------------------------------------
    # {
    #     "id":    "S3-...",
    #     "label": "Session 3 — ...",
    #     ...
    # },
]


# =============================================================================
# ENGINE
# =============================================================================

def run_session(session: dict, cfg_base: dict, source: CsvDataSource) -> dict | None:
    cfg = {**cfg_base}
    cfg["optional_criteria"]["rsi"]["sell_max"] = session["rsi_sell_max"]

    data = {}
    for s in session["symbols"]:
        try:
            data[s] = prepare_symbol(source, s, cfg)
        except FileNotFoundError:
            print(f"    {s}: lipsesc datele — sarit")
    if not data:
        return None

    params = {k: session[k] for k in [
        "spread_pips", "leverage", "start_balance", "expire_bars",
        "pullback_window", "skip_monday", "skip_hours", "atr_max_pips",
        "max_day_consec_losses", "corr_pairs", "only_long",
        "max_pos_per_symbol", "symbol_sessions", "symbol_skip_hours",
    ]}
    params["depth_range"] = None

    trades, equity, balance, max_conc, skipped, halted, split_time = \
        run_portfolio(data, cfg, params)

    return {
        "trades": trades, "equity": equity, "balance": balance,
        "max_conc": max_conc, "skipped": skipped, "halted": halted,
        "split_time": split_time,
    }


def print_session_summary(session: dict, result: dict):
    s = session
    r = result
    bal0 = s["start_balance"]
    bal1 = r["balance"]

    if not r["trades"]:
        print(f"\n  {s['label']}: 0 tranzactii")
        return

    df = pd.DataFrame(r["trades"])
    df["R"]       = df["pnl_usd"] / df["risk_usd"]
    df["entry_t"] = pd.to_datetime(df["time"])
    wins  = (df["outcome"] == "win").sum()
    total = len(df)

    eqdf = pd.DataFrame(r["equity"]).sort_values("time")
    b    = eqdf["balance"].values
    dd   = ((b - np.maximum.accumulate(b)) / np.maximum.accumulate(b)).min() * 100
    ret  = (bal1 - bal0) / bal0 * 100
    swap = df["swap"].sum() if "swap" in df.columns else 0.0

    span_days = (df["entry_t"].max() - df["entry_t"].min()).days
    trades_wk = total / max(span_days / 7, 1)

    split   = r["split_time"]
    test_df = df[df["entry_t"] >= split]
    train_df = df[df["entry_t"] < split]

    print(f"\n  {'─'*65}")
    print(f"  {s['label']}")
    print(f"  {'─'*65}")
    print(f"  Capital:   {bal0} → {bal1:.2f} USD  ({ret:+.1f}%)")
    print(f"  Trades:    {total}  (W:{wins} / L:{total-wins})  "
          f"WR={wins/total*100:.1f}%")
    print(f"  Exp/trade: {df['R'].mean():+.3f}R  "
          f"[ref backtest: {s['ref_test_exp']:+.3f}R]")
    print(f"  Frecventa: {trades_wk:.1f}/sapt  "
          f"[ref: {s['ref_trades_wk']:.1f}/sapt]")
    print(f"  Max DD:    {dd:+.1f}%  |  Swap: {swap:.1f} USD  |  "
          f"Halted: {r['halted']} zile")

    print(f"  Train ({len(train_df)}t): exp={train_df['R'].mean():+.3f}R  "
          f"WR={( (train_df['outcome']=='win').sum()/len(train_df)*100 if len(train_df) else 0):.1f}%"
          if len(train_df) else "  Train: 0 trades")
    print(f"  Test  ({len(test_df)}t): exp={test_df['R'].mean():+.3f}R  "
          f"WR={( (test_df['outcome']=='win').sum()/len(test_df)*100 if len(test_df) else 0):.1f}%"
          if len(test_df) else "  Test: 0 trades")

    print(f"  Per simbol:")
    for sym in df["symbol"].unique():
        sub = df[df["symbol"] == sym]
        w   = (sub["outcome"] == "win").sum()
        print(f"    {sym:<10} {len(sub):>4}t  WR={w/len(sub)*100:.0f}%  "
              f"exp={sub['R'].mean():+.3f}R  pnl={sub['pnl_usd'].sum():+.0f}$")

    if not s["only_long"] and "direction" in df.columns:
        print(f"  Per directie:")
        for dval, dlbl in [(1, "LONG"), (-1, "SHORT")]:
            sub = df[df["direction"] == dval]
            if len(sub):
                w = (sub["outcome"] == "win").sum()
                print(f"    {dlbl:<6} {len(sub):>4}t  WR={w/len(sub)*100:.0f}%  "
                      f"exp={sub['R'].mean():+.3f}R")

    return {"df": df, "trades_wk": trades_wk, "dd": dd, "exp": df["R"].mean(),
            "test_exp": test_df["R"].mean() if len(test_df) else 0.0,
            "test_n": len(test_df), "total": total}


def print_combined_summary(stats_list: list[dict], sessions: list[dict]):
    print(f"\n\n  {'='*65}")
    print(f"  SUMAR COMBINAT — toate sesiunile")
    print(f"  {'='*65}")
    print(f"  {'Sesiune':<32} {'Tot':>5} {'WR':>6} {'Exp':>7} {'TestR':>7} "
          f"{'TN':>5} {'T/wk':>6} {'DD':>6}")
    print(f"  {'─'*65}")

    total_wk = 0.0
    for st, sess in zip(stats_list, sessions):
        if st is None:
            print(f"  {sess['label']:<32}  (nicio tranzactie)")
            continue
        wr = (st["df"]["outcome"] == "win").sum() / st["total"] * 100
        print(f"  {sess['label']:<32} {st['total']:>5} {wr:>5.1f}% "
              f"{st['exp']:>+7.3f} {st['test_exp']:>+7.3f} {st['test_n']:>5} "
              f"{st['trades_wk']:>5.1f}/w {st['dd']:>+5.1f}%")
        total_wk += st["trades_wk"]

    print(f"  {'─'*65}")
    print(f"  Frecventa combinata estimata: {total_wk:.1f} trades/saptamana")
    print(f"  (sesiunile sunt independente — capital si loguri separate)")


# =============================================================================
# MAIN
# =============================================================================

def main():
    with open(CONFIG, encoding="utf-8") as f:
        cfg_base = json.load(f)

    source = CsvDataSource(DATA_DIR)

    print("=" * 67)
    print("  BACKTEST COMBINAT — sesiuni active")
    print("=" * 67)

    all_stats = []
    all_results = []

    for sess in SESSIONS:
        print(f"\n  [{sess['id']}] {sess['label']}")
        print(f"  Piete: {sess['symbols']}")
        result = run_session(sess, cfg_base, source)
        all_results.append(result)

        if result is None:
            print("  Nicio tranzactie sau date lipsa.")
            all_stats.append(None)
            continue

        stats = print_session_summary(sess, result)
        all_stats.append(stats)

        # Salveaza CSV per sesiune
        sid = sess["id"].lower().replace("-", "_")
        df_trades = pd.DataFrame(result["trades"])
        df_equity = pd.DataFrame(result["equity"]).sort_values("time")
        df_trades.to_csv(os.path.join(DATA_DIR, f"{sid}_trades.csv"), index=False)
        df_equity.to_csv(os.path.join(DATA_DIR, f"{sid}_equity.csv"), index=False)

    valid_stats = [s for s in all_stats if s is not None]
    if len(valid_stats) > 1:
        print_combined_summary(all_stats, SESSIONS)

    print(f"\n  CSV-uri salvate in {DATA_DIR}/")


if __name__ == "__main__":
    main()
