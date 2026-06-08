"""
Descarca date M5 pentru perechi extra (Session 2 extended).
Rulare: python scripts/descarca_m5_extra.py
MT5 trebuie sa fie deschis si logat.
"""
import os, sys
import MetaTrader5 as mt5
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

SIMBOLURI = ["AUDJPY", "NZDJPY", "GBPJPY", "EURGBP", "AUDUSD", "CADJPY", "CHFJPY", "USDCAD"]
N_BARE    = 500_000   # ~3.5 ani de date M5

if not mt5.initialize():
    print("EROARE:", mt5.last_error()); sys.exit(1)

acc = mt5.account_info()
print(f"Conectat: {acc.login} @ {acc.server}\n")

for sym in SIMBOLURI:
    if not mt5.symbol_select(sym, True):
        print(f"  {sym}: nu e disponibil"); continue

    print(f"  {sym}: descarc {N_BARE:,} bare M5...", end=" ", flush=True)
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, N_BARE)
    if rates is None or len(rates) == 0:
        print(f"EROARE: {mt5.last_error()}"); continue

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    cale = os.path.join(DATA_DIR, f"{sym}_M5.csv")
    df.to_csv(cale, index=False)
    print(f"{len(df):,} bare | {df['time'].min().date()} - {df['time'].max().date()}")

mt5.shutdown()
print("\nGata.")
