"""
SESSION 6 — US30, M15 LONG, Demo
==================================
Dow Jones Industrial Average — sesiune NY (13-21h UTC).

Rezultate scan_comprehensive (2026-06-12):
  US30 M15+M30 PW=10 LONG 13-21h skipMon:
    exp_train = +0.1439R
    exp_test  = +0.2349R   p=0.1508  (marginal, sub pragul 0.10)
    DD        = -16.1%
    Frecventa = 0.60/sapt  (~3 trades/luna)
    Ani poz   = 8/10 (cel mai consistent semn — ambele perioade pozitive)

Nota: p=0.1508 nu trece pragul 0.10 dar este singurul instrument cu:
  - train SI test pozitive (nu doar test)
  - 8/10 ani cu profit
  Monitorizam live pe Demo si re-evaluam la 30+ semnale.

US30 era anterior in S4 cu PW=6 14-21h (p=0.165). Acum separat cu PW=10 13-21h.

Sesiune:  13-21h UTC  (NYSE open 13:30, close 20:00 UTC)
skip_monday=True (validat in scan)

Rulare:  python live/session6_us30_m15.py
Output:  data/live_signals/session6/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S6-US30-M15",
    "description":  (
        "US30 M15+M30 | LONG | PW=10 | 13-21h UTC | skipMon | "
        "test=+0.2349R p=0.1508 8/10yr+ DD=-16.1% | scan_comprehensive 2026-06-12"
    ),

    # Piata
    "markets": ["US30"],
    "symbol_fallbacks": {
        "US30": ["US30", "US30.cash", "DJ30", "DJIA", "DJI30"],
    },

    # Timeframe — M15 entry, M30 trend (standard ca S1/S2)
    "entry_tf":    "M15",
    "trend_tf":    "M30",
    "bar_minutes": 15,

    # Strategie — LONG only, PW=10 (validat in scan)
    "only_long":       True,
    "pullback_window": 10,

    # Sesiune NYSE: 13:30 open, 20:00 close UTC — folosim 13-21h cu buffer
    "session_start": 13,
    "session_end":   21,
    "symbol_sessions": {
        "US30": (13, 21),
    },

    "skip_monday":   True,    # validat: +0.2349R vs mai slab fara skip
    "skip_weekdays": [],
    "skip_hours":    (),

    # Expirare — 4 bare M15 = 1 ora
    "expire_bars": 4,

    # Date MT5 — 2000 bare M15 (~21 zile), 1000 M30 (~21 zile)
    "n_bars_entry": 2000,
    "n_bars_trend": 1000,

    # Executie Demo
    "execute_trades":   True,
    "session_capital":  100,
    "account_fraction": 0.125,  # 12.5% din equity MT5
    "risk_pct":         0.01,   # 1% din capital efectiv per trade

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session6"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
