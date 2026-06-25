"""
Test BTCUSD cu filtrele S3 validate + variante de strategii (flag, IB, BE).

Filtrele S3 validate: skip Sat, skip ore 10-14 si 19-23 UTC (era Romania +2h)
pw=8, expire=4, BOTH, M15+M30

Ruleaza: python scripts/research/btc_strategy_variants.py
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
import numpy as np
from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol_tf
from engine.portfolio import run_portfolio

# Filtrele validate S3 (UTC+2 Romania)
# skip Sat (5=Sambata in weekday 0=Lun)
# skip ore 12-16h si 21-01h Romania = 10-14h si 19-23h UTC
S3_SKIP_WEEKDAYS = {5}       # Sambata
S3_SKIP_HOURS    = (12, 13, 14, 15, 21, 22, 23, 0, 1)   # ore locale Romania

with open(CONFIG) as f:
    BASE_CFG = json.load(f)

src = CsvDataSource(DATA_DIR)
df_btc = prepare_symbol_tf(src, "BTCUSD", BASE_CFG, "M15", "M30")

SYMBOL   = "BTCUSD"
SPREAD   = 12.0
PW       = 8
EXPIRE   = 4
DATA     = {SYMBOL: df_btc}

VARIANTS = [
    ("pullback",            {"flag": False, "ib": False, "be": False}),
    ("pullback+flag",       {"flag": True,  "ib": False, "be": False}),
    ("pullback+IB",         {"flag": False, "ib": True,  "be": False}),
    ("pullback+flag+IB",    {"flag": True,  "ib": True,  "be": False}),
    ("pullback+BE",         {"flag": False, "ib": False, "be": True}),
    ("all (flag+IB+BE)",    {"flag": True,  "ib": True,  "be": True}),
]

print("=" * 80)
print("BTCUSD — Variante de strategii cu filtrele S3 validate")
print(f"M15+M30 | BOTH | pw={PW} expire={EXPIRE} | skip Sat + ore 12-16+21-01")
print("=" * 80)

for name, strat in VARIANTS:
    cfg = json.loads(json.dumps(BASE_CFG))
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
        "spread_pips":               {SYMBOL: SPREAD},
        "leverage":                  5,
        "start_balance":             1000,
        "expire_bars":               EXPIRE,
        "pullback_window":           PW,
        "depth_range":               None,
        "skip_monday":               False,
        "skip_hours":                S3_SKIP_HOURS,
        "atr_max_pips":              {},
        "max_day_consec_losses":     3,
        "corr_pairs":                {},
        "max_pos_per_symbol":        1,
        "min_bars_between_same_symbol": 0,
        "symbol_sessions":           {},
        "symbol_skip_hours":         {},
        "skip_weekdays":             S3_SKIP_WEEKDAYS,
        "only_long":                 False,   # BOTH
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

    trades, equity, bal, _, _, _, split = run_portfolio(DATA, cfg, params, verbose=False)

    if not trades:
        print(f"\n{name:25s}: nicio tranzactie")
        continue

    df_t = pd.DataFrame(trades)
    df_t["R"]       = df_t["pnl_usd"] / df_t["risk_usd"]
    df_t["entry_t"] = pd.to_datetime(df_t["time"])

    train = df_t[df_t["entry_t"] < split]
    test  = df_t[df_t["entry_t"] >= split]

    eq_arr  = np.array([e["balance"] for e in equity])
    peak    = np.maximum.accumulate(eq_arr)
    dd      = float(((eq_arr - peak) / peak).min() * 100)
    wr      = int(df_t["outcome"].isin(["win","be_lock","be_lock2"]).sum()) / len(df_t) * 100

    sig_t = df_t["signal_type"].value_counts().to_dict() if "signal_type" in df_t.columns else {}

    print(f"\n{name}")
    print(f"  Total: {len(df_t)}t | WR {wr:.1f}% | Exp {float(df_t['R'].mean()):+.4f}R | DD {dd:.1f}%")
    print(f"  TRAIN {len(train)}t exp {float(train['R'].mean()) if len(train) else 0:+.4f}R | "
          f"TEST {len(test)}t exp {float(test['R'].mean()) if len(test) else 0:+.4f}R | "
          f"Split {split.date()}")
    if sig_t:
        parts = [f"pullback={sig_t.get('pullback',0)}", f"flag={sig_t.get('flag',0)}", f"IB={sig_t.get('inside_bar',0)}"]
        print(f"  Semnale: {', '.join(parts)}")
    print(f"  Balanta: 1000 -> {bal:.2f} USD")

print("\n" + "=" * 80)
