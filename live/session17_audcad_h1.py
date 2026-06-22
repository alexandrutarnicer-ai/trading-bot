"""
SESSION 17 — AUDCAD, H1+D1, LONG, pw=8
=========================================
Scan full: pullback+flag+IB, test +0.0250R, 22t, DD -24.7%, Score 0.117
Scor foarte mic — observare pura.

Rulare:  python live/session17_audcad_h1.py
Output:  data/live_signals/session17/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S17-AUDCAD-H1",
    "session_key":  "session17",
    "description":  "AUDCAD H1+D1 LONG pw=8 pullback+IB | test +0.025R DD -24.7%",

    "markets":      ["AUDCAD"],
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
    "account_fraction": 0.07,
    "risk_pct":         0.01,

    "flag_enabled":         False,
    "inside_bar_enabled":   True,
    "inside_bar_r_ratio":   2.0,
    "inside_bar_risk_pct":  0.01,

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session17"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
