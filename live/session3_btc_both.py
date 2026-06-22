"""
SESSION 3 — BTCUSD M15, BOTH, sesiune crypto optimizata
=========================================================
BTC pullback M15 cu filtru de sesiune: skip EU mid + US prime + Sambata.
+0.336R test, p=0.0075***, DD=-22.5%, $500->$3355 (+571%), 2.4 trades/sapt.
Toate cele 7 ani pozitive (inclusiv bear 2022).

Ferestre active: 00-09h UTC + 15-18h UTC  (Lun-Vin + Dum)
Skip:  10-14h UTC (EU mid/news), 19-23h UTC (US prime), Sambata

Rulare:  python live/session3_btc_both.py
Output:  data/live_signals/session3/

NOTE: pip_size pentru BTCUSD = tick_size = 0.01 (nu 1.0 ca la FX).
      Spread real: $12.00 (1200 ticks). Spread/SL median: 4.5% (OK).
ATENTIE: swap BTC este anual% pe notional — rate-ul variaza cu brokerul.
"""

import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.signal_generator import run_generator
from backtest import DATA_DIR
from strategy import signals as _sig

# Patch pip_size pentru BTCUSD — tick_size=0.01, nu fallback la 1.0
# Citim din crypto_specs.json ca sa fie consistent cu backtestele
_specs_path = os.path.join(DATA_DIR, "crypto_specs.json")
if os.path.exists(_specs_path):
    with open(_specs_path, encoding="utf-8") as _f:
        _specs = json.load(_f)
    if "BTCUSD" in _specs:
        _sig._INDEX_PIP["BTCUSD"] = _specs["BTCUSD"]["tick_size"]
else:
    _sig._INDEX_PIP["BTCUSD"] = 0.01   # fallback hardcodat

SESSION_CONFIG = {
    "session_id":   "S3-BTC-BOTH",
    "session_key":  "session3",
    "description":  "BTC M15 BOTH | crypto sesiune | +0.336R test p=0.0075 | 2.4/sapt",

    # Piete
    "markets":      ["BTCUSD"],
    "symbol_fallbacks": {"BTCUSD": ["BTCUSD", "BTC/USD", "BTCUSDT"]},

    # Timeframe
    "entry_tf":    "M15",
    "trend_tf":    "M30",
    "bar_minutes": 15,

    # Strategie
    "only_long":       False,   # BOTH: long si short
    "pullback_window": 10,      # PW=10 per scan full 2026-06

    # Sesiune — BTC activ 24/7, filtrul real e prin skip_hours + skip_weekdays
    "session_start": 0,
    "session_end":   24,

    # Skip ore UTC: EU mid (10-14h) + US prime (19-23h)
    # Rationale: structura pullback nu se respecta in aceste ferestre (noise, news, algo)
    "skip_hours":    (10, 11, 12, 13, 14, 19, 20, 21, 22, 23),

    # Skip Sambata (weekday=5): lichiditate scazuta, win rate 12% vs 22-26% restul saptamanii
    "skip_weekdays": [5],

    "skip_monday":   False,   # Luni activa pentru BTC (duminica seara = luni Asia)
    "expire_bars":   3,       # expira setup dupa 3 bare M15 per scan full 2026-06

    "symbol_sessions": {},    # nu avem sesiuni per simbol — filtrul e global prin skip_hours

    # Date — 2000 bare M15 (~21 zile) suficient pentru warm-up BTC
    "n_bars_entry": 2000,
    "n_bars_trend": 1000,

    # Executie demo/live
    "execute_trades":   True,    # plaseaza ordine pending in MT5
    "session_capital":  500,    # capital fallback daca MT5 nu e disponibil
    "account_fraction": 0.37,   # 37% din equity MT5 — minim necesar lot 0.01 BTC
    "risk_pct":         0.01,   # risc per trade = 1% din capital efectiv

    "inside_bar_enabled":   True,
    "inside_bar_r_ratio":   2.0,
    "inside_bar_risk_pct":  0.01,

    # Output
    "output_dir": os.path.join(DATA_DIR, "live_signals", "session3"),
}

if __name__ == "__main__":
    run_generator(SESSION_CONFIG)
