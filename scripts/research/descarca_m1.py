"""
Descarca date M1 din MT5 -> CSV
---------------------------------
Trage bare M1 pentru EURUSD, GBPUSD, EURJPY (portofoliul core).
~500k bare per simbol (aprox 4-5 ani de date M1).

CERINTE:
  - MT5 desktop deschis si logat pe cont demo
  - pip install MetaTrader5 pandas
  - Deschide chartul M1 pentru fiecare simbol in MT5 si deruleaza
    cat mai mult in stanga (forteaza descarcarea istoricului)

Rulare (din folderul trading-bot):  python scripts/descarca_m1.py

Output: data/EURUSD_M1.csv, data/GBPUSD_M1.csv, data/EURJPY_M1.csv
"""

import os
import sys
import MetaTrader5 as mt5
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)

SIMBOLURI = ["EURUSD", "GBPUSD", "EURJPY"]

# 500k bare M1 = ~347 zile de tranzactionare = ~1.4 ani
# 1M bare M1  = ~694 zile = ~2.8 ani
# 2M bare M1  = ~1388 zile = ~5.5 ani (poate depasi limita MT5)
# Incercam 2M si luam cat da brokerul
N_BARE = 2_000_000

if not mt5.initialize():
    print("EROARE la initialize():", mt5.last_error())
    print("Asigura-te ca MT5 este deschis si logat.")
    sys.exit(1)

acc = mt5.account_info()
if acc:
    print(f"Conectat: {acc.login} @ {acc.server} | {acc.currency} | {'DEMO' if acc.trade_mode == 0 else 'LIVE'}")
    if acc.trade_mode != 0:
        print("ATENTIE: cont LIVE detectat. Descarcarea datelor este sigura dar verifica.")
else:
    print("Nu am putut citi informatii cont.")

print(f"\nDescarc date M1 -> {DATA_DIR}\n")

for sym in SIMBOLURI:
    if not mt5.symbol_select(sym, True):
        print(f"  {sym}: nu am putut selecta simbolul -> {mt5.last_error()}")
        continue

    print(f"  {sym}: incerc {N_BARE:,} bare M1...", end=" ", flush=True)
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M1, 0, N_BARE)

    if rates is None or len(rates) == 0:
        print(f"\n    EROARE: nu am primit date -> {mt5.last_error()}")
        print(f"    Sfat: deschide chartul {sym} M1 in MT5, deruleaza complet in stanga,")
        print(f"    asteptati sa se incarce, apoi rerulati scriptul.")
        continue

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")

    cale = os.path.join(DATA_DIR, f"{sym}_M1.csv")
    df.to_csv(cale, index=False)

    print(f"{len(df):,} bare")
    print(f"    interval: {df['time'].min()} ... {df['time'].max()}")
    print(f"    salvat: {cale}")

mt5.shutdown()
print("\nGata. Acum poti rula:  python m1_test.py")
