"""
SESSION 22 — SOFI.NAS (SoFi), M15+M30, LONG, pw=8
==================================================
Backtest (2022-2026, train/test): M15+M30 LONG = marginal robust (train +0.03 /
test +0.48) — candidat mai slab, volatil, istoric scurt (IPO 2021). Filtru ore:
skip DOAR 20h ora RO (19h e POZITIV pe SOFI, spre deosebire de CSCO — nu-l taiem).
Sesiune US 16-23 ora RO. execute_trades=False (OBSERVATIE pe cont real).
ATENTIE: frecventa MICA, edge incert (mai overfit-prone), backtest fara costuri.

Rulare:  python live/session22_sofi.py
Output:  data/live_signals/session22/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S22-SOFI",
    "session_key":  "session22",
    "description":  "SOFI.NAS M15+M30 LONG pw=8 | obs | US 16-23h RO, skip 20h",

    "markets":      ["SOFI.NAS"],
    "symbol_fallbacks": {
        "SOFI.NAS": ["SOFI.NAS", "SOFI", "SOFI.NASDAQ", "#SOFI"],
    },

    "entry_tf":    "M15",
    "trend_tf":    "M30",
    "bar_minutes": 15,

    "only_long":       True,
    "pullback_window": 8,

    "session_start": 16,        # sesiunea US, ora RO
    "session_end":   23,
    "skip_hours":    (20,),     # doar 20h (19h e profitabil pe SOFI)
    "skip_monday":   False,
    "skip_weekdays": set(),
    "expire_bars":   4,
    "symbol_sessions": {},

    "n_bars_entry": 2000,
    "n_bars_trend": 1000,

    "execute_trades":   True,   # LIVE — plaseaza ordine (cont real; runtime profile suprascrie)
    "session_capital":  100,
    "account_fraction": 0.10,
    "risk_pct":         0.01,

    "flag_enabled":         False,
    "inside_bar_enabled":   False,

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session22"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
