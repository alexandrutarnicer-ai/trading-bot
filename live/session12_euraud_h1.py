"""
SESSION 12 — EURAUD, H1+D1, LONG, pw=8
=========================================
Scan full: pullback, test +0.2323R, 21t, DD -18.7%, Score 1.064
Train negativ (-0.110R) — urmareste cu atentie.

Rulare:  python live/session12_euraud_h1.py
Output:  data/live_signals/session12/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S12-EURAUD-H1",
    "session_key":  "session12",
    "description":  "EURAUD H1+D1 LONG pw=8 pullback | test +0.232R DD -18.7%",

    "markets":      ["EURAUD"],
    "symbol_fallbacks": {},

    "entry_tf":    "H1",
    "trend_tf":    "D1",
    "bar_minutes": 60,

    "only_long":       True,
    "pullback_window": 8,

    "session_start": 0,
    "session_end":   24,
    "skip_hours":    (),
    "skip_monday":   False,
    "skip_weekdays": set(),
    "expire_bars":   4,
    "symbol_sessions": {},

    "n_bars_entry": 2000,
    "n_bars_trend": 600,

    "execute_trades":   True,
    "session_capital":  100,
    "account_fraction": 0.08,
    "risk_pct":         0.01,

    "flag_enabled":         False,
    "inside_bar_enabled":   False,

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session12"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
