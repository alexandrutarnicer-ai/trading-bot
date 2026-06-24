import logging
import pandas as pd

from strategy.signals import pip_size

CONTRACT = 100_000
_costs_log = logging.getLogger("strategy.costs")
_WARNED_UNKNOWN: set = set()   # evita spam in log la fiecare bara
BASE_USD_APROX = {"GBP": 1.27, "EUR": 1.08, "AUD": 0.64, "USD": 1.0}

# Specificatii reale din MT5 (trade_tick_size, trade_tick_value_usd).
# trade_tick_value este DEJA in USD (account currency) — MT5 converteste automat.
# pip_size pentru toti indicii = 1.0 (1 punct index = 1 "pip" in engine).
# pip_value_usd per lot = tick_value / tick_size.
_INDEX_TICK = {
    "US500":  (0.01, 0.010000),   # $1.00/pt/lot
    "US30":   (0.01, 0.010000),   # $1.00/pt/lot
    "US2000": (0.01, 0.010000),   # $1.00/pt/lot
    "UK100":  (0.01, 0.013334),   # $1.33/pt/lot  (GBP profit, convertit de MT5)
    "GER40":  (0.01, 0.010800),   # $1.08/pt/lot  (EUR profit @ EUR/USD=1.08)
    "DE40":   (0.01, 0.010800),   # alias broker pt GER40
    "XAUUSD": (0.01, 1.000000),   # $100.00/pt/lot  (100 oz, tick_val=$1/tick)
}

# Crypto: 1 lot = 1 moneda. pip_value = tick_value_usd direct (nu /tick_size ca indicii).
# notional = lots × price_USD (1 BTC = 1 BTC, nu 100_000 unitati forex).
_CRYPTO_TICK = {
    "BTCUSD": 0.01,   # tick_value_usd (USD per tick per lot)
    "ETHUSD": 0.01,
}

# Swap real din MT5 (swap_long, tratate ca USD per lot per noapte).
# Forex: valorile existente validate pe backtest.
# Indici: valori directe MT5 — mode=2 e exact USD; mode=3 e aproximatie flat.
SWAP_PER_LOT_NIGHT = {
    # Forex validat
    "EURUSD": 7.0,  "GBPUSD": 8.0,  "USDJPY": 10.0, "GBPJPY": 12.0,
    # Forex estimate (de verificat in MT5 inainte de live)
    "AUDUSD": 6.5,  "NZDUSD": 7.0,  "USDCAD": 5.5,  "USDCHF": 5.0,
    "AUDJPY": 9.0,  "CADJPY": 8.5,  "CHFJPY": 6.5,  "NZDJPY": 8.0,
    "EURJPY": 9.5,  "EURGBP": 6.0,
    # Indici
    "US500":  1.735, "US30": 11.812, "US2000": 0.671,
    "UK100":  2.459, "GER40": 4.528, "DE40": 4.528,
    "XAUUSD": 54.015,
}


def swap_cost(symbol, entry_time, exit_time, lots):
    """Cost de swap: nr. nopti tinute x rata x loti. Miercuri = tripla."""
    e = pd.Timestamp(entry_time).normalize()
    x = pd.Timestamp(exit_time).normalize()
    nights = (x - e).days
    if nights <= 0:
        return 0.0
    units = 0
    d = e
    for _ in range(nights):
        d = d + pd.Timedelta(days=1)
        units += 3 if d.weekday() == 2 else 1
    return units * SWAP_PER_LOT_NIGHT.get(symbol, 8.0) * lots


def pip_value_usd(symbol, price, usdjpy_rate=None):
    """Valoarea unui pip (1 unitate de pret), pentru 1.0 lot, in USD."""
    if symbol in _INDEX_TICK:
        tick_size, tick_value_usd = _INDEX_TICK[symbol]
        return tick_value_usd / tick_size      # USD per 1 punct per lot
    if symbol in _CRYPTO_TICK:
        return _CRYPTO_TICK[symbol]            # tick_value_usd direct (pip = tick_size)
    # ---- forex sau simbol necunoscut ----
    _FX_Q = {"USD","EUR","GBP","JPY","AUD","CAD","CHF","NZD"}
    _looks_non_forex = not (len(symbol) == 6 and symbol[3:] in _FX_Q)
    if _looks_non_forex and symbol not in _WARNED_UNKNOWN:
        _costs_log.warning(
            "pip_value_usd(%s): simbol neregistrat in _INDEX_TICK/_CRYPTO_TICK — "
            "backtest foloseste formula forex (inexact). "
            "Adauga in _INDEX_TICK din strategy/costs.py pentru acuratete.", symbol
        )
        _WARNED_UNKNOWN.add(symbol)
    pip = pip_size(symbol)
    val_in_quote = pip * CONTRACT
    quote = symbol[3:]
    if quote == "USD":
        return val_in_quote
    if symbol[:3] == "USD":
        return val_in_quote / price
    if quote == "JPY" and usdjpy_rate:
        return val_in_quote / usdjpy_rate
    if quote in BASE_USD_APROX:
        return val_in_quote * BASE_USD_APROX[quote]
    # Cross pairs (ex: AUDCAD, AUDNZD, EURCAD, GBPCAD): convertim val_in_quote
    # (in quote currency) la USD via rata bazei: val_quote × USD_base / cross_price
    # = val_quote × USD_base / (base/quote) = val_quote × USD_base × (quote/base)
    # = val_quote / (base/USD) = val_quote_in_USD. Formula corecta 1:1 cu MT5.
    return val_in_quote * BASE_USD_APROX.get(symbol[:3], 1.0) / price


def notional_usd(symbol, price, lots):
    """Expunerea (notional) in USD — folosit doar la calculul marjei."""
    if symbol in _INDEX_TICK:
        tick_size, tick_value_usd = _INDEX_TICK[symbol]
        pip_val = tick_value_usd / tick_size
        return lots * price * pip_val          # notional USD = lots × pret × valoare/punct
    if symbol in _CRYPTO_TICK:
        return lots * price                    # 1 lot = 1 moneda, notional = lots × price_USD
    # ---- forex (cod neschimbat) ----
    base = symbol[:3]
    if base == "USD":
        return lots * CONTRACT
    if symbol[3:] == "USD":
        return lots * CONTRACT * price
    return lots * CONTRACT * BASE_USD_APROX.get(base, 1.0)
