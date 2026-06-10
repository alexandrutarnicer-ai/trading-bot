"""
SESSION 4 — GER40 + US30, LONG only, DEMO EXECUTION
=====================================================
ATENTIE: Sesiune in validare statistica — nu are semnificatie suficienta pentru real.
Scopul: acumulare date live ~6 luni, re-evaluare Dec 2026. Demo OK.

  GER40 Matinal  09-14h UTC  PW=6  LONG  exp_test=+0.480R p=0.045 (pre-Bonferroni)
  US30  skipMon  14-21h UTC  PW=6  LONG  exp_test=+0.224R p=0.165
  Capital: $175 (parte din $700 total demo — 4 sesiuni)
  Frecventa asteptata: ~0.8 semnale/sapt (0.35 GER40 + 0.45 US30)

Orar rulare (ora locala Romania):
  Vara  (EEST, UTC+3):  12:00 – 00:00
  Iarna (EET,  UTC+2):  11:00 – 23:00

Rulare:  python live/session4_obs.py
Output:  data/live_signals/session4/

NOTE: skip_monday=True se aplica ambelor simboluri.
      GER40 pip=$1.15/lot, US30 pip=$1.00/lot (lot minim 0.01).
      Executa ordine pending in MT5 (demo) SI logheaza in CSV (paralel).
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S4-DEMO",
    "description":  (
        "GER40 09-14h + US30 14-21h | LONG only | DEMO | "
        "GER40 p=0.045 pre-Bonferroni | US30 p=0.165 | re-test Dec 2026"
    ),

    # Piete
    "markets":      ["GER40", "US30"],
    "symbol_fallbacks": {
        "GER40": ["GER40", "GER40.cash", "DAX40", "DAX30", "DE30", "DE40"],
        "US30":  ["US30",  "US30.cash",  "DJ30",  "DJIA",  "DJI30"],
    },

    # Timeframe
    "entry_tf":    "M15",
    "trend_tf":    "M30",
    "bar_minutes": 15,

    # Strategie — LONG only confirmat in research
    "only_long":       True,
    "pullback_window": 6,   # PW=6 optim pentru ambele simboluri

    # Sesiune globala — de la primul simbol pana la ultimul
    "session_start": 9,
    "session_end":   21,

    # Sesiuni per simbol (orele active UTC)
    # GER40: 09-14h (EU morning, pre-US deschidere)
    # US30:  14-21h (NYSE 09:30-16:00 EST)
    "symbol_sessions": {
        "GER40": (9,  14),
        "US30":  (14, 21),
    },

    # skip_monday=True: validat pentru US30 (+0.224R vs +0.122R fara skip)
    # Impact GER40: -~0.05 trades/sapt (neglijabil in observare)
    "skip_monday":   True,
    "skip_weekdays": [],
    "skip_hours":    (),

    "expire_bars": 4,   # expira setup dupa 1 ora (4 bare M15) fara trigger

    # Date — 2000 bare M15 (~21 zile), suficient pentru warm-up indici
    "n_bars_entry": 2000,
    "n_bars_trend": 1000,

    # Executie demo — ordine pending in MT5 + CSV logging in paralel
    "execute_trades":  True,    # plaseaza ordine pending in MT5 (demo)
    "session_capital": 175,     # capital virtual — $700 total / 4
    "risk_pct":        0.01,    # risc per trade = 1% = $1.75/trade

    # Output separat de sesiunile validate
    "output_dir": os.path.join(DATA_DIR, "live_signals", "session4"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
