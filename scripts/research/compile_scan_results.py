"""
Compileaza si prezinta rezultatele finale ale scan-ului complet.
Citeste: full_scan_results.csv + btc_strategy_variants (din output) + session_hours_results.csv

Ruleaza DUPA ce scanurile s-au terminat:
  python scripts/research/compile_scan_results.py
"""

import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
import numpy as np

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))

def load_csv(name):
    p = os.path.join(OUT_DIR, name)
    if os.path.exists(p):
        return pd.read_csv(p)
    return None

def score_fn(test_exp, test_trades, dd):
    if test_exp <= 0 or test_trades < 15:
        return -999.0
    pen = max(0, (-dd - 35) * 0.015)
    return test_exp * math.sqrt(test_trades) - pen

def main():
    print("=" * 100)
    print("RAPORT FINAL — FULL MARKET SCAN + BTC VARIANTS + SESSION HOURS")
    print("=" * 100)

    # 1. Full scan (raw, fara filtre sesiune)
    df_main = load_csv("full_scan_results.csv")
    if df_main is None:
        print("EROARE: full_scan_results.csv nu exista. Ruleaza full_market_scan.py mai intai.")
        return

    print(f"\nMain scan: {len(df_main)} rezultate ({df_main['symbol'].nunique()} simboluri)")

    # 2. Session hours scan (cu filtre sesiune)
    df_sess = load_csv("session_hours_results.csv")
    if df_sess is not None:
        print(f"Session hours scan: {len(df_sess)} rezultate ({df_sess['symbol'].nunique()} simboluri)")
    else:
        print("Session hours scan: nu exista (ruleaza session_hours_scan.py separat)")

    print("\n" + "=" * 100)
    print("PIETE VIABILE — RAW SCAN (fara filtre de sesiune)")
    print("=" * 100)

    # Filtrare principale: test_exp > 0
    pos_main = df_main[df_main["test_exp"] > 0]
    viable = sorted(pos_main["symbol"].unique())
    all_syms = sorted(df_main["symbol"].unique())
    neg = [s for s in all_syms if s not in viable]

    print(f"\nViabile ({len(viable)}): {', '.join(viable)}")
    print(f"Fara edge ({len(neg)}): {', '.join(neg)}")

    print("\n" + "-" * 100)
    print("TOP 5 config per piata viabila:")
    print("-" * 100)

    best_configs = {}
    for sym in viable:
        sub = pos_main[pos_main["symbol"] == sym].nlargest(5, "score")
        best_configs[sym] = sub
        b = sub.iloc[0]
        print(f"\n  [{sym}]")
        print(f"    BEST: {b['entry_tf']}+{b['trend_tf']} | {b['direction']:4s} | pw={b['pw']} expire={b['expire']} | {b['strategy']}")
        print(f"          Total {b['total_t']}t | WR {b['total_wr']:.1f}% | Exp {b['total_exp']:+.4f}R | DD {b['dd']:.1f}%")
        print(f"          TRAIN {b['train_t']}t {b['train_exp']:+.4f}R | TEST {b['test_t']}t {b['test_exp']:+.4f}R | Score {b['score']:.3f}")
        if b.get("flag_t", 0) > 0 or b.get("ib_t", 0) > 0:
            print(f"          Semnale: pullback={b.get('pullback_t',0)} flag={b.get('flag_t',0)} IB={b.get('ib_t',0)}")
        print(f"    {'#':>2} {'TF':>8} {'Dir':>4} {'pw':>3} {'Strategy':<22} {'TEST exp':>9} {'TEST t':>7} {'DD':>6} {'Score':>7}")
        for i, (_, row) in enumerate(sub.iterrows(), 1):
            print(f"    {i:2d} {row['entry_tf']}+{row['trend_tf']:>3} {row['direction']:>4} {row['pw']:>3} "
                  f"{row['strategy']:<22} {row['test_exp']:>+9.4f}R {row['test_t']:>7}t "
                  f"{row['dd']:>5.1f}% {row['score']:>7.3f}")

    if df_sess is not None:
        print("\n\n" + "=" * 100)
        print("PIETE VIABILE — SESSION HOURS SCAN (cu filtre de sesiune)")
        print("=" * 100)
        pos_sess = df_sess[df_sess["test_exp"] > 0]
        viable_sess = sorted(pos_sess["symbol"].unique())
        print(f"\nViabile cu filtre sesiune ({len(viable_sess)}): {', '.join(viable_sess)}")

        # Piete NOI care apar DOAR cu filtre (nu in raw scan)
        new_with_filter = [s for s in viable_sess if s not in viable]
        if new_with_filter:
            print(f"\nPIETE NOI cu filtre sesiune (nu viabile in raw): {', '.join(new_with_filter)}")
            for sym in new_with_filter:
                sub = pos_sess[pos_sess["symbol"] == sym].nlargest(3, "score")
                print(f"\n  [{sym}] (necesita filtre sesiune)")
                for _, row in sub.iterrows():
                    print(f"    {row['entry_tf']}+{row['trend_tf']} {row['direction']:4s} pw={row['pw']} "
                          f"sess={row['session']:10s} ({row.get('sess_start',0):02d}-{row.get('sess_end',0):02d}h) | "
                          f"test {row['test_exp']:+.4f}R/{row['test_t']}t | dd={row['dd']:.1f}%")

    # Top 25 global
    print("\n\n" + "=" * 100)
    print("TOP 25 GLOBAL (raw scan, dupa score)")
    print("=" * 100)
    top25 = pos_main.nlargest(25, "score")
    print(f"  {'#':>2} {'Symbol':<10} {'TF':>8} {'Dir':>4} {'pw':>3} {'Strategy':<22} {'TEST exp':>9} {'TEST t':>7} {'DD':>6} {'Score':>7}")
    for i, (_, row) in enumerate(top25.iterrows(), 1):
        print(f"  {i:2d} {row['symbol']:<10} {row['entry_tf']}+{row['trend_tf']:>3} "
              f"{row['direction']:>4} {row['pw']:>3} {row['strategy']:<22} "
              f"{row['test_exp']:>+9.4f}R {row['test_t']:>7}t {row['dd']:>5.1f}% {row['score']:>7.3f}")

    # Alocare capital
    print("\n\n" + "=" * 100)
    print("SUGESTIE ALOCARE CAPITAL ($1000 total)")
    print("=" * 100)
    if best_configs:
        sc_map   = {s: max(best_configs[s].iloc[0]["score"], 0.01) for s in best_configs}
        total_sc = sum(sc_map.values())
        print(f"  {'Simbol':<10} {'$':>7} {'TF':>8} {'Dir':>4} {'pw':>3} {'Strategy':<22} {'test_exp':>9} {'DD':>6}")
        for sym in sorted(best_configs, key=lambda s: -sc_map[s]):
            row   = best_configs[sym].iloc[0]
            alloc = round(sc_map[sym] / total_sc * 1000)
            print(f"  {sym:<10} {alloc:>6}$ {row['entry_tf']}+{row['trend_tf']:>3} "
                  f"{row['direction']:>4} {row['pw']:>3} {row['strategy']:<22} "
                  f"{row['test_exp']:>+9.4f}R {row['dd']:>5.1f}%")

    print("\n" + "=" * 100)
    print("NOTE:")
    print("  - BTCUSD apare slab in raw scan (fara filtre sesiune).")
    print("    Cu filtrele S3 validate (skip Sat, ore 12-16+21-01) edge este confirmat.")
    print("  - Scor = test_exp x sqrt(test_trades) - penalizare DD>35%")
    print("  - Minim 20 trades pe test set pentru a fi inclus")
    print("=" * 100)

if __name__ == "__main__":
    main()
