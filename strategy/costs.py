import pandas as pd

from strategy.signals import pip_size

CONTRACT = 100_000
BASE_USD_APROX = {"GBP": 1.27, "EUR": 1.10, "AUD": 0.66, "USD": 1.0}
SWAP_PER_LOT_NIGHT = {"EURUSD": 7.0, "GBPUSD": 8.0, "USDJPY": 10.0, "GBPJPY": 12.0}


def swap_cost(symbol, entry_time, exit_time, lots):
    """Cost de swap: nr. de nopti tinute x rata x loti. Miercuri = tripla."""
    e = pd.Timestamp(entry_time).normalize()
    x = pd.Timestamp(exit_time).normalize()
    nights = (x - e).days
    if nights <= 0:
        return 0.0
    units = 0
    d = e
    for _ in range(nights):
        d = d + pd.Timedelta(days=1)
        units += 3 if d.weekday() == 2 else 1     # miercuri (weekday 2) = swap triplu
    return units * SWAP_PER_LOT_NIGHT.get(symbol, 8.0) * lots


def pip_value_usd(symbol, price, usdjpy_rate=None):
    """Valoarea unui pip, pentru 1.0 lot, exprimata in USD."""
    pip = pip_size(symbol)
    val_in_quote = pip * CONTRACT          # valoare pip in moneda de cotatie
    quote = symbol[3:]
    if quote == "USD":                     # EURUSD, GBPUSD, AUDUSD
        return val_in_quote
    if symbol[:3] == "USD":                # USDJPY, USDCAD (USD ca baza)
        return val_in_quote / price        # pretul = cotatie per USD
    # cross fara USD (ex: GBPJPY) -> convertim cotatia in USD
    if quote == "JPY" and usdjpy_rate:
        return val_in_quote / usdjpy_rate  # JPY -> USD prin cursul USDJPY
    return val_in_quote / price            # fallback aproximativ


def notional_usd(symbol, price, lots):
    """Expunerea (notional) in USD (aproximativ pt cross-uri, folosit doar la marja)."""
    base = symbol[:3]
    if base == "USD":                      # baza USD
        return lots * CONTRACT
    if symbol[3:] == "USD":                # baza straina, cotatie USD
        return lots * CONTRACT * price     # pretul = USD per unitate baza
    # cross: convertim baza in USD aproximativ
    return lots * CONTRACT * BASE_USD_APROX.get(base, 1.0)
