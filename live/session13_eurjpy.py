"""
SESSION 13 — EURJPY, M15+M30, LONG, pw=8
==========================================
Scan full: pullback, test +0.0752R, 96t, DD -30.1%, Score 0.737
Scor mic — urmarire 2 luni inainte de decizie.

Rulare:  python live/session13_eurjpy.py
Output:  data/live_signals/session13/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S13-EURJPY",
    "session_key":  "session13",
    "description":  "EURJPY M15+M30 LONG pw=8 pullback | test +0.075R DD -30.1%",

    "markets":      ["EURJPY"],
    "symbol_fallbacks": {},

    "entry_tf":    "M15",
    "trend_tf":    "M30",
    "bar_minutes": 15,

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
    "n_bars_trend": 1000,

    "execute_trades":   True,
    "session_capital":  100,
    "account_fraction": 0.06,
    "risk_pct":         0.01,

    "flag_enabled":         False,
    "inside_bar_enabled":   False,

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session13"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
