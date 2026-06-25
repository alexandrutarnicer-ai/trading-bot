"""
Scan cu filtre de sesiune pentru piete forex care au potential marginal in scan raw.
Testam ferestre de timp diferite pentru fiecare piata.

Ruleaza: python scripts/research/session_hours_scan.py
"""

import sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol_tf
from engine.portfolio import run_portfolio

MAX_WORKERS = 6

SPREAD_DEFAULTS = {
    "EURUSD": 0.5, "GBPUSD": 0.8, "EURJPY": 1.5, "USDJPY": 0.6,
    "AUDJPY": 1.2, "NZDJPY": 1.5, "USDCHF": 1.0, "USDCAD": 1.2,
    "AUDUSD": 0.7, "GBPJPY": 1.8, "NZDUSD": 1.2, "CADJPY": 1.5,
    "CHFJPY": 1.8, "EURGBP": 0.8, "EURAUD": 1.5, "EURCAD": 1.5,
    "GBPAUD": 2.0, "GBPCAD": 2.0,
    "GER40": 1.0, "US30": 2.0, "US500": 0.5, "UK100": 1.5,
    "XAUUSD": 0.3,
}

# Ferestre de sesiune de testat (start_h, end_h) — ora locala Romania (UTC+2 summer)
SESSION_WINDOWS = {
    "london":     (8, 18),    # Londra
    "ny":         (13, 22),   # New York
    "london_ny":  (12, 18),   # Overlap Londra-NY
    "asian":      (0, 9),     # Sesiune asiatica
    "full":       (6, 22),    # Zi completa
}

# Piete cu TF + directii de testat, pw, expire
TARGETS = [
    # Forex majors
    ("EURUSD",  "M15","M30", ["LONG","BOTH"], [6,8,10], 4),
    ("GBPUSD",  "M15","M30", ["LONG","BOTH"], [6,8,10], 4),
    ("USDJPY",  "M15","M30", ["LONG","BOTH"], [6,8,10], 4),
    ("AUDUSD",  "M15","M30", ["LONG","BOTH"], [6,8],    4),
    ("USDCHF",  "M15","M30", ["LONG","BOTH"], [6,8],    4),
    ("USDCAD",  "M15","M30", ["LONG","BOTH"], [6,8],    4),
    ("NZDUSD",  "M15","M30", ["LONG","BOTH"], [8],      4),
    # JPY crosses
    ("EURJPY",  "M15","M30", ["LONG","BOTH"], [6,8,10], 4),
    ("GBPJPY",  "M15","M30", ["LONG","BOTH"], [8,10],   4),
    ("AUDJPY",  "M15","M30", ["LONG","BOTH"], [6,8],    4),
    ("NZDJPY",  "M15","M30", ["BOTH"],        [8],      4),
    ("CADJPY",  "M15","M30", ["BOTH"],        [8],      4),
    ("CHFJPY",  "M15","M30", ["LONG","BOTH"], [8],      4),
    # EUR/GBP crosses
    ("EURGBP",  "M15","M30", ["BOTH"],        [8],      4),
    ("EURAUD",  "M15","M30", ["LONG","BOTH"], [6,8],    4),
    ("EURCAD",  "M15","M30", ["BOTH"],        [8],      4),
    ("GBPAUD",  "M15","M30", ["BOTH"],        [8],      4),
    ("GBPCAD",  "M15","M30", ["BOTH"],        [8],      4),
    # Indici
    ("GER40",   "M15","M30", ["LONG"],        [6,8],    4),
    ("US30",    "M15","M30", ["LONG"],        [8,10],   4),
    ("US500",   "M15","M30", ["LONG","BOTH"], [6,8],    4),
    ("UK100",   "M15","M30", ["LONG"],        [8],      4),
    # Gold
    ("XAUUSD",  "M15","M30", ["LONG","BOTH"], [6,8],    4),
    # H1+D1
    ("USDCHF",  "H1","D1",   ["LONG","BOTH"], [6,8],    4),
    ("GER40",   "H1","D1",   ["LONG"],        [6,8],    4),
    ("US30",    "H1","D1",   ["LONG"],        [8],      4),
    ("XAUUSD",  "H1","D1",   ["LONG","BOTH"], [8],      4),
]

_cfg_cache = {}
_df_cache  = {}
_lock = threading.Lock()

def get_cfg():
    with _lock:
        if "cfg" not in _cfg_cache:
            with open(CONFIG) as f:
                _cfg_cache["cfg"] = json.load(f)
    return json.loads(json.dumps(_cfg_cache["cfg"]))

def get_df(symbol, entry_tf, trend_tf):
    key = f"{symbol}_{entry_tf}_{trend_tf}"
    with _lock:
        if key in _df_cache:
            return _df_cache[key]
    src = CsvDataSource(DATA_DIR)
    path_e = os.path.join(DATA_DIR, f"{symbol}_{entry_tf}.csv")
    path_t = os.path.join(DATA_DIR, f"{symbol}_{trend_tf}.csv")
    if not (os.path.exists(path_e) and os.path.exists(path_t)):
        with _lock: _df_cache[key] = None
        return None
    try:
        df = prepare_symbol_tf(src, symbol, get_cfg(), entry_tf, trend_tf)
    except Exception:
        df = None
    with _lock: _df_cache[key] = df
    return df

def run_one(symbol, entry_tf, trend_tf, direction, pw, expire, sess_name, sess_start, sess_end):
    df = get_df(symbol, entry_tf, trend_tf)
    if df is None or len(df) < 300: return None

    skip_h = tuple(h % 24 for h in range(0, 24) if not (sess_start <= h < sess_end))

    cfg = get_cfg()
    cfg["optional_criteria"]["rsi"]["enabled"]           = True
    cfg["optional_criteria"]["ema_alignment"]["enabled"] = True
    cfg["optional_criteria"]["body_strength"]            = {"enabled": False}
    cfg["reward_ladder"]["rr_if_3_criteria"]  = 2.5
    cfg["reward_ladder"]["rr_if_4_criteria"]  = 3.5
    cfg["reward_ladder"]["rr_if_5_criteria"]  = 4.5
    cfg["reward_ladder"]["rr_if_6_criteria"]  = 5.5
    cfg["reward_ladder"]["threshold_mid"] = 1
    cfg["reward_ladder"]["threshold_top"] = 2
    cfg["reward_ladder"]["threshold_max"] = 3
    cfg["account"]["risk_per_trade_pct"]              = 1.0
    cfg["account"]["risk_per_trade_pct_all_criteria"] = 1.2

    params = {
        "spread_pips":               {symbol: SPREAD_DEFAULTS.get(symbol, 1.5)},
        "leverage":                  30,
        "start_balance":             1000,
        "expire_bars":               expire,
        "pullback_window":           pw,
        "depth_range":               None,
        "skip_monday":               False,
        "skip_hours":                skip_h,
        "atr_max_pips":              {},
        "max_day_consec_losses":     3,
        "corr_pairs":                {},
        "max_pos_per_symbol":        1,
        "min_bars_between_same_symbol": 0,
        "symbol_sessions":           {},
        "symbol_skip_hours":         {},
        "skip_weekdays":             {5} if symbol not in ("BTCUSD","ETHUSD","SOLUSD","XRPUSD") else set(),
        "only_long":                 (direction == "LONG"),
        "be_cfg":         {"enabled": False, "phase2_enabled": True, "trigger_pct": 80, "lock1_pct": 30, "lock2_pct": 50, "phase2_zone_pct": 40},
        "flag_cfg":       {"enabled": False, "r_ratio": 2.5, "risk_pct": 0.01},
        "inside_bar_cfg": {"enabled": False, "r_ratio": 2.0, "risk_pct": 0.01},
    }

    try:
        trades, equity, bal, _, _, _, split = run_portfolio({symbol: df}, cfg, params, verbose=False)
    except Exception:
        return None

    if not trades: return None
    df_t = pd.DataFrame(trades)
    df_t["R"]       = df_t["pnl_usd"] / df_t["risk_usd"]
    df_t["entry_t"] = pd.to_datetime(df_t["time"])
    if len(df_t) < 25: return None

    train = df_t[df_t["entry_t"] < split]
    test  = df_t[df_t["entry_t"] >= split]
    if len(test) < 15: return None

    eq    = np.array([e["balance"] for e in equity])
    peak  = np.maximum.accumulate(eq)
    dd    = float(((eq - peak) / peak).min() * 100) if len(eq) > 1 else 0.0

    return {
        "symbol": symbol, "entry_tf": entry_tf, "trend_tf": trend_tf,
        "direction": direction, "pw": pw, "expire": expire,
        "session": sess_name, "sess_start": sess_start, "sess_end": sess_end,
        "total_t": len(df_t),
        "train_exp": round(float(train["R"].mean()) if len(train) else 0, 4),
        "test_exp":  round(float(test["R"].mean())  if len(test)  else 0, 4),
        "test_t":    len(test),
        "dd":        round(dd, 1),
        "score":     round((float(test["R"].mean()) if len(test) else -99) * math.sqrt(len(test)), 4),
    }

def main():
    tasks = []
    for (sym, etf, ttf, dirs, pws, exp) in TARGETS:
        for direction in dirs:
            for pw in pws:
                for sname, (ss, se) in SESSION_WINDOWS.items():
                    tasks.append((sym, etf, ttf, direction, pw, exp, sname, ss, se))

    print(f"Session Hours Scan: {len(tasks)} teste su {MAX_WORKERS} workeri")
    results = []
    done = 0
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import time
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(run_one, *t): t for t in tasks}
        for fut in as_completed(futures):
            done += 1
            r = fut.result()
            if r: results.append(r)
            if done % 100 == 0 or done == len(tasks):
                print(f"  [{done}/{len(tasks)}] valid={len(results)} | {time.time()-t0:.0f}s")

    if not results:
        print("Niciun rezultat.")
        return

    df = pd.DataFrame(results).sort_values("score", ascending=False)
    out = os.path.join(os.path.dirname(__file__), "session_hours_results.csv")
    df.to_csv(out, index=False)
    print(f"\nSalvat: {out}")

    # Per simbol: top 3
    print("\n" + "=" * 90)
    print("TOP CONFIG PER PIATA (cu filtre sesiune)")
    print("=" * 90)
    for sym in sorted(df["symbol"].unique()):
        sub = df[(df["symbol"] == sym) & (df["test_exp"] > 0)].head(3)
        if len(sub) == 0:
            print(f"\n{sym}: niciun config pozitiv pe test")
            continue
        print(f"\n{sym}:")
        for _, row in sub.iterrows():
            print(f"  {row['entry_tf']}+{row['trend_tf']} {row['direction']:4s} pw={row['pw']} "
                  f"sess={row['session']:10s} ({row['sess_start']:02d}-{row['sess_end']:02d}h) | "
                  f"test {row['test_exp']:+.4f}R/{row['test_t']}t | "
                  f"dd={row['dd']:.1f}% | score={row['score']:.3f}")

    # Top 20 global
    print("\n" + "=" * 90)
    print("TOP 20 GLOBAL (session hours scan)")
    print("=" * 90)
    top = df[df["test_exp"] > 0].head(20)
    for i, (_, row) in enumerate(top.iterrows(), 1):
        print(f"  {i:2d}. {row['symbol']:8s} {row['entry_tf']}+{row['trend_tf']} "
              f"{row['direction']:4s} pw={row['pw']} sess={row['session']:10s} "
              f"({row['sess_start']:02d}-{row['sess_end']:02d}h) | "
              f"test {row['test_exp']:+.4f}R/{row['test_t']}t | score={row['score']:.3f}")

if __name__ == "__main__":
    main()
