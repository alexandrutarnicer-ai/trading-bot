"""
SESSION 6 — US30, M15+M30, BOTH, pw=10
=========================================
Scan full (2026-06): US30 pullback BOTH M15+M30  test +0.229R  Score 2.71  DD -16.3%
Sesiune NYSE: 15-22h UTC.

Nota: Anterior LONG only cu skip_monday. Acum BOTH (short inclus) per scan.
      Fractie 57% din equity — lot minim US30 necesita ~$456 capital.

Rulare:  python live/session6_us30_m15.py
Output:  data/live_signals/session6/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S6-US30",
    "session_key":  "session6",
    "description":  "US30 M15+M30 BOTH pw=10 pullback | test +0.229R Score 2.71 | 15-22h",

    "markets": ["US30"],
    "symbol_fallbacks": {
        "US30": ["US30", "US30.cash", "DJ30", "DJIA", "DJI30"],
    },

    "entry_tf":    "M15",
    "trend_tf":    "M30",
    "bar_minutes": 15,

    "only_long":       False,
    "pullback_window": 10,

    "session_start": 15,
    "session_end":   22,
    "symbol_sessions": {
        "US30": (15, 22),
    },

    "skip_monday":   False,
    "skip_weekdays": [],
    "skip_hours":    (),

    "expire_bars": 4,

    "n_bars_entry": 2000,
    "n_bars_trend": 1000,

    "execute_trades":   True,
    "session_capital":  450,
    "account_fraction": 0.57,   # 57% din equity — lot minim US30 necesita ~$456
    "risk_pct":         0.01,

    "flag_enabled":         False,
    "inside_bar_enabled":   False,

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session6"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
