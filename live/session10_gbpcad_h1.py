"""
SESSION 10 — GBPCAD, H1+D1, LONG, pw=8
=========================================
Scan full: pullback+flag, test +0.2104R, 32t, DD -23.4%, Score 1.190
Train pozitiv +0.037R.

Rulare:  python live/session10_gbpcad_h1.py
Output:  data/live_signals/session10/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S10-GBPCAD-H1",
    "session_key":  "session10",
    "description":  "GBPCAD H1+D1 LONG pw=8 pullback+flag | test +0.210R DD -23.4%",

    "markets":      ["GBPCAD"],
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

    "flag_enabled":         True,
    "flag_r_ratio":         2.5,
    "flag_risk_pct":        0.01,
    "inside_bar_enabled":   False,

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session10"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
