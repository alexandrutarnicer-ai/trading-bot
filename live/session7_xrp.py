"""
SESSION 7 — XRPUSD, M15+M30, BOTH, pw=10
==========================================
Scan full: pullback+flag+IB, test +0.2448R, 157t, DD -11.2%, Score 3.068
Crypto non-stop. Lot min 100 unitati XRP (nu loturi forex).

Rulare:  python live/session7_xrp.py
Output:  data/live_signals/session7/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S7-XRP",
    "session_key":  "session7",
    "description":  "XRPUSD M15+M30 BOTH pw=10 pullback+IB | test +0.245R DD -11.2%",

    "markets":      ["XRPUSD"],
    "symbol_fallbacks": {
        "XRPUSD": ["XRPUSD", "XRP/USD", "XRPUSD."],
    },

    "entry_tf":    "M15",
    "trend_tf":    "M30",
    "bar_minutes": 15,

    "only_long":       False,
    "pullback_window": 10,

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
    "account_fraction": 0.10,
    "risk_pct":         0.01,

    "flag_enabled":         True,
    "flag_r_ratio":         2.5,
    "flag_risk_pct":        0.01,
    "inside_bar_enabled":   True,
    "inside_bar_r_ratio":   2.0,
    "inside_bar_risk_pct":  0.01,

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session7"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
