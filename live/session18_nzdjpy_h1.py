"""
SESSION 18 — NZDJPY, H1+D1, BOTH, pw=8
=========================================
Scan full: pullback+IB, test +0.0015R, 91t, DD -29.9%, Score 0.014
Edge marginal — observare pura.

Rulare:  python live/session18_nzdjpy_h1.py
Output:  data/live_signals/session18/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S18-NZDJPY-H1",
    "session_key":  "session18",
    "description":  "NZDJPY H1+D1 BOTH pw=8 pullback+IB | test +0.002R DD -29.9%",

    "markets":      ["NZDJPY"],
    "symbol_fallbacks": {},

    "entry_tf":    "H1",
    "trend_tf":    "D1",
    "bar_minutes": 60,

    "only_long":       False,
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
    "account_fraction": 0.07,
    "risk_pct":         0.01,

    "flag_enabled":         False,
    "inside_bar_enabled":   True,
    "inside_bar_r_ratio":   2.0,
    "inside_bar_risk_pct":  0.01,

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session18"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
