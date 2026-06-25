"""
scan_fast.py — Sweep rapid parametri pentru +0.4R

Design:
  - 64 combo/piata (vs 394 inainte) = ~5.5x mai rapid
  - Scrie rezultate pe disk dupa fiecare piata (nu pierde date la crash)
  - M15+M30 doar (H1+D1 optional cu --h1 flag)
  - 4 workeri in paralel

Estimare:
  64 combo × ~35s/combo (cu 4 workeri) × 16 piete / 4 = ~3600s = ~1 ora
  (pessimist: 64 × 88s × 16 / 4 = 22528s = ~6h)

Output:
  scripts/research/fast_scan_SYMBOL.csv    (per piata, imediat dupa finalizare)
  scripts/research/fast_scan_results.csv  (complet, la final)
  scripts/research/fast_scan_report.txt   (raport)

Rulare:
  python scripts/research/scan_fast.py
  python scripts/research/scan_fast.py --h1   (include si H1+D1)
"""

import sys, os, json, math, time, csv
from datetime import datetime
from multiprocessing import Pool, cpu_count

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

OUT_DIR  = os.path.join(ROOT, "scripts", "research")
CSV_OUT  = os.path.join(OUT_DIR, "fast_scan_results.csv")
TXT_OUT  = os.path.join(OUT_DIR, "fast_scan_report.txt")

INCLUDE_H1 = "--h1" in sys.argv

TARGETS = {
    "EURUSD":  [("M15","M30")] + ([("H1","D1")] if INCLUDE_H1 else []),
    "AUDJPY":  [("M15","M30")] + ([("H1","D1")] if INCLUDE_H1 else []),
    "USDCHF":  [("M15","M30")] + ([("H1","D1")] if INCLUDE_H1 else []),
    "XRPUSD":  [("M15","M30")],
    "EURCAD":  [("M15","M30")] + ([("H1","D1")] if INCLUDE_H1 else []),
    "USDJPY":  [("M15","M30")] + ([("H1","D1")] if INCLUDE_H1 else []),
    "GBPCAD":  [("M15","M30")] + ([("H1","D1")] if INCLUDE_H1 else []),
    "USDCAD":  [("M15","M30")] + ([("H1","D1")] if INCLUDE_H1 else []),
    "EURAUD":  [("M15","M30")] + ([("H1","D1")] if INCLUDE_H1 else []),
    "EURJPY":  [("M15","M30")] + ([("H1","D1")] if INCLUDE_H1 else []),
    "CHFJPY":  [("M15","M30")] + ([("H1","D1")] if INCLUDE_H1 else []),
    "GBPUSD":  [("M15","M30")] + ([("H1","D1")] if INCLUDE_H1 else []),
    "GBPAUD":  [("M15","M30")] + ([("H1","D1")] if INCLUDE_H1 else []),
    "AUDCAD":  [("M15","M30")] + ([("H1","D1")] if INCLUDE_H1 else []),
    "NZDJPY":  [("M15","M30")] + ([("H1","D1")] if INCLUDE_H1 else []),
    "AUDNZD":  [("M15","M30")] + ([("H1","D1")] if INCLUDE_H1 else []),
}

SPREAD_DEFAULTS = {
    "EURUSD": 0.5, "GBPUSD": 0.8, "USDJPY": 0.6, "USDCHF": 1.0, "USDCAD": 1.2,
    "AUDJPY": 1.2, "NZDJPY": 1.5, "CHFJPY": 1.8, "EURJPY": 1.5,
    "EURAUD": 1.5, "EURCAD": 1.5, "GBPAUD": 2.0, "GBPCAD": 2.0,
    "AUDCAD": 1.5, "AUDNZD": 1.5, "XRPUSD": 0.003,
}

MIN_TRADES = 40
MIN_TEST_T = 20
MAX_WORKERS = min(4, cpu_count())

# ── Parametri (focus pe cei mai impactanti) ───────────────────────────────────
PW_LIST     = [6, 8, 10, 12, 14]   # pullback window — sweep complet
EXPIRE_LIST = [4]                  # expire=4 este sweet spot din experienta
DIR_LIST    = ["LONG", "BOTH"]

STRATEGY_COMBOS = {
    "pb_only":   {"flag": False, "ib": False, "be": False},
    "pb+flag":   {"flag": True,  "ib": False, "be": False},
    "pb+IB":     {"flag": False, "ib": True,  "be": False},
    "pb+f+IB":   {"flag": True,  "ib": True,  "be": False},
    "pb+BE":     {"flag": False, "ib": False, "be": True},
    "all":       {"flag": True,  "ib": True,  "be": True},
}

# RSI: top 2 (RSI enabled standard, RSI disabled)
RSI_PRESETS = [
    {"name": "rsi_on",  "buy_min": 40, "buy_max": 65, "sell_min": 35, "sell_max": 60, "enabled": True},
    {"name": "rsi_off", "buy_min": 30, "buy_max": 70, "sell_min": 30, "sell_max": 70, "enabled": False},
]

# Standalone (pullback disabled)
STANDALONE_COMBOS = {
    "flag_only": {"flag": True,  "ib": False, "be": False},
    "IB_only":   {"flag": False, "ib": True,  "be": False},
    "f+IB":      {"flag": True,  "ib": True,  "be": False},
    "f+IB+BE":   {"flag": True,  "ib": True,  "be": True},
}

BE_STD = {"trigger": 80, "lock1": 30, "lock2": 50, "zone": 40}

CSV_FIELDS = [
    "symbol","part","entry_tf","trend_tf","direction","pw","expire","strategy",
    "rsi","total_t","train_t","test_t","total_exp","train_exp","test_exp",
    "dd","final_bal","score","pb_t","flag_t","ib_t","split",
]


def score_fn(test_exp, test_trades, dd):
    if test_exp <= 0 or test_trades < MIN_TEST_T:
        return -999.0
    return test_exp * math.sqrt(test_trades) - max(0, (-dd - 35) * 0.015)


def process_market(task):
    symbol, tf_list, cfg_path, data_dir, spreads, out_dir = task

    import json, math, sys, os
    import pandas as pd, numpy as np

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, root)

    from adapters.csv_source import CsvDataSource
    from strategy.preparation import prepare_symbol_tf
    from engine.portfolio import run_portfolio
    import strategy.structure as _struct

    with open(cfg_path, encoding="utf-8") as f:
        base_cfg = json.load(f)

    src     = CsvDataSource(data_dir)
    spread  = spreads.get(symbol, 1.5)
    results = []

    # Pre-incarca DataFrames
    dfs = {}
    for etf, ttf in tf_list:
        if not os.path.exists(os.path.join(data_dir, f"{symbol}_{etf}.csv")):
            continue
        if not os.path.exists(os.path.join(data_dir, f"{symbol}_{ttf}.csv")):
            continue
        try:
            df = prepare_symbol_tf(src, symbol, base_cfg, etf, ttf)
            if df is not None and len(df) >= 500:
                dfs[(etf, ttf)] = df
        except Exception:
            pass

    if not dfs:
        return symbol, []

    def make_cfg(rsi_p):
        cfg = json.loads(json.dumps(base_cfg))
        cfg["optional_criteria"]["rsi"]["enabled"]           = rsi_p["enabled"]
        cfg["optional_criteria"]["rsi"]["buy_min"]           = rsi_p["buy_min"]
        cfg["optional_criteria"]["rsi"]["buy_max"]           = rsi_p["buy_max"]
        cfg["optional_criteria"]["rsi"]["sell_min"]          = rsi_p["sell_min"]
        cfg["optional_criteria"]["rsi"]["sell_max"]          = rsi_p["sell_max"]
        cfg["optional_criteria"]["ema_alignment"]["enabled"] = True
        cfg["optional_criteria"]["body_strength"]            = {"enabled": False, "min_atr_ratio": 0.15}
        cfg["reward_ladder"]["rr_if_3_criteria"]  = 2.5
        cfg["reward_ladder"]["rr_if_4_criteria"]  = 3.5
        cfg["reward_ladder"]["rr_if_5_criteria"]  = 4.5
        cfg["reward_ladder"]["rr_if_6_criteria"]  = 5.5
        cfg["reward_ladder"]["threshold_mid"] = 1
        cfg["reward_ladder"]["threshold_top"] = 2
        cfg["reward_ladder"]["threshold_max"] = 3
        cfg["account"]["risk_per_trade_pct"]              = 1.0
        cfg["account"]["risk_per_trade_pct_all_criteria"] = 1.2
        return cfg

    def make_params(direction, pw, expire, strat):
        return {
            "spread_pips":                   {symbol: spread},
            "leverage":                      30, "start_balance": 1000,
            "expire_bars":                   expire, "pullback_window": pw,
            "depth_range":                   None, "skip_monday": False,
            "skip_hours":                    (), "atr_max_pips": {},
            "max_day_consec_losses":         3, "corr_pairs": {},
            "max_pos_per_symbol":            1,
            "min_bars_between_same_symbol":  0,
            "symbol_sessions":               {}, "symbol_skip_hours": {},
            "skip_weekdays":                 set(), "only_long": (direction == "LONG"),
            "be_cfg":  {"enabled": strat["be"], "phase2_enabled": True,
                        "trigger_pct": BE_STD["trigger"], "lock1_pct": BE_STD["lock1"],
                        "lock2_pct": BE_STD["lock2"], "phase2_zone_pct": BE_STD["zone"]},
            "flag_cfg":       {"enabled": strat["flag"], "r_ratio": 2.5, "risk_pct": 0.01},
            "inside_bar_cfg": {"enabled": strat["ib"],   "r_ratio": 2.0, "risk_pct": 0.01},
        }

    def run_one(cfg, params, df, cols):
        try:
            trades, equity, bal, _, _, _, split = run_portfolio(
                {symbol: df}, cfg, params, verbose=False
            )
            if not trades:
                return None
            df_t = pd.DataFrame(trades)
            df_t["R"]       = df_t["pnl_usd"] / df_t["risk_usd"]
            df_t["entry_t"] = pd.to_datetime(df_t["time"])
            train = df_t[df_t["entry_t"] < split]
            test  = df_t[df_t["entry_t"] >= split]
            if len(df_t) < MIN_TRADES:
                return None
            eq = np.array([e["balance"] for e in equity])
            pk = np.maximum.accumulate(eq)
            dd = float(((eq - pk) / pk).min() * 100) if len(eq) > 1 else 0.0
            te = float(test["R"].mean()) if len(test) else 0.0
            sig = (df_t["signal_type"].value_counts().to_dict()
                   if "signal_type" in df_t.columns else {})
            row = {
                "symbol": symbol,
                "total_t": len(df_t), "train_t": len(train), "test_t": len(test),
                "total_exp": round(float(df_t["R"].mean()), 4),
                "train_exp": round(float(train["R"].mean()) if len(train) else 0, 4),
                "test_exp":  round(te, 4), "dd": round(dd, 1),
                "final_bal": round(bal, 2),
                "score":     round(score_fn(te, len(test), dd), 4),
                "pb_t":   sig.get("pullback", 0),
                "flag_t": sig.get("flag", 0),
                "ib_t":   sig.get("inside_bar", 0),
                "split":  str(split.date()),
            }
            row.update(cols)
            return row
        except Exception:
            return None

    # ── PARTE 1: Pullback sweep ────────────────────────────────────────────────
    for (etf, ttf), df in dfs.items():
        for direction in DIR_LIST:
            for rsi_p in RSI_PRESETS:
                cfg = make_cfg(rsi_p)
                for pw in PW_LIST:
                    for expire in EXPIRE_LIST:
                        for sn, strat in STRATEGY_COMBOS.items():
                            params = make_params(direction, pw, expire, strat)
                            r = run_one(cfg, params, df, {
                                "part": "pullback",
                                "entry_tf": etf, "trend_tf": ttf,
                                "direction": direction, "pw": pw, "expire": expire,
                                "strategy": sn, "rsi": rsi_p["name"],
                            })
                            if r: results.append(r)

    # ── PARTE 2: Standalone (pullback disabled) ────────────────────────────────
    orig = _struct.detect_setup
    _struct.detect_setup = lambda *a, **k: None
    try:
        for (etf, ttf), df in dfs.items():
            for direction in DIR_LIST:
                for rsi_p in RSI_PRESETS:
                    cfg = make_cfg(rsi_p)
                    for sn, strat in STANDALONE_COMBOS.items():
                        params = make_params(direction, 10, 4, strat)
                        r = run_one(cfg, params, df, {
                            "part": "standalone",
                            "entry_tf": etf, "trend_tf": ttf,
                            "direction": direction, "pw": 0, "expire": 4,
                            "strategy": sn, "rsi": rsi_p["name"],
                        })
                        if r: results.append(r)
    finally:
        _struct.detect_setup = orig

    # ── Scrie pe disk imediat dupa finalizare ─────────────────────────────────
    if results:
        per_market_csv = os.path.join(out_dir, f"fast_scan_{symbol}.csv")
        with open(per_market_csv, "w", newline="", encoding="utf-8") as f:
            import csv as _csv
            fields = [k for k in results[0].keys()]
            w = _csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(results)

    return symbol, results


# ─────────────────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────────────────

def report(all_results, txt_path):
    import pandas as pd
    df = pd.DataFrame(all_results)
    if df.empty:
        print("Niciun rezultat valid.")
        return

    W = 125
    lines = []
    lines.append("=" * W)
    lines.append(f"FAST SCAN REZULTATE  --  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Total teste: {len(df)} | Simboluri: {df['symbol'].nunique()}")
    lines.append("=" * W)

    # ── Best per simbol ────────────────────────────────────────────────────────
    lines.append("\n## BEST PER SIMBOL (TARGET: test_exp >= +0.4R)\n")
    lines.append(f"  {'Simbol':>8}  {'Part':>10}  {'TF':>8}  {'Dir':>4}  {'pw':>3}  {'exp':>6}  "
                 f"{'Strategy':>10}  {'RSI':>7}  {'TRAIN':>8}  {'TEST':>8}  {'Tt':>4}  {'DD':>6}  {'Score':>7}  STATUS")

    achieved, missed = [], []

    for sym in sorted(df["symbol"].unique()):
        sub  = df[df["symbol"] == sym]
        pos  = sub[sub["test_exp"] > 0]
        best = (pos if not pos.empty else sub).nlargest(1, "score").iloc[0]
        target = ">>TARGET" if float(best["test_exp"]) >= 0.4 else "..."
        (achieved if float(best["test_exp"]) >= 0.4 else missed).append(sym)
        etf = best.get("entry_tf","?"); ttf = best.get("trend_tf","?")
        lines.append(
            f"  {sym:>8}  {str(best.get('part','?')):>10}  {etf}+{ttf:>3}  "
            f"{str(best.get('direction','?')):>4}  {int(best.get('pw',0)):>3}  "
            f"{float(best.get('total_exp',0)):>+6.3f}R  "
            f"{str(best.get('strategy','?')):>10}  {str(best.get('rsi','?')):>7}  "
            f"{float(best['train_exp']):>+8.4f}R  {float(best['test_exp']):>+8.4f}R  "
            f"{int(best['test_t']):>4}t  {float(best['dd']):>5.1f}%  "
            f"{float(best['score']):>7.3f}  {target}"
        )

    lines.append(f"\n  ATINS >= +0.4R: {len(achieved)}  --  {', '.join(achieved) or 'niciunul'}")
    lines.append(f"  Sub target:     {len(missed)}   --  {', '.join(missed) or 'niciunul'}")

    # ── Top 5 per simbol ──────────────────────────────────────────────────────
    lines.append("\n" + "=" * W)
    lines.append("## TOP 5 CONFIG PER SIMBOL")

    for sym in sorted(df["symbol"].unique()):
        sub = df[df["symbol"] == sym]
        top = sub[sub["test_exp"] > 0].nlargest(5, "score")
        if top.empty:
            top = sub.nlargest(3, "score")
        lines.append(f"\n  --- {sym}  ({len(sub)} teste) ---")
        for i, (_, r) in enumerate(top.iterrows(), 1):
            etf = r.get("entry_tf","?"); ttf = r.get("trend_tf","?")
            lines.append(
                f"  {i}. [{str(r.get('part','?')):>10}]  {etf}+{ttf:>3}  "
                f"{str(r.get('direction','?')):>4}  pw={int(r.get('pw',0))}  "
                f"exp={float(r.get('total_exp',0)):>+5.3f}R  "
                f"{str(r.get('strategy','?')):>10}  RSI={str(r.get('rsi','?')):<7}  "
                f"TRAIN={float(r['train_exp']):>+8.4f}R  TEST={float(r['test_exp']):>+8.4f}R  "
                f"{int(r['test_t'])}t  DD={float(r['dd']):.1f}%  score={float(r['score']):.3f}"
            )

    # ── Standalone analiza ─────────────────────────────────────────────────────
    sa = df[df["part"] == "standalone"]
    lines.append("\n" + "=" * W)
    lines.append("## PULLBACK DISABLED — STANDALONE (flag/IB fara pullback)")
    if sa.empty:
        lines.append("  Nu s-a testat standalone.")
    else:
        good = sa[sa["test_exp"] >= 0.4]
        lines.append(f"  {len(good)} configuratii standalone cu test_exp >= +0.4R:")
        show = good.nlargest(15, "score") if not good.empty else sa.nlargest(10, "score")
        for _, r in show.iterrows():
            lines.append(
                f"    {r['symbol']:>8}  {r.get('entry_tf','?')}+{r.get('trend_tf','?'):>3}  "
                f"{str(r.get('direction','?')):>4}  {str(r.get('strategy','?')):>10}  "
                f"RSI={str(r.get('rsi','?')):<7}  "
                f"TRAIN={float(r['train_exp']):>+8.4f}R  TEST={float(r['test_exp']):>+8.4f}R  "
                f"{int(r['test_t'])}t  DD={float(r['dd']):.1f}%  score={float(r['score']):.3f}"
            )
        if good.empty:
            lines.append("  (niciunul — pullback ramane obligatoriu)")

    # ── Concluzie ──────────────────────────────────────────────────────────────
    lines.append("\n" + "=" * W)
    lines.append("## CONCLUZIE")
    n_viable = len(achieved)
    lines.append(f"  {n_viable}/16 piete ating target >= +0.4R pe test set.")
    if n_viable >= 12:
        lines.append("  Majoritate viabile. Potentiale imbunatatiri semnificative.")
    elif n_viable >= 8:
        lines.append("  Jumatate viabile. Cateva piete au nevoie de ajustare.")
    else:
        lines.append("  Putine piete viabile. Revizuieste data quality sau reducere spread.")
    lines.append("")
    if sa[sa["test_exp"] >= 0.4].shape[0] > 2 if not sa.empty else False:
        lines.append("  PULLBACK OPTIONAL: Standaloneul produce rezultate bune — feature util!")
    else:
        lines.append("  PULLBACK OPTIONAL: Standalone sub target — pullback ramane esential.")

    txt = "\n".join(lines)
    print(txt)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(txt)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    from backtest import DATA_DIR
    cfg_path = os.path.join(ROOT, "config", "standard_profile.json")

    # Combos per piata
    n_tf   = 1 + (1 if INCLUDE_H1 else 0)
    n_pull = n_tf * len(DIR_LIST) * len(RSI_PRESETS) * len(PW_LIST) * len(EXPIRE_LIST) * len(STRATEGY_COMBOS)
    n_sa   = n_tf * len(DIR_LIST) * len(RSI_PRESETS) * len(STANDALONE_COMBOS)
    n_tot  = n_pull + n_sa

    tasks = [
        (sym, tfs, cfg_path, DATA_DIR, SPREAD_DEFAULTS, OUT_DIR)
        for sym, tfs in TARGETS.items()
    ]

    # Estimare timp (35s/combo cu 4 workeri)
    t_est_h = n_tot * 35 * len(tasks) / MAX_WORKERS / 3600

    print(f"\n{'='*60}")
    print(f"FAST SCAN  --  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Piete: {len(tasks)} | Workeri: {MAX_WORKERS}")
    print(f"TF: M15+M30{'+ H1+D1' if INCLUDE_H1 else ''}")
    print(f"Combos/piata: {n_tot} (pullback={n_pull}, standalone={n_sa})")
    print(f"Total: {n_tot*len(tasks)} | Estimat: ~{t_est_h:.1f} ore")
    print(f"Output: {TXT_OUT}")
    print(f"{'='*60}\n")
    print("Rezultate per piata scrise la: scripts/research/fast_scan_SYMBOL.csv\n")

    t0 = time.time()
    all_results = []

    if MAX_WORKERS > 1:
        with Pool(MAX_WORKERS) as pool:
            for i, (sym, res) in enumerate(pool.imap_unordered(process_market, tasks), 1):
                elapsed = time.time() - t0
                print(f"  [{i:>2}/{len(tasks)}] {sym:>8}  {len(res):>4} rezultate  "
                      f"{elapsed:.0f}s ({elapsed/3600:.2f}h) elapsed")
                all_results.extend(res)
    else:
        for i, task in enumerate(tasks, 1):
            sym, res = process_market(task)
            elapsed = time.time() - t0
            print(f"  [{i:>2}/{len(tasks)}] {sym:>8}  {len(res):>4} rezultate  "
                  f"{elapsed:.0f}s ({elapsed/3600:.2f}h) elapsed")
            all_results.extend(res)

    elapsed_total = time.time() - t0
    print(f"\nFINIT: {len(all_results)} rezultate in {elapsed_total/3600:.2f} ore")

    if not all_results:
        print("Niciun rezultat. Verifica CSV-urile in data/.")
        return

    import pandas as pd
    df = pd.DataFrame(all_results)
    df.to_csv(CSV_OUT, index=False, encoding="utf-8")
    print(f"CSV: {CSV_OUT}")

    report(all_results, TXT_OUT)
    print(f"Raport: {TXT_OUT}")


if __name__ == "__main__":
    main()
