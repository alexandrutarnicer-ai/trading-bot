"""
SESSION 2 — AUDJPY, M15+M30, BOTH, pw=10
==========================================
Scan full (2026-06): AUDJPY pullback+BE BOTH  test +0.410R  Score 2.05  DD -28.6%
O singura piata per sesiune — sesiune non-stop (0-24h).

Nota: In sesiunea anterioara S2 acoperea USDJPY/AUDJPY/NZDJPY.
Acum AUDJPY este singurul in S2; USDJPY a primit propria sesiune S9.
NZDJPY -> S18 (H1+D1).

Rulare:  python live/session2_m5_both.py
Output:  data/live_signals/session2/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S2-AUDJPY",
    "session_key":  "session2",
    "description":  "AUDJPY M15+M30 BOTH pw=10 pullback+BE | test +0.410R Score 2.05",

    "markets":      ["AUDJPY"],
    "symbol_fallbacks": {},

    "entry_tf":    "M15",
    "trend_tf":    "M30",
    "bar_minutes": 15,

    "only_long":       False,
    "pullback_window": 10,

    "session_start": 0,
    "session_end":   24,
    "skip_hours":    (),
    "skip_monday":   False,
    "skip_weekdays": [],
    "expire_bars":   4,
    "symbol_sessions": {},

    "n_bars_entry": 2000,
    "n_bars_trend": 1000,

    "execute_trades":   True,
    "session_capital":  100,
    "account_fraction": 0.07,
    "risk_pct":         0.01,

    "flag_enabled":         False,
    "inside_bar_enabled":   False,
    "break_even_enabled":   True,
    "be_trigger_pct":       80,
    "be_lock1_pct":         30,
    "be_lock2_pct":         50,
    "be_phase2_zone_pct":   40,

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session2"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
