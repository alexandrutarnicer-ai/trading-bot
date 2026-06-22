"""
SESSION 9 — USDJPY, M15+M30, LONG, pw=6
==========================================
Scan full: pullback, test +0.1583R, 76t, DD -23.4%, Score 1.380
Train pozitiv +0.112R — edge consistent pe 8 ani.

Rulare:  python live/session9_usdjpy.py
Output:  data/live_signals/session9/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S9-USDJPY",
    "session_key":  "session9",
    "description":  "USDJPY M15+M30 LONG pw=6 pullback | test +0.158R DD -23.4%",

    "markets":      ["USDJPY"],
    "symbol_fallbacks": {},

    "entry_tf":    "M15",
    "trend_tf":    "M30",
    "bar_minutes": 15,

    "only_long":       True,
    "pullback_window": 6,

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
    "account_fraction": 0.05,
    "risk_pct":         0.01,

    "flag_enabled":         False,
    "inside_bar_enabled":   False,

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session9"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
