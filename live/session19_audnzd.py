"""
SESSION 19 — AUDNZD, M15+M30, BOTH, pw=8
==========================================
Scan full: pullback, test +0.3387R, 19t, DD -34.6%, Score -999 (insuficient test trades)
Date insuficiente pe test set — observare pura, nu baza decizii pe aceasta sesiune.

Rulare:  python live/session19_audnzd.py
Output:  data/live_signals/session19/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S19-AUDNZD",
    "session_key":  "session19",
    "description":  "AUDNZD M15+M30 BOTH pw=8 pullback | test +0.339R (19t insuf)",

    "markets":      ["AUDNZD"],
    "symbol_fallbacks": {},

    "entry_tf":    "M15",
    "trend_tf":    "M30",
    "bar_minutes": 15,

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
    "n_bars_trend": 1000,

    "execute_trades":   True,
    "session_capital":  100,
    "account_fraction": 0.05,
    "risk_pct":         0.01,

    "flag_enabled":         False,
    "inside_bar_enabled":   False,

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session19"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
