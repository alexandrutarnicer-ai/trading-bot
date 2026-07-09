"""
m0.validate_runner — dovada ca runner-ul reproduce baseline-urile documentate.

CLAUDE.md fixeaza: portfolio_backtest.py -> S1: 284 trades, Exp +0.025R.
Daca run_with_params, apelat cu ACEIASI parametri ca portfolio_backtest.py,
da 284 trade-uri, atunci apelul de engine din m0 este mecanic corect si
putem avea incredere in run_profile_session pentru toate cele 20 de sesiuni.

Rulare:  python -m m0.validate_runner
"""

import json

from backtest import CONFIG
from m0.session_runner import run_with_params


def validate_portfolio_baseline() -> bool:
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)

    # Parametri IDENTICI cu portfolio_backtest.py (baseline S1: 284 trades).
    params = {
        "spread_pips":           {"EURUSD": 0.5, "GBPUSD": 0.8, "EURJPY": 1.5},
        "leverage":              30,
        "start_balance":         300,
        "expire_bars":           4,
        "pullback_window":       8,
        "depth_range":           None,
        "skip_monday":           True,
        "skip_hours":            (15, 16),
        "atr_max_pips":          {"EURUSD": 7.5},
        "max_day_consec_losses": 3,
        "corr_pairs":            {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD"},
        "only_long":             True,
        "max_pos_per_symbol":    1,
        "symbol_sessions":       {},
        "symbol_skip_hours":     {},
    }
    df = run_with_params(cfg, params, ["EURUSD", "GBPUSD", "EURJPY"])
    n = len(df)
    exp = df["R"].mean() if n else float("nan")
    expected = 284
    ok = (n == expected)
    print(f"portfolio_backtest baseline: {n} trades (asteptat {expected}) | "
          f"expectancy {exp:+.3f}R (asteptat ~+0.025R)")
    print("  " + ("OK — runner corect" if ok else "MISMATCH — verifica engine/mapping"))
    return ok


if __name__ == "__main__":
    ok = validate_portfolio_baseline()
    raise SystemExit(0 if ok else 1)
