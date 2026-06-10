"""
SESSION 1 — M15, ONLY_LONG, PW=8
==================================
Cea mai buna strategie din backteste: +0.375R test, -50.6% DD.
Piete: EURUSD, GBPUSD, EURJPY  |  Sesiune: 10-18h EET  |  ~0.9 trades/sapt

Rulare:  python live/session1_m15_long.py
Output:  data/live_signals/session1/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S1-M15-LONG",
    "description":  "M15 LONG PW=8 | best edge backtested | +0.375R test",

    # Piete
    "markets":      ["EURUSD", "GBPUSD", "EURJPY"],
    "symbol_fallbacks": {},

    # Timeframe
    "entry_tf":     "M15",
    "trend_tf":     "M30",
    "bar_minutes":  15,        # verifica la fiecare bara M15 inchisa

    # Strategie
    "only_long":       True,
    "pullback_window": 8,

    # Sesiune (10-18h EET, fara luni, fara 15-16h)
    "session_start": 10,
    "session_end":   18,
    "skip_hours":    (15, 16),
    "skip_monday":   True,
    "expire_bars":   4,        # expira setup dupa 4 bare M15 (1 ora) fara trigger
    "symbol_sessions": {},     # toate perechile: sesiunea globala de mai sus

    # Date
    "n_bars_entry": 2000,      # 2000 bare M15 = ~500 ore = warm-up complet
    "n_bars_trend": 1000,      # 1000 bare M30

    # Executie demo/live
    "execute_trades":   True,    # plaseaza ordine pending in MT5
    "session_capital":  100,    # capital fallback daca MT5 nu e disponibil
    "account_fraction": 0.125,  # 12.5% din equity real MT5 ($100 din $800 start)
    "risk_pct":         0.01,   # risc per trade = 1% din capital efectiv

    # Output
    "output_dir": os.path.join(DATA_DIR, "live_signals", "session1"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
