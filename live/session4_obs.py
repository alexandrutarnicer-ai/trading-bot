"""
SESSION 4 — GER40, M15+M30, LONG+Flag, pw=6
=============================================
Scan full (2026-06): GER40 pullback+flag LONG  test +0.334R  Score 3.31  DD -19.4%
Sesiune bursiera EU: 09-17h UTC.

Nota: Anterior sesiunea acoperea GER40+US30 (obs). Acum GER40 individual cu
      flag pattern activat (cel mai bun config din scan). US30 -> S6.
      Fractie 50% din equity — lot minim GER40 necesita capital mai mare.

Rulare:  python live/session4_obs.py
Output:  data/live_signals/session4/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S4-GER40",
    "session_key":  "session4",
    "description":  "GER40 M15+M30 LONG pw=6 pullback+flag | test +0.334R Score 3.31 | 09-17h",

    "markets":      ["GER40"],
    "symbol_fallbacks": {
        "GER40": ["GER40", "GER40.cash", "DAX40", "DAX30", "DE30", "DE40"],
    },

    "entry_tf":    "M15",
    "trend_tf":    "M30",
    "bar_minutes": 15,

    "only_long":       True,
    "pullback_window": 6,

    "session_start": 9,
    "session_end":   17,
    "symbol_sessions": {
        "GER40": (9, 17),
    },

    "skip_monday":   False,
    "skip_weekdays": [],
    "skip_hours":    (),

    "expire_bars": 4,

    "n_bars_entry": 2000,
    "n_bars_trend": 1000,

    "execute_trades":   True,
    "session_capital":  400,
    "account_fraction": 0.50,   # 50% din equity — lot minim GER40 necesita ~$397
    "risk_pct":         0.01,

    "flag_enabled":         True,
    "flag_r_ratio":         2.5,
    "flag_risk_pct":        0.01,
    "inside_bar_enabled":   False,

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session4"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
