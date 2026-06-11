"""
Descarca date forex extinse pentru perechi Asia session
=======================================================
Target: AUDJPY, NZDUSD, NZDJPY, AUDUSD — cat mai mult istoriec din MT5
Daca brokerul furnizeaza >2 ani, va imbunatati calitatea testelor.

Rulare: python scripts/research/descarca_forex_extra.py
"""
import os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    import MetaTrader5 as mt5
    import pandas as pd
except ImportError:
    print("EROARE: pip install MetaTrader5 pandas")
    sys.exit(1)

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

SYMBOLS = ["AUDJPY", "NZDUSD", "NZDJPY", "AUDUSD"]
MAX_BARS = 200_000   # maxim posibil din MT5

if not mt5.initialize():
    print("EROARE initialize MT5:", mt5.last_error())
    print("Asigura-te ca MT5 e deschis si logat.")
    sys.exit(1)

print(f"MT5 versiune: {mt5.version()}")
print(f"Descarcam pana la {MAX_BARS:,} bare M15 + M30 per simbol\n")

for sym in SYMBOLS:
    if not mt5.symbol_select(sym, True):
        print(f"  {sym}: nu a putut fi selectat in Market Watch")
        continue

    info = mt5.symbol_info(sym)
    if info is None:
        print(f"  {sym}: info N/A")
        continue

    for tf_name, tf in [("M15", mt5.TIMEFRAME_M15), ("M30", mt5.TIMEFRAME_M30)]:
        rates = mt5.copy_rates_from_pos(sym, tf, 0, MAX_BARS)
        if rates is None or len(rates) == 0:
            print(f"  {sym} {tf_name}: fara date — {mt5.last_error()}")
            continue

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df[["time", "open", "high", "low", "close", "tick_volume"]]
        df.columns = ["time", "open", "high", "low", "close", "volume"]

        t0 = df["time"].iloc[0].strftime("%Y-%m-%d")
        t1 = df["time"].iloc[-1].strftime("%Y-%m-%d")
        yrs = (df["time"].iloc[-1] - df["time"].iloc[0]).days / 365.25

        outfile = os.path.join(DATA_DIR, f"{sym}_{tf_name}.csv")
        existing = 0
        if os.path.exists(outfile):
            existing = sum(1 for _ in open(outfile)) - 1

        df.to_csv(outfile, index=False)
        new_rows = sum(1 for _ in open(outfile)) - 1

        status = "ACTUALIZAT" if new_rows > existing else "NESCHIMBAT"
        print(f"  {sym} {tf_name}: {len(df):,} bare  {t0} -> {t1}  ({yrs:.1f} ani)  [{status}]")

mt5.shutdown()
print("\nGata! Fisierele CSV au fost actualizate in data/")
