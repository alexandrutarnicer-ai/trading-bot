"""
SESSION 5 — USDCHF, H1+D1, BOTH, pw=10
=========================================
Scan full (2026-06): USDCHF pullback BOTH H1+D1  test +0.413R  Score 2.37  DD -18.3%
O singura piata per sesiune — sesiune non-stop (0-24h).

Nota: Anterior sesiunea acoperea GER40+USDCHF. Acum USDCHF individual;
      GER40 H1+D1 nu a trecut pragul de validare in scan final.

Rulare:  python live/session5_ger40_h1.py
Output:  data/live_signals/session5/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S5-USDCHF-H1",
    "session_key":  "session5",
    "description":  "USDCHF H1+D1 BOTH pw=10 pullback | test +0.413R Score 2.37",

    "markets":      ["USDCHF"],
    "symbol_fallbacks": {},

    "entry_tf":    "H1",
    "trend_tf":    "D1",
    "bar_minutes": 60,

    "only_long":       False,
    "pullback_window": 10,

    "session_start": 0,
    "session_end":   24,
    "symbol_sessions": {},

    "skip_monday":   False,
    "skip_weekdays": [],
    "skip_hours":    (),

    "expire_bars": 3,

    "n_bars_entry": 2000,
    "n_bars_trend": 600,

    "execute_trades":   True,
    "session_capital":  100,
    "account_fraction": 0.08,
    "risk_pct":         0.01,

    "flag_enabled":         False,
    "inside_bar_enabled":   False,

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session5"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
