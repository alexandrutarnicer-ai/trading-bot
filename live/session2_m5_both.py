"""
SESSION 2 — M15, BOTH, PW=6, 3 perechi JPY (sesiune asiatica)
==============================================================
Sesiune asiatica: USDJPY, AUDJPY, NZDJPY  02-10h UTC

EURUSD, GBPUSD, EURJPY au fost scoase din S2 (2026-06-12) pentru a elimina
overlap-ul cu S1 (aceleasi 3 perechi, aceeasi fereastra 10-18h, risk duplicate ordine).
S1 acopera EUR pairs LONG only; S2 se concentreaza exclusiv pe sesiunea asiatica JPY.

Validare USDJPY: +0.154R test  (sesiune asiatica 02-10h)
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
    "session_key":  "session2",
    "description":  "M15 BOTH PW=6 | JPY 02-10h UTC | USDJPY/AUDJPY/NZDJPY | EUR pairs -> S1",

    # Piete — doar JPY pairs sesiune asiatica (EUR pairs mutate in S1 pentru a evita overlap)
    "markets": ["USDJPY", "AUDJPY", "NZDJPY"],
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

    # Sesiuni per simbol — exclusiv sesiunea asiatica (fara overlap cu S1 10-18h)
    "symbol_sessions": {
        "USDJPY": (2, 10),    # sesiune Tokyo (validat +0.154R test)
        "AUDJPY": (2, 10),
        "NZDJPY": (2, 10),
    },

    # Date
    "n_bars_entry": 2000,   # 2000 bare M15 = ~500 ore = warm-up adecvat
    "n_bars_trend": 1000,   # 1000 bare M30

    # Executie demo/live
    "execute_trades":   True,    # plaseaza ordine pending in MT5
    "session_capital":  100,    # capital fallback daca MT5 nu e disponibil
    "account_fraction": 0.125,  # 12.5% din equity real MT5 ($100 din $800 start)
    "risk_pct":         0.01,   # risc per trade = 1% din capital efectiv

    # Output
    "output_dir": os.path.join(DATA_DIR, "live_signals", "session2"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
