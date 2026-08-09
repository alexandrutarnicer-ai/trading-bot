"""
SESSION 21 — CSCO.NAS (Cisco), M15+M30, LONG, pw=8
===================================================
Backtest (2020-2026, train/test): M15+M30 = TF robust (train +0.06 / test +0.26).
Filtru ore OOS-validat: skip 19-20h ora RO (pranzul US, chop de midday) ->
CSCO BOTH train +0.05->+0.19, test +0.22->+0.39. Directie LONG (bias actiuni).
Sesiune US 16-23 ora RO. execute_trades=False (OBSERVATIE pe cont real).
ATENTIE: frecventa MICA (~0.35 trade/sapt LONG), edge subtire, backtest fara costuri.

Rulare:  python live/session21_csco.py
Output:  data/live_signals/session21/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S21-CSCO",
    "session_key":  "session21",
    "description":  "CSCO.NAS M15+M30 LONG pw=8 | obs | US 16-23h RO, skip 19-20h",

    "markets":      ["CSCO.NAS"],
    "symbol_fallbacks": {
        "CSCO.NAS": ["CSCO.NAS", "CSCO", "CSCO.NASDAQ", "#CSCO"],
    },

    "entry_tf":    "M15",
    "trend_tf":    "M30",
    "bar_minutes": 15,

    "only_long":       True,
    "pullback_window": 8,

    "session_start": 16,        # sesiunea US, ora RO
    "session_end":   23,
    "skip_hours":    (19, 20),  # pranzul US (chop de midday) — OOS-validat
    "skip_monday":   False,
    "skip_weekdays": set(),
    "expire_bars":   4,
    "symbol_sessions": {},

    "n_bars_entry": 2000,
    "n_bars_trend": 1000,

    "execute_trades":   False,  # OBSERVATIE — nu plaseaza ordine reale
    "session_capital":  100,
    "account_fraction": 0.10,
    "risk_pct":         0.01,

    "flag_enabled":         False,
    "inside_bar_enabled":   False,

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session21"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
