"""
Analiza rezultate sesiune OBSERVE
==================================
Citeste signals.csv + outcomes.csv dintr-un director de sesiune
si produce un sumar comparabil cu rezultatele backtestului.

Rulare:
  python scripts/analiza_observe.py --session session1
  python scripts/analiza_observe.py --session session2
  python scripts/analiza_observe.py --dir data/live_signals/session1

Referinte backtest:
  Session 1 (S1-M15-LONG):  test_exp=+0.375R, 0.9/wk, WR~40%, DD=-50.6%
  Session 2 (S2-M15-BOTH):  test_exp=+0.142R, 3.2/wk, WR~22%, DD=-52.9%
"""

import argparse
import os
import sys

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest import DATA_DIR

BACKTEST_REF = {
    "S1-M15-LONG": {"label": "Session 1",  "test_exp": 0.344, "wr": 32.0,
                    "trades_wk": 0.7,  "dd": -40.5},
    "S2-M15-BOTH": {"label": "Session 2",  "test_exp": 0.127, "wr": 25.8,
                    "trades_wk": 2.4,  "dd": -51.1},
}

MIN_TRADES_PENTRU_COMPARATIE = 30


def load_session(session_dir: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    sig_f = os.path.join(session_dir, "signals.csv")
    out_f = os.path.join(session_dir, "outcomes.csv")

    if not os.path.exists(sig_f):
        print(f"EROARE: nu exista {sig_f}"); sys.exit(1)

    sigs = pd.read_csv(sig_f, parse_dates=["time"])
    outs = pd.read_csv(out_f, parse_dates=["time_check"]) if os.path.exists(out_f) else pd.DataFrame()
    return sigs, outs


def analyze(session_dir: str):
    sigs, outs = load_session(session_dir)

    session_id = None
    if len(sigs) and "signal_id" in sigs.columns:
        session_id = sigs["signal_id"].iloc[0].rsplit("-SIG", 1)[0]

    ref = BACKTEST_REF.get(session_id, {})
    label = ref.get("label", session_id or os.path.basename(session_dir))

    print(f"\n{'='*70}")
    print(f"  ANALIZA OBSERVE — {label}  ({session_dir})")
    print(f"{'='*70}")

    # ---- Semnale ----
    print(f"\n  SEMNALE GENERATE: {len(sigs)}")
    if len(sigs) == 0:
        print("  (niciun semnal inca)"); return

    span_days = (sigs["time"].max() - sigs["time"].min()).days
    weeks = max(span_days / 7, 0.1)
    trades_wk = len(sigs) / weeks

    print(f"  Perioada:  {sigs['time'].min().date()} — {sigs['time'].max().date()}  "
          f"({span_days} zile / {weeks:.1f} sapt)")
    print(f"  Frecventa: {trades_wk:.1f} semnale/sapt  "
          f"[backtest: {ref.get('trades_wk', '?')}/wk]")

    if "symbol" in sigs.columns:
        print(f"\n  Per simbol:")
        for sym, grp in sigs.groupby("symbol"):
            dirs = grp.get("dir_str", pd.Series()).value_counts().to_dict() if "dir_str" in grp else {}
            dir_str = "  ".join(f"{k}:{v}" for k, v in dirs.items())
            print(f"    {sym:<10} {len(grp):>3} semnale  {dir_str}")

    # ---- Outcomes ----
    if len(outs) == 0:
        print("\n  OUTCOMES: niciun semnal inchis inca")
        return

    closed = outs[outs["status"].isin(["TP", "SL"])].copy()
    expired = outs[outs["status"] == "expirat"]
    invalidated = outs[outs["status"] == "invalidat"]

    print(f"\n  OUTCOMES:")
    print(f"    Total semnale:   {len(sigs)}")
    print(f"    TP + SL inchis:  {len(closed)}")
    print(f"    Expirate:        {len(expired)}")
    print(f"    Invalidate:      {len(invalidated)}")
    print(f"    Inca pendinge:   {len(sigs) - len(outs)}")

    if len(closed) == 0:
        print("\n  Niciun trade inchis inca."); return

    wins = (closed["result_r"] > 0).sum()
    losses = (closed["result_r"] < 0).sum()
    wr = wins / len(closed) * 100
    exp = closed["result_r"].mean()

    # Drawdown pe equity fictiva
    equity = [1.0]
    for r in closed["result_r"]:
        equity.append(equity[-1] * (1 + r * 0.01))  # 1% risc per trade
    eq = np.array(equity)
    dd = ((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq)).min() * 100

    print(f"\n  PERFORMANTA (pe {len(closed)} trades inchise):")
    print(f"    Win Rate:    {wr:.1f}%       [backtest: {ref.get('wr', '?')}%]")
    print(f"    Expectancy:  {exp:+.3f}R     [backtest: {ref.get('test_exp', '?'):+.3f}R]")
    print(f"    Drawdown:    {dd:+.1f}%      [backtest: {ref.get('dd', '?'):+.1f}%]")
    print(f"    W:{wins}  L:{losses}")

    if "symbol" in closed.columns:
        print(f"\n  Per simbol:")
        for sym, grp in closed.groupby("symbol"):
            w = (grp["result_r"] > 0).sum()
            e = grp["result_r"].mean()
            print(f"    {sym:<10} {len(grp):>3}t  WR={w/len(grp)*100:.0f}%  Exp={e:+.3f}R")

    if "dir_str" in closed.columns:
        print(f"\n  Per directie:")
        for d, grp in closed.groupby("dir_str"):
            w = (grp["result_r"] > 0).sum()
            e = grp["result_r"].mean()
            print(f"    {d:<6} {len(grp):>3}t  WR={w/len(grp)*100:.0f}%  Exp={e:+.3f}R")

    # ---- Verdict comparatie ----
    print(f"\n  COMPARATIE CU BACKTESTUL:")
    if len(closed) < MIN_TRADES_PENTRU_COMPARATIE:
        needed = MIN_TRADES_PENTRU_COMPARATIE - len(closed)
        print(f"    *** Prea putine date ({len(closed)}/{MIN_TRADES_PENTRU_COMPARATIE} min) ***")
        print(f"    Mai trebuie ~{needed} trades inchise (~{needed/max(trades_wk,0.1):.0f} saptamani)")
    else:
        ref_exp = ref.get("test_exp")
        if ref_exp is not None:
            diff = exp - ref_exp
            verdict = "IN LINIE" if abs(diff) < 0.15 else ("PESTE ASTEPTARI" if diff > 0 else "SUB ASTEPTARI")
            print(f"    Expectancy: live={exp:+.3f}R vs backtest={ref_exp:+.3f}R  "
                  f"(diff={diff:+.3f}R)  → {verdict}")
        ref_wr = ref.get("wr")
        if ref_wr is not None:
            wr_diff = wr - ref_wr
            print(f"    Win Rate:   live={wr:.1f}% vs backtest={ref_wr:.1f}%  "
                  f"(diff={wr_diff:+.1f}pp)")

    print()


def main():
    parser = argparse.ArgumentParser(description="Analiza sesiune OBSERVE")
    parser.add_argument("--session", choices=["session1", "session2"],
                        help="Sesiunea de analizat")
    parser.add_argument("--dir", help="Director direct (alternativ la --session)")
    args = parser.parse_args()

    if args.dir:
        analyze(args.dir)
    elif args.session:
        analyze(os.path.join(DATA_DIR, "live_signals", args.session))
    else:
        # Analizeaza ambele daca exista
        for s in ["session1", "session2"]:
            d = os.path.join(DATA_DIR, "live_signals", s)
            if os.path.exists(os.path.join(d, "signals.csv")):
                analyze(d)
            else:
                print(f"\n  {s}: nu a fost pornita inca (lipseste {d}/signals.csv)")


if __name__ == "__main__":
    main()
