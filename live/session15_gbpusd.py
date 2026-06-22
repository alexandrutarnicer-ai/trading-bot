"""
SESSION 15 — GBPUSD, M15+M30, LONG, pw=8
==========================================
Scan full: pullback, test +0.0829R, 68t, DD -48.2%, Score 0.486
DD ridicat — urmarire atenta.

Rulare:  python live/session15_gbpusd.py
Output:  data/live_signals/session15/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S15-GBPUSD",
    "session_key":  "session15",
    "description":  "GBPUSD M15+M30 LONG pw=8 pullback | test +0.083R DD -48.2%",

    "markets":      ["GBPUSD"],
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
    "account_fraction": 0.08,
    "risk_pct":         0.01,

    "flag_enabled":         False,
    "inside_bar_enabled":   False,

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session15"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
