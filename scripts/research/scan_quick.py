"""
scan_quick.py — Micro-scan rapid, rezultate in 10-20 minute

Testeaza cele mai probabile configuratii castigatoare:
- pw=[6,8,10,12,14], expire=4
- dir=[LONG, BOTH]
- RSI=[on, off]
- Strategii: pb_only / pb+flag / pb+IB / all (fara BE pt viteza)
- Standalone: flag_only / f+IB
= 5×1×2×2×4 + 2×2×2 = 80 + 8 = 88 combos/piata

Single-threaded (fara Pool overhead) → primele rezultate in ~30s per piata.
Fiecare piata e afisata imediat dupa finalizare.
"""

import sys, os, json, math, time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from backtest import DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol_tf
from engine.portfolio import run_portfolio
import strategy.structure as _struct
import pandas as pd
import numpy as np

OUT_DIR = os.path.join(ROOT, "scripts", "research")
TXT_OUT = os.path.join(OUT_DIR, "quick_scan_report.txt")

with open(os.path.join(ROOT, "config", "standard_profile.json"), encoding="utf-8") as f:
    BASE_CFG = json.load(f)

SPREADS = {
    "EURUSD": 0.5, "GBPUSD": 0.8, "USDJPY": 0.6, "USDCHF": 1.0, "USDCAD": 1.2,
    "AUDJPY": 1.2, "NZDJPY": 1.5, "CHFJPY": 1.8, "EURJPY": 1.5,
    "EURAUD": 1.5, "EURCAD": 1.5, "GBPAUD": 2.0, "GBPCAD": 2.0,
    "AUDCAD": 1.5, "AUDNZD": 1.5, "XRPUSD": 0.003,
}

TARGETS = [
    "EURUSD","AUDJPY","USDCHF","XRPUSD","EURCAD","USDJPY",
    "GBPCAD","USDCAD","EURAUD","EURJPY","CHFJPY","GBPUSD",
    "GBPAUD","AUDCAD","NZDJPY","AUDNZD",
]

PW_LIST = [6, 8, 10, 12, 14]
DIR_LIST = ["LONG", "BOTH"]

RSI_PRESETS = [
    {"name": "rsi_on",  "buy_min": 40, "buy_max": 65, "sell_min": 35, "sell_max": 60, "enabled": True},
    {"name": "rsi_off", "buy_min": 30, "buy_max": 70, "sell_min": 30, "sell_max": 70, "enabled": False},
]

STRAT_COMBOS = {
    "pb_only":  {"flag": False, "ib": False},
    "pb+flag":  {"flag": True,  "ib": False},
    "pb+IB":    {"flag": False, "ib": True},
    "all":      {"flag": True,  "ib": True},
}

SA_COMBOS = {
    "flag_only": {"flag": True,  "ib": False},
    "f+IB":      {"flag": True,  "ib": True},
}

MIN_TRADES = 40
MIN_TEST_T = 20


def score_fn(te, tt, dd):
    if te <= 0 or tt < MIN_TEST_T:
        return -999.0
    return te * math.sqrt(tt) - max(0, (-dd - 35) * 0.015)


def make_cfg(rsi_p):
    cfg = json.loads(json.dumps(BASE_CFG))
    cfg["optional_criteria"]["rsi"]["enabled"]           = rsi_p["enabled"]
    cfg["optional_criteria"]["rsi"]["buy_min"]           = rsi_p["buy_min"]
    cfg["optional_criteria"]["rsi"]["buy_max"]           = rsi_p["buy_max"]
    cfg["optional_criteria"]["rsi"]["sell_min"]          = rsi_p["sell_min"]
    cfg["optional_criteria"]["rsi"]["sell_max"]          = rsi_p["sell_max"]
    cfg["optional_criteria"]["ema_alignment"]["enabled"] = True
    cfg["optional_criteria"]["body_strength"]            = {"enabled": False, "min_atr_ratio": 0.15}
    cfg["reward_ladder"]["rr_if_3_criteria"] = 2.5
    cfg["reward_ladder"]["rr_if_4_criteria"] = 3.5
    cfg["reward_ladder"]["rr_if_5_criteria"] = 4.5
    cfg["reward_ladder"]["rr_if_6_criteria"] = 5.5
    cfg["reward_ladder"]["threshold_mid"] = 1
    cfg["reward_ladder"]["threshold_top"] = 2
    cfg["reward_ladder"]["threshold_max"] = 3
    cfg["account"]["risk_per_trade_pct"]              = 1.0
    cfg["account"]["risk_per_trade_pct_all_criteria"] = 1.2
    return cfg


def make_params(symbol, direction, pw, strat):
    return {
        "spread_pips": {symbol: SPREADS.get(symbol, 1.5)},
        "leverage": 30, "start_balance": 1000,
        "expire_bars": 4, "pullback_window": pw,
        "depth_range": None, "skip_monday": False,
        "skip_hours": (), "atr_max_pips": {},
        "max_day_consec_losses": 3, "corr_pairs": {},
        "max_pos_per_symbol": 1, "min_bars_between_same_symbol": 0,
        "symbol_sessions": {}, "symbol_skip_hours": {},
        "skip_weekdays": set(), "only_long": (direction == "LONG"),
        "be_cfg": {"enabled": False, "phase2_enabled": True,
                   "trigger_pct": 80, "lock1_pct": 30, "lock2_pct": 50, "phase2_zone_pct": 40},
        "flag_cfg":       {"enabled": strat["flag"], "r_ratio": 2.5, "risk_pct": 0.01},
        "inside_bar_cfg": {"enabled": strat["ib"],   "r_ratio": 2.0, "risk_pct": 0.01},
    }


def run_one(symbol, df, cfg, params, extra):
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
        return {
            "symbol": symbol,
            "total_t": len(df_t), "test_t": len(test), "train_t": len(train),
            "total_exp": round(float(df_t["R"].mean()), 4),
            "train_exp": round(float(train["R"].mean()) if len(train) else 0, 4),
            "test_exp":  round(te, 4), "dd": round(dd, 1),
            "score":     round(score_fn(te, len(test), dd), 4),
            "pb_t": sig.get("pullback", 0), "flag_t": sig.get("flag", 0),
            "ib_t": sig.get("inside_bar", 0),
            "split": str(split.date()), **extra,
        }
    except Exception:
        return None


def scan_symbol(symbol):
    src = CsvDataSource(DATA_DIR)
    try:
        df = prepare_symbol_tf(src, symbol, BASE_CFG, "M15", "M30")
    except Exception:
        return []
    if df is None or len(df) < 500:
        return []

    results = []

    # ── Pullback sweep ─────────────────────────────────────────────────────────
    for direction in DIR_LIST:
        for rsi_p in RSI_PRESETS:
            cfg = make_cfg(rsi_p)
            for pw in PW_LIST:
                for sn, strat in STRAT_COMBOS.items():
                    params = make_params(symbol, direction, pw, strat)
                    r = run_one(symbol, df, cfg, params, {
                        "part": "pullback", "direction": direction,
                        "pw": pw, "strategy": sn, "rsi": rsi_p["name"],
                    })
                    if r: results.append(r)

    # ── Standalone ─────────────────────────────────────────────────────────────
    orig = _struct.detect_setup
    _struct.detect_setup = lambda *a, **k: None
    try:
        for direction in DIR_LIST:
            for rsi_p in RSI_PRESETS:
                cfg = make_cfg(rsi_p)
                for sn, strat in SA_COMBOS.items():
                    params = make_params(symbol, direction, 10, strat)
                    r = run_one(symbol, df, cfg, params, {
                        "part": "standalone", "direction": direction,
                        "pw": 0, "strategy": sn, "rsi": rsi_p["name"],
                    })
                    if r: results.append(r)
    finally:
        _struct.detect_setup = orig

    return results


def print_symbol_results(sym, results, lines_acc):
    if not results:
        msg = f"  {sym:>8}: niciun rezultat valid"
        print(msg); lines_acc.append(msg)
        return

    df = pd.DataFrame(results)
    pos = df[df["test_exp"] > 0]
    best = (pos if not pos.empty else df).nlargest(1, "score").iloc[0]
    top5 = (pos if not pos.empty else df).nlargest(5, "score")

    target = ">>TARGET<<" if float(best["test_exp"]) >= 0.4 else "sub target"
    hdr = (f"\n  {'─'*110}\n"
           f"  {sym:>8}  {len(results)} teste  |  "
           f"BEST: {str(best.get('strategy','?')):>8}  "
           f"pw={int(best.get('pw',0))}  dir={str(best.get('direction','?')):>4}  "
           f"RSI={str(best.get('rsi','?')):<7}  "
           f"TRAIN={float(best['train_exp']):>+7.4f}R  TEST={float(best['test_exp']):>+7.4f}R  "
           f"{int(best['test_t'])}t  DD={float(best['dd']):.1f}%  [{target}]")
    print(hdr); lines_acc.append(hdr)

    for i, (_, r) in enumerate(top5.iterrows(), 1):
        line = (f"         {i}. [{str(r.get('part','?')):>10}]  "
                f"{str(r.get('strategy','?')):>10}  "
                f"pw={int(r.get('pw',0))}  dir={str(r.get('direction','?')):>4}  "
                f"RSI={str(r.get('rsi','?')):<7}  "
                f"TRAIN={float(r['train_exp']):>+7.4f}R  TEST={float(r['test_exp']):>+7.4f}R  "
                f"{int(r['test_t'])}t  DD={float(r['dd']):.1f}%  score={float(r['score']):.3f}")
        print(line); lines_acc.append(line)


def main():
    print(f"\n{'='*110}")
    print(f"QUICK SCAN  --  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Piete: {len(TARGETS)} | Single-threaded (rezultate imediate per piata)")
    print(f"Combos/piata: {len(DIR_LIST)*len(RSI_PRESETS)*len(PW_LIST)*len(STRAT_COMBOS) + len(DIR_LIST)*len(RSI_PRESETS)*len(SA_COMBOS)}")
    print(f"{'='*110}\n")

    t0 = time.time()
    all_results = []
    lines = []
    header = (f"QUICK SCAN  --  {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
              f"pw=[6,8,10,12,14]  expire=4  dir=[LONG,BOTH]  RSI=[on,off]  "
              f"strat=[pb/pb+f/pb+IB/all] + standalone[flag/f+IB]\n")
    lines.append(header)
    print(header)

    achieved, missed = [], []

    for sym in TARGETS:
        t1 = time.time()
        print(f"  Procesez {sym}...", end="", flush=True)
        results = scan_symbol(sym)
        elapsed = time.time() - t1
        print(f" {len(results)} rezultate ({elapsed:.0f}s)")
        all_results.extend(results)
        print_symbol_results(sym, results, lines)

        if results:
            df_r = pd.DataFrame(results)
            best_te = float(df_r["test_exp"].max())
            (achieved if best_te >= 0.4 else missed).append(sym)

    elapsed_total = time.time() - t0
    summary = (f"\n{'='*110}\n"
               f"TOTAL: {len(all_results)} rezultate in {elapsed_total:.0f}s ({elapsed_total/60:.1f} min)\n"
               f"ATINS >= +0.4R: {len(achieved)}  --  {', '.join(achieved) or 'niciunul'}\n"
               f"Sub target:     {len(missed)}   --  {', '.join(missed) or 'niciunul'}\n")
    print(summary); lines.append(summary)

    # Salveaza raport
    with open(TXT_OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Raport: {TXT_OUT}")

    # Salveaza CSV
    if all_results:
        import csv
        csv_out = os.path.join(OUT_DIR, "quick_scan_results.csv")
        fields = list(all_results[0].keys())
        with open(csv_out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(all_results)
        print(f"CSV: {csv_out}")


if __name__ == "__main__":
    main()
