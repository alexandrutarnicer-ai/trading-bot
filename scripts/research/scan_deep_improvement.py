"""
scan_deep_improvement.py — Sweep complet pentru imbunatatire sesiuni sub 0.4R

PARTE 1: Pullback sweep (pw / expire / dir / RSI / strategie) × 2 TF perechi
PARTE 2: Pullback DISABLED — flag-only / IB-only standalone
PARTE 3: Session hours (London / NY / no-US) pentru M15

Estimare durata:
  ~316 combos per piata × 18.5s/combo = ~5800s per piata
  16 piete / 4 workeri = 4 piete secvential per worker = ~6.5 ore

Output:
  scripts/research/deep_scan_results.csv
  scripts/research/deep_scan_report.txt

Rulare: python scripts/research/scan_deep_improvement.py
"""

import sys, os, json, math, time
from datetime import datetime
from multiprocessing import Pool, cpu_count

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

OUT_DIR = os.path.join(ROOT, "scripts", "research")
CSV_OUT = os.path.join(OUT_DIR, "deep_scan_results.csv")
TXT_OUT = os.path.join(OUT_DIR, "deep_scan_report.txt")

# ── Piete de analizat ─────────────────────────────────────────────────────────
TARGETS = {
    "EURUSD":  [("M15","M30"), ("H1","D1")],
    "AUDJPY":  [("M15","M30"), ("H1","D1")],
    "USDCHF":  [("M15","M30"), ("H1","D1")],
    "XRPUSD":  [("M15","M30")],
    "EURCAD":  [("M15","M30"), ("H1","D1")],
    "USDJPY":  [("M15","M30"), ("H1","D1")],
    "GBPCAD":  [("M15","M30"), ("H1","D1")],
    "USDCAD":  [("M15","M30"), ("H1","D1")],
    "EURAUD":  [("M15","M30"), ("H1","D1")],
    "EURJPY":  [("M15","M30"), ("H1","D1")],
    "CHFJPY":  [("M15","M30"), ("H1","D1")],
    "GBPUSD":  [("M15","M30"), ("H1","D1")],
    "GBPAUD":  [("M15","M30"), ("H1","D1")],
    "AUDCAD":  [("M15","M30"), ("H1","D1")],
    "NZDJPY":  [("M15","M30"), ("H1","D1")],
    "AUDNZD":  [("M15","M30"), ("H1","D1")],
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

# ── Spatiu parametri (optimizat pentru ~6-7 ore overnight) ───────────────────

PW_LIST     = [6, 8, 10, 12, 14]
EXPIRE_LIST = [3, 4, 5]
DIR_LIST    = ["LONG", "BOTH"]

# RSI: standard cu filtru activ sau dezactivat complet
RSI_PRESETS = [
    {"name": "rsi_on",  "buy_min": 40, "buy_max": 65, "sell_min": 35, "sell_max": 60, "enabled": True},
    {"name": "rsi_off", "buy_min": 30, "buy_max": 70, "sell_min": 30, "sell_max": 70, "enabled": False},
]

STRATEGY_COMBOS = {
    "pullback":         {"flag": False, "ib": False, "be": False},
    "pullback+flag":    {"flag": True,  "ib": False, "be": False},
    "pullback+IB":      {"flag": False, "ib": True,  "be": False},
    "pullback+flag+IB": {"flag": True,  "ib": True,  "be": False},
    "pullback+BE":      {"flag": False, "ib": False, "be": True},
    "all":              {"flag": True,  "ib": True,  "be": True},
}

# Standalone (fara pullback): flag si/sau IB singure
STANDALONE_COMBOS = {
    "flag_only":  {"flag": True,  "ib": False, "be": False},
    "IB_only":    {"flag": False, "ib": True,  "be": False},
    "flag+IB":    {"flag": True,  "ib": True,  "be": False},
    "flag+IB+BE": {"flag": True,  "ib": True,  "be": True},
}

BE_STD = {"trigger": 80, "lock1": 30, "lock2": 50, "zone": 40}

# Hours sweep (M15 only) — evita ore cu noise crescut
HOURS_PRESETS = [
    {"name": "no_us_prime", "skip": set(range(13, 21))},  # evita NY prime 13-21h
    {"name": "london_ny",   "skip": set(range(0, 7)) | set(range(20, 24))},  # 7-20h
    {"name": "eu_only",     "skip": set(range(0, 7)) | set(range(16, 24))},  # 7-16h
]


def score_fn(test_exp, test_trades, dd):
    if test_exp <= 0 or test_trades < MIN_TEST_T:
        return -999.0
    pen = max(0, (-dd - 35) * 0.015)
    return test_exp * math.sqrt(test_trades) - pen


# ─────────────────────────────────────────────────────────────────────────────
# Worker (module-level pentru pickling pe Windows)
# ─────────────────────────────────────────────────────────────────────────────

def process_market(task):
    symbol, tf_list, cfg_path, data_dir, spreads = task

    import json, math, sys, os
    import pandas as pd
    import numpy as np

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, root)

    from adapters.csv_source import CsvDataSource
    from strategy.preparation import prepare_symbol_tf
    from engine.portfolio import run_portfolio
    import strategy.structure as _struct

    with open(cfg_path, encoding="utf-8") as f:
        base_cfg = json.load(f)

    src    = CsvDataSource(data_dir)
    spread = spreads.get(symbol, 1.5)
    results = []

    # Pre-incarca toate TF-urile o singura data
    dfs = {}
    for entry_tf, trend_tf in tf_list:
        csv_e = os.path.join(data_dir, f"{symbol}_{entry_tf}.csv")
        csv_t = os.path.join(data_dir, f"{symbol}_{trend_tf}.csv")
        if not (os.path.exists(csv_e) and os.path.exists(csv_t)):
            continue
        try:
            df = prepare_symbol_tf(src, symbol, base_cfg, entry_tf, trend_tf)
            if df is not None and len(df) >= 500:
                dfs[(entry_tf, trend_tf)] = df
        except Exception:
            pass

    if not dfs:
        return results

    def make_cfg(rsi_p, ema_en=True):
        cfg = json.loads(json.dumps(base_cfg))
        cfg["optional_criteria"]["rsi"]["enabled"]           = rsi_p["enabled"]
        cfg["optional_criteria"]["rsi"]["buy_min"]           = rsi_p["buy_min"]
        cfg["optional_criteria"]["rsi"]["buy_max"]           = rsi_p["buy_max"]
        cfg["optional_criteria"]["rsi"]["sell_min"]          = rsi_p["sell_min"]
        cfg["optional_criteria"]["rsi"]["sell_max"]          = rsi_p["sell_max"]
        cfg["optional_criteria"]["ema_alignment"]["enabled"] = ema_en
        cfg["optional_criteria"]["body_strength"]            = {"enabled": False, "min_atr_ratio": 0.15}
        cfg["reward_ladder"]["rr_if_3_criteria"]  = 2.5
        cfg["reward_ladder"]["rr_if_4_criteria"]  = 3.5
        cfg["reward_ladder"]["rr_if_5_criteria"]  = 4.5
        cfg["reward_ladder"]["rr_if_6_criteria"]  = 5.5
        cfg["reward_ladder"]["threshold_mid"]     = 1
        cfg["reward_ladder"]["threshold_top"]     = 2
        cfg["reward_ladder"]["threshold_max"]     = 3
        cfg["account"]["risk_per_trade_pct"]              = 1.0
        cfg["account"]["risk_per_trade_pct_all_criteria"] = 1.2
        return cfg

    def make_params(direction, pw, expire, strat, be=None, skip_hours=()):
        be = be or BE_STD
        return {
            "spread_pips":                   {symbol: spread},
            "leverage":                      30,
            "start_balance":                 1000,
            "expire_bars":                   expire,
            "pullback_window":               pw,
            "depth_range":                   None,
            "skip_monday":                   False,
            "skip_hours":                    skip_hours,
            "atr_max_pips":                  {},
            "max_day_consec_losses":         3,
            "corr_pairs":                    {},
            "max_pos_per_symbol":            1,
            "min_bars_between_same_symbol":  0,
            "symbol_sessions":               {},
            "symbol_skip_hours":             {},
            "skip_weekdays":                 set(),
            "only_long":                     (direction == "LONG"),
            "be_cfg":  {"enabled": strat["be"], "phase2_enabled": True,
                        "trigger_pct": be["trigger"], "lock1_pct": be["lock1"],
                        "lock2_pct": be["lock2"], "phase2_zone_pct": be["zone"]},
            "flag_cfg":         {"enabled": strat["flag"], "r_ratio": 2.5, "risk_pct": 0.01},
            "inside_bar_cfg":   {"enabled": strat["ib"],   "r_ratio": 2.0, "risk_pct": 0.01},
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
            eq  = np.array([e["balance"] for e in equity])
            pk  = np.maximum.accumulate(eq)
            dd  = float(((eq - pk) / pk).min() * 100) if len(eq) > 1 else 0.0
            sig = (df_t["signal_type"].value_counts().to_dict()
                   if "signal_type" in df_t.columns else {})
            row = {
                "symbol":     symbol,
                "total_t":    len(df_t),
                "train_t":    len(train),
                "test_t":     len(test),
                "total_exp":  round(float(df_t["R"].mean()), 4),
                "train_exp":  round(float(train["R"].mean()) if len(train) else 0, 4),
                "test_exp":   round(float(test["R"].mean())  if len(test)  else 0, 4),
                "dd":         round(dd, 1),
                "final_bal":  round(bal, 2),
                "score":      round(score_fn(float(test["R"].mean()) if len(test) else 0,
                                             len(test), dd), 4),
                "pb_t":       sig.get("pullback", 0),
                "flag_t":     sig.get("flag", 0),
                "ib_t":       sig.get("inside_bar", 0),
                "split":      str(split.date()),
            }
            row.update(cols)
            return row
        except Exception:
            return None

    # ── PARTE 1: Pullback sweep ───────────────────────────────────────────────
    for (etf, ttf), df in dfs.items():
        for direction in DIR_LIST:
            for rsi_p in RSI_PRESETS:
                cfg = make_cfg(rsi_p)
                for pw in PW_LIST:
                    for expire in EXPIRE_LIST:
                        for sn, strat in STRATEGY_COMBOS.items():
                            params = make_params(direction, pw, expire, strat)
                            r = run_one(cfg, params, df, {
                                "part": "pullback", "entry_tf": etf, "trend_tf": ttf,
                                "direction": direction, "pw": pw, "expire": expire,
                                "strategy": sn, "rsi": rsi_p["name"],
                                "ema": True, "hours": "all",
                            })
                            if r: results.append(r)

    # ── PARTE 2: Standalone (pullback disabled) ───────────────────────────────
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
                            "part": "standalone", "entry_tf": etf, "trend_tf": ttf,
                            "direction": direction, "pw": 0, "expire": 4,
                            "strategy": sn, "rsi": rsi_p["name"],
                            "ema": True, "hours": "all",
                        })
                        if r: results.append(r)
    finally:
        _struct.detect_setup = orig

    # ── PARTE 3: Hours sweep (M15 only, pw=10, expire=4) ─────────────────────
    m15_df = dfs.get(("M15", "M30"))
    if m15_df is not None:
        for direction in DIR_LIST:
            rsi_std = RSI_PRESETS[0]
            cfg = make_cfg(rsi_std)
            for hp in HOURS_PRESETS:
                for sn, strat in [("pullback",       STRATEGY_COMBOS["pullback"]),
                                   ("pullback+flag",  STRATEGY_COMBOS["pullback+flag"]),
                                   ("all",            STRATEGY_COMBOS["all"])]:
                    params = make_params(direction, 10, 4, strat, skip_hours=hp["skip"])
                    r = run_one(cfg, params, m15_df, {
                        "part": "hours", "entry_tf": "M15", "trend_tf": "M30",
                        "direction": direction, "pw": 10, "expire": 4,
                        "strategy": sn, "rsi": "rsi_on", "ema": True,
                        "hours": hp["name"],
                    })
                    if r: results.append(r)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────────────────

def report(all_results, txt_path):
    import pandas as pd
    df = pd.DataFrame(all_results)
    if df.empty:
        print("Niciun rezultat valid.")
        return df

    W = 120
    lines = []
    lines.append("=" * W)
    lines.append(f"DEEP IMPROVEMENT SCAN  --  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Total teste valide: {len(df)} | Simboluri: {df['symbol'].nunique()}")
    lines.append("=" * W)

    # ── Best per simbol ───────────────────────────────────────────────────────
    lines.append("\n## BEST CONFIG PER SIMBOL (TARGET: test_exp >= +0.4R)\n")
    hdr = f"  {'Simbol':>8}  {'Part':>10}  {'TF':>8}  {'Dir':>4}  {'pw':>3}  {'exp':>5}  "
    hdr += f"{'Strategy':>20}  {'RSI':>7}  {'Hours':>10}  "
    hdr += f"{'TRAIN':>7}  {'TEST':>7}  {'Tt':>4}  {'DD':>6}  {'Score':>7}  STATUS"
    lines.append(hdr)

    achieved, missed = [], []

    for sym in sorted(df["symbol"].unique()):
        sub = df[df["symbol"] == sym]
        pos = sub[sub["test_exp"] > 0]
        best = (pos if not pos.empty else sub).nlargest(1, "score").iloc[0]

        target = "TARGET >>" if float(best["test_exp"]) >= 0.4 else "sub target"
        (achieved if float(best["test_exp"]) >= 0.4 else missed).append(sym)

        etf = best.get("entry_tf", "?")
        ttf = best.get("trend_tf", "?")
        lines.append(
            f"  {sym:>8}  {str(best.get('part','?')):>10}  {etf}+{ttf:>3}  "
            f"{str(best.get('direction','?')):>4}  {int(best.get('pw',0)):>3}  "
            f"{float(best.get('total_exp',0)):>+5.3f}R  "
            f"{str(best.get('strategy','?')):>20}  {str(best.get('rsi','?')):>7}  "
            f"{str(best.get('hours','all')):>10}  "
            f"{float(best['train_exp']):>+7.4f}R  {float(best['test_exp']):>+7.4f}R  "
            f"{int(best['test_t']):>4}t  {float(best['dd']):>5.1f}%  "
            f"{float(best['score']):>7.3f}  {target}"
        )

    lines.append(f"\n  ATINS >= +0.4R: {len(achieved)} -- {', '.join(achieved)}")
    lines.append(f"  Sub target:     {len(missed)} -- {', '.join(missed)}")

    # ── Top 10 per simbol ─────────────────────────────────────────────────────
    lines.append("\n" + "=" * W)
    lines.append("## TOP 10 CONFIG PER SIMBOL")

    for sym in sorted(df["symbol"].unique()):
        sub = df[df["symbol"] == sym]
        top = sub[sub["test_exp"] > 0].nlargest(10, "score")
        if top.empty:
            top = sub.nlargest(5, "score")
        lines.append(f"\n  --- {sym}  ({len(sub)} teste) ---")
        for i, (_, row) in enumerate(top.iterrows(), 1):
            etf = row.get("entry_tf", "?")
            ttf = row.get("trend_tf", "?")
            lines.append(
                f"  {i:>2}. [{str(row.get('part','?')):>10}]  {etf}+{ttf:>3}  "
                f"{str(row.get('direction','?')):>4}  pw={int(row.get('pw',0))}  "
                f"exp={float(row.get('total_exp',0)):>+5.3f}R  "
                f"{str(row.get('strategy','?')):>20}  RSI={str(row.get('rsi','?')):>7}  "
                f"hours={str(row.get('hours','all')):<12}  "
                f"TRAIN={float(row['train_exp']):>+7.4f}R  TEST={float(row['test_exp']):>+7.4f}R  "
                f"{int(row['test_t'])}t  DD={float(row['dd']):.1f}%  score={float(row['score']):.3f}"
            )

    # ── Analiza standalone ────────────────────────────────────────────────────
    sa = df[df["part"] == "standalone"]
    lines.append("\n" + "=" * W)
    lines.append("## ANALIZA PULLBACK DISABLED (flag-only / IB-only standalone)")
    if sa.empty:
        lines.append("  Nicio configuratie standalone testata sau niciun rezultat.")
    else:
        good = sa[sa["test_exp"] >= 0.4]
        if good.empty:
            lines.append(f"  Niciun standalone nu atinge +0.4R. Best standalone:")
            top_sa = sa.nlargest(10, "score")
        else:
            lines.append(f"  {len(good)} configuratii standalone cu test_exp >= +0.4R:")
            top_sa = good.nlargest(20, "score")
        for _, row in top_sa.iterrows():
            lines.append(
                f"    {row['symbol']:>8}  {row.get('entry_tf','?')}+{row.get('trend_tf','?'):>3}  "
                f"{str(row.get('direction','?')):>4}  {str(row.get('strategy','?')):>12}  "
                f"RSI={str(row.get('rsi','?')):>7}  "
                f"TRAIN={float(row['train_exp']):>+7.4f}R  TEST={float(row['test_exp']):>+7.4f}R  "
                f"{int(row['test_t'])}t  DD={float(row['dd']):.1f}%  score={float(row['score']):.3f}"
            )

    # ── Concluzie pullback optional ───────────────────────────────────────────
    lines.append("\n" + "=" * W)
    lines.append("## CONCLUZIE: IMPLEMENTARE 'PULLBACK OPTIONAL' (Task 3)")
    lines.append("""
  ENGINE: Flag si Inside Bar sunt deja STANDALONE in engine/portfolio.py.
  Nu depind de detect_setup() — ruleaza pe slot propriu.

  MODIFICARE NECESARA (minima, backward-compatible):
    engine/portfolio.py  — adauga: pullback_enabled = params.get("pullback_enabled", True)
                           conditioneaza linia 230: if pullback_enabled and ...
    live/signal_generator.py — transmite pullback_enabled din session_cfg
    data/profiles/standard.json — "pullback_enabled": true  (default = comportament actual)
    SessionEditor.tsx — toggle in sectiunea Criterii Obligatorii

  IMPACT BASELINE: ZERO (pullback_enabled=True by default → baselines neschimbate)

  CONCLUZIE: Verifica sectiunea STANDALONE de mai sus.
  Daca flag_only / IB_only produc >= +0.4R pe cateva piete → feature util.
  Altfel → pullback ramane obligatoriu pentru edge pozitiv.
""")

    txt = "\n".join(lines)
    print(txt[:3000])   # Afiseaza primele 3000 chars in terminal
    print(f"\n[...] Raport complet in: {txt_path}")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(txt)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    from backtest import DATA_DIR
    cfg_path = os.path.join(ROOT, "config", "standard_profile.json")

    tasks = [
        (sym, tfs, cfg_path, DATA_DIR, SPREAD_DEFAULTS)
        for sym, tfs in TARGETS.items()
    ]

    n_combos_est = len(tasks) * 320  # ~320 combos per piata (aproximare)
    t_est_h = n_combos_est * 18.5 / MAX_WORKERS / 3600

    print(f"\n{'='*60}")
    print(f"DEEP IMPROVEMENT SCAN  --  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Piete: {len(tasks)} | Workeri: {MAX_WORKERS}")
    print(f"Estimare: ~{n_combos_est} teste | ~{t_est_h:.1f} ore")
    print(f"Output: {TXT_OUT}")
    print(f"{'='*60}\n")

    t0 = time.time()
    all_results = []

    if MAX_WORKERS > 1:
        with Pool(MAX_WORKERS) as pool:
            for i, res in enumerate(pool.imap_unordered(process_market, tasks), 1):
                sym = res[0]["symbol"] if res else "?"
                elapsed = time.time() - t0
                print(f"  [{i:>2}/{len(tasks)}] {sym:>8}  {len(res):>4} rezultate  "
                      f"{elapsed:.0f}s elapsed")
                all_results.extend(res)
    else:
        for i, task in enumerate(tasks, 1):
            res = process_market(task)
            elapsed = time.time() - t0
            print(f"  [{i:>2}/{len(tasks)}] {task[0]:>8}  {len(res):>4} rezultate  "
                  f"{elapsed:.0f}s elapsed")
            all_results.extend(res)

    elapsed_total = time.time() - t0
    print(f"\nFINIT: {len(all_results)} rezultate valide in {elapsed_total/3600:.2f} ore")

    if not all_results:
        print("Niciun rezultat. Verifica ca datele CSV exista in data/.")
        return

    import pandas as pd
    df = pd.DataFrame(all_results)
    df.to_csv(CSV_OUT, index=False, encoding="utf-8")
    print(f"CSV: {CSV_OUT}")

    report(all_results, TXT_OUT)
    print(f"\nRaport complet: {TXT_OUT}")


if __name__ == "__main__":
    main()
