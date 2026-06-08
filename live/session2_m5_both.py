"""
SESSION 2 — M15, BOTH, PW=6, 6 piete cu sesiuni separate
==========================================================
Frecventa maxima cu edge pozitiv: +0.142R test, ~3.2 trades/sapt.
EUR pairs: sesiune europeana 10-18h EET
JPY pairs: sesiune asiatica 02-10h EET  (USDJPY validat +0.154R test)

Piete: EURUSD, GBPUSD, EURJPY + USDJPY, AUDJPY, NZDJPY
Rulare:  python live/session2_m5_both.py
Output:  data/live_signals/session2/

NOTE: M15 entry (nu M5 — M5 confirmat negativ in backteste, WR~16%, DD -80%).
      skip_monday=False: +0.6 trades/saptamana, penalizare minima de edge (-0.023R).
ATENTIE: swap-urile AUDJPY/NZDJPY sunt estimate — verifica in MT5.
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S2-M15-BOTH",
    "description":  "M15 BOTH PW=6 | 6 piete | +0.142R test | ~3.2/sapt",

    # Piete
    "markets": ["EURUSD", "GBPUSD", "EURJPY", "USDJPY", "AUDJPY", "NZDJPY"],
    "symbol_fallbacks": {},

    # Timeframe — M15 entry (M5 confirmat negativ, DD -80%)
    "entry_tf":    "M15",
    "trend_tf":    "M30",
    "bar_minutes": 15,

    # Strategie
    "only_long":       False,   # BOTH: long si short
    "pullback_window": 6,       # PW=6 = cel mai bun pe combo 6 piete din teste

    # Sesiune globala (fallback pentru simboluri fara sesiune specifica)
    "session_start": 2,
    "session_end":   20,
    "skip_hours":    (15, 16),
    "skip_monday":   False,     # luni inclusa: +0.6/sapt, penalizare mica (-0.023R)
    "expire_bars":   4,         # expira setup dupa 4 bare M15 (1 ora) fara trigger

    # Sesiuni per simbol — sesiunile nu se suprapun, zero conflict intre EUR si JPY
    "symbol_sessions": {
        "EURUSD": (10, 18),   # sesiune europeana
        "GBPUSD": (10, 18),
        "EURJPY": (10, 18),
        "USDJPY": (2, 10),    # sesiune Tokyo (validat +0.154R test)
        "AUDJPY": (2, 10),
        "NZDJPY": (2, 10),
    },

    # Date
    "n_bars_entry": 2000,   # 2000 bare M15 = ~500 ore = warm-up adecvat
    "n_bars_trend": 1000,   # 1000 bare M30

    # Output
    "output_dir": os.path.join(DATA_DIR, "live_signals", "session2"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
