"""
SESSION 16 — GBPAUD, H1+D1, BOTH, pw=8
=========================================
Scan full: pullback+BE, test +0.0538R, 41t, DD -29.0%, Score 0.345
Scor mic — urmarire.

Rulare:  python live/session16_gbpaud_h1.py
Output:  data/live_signals/session16/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S16-GBPAUD-H1",
    "session_key":  "session16",
    "description":  "GBPAUD H1+D1 BOTH pw=8 pullback+BE | test +0.054R DD -29.0%",

    "markets":      ["GBPAUD"],
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
    "account_fraction": 0.09,
    "risk_pct":         0.01,

    "flag_enabled":         False,
    "inside_bar_enabled":   False,
    "break_even_enabled":   True,
    "be_trigger_pct":       80,
    "be_lock1_pct":         30,
    "be_lock2_pct":         50,
    "be_phase2_zone_pct":   40,

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session16"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
