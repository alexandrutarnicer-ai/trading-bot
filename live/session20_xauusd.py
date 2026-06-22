"""
SESSION 20 — XAUUSD, M15+M30, BOTH, pw=8
==========================================
Scan full: pullback, test +0.4737R, 4t, Score -999 (insuficient test trades)
ATENTIE: lot minim 0.01 = 1 oz aur ~ $8-10 risc minim. Necesita ~$900+ capital.
execute_trades=False implicit — activat manual daca cont suficient de mare.

Rulare:  python live/session20_xauusd.py
Output:  data/live_signals/session20/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S20-XAUUSD",
    "session_key":  "session20",
    "description":  "XAUUSD M15+M30 BOTH pw=8 pullback | obs only (lot min > $8 risc)",

    "markets":      ["XAUUSD"],
    "symbol_fallbacks": {
        "XAUUSD": ["XAUUSD", "GOLD", "XAUUSDm", "XAUUSD."],
    },

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

    "execute_trades":   False,   # dezactivat — lot minim prea mare pt cont mic
    "session_capital":  100,
    "account_fraction": 0.10,
    "risk_pct":         0.01,

    "flag_enabled":         False,
    "inside_bar_enabled":   False,

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session20"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
