"""
SESSION 14 — CHFJPY, H1+D1, LONG, pw=8
=========================================
Scan full: all (pullback+flag+IB+BE), test +0.0776R, 75t, DD -24.7%, Score 0.672

Rulare:  python live/session14_chfjpy_h1.py
Output:  data/live_signals/session14/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S14-CHFJPY-H1",
    "session_key":  "session14",
    "description":  "CHFJPY H1+D1 LONG pw=8 all | test +0.078R DD -24.7%",

    "markets":      ["CHFJPY"],
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
    "account_fraction": 0.09,
    "risk_pct":         0.01,

    "flag_enabled":         True,
    "flag_r_ratio":         2.5,
    "flag_risk_pct":        0.01,
    "inside_bar_enabled":   True,
    "inside_bar_r_ratio":   2.0,
    "inside_bar_risk_pct":  0.01,
    "break_even_enabled":   True,
    "be_trigger_pct":       80,
    "be_lock1_pct":         30,
    "be_lock2_pct":         50,
    "be_phase2_zone_pct":   40,

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session14"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
