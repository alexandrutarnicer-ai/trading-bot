"""
SESSION 5 — GER40 + USDCHF, H1+D1, BOTH
=========================================
H1 entry + D1 trend. Doua instrumente cu aceeasi combinatie TF.

Rezultate tf_scan_targeted (2026-06-11):
  GER40  H1+D1 PW=6: exp_test=+0.6505R  p=0.103  DD=-21.9%  0.3/sapt
  USDCHF H1+D1 PW=8: exp_test=+0.5269R  p=0.0896* DD=-13.7% 0.3/sapt (VIABLE)

USDCHF validat pe 8 ani de date, split Jan 2024.
GER40 borderline — continua acumularea de semnale live.

Sesiuni:
  GER40:  07-16h UTC (piata EU cash)
  USDCHF: 07-17h UTC (London + NY overlap)

Parallel cu S4 (GER40 M15) — ordine independente pe GER40 in MT5.

Rulare:  python live/session5_ger40_h1.py
Output:  data/live_signals/session5/
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR

SESSION_CONFIG = {
    "session_id":   "S5-H1D1",
    "description":  (
        "GER40+USDCHF H1+D1 | BOTH | OBSERVARE | "
        "USDCHF p=0.0896* VIABLE | GER40 p=0.103 borderline"
    ),

    # Piete — GER40 (EU cash) + USDCHF (London+NY)
    "markets":      ["GER40", "USDCHF"],
    "symbol_fallbacks": {
        "GER40": ["GER40", "GER40.cash", "DAX40", "DAX30", "DE30", "DE40"],
    },

    # Timeframe — H1 entry + D1 trend (analog M15+M30 din S1/S2 dar cu un pas mai sus)
    "entry_tf":    "H1",
    "trend_tf":    "D1",
    "bar_minutes": 60,   # trezire la fiecare inchidere bara H1 (5s dupa ora rotunda)

    # Strategie — BOTH (per simbol PW diferit, folosim PW=8 comun — conservator)
    "only_long":       False,
    "pullback_window": 8,   # GER40 PW=6 optim, USDCHF PW=8 optim — folosim 8 comun

    # Sesiuni per simbol
    "session_start": 7,
    "session_end":   17,
    "symbol_sessions": {
        "GER40":  (7, 16),   # piata EU cash 07-16h UTC
        "USDCHF": (7, 17),   # London + NY overlap 07-17h UTC
    },

    "skip_monday":   False,   # tf_scan fara skip_monday
    "skip_weekdays": [],
    "skip_hours":    (),

    # Expirare — 4 bare H1 = 4 ore (analog cu 4 bare M15 = 1 ora din S1/S2)
    "expire_bars": 4,

    # Date MT5 — H1 bars pentru entry, D1 bars pentru trend + regim
    # 2000 H1 bars ~ 83 zile calendar (suficient pentru EMA50 + swing detection)
    # 600 D1 bars ~ 2.5 ani (suficient pentru EMA200 warmup = 200 zile)
    "n_bars_entry": 2000,
    "n_bars_trend": 600,

    # Executa ordine pe Demo — USDCHF validat (p=0.0896*), GER40 borderline in acumulare
    "execute_trades":   True,
    "session_capital":  175,    # capital vizat (12.5% din $1400 target total)
    "account_fraction": 0.125,  # 12.5% din equity real MT5
    "risk_pct":         0.01,   # 1% din session_capital per trade

    "output_dir": os.path.join(DATA_DIR, "live_signals", "session5"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
