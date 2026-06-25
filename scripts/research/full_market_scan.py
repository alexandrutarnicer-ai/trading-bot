"""
Full Market Scan — testare exhaustiva cu multiprocessing (bypass GIL).

Structura: 1 proces per piata. Fiecare proces:
 - incarca datele local (CSV)
 - ruleaza toate testele pentru piata respectiva (TF x dir x pw x expire x strategie)
 - returneaza rezultatele

PASS 1 (pw=8, expire=4): toti piete
PASS 2 (pw=[6,10], expire=[3,4]): top 12 piete din pass 1

Output:
  scripts/research/full_scan_results.csv
  scripts/research/full_scan_top.txt

Rulare: python scripts/research/full_market_scan.py
"""

import sys, os, json, math, time
from datetime import datetime

import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from backtest import CONFIG, DATA_DIR

# ── Constante globale (necesare in procese worker) ─────────────────────────────

MAX_WORKERS = 4   # procese paralele (nu threads)

MIN_TRADES  = 40
MIN_TEST_T  = 20

SPREAD_DEFAULTS = {
    "EURUSD": 0.5, "GBPUSD": 0.8, "EURJPY": 1.5, "USDJPY": 0.6,
    "AUDJPY": 1.2, "NZDJPY": 1.5, "USDCHF": 1.0, "USDCAD": 1.2,
    "AUDUSD": 0.7, "GBPJPY": 1.8, "NZDUSD": 1.2, "CADJPY": 1.5,
    "CHFJPY": 1.8, "EURGBP": 0.8, "EURAUD": 1.5, "EURCAD": 1.5,
    "EURNZD": 2.0, "GBPAUD": 2.0, "GBPCAD": 2.0, "GBPNZD": 2.5,
    "AUDNZD": 1.5, "AUDCAD": 1.5,
    "GER40": 1.0, "US30": 2.0, "US500": 0.5, "UK100": 1.5,
    "BTCUSD": 12.0, "ETHUSD": 3.0, "SOLUSD": 0.1, "XRPUSD": 0.003,
    "XAUUSD": 0.3, "XAGUSD": 0.03,
}

MARKETS_TF = {
    "EURUSD": [("M15","M30"), ("H1","D1")],
    "GBPUSD": [("M15","M30"), ("H1","D1")],
    "USDJPY": [("M15","M30"), ("H1","D1")],
    "USDCHF": [("M15","M30"), ("H1","D1")],
    "USDCAD": [("M15","M30"), ("H1","D1")],
    "AUDUSD": [("M15","M30"), ("H1","D1")],
    "NZDUSD": [("M15","M30"), ("H1","D1")],
    "EURJPY": [("M15","M30"), ("H1","D1")],
    "GBPJPY": [("M15","M30"), ("H1","D1")],
    "AUDJPY": [("M15","M30"), ("H1","D1")],
    "NZDJPY": [("M15","M30"), ("H1","D1")],
    "CADJPY": [("M15","M30"), ("H1","D1")],
    "CHFJPY": [("M15","M30"), ("H1","D1")],
    "EURGBP": [("M15","M30"), ("H1","D1")],
    "EURAUD": [("M15","M30"), ("H1","D1")],
    "EURCAD": [("M15","M30"), ("H1","D1")],
    "EURNZD": [("M15","M30")],
    "GBPAUD": [("M15","M30"), ("H1","D1")],
    "GBPCAD": [("M15","M30"), ("H1","D1")],
    "GBPNZD": [("M15","M30")],
    "AUDNZD": [("M15","M30"), ("H1","D1")],
    "AUDCAD": [("M15","M30"), ("H1","D1")],
    "GER40":  [("M15","M30"), ("H1","D1")],
    "US30":   [("M15","M30"), ("H1","D1")],
    "US500":  [("M15","M30"), ("H1","D1")],
    "UK100":  [("M15","M30"), ("H1","D1")],
    "BTCUSD": [("M15","M30")],
    "ETHUSD": [("M15","M30")],
    "SOLUSD": [("M15","M30")],
    "XRPUSD": [("M15","M30")],
    "XAUUSD": [("M15","M30"), ("H1","D1")],
    "XAGUSD": [("M30","H1")],
}

DIRECTIONS = ["LONG", "BOTH"]

STRATEGY_COMBOS = {
    "pullback":           {"flag": False, "ib": False, "be": False},
    "pullback+flag":      {"flag": True,  "ib": False, "be": False},
    "pullback+IB":        {"flag": False, "ib": True,  "be": False},
    "pullback+flag+IB":   {"flag": True,  "ib": True,  "be": False},
    "pullback+BE":        {"flag": False, "ib": False, "be": True},
    "all":                {"flag": True,  "ib": True,  "be": True},
}


def score_fn(test_exp, test_trades, dd):
    if test_exp <= 0 or test_trades < MIN_TEST_T:
        return -999.0
    pen = max(0, (-dd - 35) * 0.015)
    return test_exp * math.sqrt(test_trades) - pen


# ── Worker function (module-level pentru pickling pe Windows) ──────────────────

def process_market(task):
    """
    task = (symbol, tf_list, pw_list, expire_list, directions, strategy_combos, cfg_path, data_dir)
    Ruleaza toate testele pentru un singur simbol.
    Returneaza lista de dicts cu rezultate.
    """
    (symbol, tf_list, pw_list, expire_list, directions, strategy_combos,
     cfg_path, data_dir, spreads) = task

    # Import local (fiecare proces isi importa propriile module)
    import json, math
    import pandas as pd
    import numpy as np

    # Add root to path
    import sys, os
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, root)

    from adapters.csv_source import CsvDataSource
    from strategy.preparation import prepare_symbol_tf
    from engine.portfolio import run_portfolio

    with open(cfg_path, encoding="utf-8") as f:
        base_cfg = json.load(f)

    src = CsvDataSource(data_dir)
    results = []

    for entry_tf, trend_tf in tf_list:
        csv_e = os.path.join(data_dir, f"{symbol}_{entry_tf}.csv")
        csv_t = os.path.join(data_dir, f"{symbol}_{trend_tf}.csv")
        if not (os.path.exists(csv_e) and os.path.exists(csv_t)):
            continue

        try:
            df = prepare_symbol_tf(src, symbol, base_cfg, entry_tf, trend_tf)
        except Exception:
            continue

        if df is None or len(df) < 500:
            continue

        spread = spreads.get(symbol, 1.5)

        for direction in directions:
            for pw in pw_list:
                for expire in expire_list:
                    for strat_name, strat in strategy_combos.items():
                        try:
                            cfg = json.loads(json.dumps(base_cfg))
                            cfg["optional_criteria"]["rsi"]["enabled"]           = True
                            cfg["optional_criteria"]["rsi"]["buy_min"]           = 40
                            cfg["optional_criteria"]["rsi"]["buy_max"]           = 65
                            cfg["optional_criteria"]["rsi"]["sell_min"]          = 35
                            cfg["optional_criteria"]["rsi"]["sell_max"]          = 60
                            cfg["optional_criteria"]["ema_alignment"]["enabled"] = True
                            cfg["optional_criteria"]["body_strength"]            = {"enabled": False, "min_atr_ratio": 0.15}
                            cfg["reward_ladder"]["rr_if_3_criteria"]  = 2.5
                            cfg["reward_ladder"]["rr_if_4_criteria"]  = 3.5
                            cfg["reward_ladder"]["rr_if_5_criteria"]  = 4.5
                            cfg["reward_ladder"]["rr_if_6_criteria"]  = 5.5
                            cfg["reward_ladder"]["threshold_mid"]     = 1
                            cfg["reward_ladder"]["threshold_top"]     = 2
                            cfg["reward_ladder"]["threshold_max"]     = 3
                            cfg["account"]["risk_per_trade_pct"]               = 1.0
                            cfg["account"]["risk_per_trade_pct_all_criteria"]  = 1.2

                            params = {
                                "spread_pips":               {symbol: spread},
                                "leverage":                  30,
                                "start_balance":             1000,
                                "expire_bars":               expire,
                                "pullback_window":           pw,
                                "depth_range":               None,
                                "skip_monday":               False,
                                "skip_hours":                (),
                                "atr_max_pips":              {},
                                "max_day_consec_losses":     3,
                                "corr_pairs":                {},
                                "max_pos_per_symbol":        1,
                                "min_bars_between_same_symbol": 0,
                                "symbol_sessions":           {},
                                "symbol_skip_hours":         {},
                                "skip_weekdays":             set(),
                                "only_long":                 (direction == "LONG"),
                                "be_cfg": {
                                    "enabled":        strat["be"],
                                    "phase2_enabled": True,
                                    "trigger_pct":    80,
                                    "lock1_pct":      30,
                                    "lock2_pct":      50,
                                    "phase2_zone_pct": 40,
                                },
                                "flag_cfg": {
                                    "enabled":  strat["flag"],
                                    "r_ratio":  2.5,
                                    "risk_pct": 0.01,
                                },
                                "inside_bar_cfg": {
                                    "enabled":  strat["ib"],
                                    "r_ratio":  2.0,
                                    "risk_pct": 0.01,
                                },
                            }

                            trades, equity, bal, _, _, _, split = run_portfolio(
                                {symbol: df}, cfg, params, verbose=False
                            )
                            if not trades:
                                continue

                            df_t = pd.DataFrame(trades)
                            df_t["R"]       = df_t["pnl_usd"] / df_t["risk_usd"]
                            df_t["entry_t"] = pd.to_datetime(df_t["time"])

                            train = df_t[df_t["entry_t"] < split]
                            test  = df_t[df_t["entry_t"] >= split]

                            if len(df_t) < MIN_TRADES:
                                continue

                            eq_arr = np.array([e["balance"] for e in equity])
                            peak   = np.maximum.accumulate(eq_arr)
                            dd     = float(((eq_arr - peak) / peak).min() * 100) if len(eq_arr) > 1 else 0.0

                            train_exp = float(train["R"].mean()) if len(train) else 0.0
                            test_exp  = float(test["R"].mean())  if len(test)  else 0.0
                            total_wr  = int(df_t["outcome"].isin(["win","be_lock","be_lock2"]).sum())
                            sig_types = (df_t["signal_type"].value_counts().to_dict()
                                         if "signal_type" in df_t.columns else {})

                            results.append({
                                "symbol":     symbol,
                                "entry_tf":   entry_tf,
                                "trend_tf":   trend_tf,
                                "direction":  direction,
                                "pw":         pw,
                                "expire":     expire,
                                "strategy":   strat_name,
                                "flag":       strat["flag"],
                                "ib":         strat["ib"],
                                "be":         strat["be"],
                                "total_t":    len(df_t),
                                "train_t":    len(train),
                                "test_t":     len(test),
                                "total_wr":   round(total_wr / len(df_t) * 100, 1),
                                "total_exp":  round(float(df_t["R"].mean()), 4),
                                "train_exp":  round(train_exp, 4),
                                "test_exp":   round(test_exp, 4),
                                "dd":         round(dd, 1),
                                "final_bal":  round(bal, 2),
                                "score":      round(score_fn(test_exp, len(test), dd), 4),
                                "pullback_t": sig_types.get("pullback", len(df_t)),
                                "flag_t":     sig_types.get("flag", 0),
                                "ib_t":       sig_types.get("inside_bar", 0),
                                "split":      str(split.date()),
                            })
                        except Exception:
                            pass

    return results


# ── Report ─────────────────────────────────────────────────────────────────────

def report(df, path):
    W = 100
    lines = []
    lines.append("=" * W)
    lines.append(f"FULL MARKET SCAN -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Rezultate valide: {len(df)} | Simboluri: {df['symbol'].nunique()}")
    lines.append("=" * W)

    pos         = df[df["test_exp"] > 0]
    viable_syms = sorted(pos["symbol"].unique())
    all_syms    = sorted(df["symbol"].unique())
    negat_syms  = [s for s in all_syms if s not in viable_syms]

    lines.append(f"\nVIABILE ({len(viable_syms)}): {', '.join(viable_syms)}")
    lines.append(f"FARA EDGE ({len(negat_syms)}): {', '.join(negat_syms)}")

    lines.append("\n" + "-" * W)
    lines.append("DETALII PER PIATA VIABILA (top 5 config)")
    lines.append("-" * W)

    best_per_sym = {}
    for sym in viable_syms:
        sub = pos[pos["symbol"] == sym].nlargest(5, "score")
        best_per_sym[sym] = sub
        best = sub.iloc[0]

        lines.append(f"\n--- {sym} ---")
        lines.append(
            f"  BEST: {best['entry_tf']}+{best['trend_tf']} | {best['direction']:4s} | "
            f"pw={best['pw']} expire={best['expire']} | {best['strategy']}"
        )
        lines.append(
            f"        Total {best['total_t']}t | WR {best['total_wr']:.1f}% | "
            f"Exp {best['total_exp']:+.4f}R | DD {best['dd']:.1f}%"
        )
        lines.append(
            f"        TRAIN {best['train_t']}t exp {best['train_exp']:+.4f}R | "
            f"TEST {best['test_t']}t exp {best['test_exp']:+.4f}R | "
            f"Score {best['score']:.3f}"
        )
        if best.get("flag_t", 0) > 0 or best.get("ib_t", 0) > 0:
            lines.append(
                f"        Semnale: pullback={best.get('pullback_t',0)} "
                f"flag={best.get('flag_t',0)} IB={best.get('ib_t',0)}"
            )
        lines.append(
            f"  {'#':>2} {'TF':>8} {'Dir':>4} {'pw':>3} {'expire':>7} "
            f"{'Strategy':<22} {'TEST exp':>9} {'TEST t':>7} {'DD':>6} {'Score':>7}"
        )
        for i, (_, row) in enumerate(sub.iterrows(), 1):
            lines.append(
                f"  {i:2d} {row['entry_tf']}+{row['trend_tf']:>3} "
                f"{row['direction']:>4} {row['pw']:>3} {row['expire']:>7} "
                f"{row['strategy']:<22} {row['test_exp']:>+9.4f}R "
                f"{row['test_t']:>7}t {row['dd']:>5.1f}% {row['score']:>7.3f}"
            )

    lines.append("\n" + "-" * W)
    lines.append(f"FARA EDGE ({len(negat_syms)})")
    lines.append("-" * W)
    for sym in sorted(negat_syms):
        sub = df[df["symbol"] == sym]
        if len(sub) == 0:
            continue
        best = sub.nlargest(1, "score").iloc[0]
        lines.append(
            f"  {sym:10s}  best test={best['test_exp']:+.4f}R ({best['test_t']}t) | "
            f"{best['entry_tf']}+{best['trend_tf']} {best['direction']} pw={best['pw']}"
        )

    lines.append("\n" + "-" * W)
    lines.append("TOP 25 GLOBAL (dupa score)")
    lines.append("-" * W)
    lines.append(
        f"  {'#':>2} {'Symbol':<10} {'TF':>8} {'Dir':>4} {'pw':>3} "
        f"{'Strategy':<22} {'TEST exp':>9} {'TEST t':>7} {'DD':>6} {'Score':>7}"
    )
    for i, (_, row) in enumerate(pos.nlargest(25, "score").iterrows(), 1):
        lines.append(
            f"  {i:2d} {row['symbol']:<10} {row['entry_tf']}+{row['trend_tf']:>3} "
            f"{row['direction']:>4} {row['pw']:>3} {row['strategy']:<22} "
            f"{row['test_exp']:>+9.4f}R {row['test_t']:>7}t "
            f"{row['dd']:>5.1f}% {row['score']:>7.3f}"
        )

    lines.append("\n" + "-" * W)
    lines.append("SUGESTIE ALOCARE CAPITAL ($1000 total)")
    lines.append("-" * W)
    if best_per_sym:
        sc_map   = {s: max(best_per_sym[s].iloc[0]["score"], 0.01) for s in best_per_sym}
        total_sc = sum(sc_map.values())
        lines.append(
            f"  {'Simbol':<10} {'$':>7} {'TF':>8} {'Dir':>4} {'pw':>3} "
            f"{'Strategy':<22} {'test_exp':>9} {'DD':>6}"
        )
        for sym in sorted(best_per_sym, key=lambda s: -sc_map[s]):
            row   = best_per_sym[sym].iloc[0]
            alloc = round(sc_map[sym] / total_sc * 1000)
            lines.append(
                f"  {sym:<10} {alloc:>6}$ {row['entry_tf']}+{row['trend_tf']:>3} "
                f"{row['direction']:>4} {row['pw']:>3} {row['strategy']:<22} "
                f"{row['test_exp']:>+9.4f}R {row['dd']:>5.1f}%"
            )

    lines.append("\n" + "=" * W)
    text = "\n".join(lines)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(text[-3000:])   # preview ultimele 3000 chars


# ── Main ────────────────────────────────────────────────────────────────────────

def build_market_tasks(pw_list, expire_list, markets_tf=None):
    """Un task per piata (nu per test individual)."""
    mkt = markets_tf or MARKETS_TF
    tasks = []
    for symbol, tf_list in mkt.items():
        valid_tfs = []
        for entry_tf, trend_tf in tf_list:
            ce = os.path.join(DATA_DIR, f"{symbol}_{entry_tf}.csv")
            ct = os.path.join(DATA_DIR, f"{symbol}_{trend_tf}.csv")
            if os.path.exists(ce) and os.path.exists(ct):
                valid_tfs.append((entry_tf, trend_tf))
        if not valid_tfs:
            continue
        tasks.append((
            symbol, valid_tfs, pw_list, expire_list, DIRECTIONS,
            STRATEGY_COMBOS, CONFIG, DATA_DIR, SPREAD_DEFAULTS
        ))
    return tasks


def run_pass(market_tasks, label, n_workers):
    from multiprocessing import Pool
    total_markets = len(market_tasks)
    print(f"\n[{label}] {total_markets} piete pe {n_workers} procese -- {datetime.now().strftime('%H:%M:%S')}")

    all_results = []
    done = 0
    t0 = time.time()

    with Pool(processes=n_workers) as pool:
        for results in pool.imap_unordered(process_market, market_tasks):
            done += 1
            all_results.extend(results)
            elapsed = time.time() - t0
            eta = (elapsed / done) * (total_markets - done) if done else 0
            sym = market_tasks[done - 1][0] if done <= len(market_tasks) else "?"
            print(f"  [{done:2d}/{total_markets}] {sym:10s} -- "
                  f"+{len(results):3d} rezultate | {elapsed:.0f}s | ETA~{eta:.0f}s")

    print(f"[{label}] Finalizat: {len(all_results)} rezultate in {time.time()-t0:.0f}s")
    return all_results


def main():
    out_dir = os.path.join(ROOT, "scripts", "research")
    os.makedirs(out_dir, exist_ok=True)
    csv_out = os.path.join(out_dir, "full_scan_results.csv")
    top_out = os.path.join(out_dir, "full_scan_top.txt")

    # PASS 1: toate piete, pw=8, expire=4
    tasks1 = build_market_tasks(pw_list=[8], expire_list=[4])
    print(f"=== PASS 1: {len(tasks1)} piete, pw=8, expire=4 ===")
    res1 = run_pass(tasks1, "PASS1", MAX_WORKERS)

    if not res1:
        print("Niciun rezultat valid.")
        return

    df1 = pd.DataFrame(res1)

    # PASS 2: pw=[6,10], expire=[3,4] pentru top 12 piete viabile
    viable = (df1[df1["test_exp"] > 0]
              .groupby("symbol")["score"].max()
              .nlargest(12).index.tolist())
    print(f"\nPiete pentru PASS 2: {viable}")

    res2 = []
    if viable:
        best_tf_dir = {}
        for sym in viable:
            sub = df1[(df1["symbol"] == sym) & (df1["test_exp"] > 0)]
            if len(sub):
                row = sub.nlargest(1, "score").iloc[0]
                best_tf_dir[sym] = [(row["entry_tf"], row["trend_tf"])]

        tasks2 = build_market_tasks(pw_list=[6, 10], expire_list=[3, 4], markets_tf=best_tf_dir)
        print(f"=== PASS 2: {len(tasks2)} piete, pw=[6,10], expire=[3,4] ===")
        res2 = run_pass(tasks2, "PASS2", MAX_WORKERS)

    all_results = res1 + res2
    df_all = pd.DataFrame(all_results).sort_values("score", ascending=False)
    df_all.to_csv(csv_out, index=False, encoding="utf-8")
    print(f"\nSalvat: {csv_out} ({len(df_all)} randuri)")
    report(df_all, top_out)
    print(f"\nRaport: {top_out}")


if __name__ == "__main__":
    main()
