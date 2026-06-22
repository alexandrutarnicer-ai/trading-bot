"""
SESSION 11 — USDCAD, M15+M30, LONG, pw=8
==========================================
Scan full: pullback+IB, test +0.1400R, 58t, DD -30.8%, Score 1.067

Rulare:  python live/session11_usdcad.py
Output:  data/live_signals/session11/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S11-USDCAD",
    "session_key":  "session11",
    "description":  "USDCAD M15+M30 LONG pw=8 pullback+IB | test +0.140R DD -30.8%",

    "markets":      ["USDCAD"],
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
    "inside_bar_enabled":   True,
    "inside_bar_r_ratio":   2.0,
    "inside_bar_risk_pct":  0.01,

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session11"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
