"""
SESSION 4 — GER40, LONG only, DEMO EXECUTION
=============================================
ATENTIE: Sesiune in validare statistica — nu are semnificatie suficienta pentru real.
Scopul: acumulare date live ~6 luni, re-evaluare Dec 2026. Demo OK.

  GER40 Matinal  09-14h UTC  PW=6  LONG  exp_test=+0.480R p=0.045 (pre-Bonferroni)

NOTE: US30 a fost mutat in S6 (session6_us30_m15.py) cu parametrii validati mai buni
      (PW=10, 13-21h, 8/10 ani pozitivi — scan_comprehensive 2026-06-12).

Orar rulare (ora locala Romania):
  Vara  (EEST, UTC+3):  12:00 – 17:00
  Iarna (EET,  UTC+2):  11:00 – 16:00

Rulare:  python live/session4_obs.py
Output:  data/live_signals/session4/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S4-DEMO",
    "session_key":  "session4",
    "description":  (
        "GER40 09-14h | LONG only | DEMO | "
        "p=0.045 pre-Bonferroni | re-test Dec 2026 | US30 -> S6"
    ),

    # Piete — US30 mutat in S6 cu PW=10 13-21h (parametri mai buni)
    "markets":      ["GER40"],
    "symbol_fallbacks": {
        "GER40": ["GER40", "GER40.cash", "DAX40", "DAX30", "DE30", "DE40"],
    },

    # Timeframe
    "entry_tf":    "M15",
    "trend_tf":    "M30",
    "bar_minutes": 15,

    # Strategie — LONG only confirmat in research
    "only_long":       True,
    "pullback_window": 6,   # PW=6 optim pentru ambele simboluri

    # Sesiune GER40: 09-14h (EU morning, pre-US deschidere)
    "session_start": 9,
    "session_end":   14,
    "symbol_sessions": {
        "GER40": (9, 14),
    },

    "skip_monday":   True,
    "skip_weekdays": [],
    "skip_hours":    (),

    "expire_bars": 4,   # expira setup dupa 1 ora (4 bare M15) fara trigger

    # Date — 2000 bare M15 (~21 zile), suficient pentru warm-up indici
    "n_bars_entry": 2000,
    "n_bars_trend": 1000,

    # Executie demo — ordine pending in MT5 + CSV logging in paralel
    "execute_trades":   True,    # plaseaza ordine pending in MT5 (demo)
    "session_capital":  100,    # capital fallback daca MT5 nu e disponibil
    "account_fraction": 0.125,  # 12.5% din equity real MT5 ($100 din $800 start)
    "risk_pct":         0.01,   # risc per trade = 1% din capital efectiv

    # Output separat de sesiunile validate
    "output_dir": os.path.join(DATA_DIR, "live_signals", "session4"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
