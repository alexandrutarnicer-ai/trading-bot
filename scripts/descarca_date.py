"""
Descarca date istorice din MT5 -> CSV  (versiunea pentru strategie)
-------------------------------------------------------------------
Trage M15, M30, H1, D1 pentru cele trei perechi si salveaza in ./data/

Inainte sa rulezi:
  - MT5 desktop deschis si logat.
  - pip install MetaTrader5 pandas

Rulare (din folderul trading-bot):  python scripts/descarca_date.py
"""

import os
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import pandas as pd

if not mt5.initialize():
    print("EROARE la initialize():", mt5.last_error())
    quit()

# salvam in folderul data/ (il cream daca nu exista)
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

simboluri = ["EURUSD", "GBPUSD", "USDJPY", "AUDJPY", "CADJPY", "NZDJPY", "CHFJPY"]

# (timeframe, cate bare). M15 are nevoie de multe bare pt cativa ani.
timeframes = {
    "M15": (mt5.TIMEFRAME_M15, 60000),
    "M30": (mt5.TIMEFRAME_M30, 60000),
    "H1":  (mt5.TIMEFRAME_H1,  30000),
    "D1":  (mt5.TIMEFRAME_D1,   2500),
}

print("Descarc date...\n")

for sym in simboluri:
    if not mt5.symbol_select(sym, True):
        print(f"  {sym}: nu am putut selecta simbolul")
        continue

    for tf_nume, (tf, n_bare) in timeframes.items():
        rates = mt5.copy_rates_from_pos(sym, tf, 0, n_bare)

        # fallback: daca nu merge cu numar de bare, incearca pe interval de date
        if rates is None or len(rates) == 0:
            to = datetime.now()
            frm = to - timedelta(days=365 * 4)
            rates = mt5.copy_rates_range(sym, tf, frm, to)

        if rates is None or len(rates) == 0:
            print(f"  {sym} {tf_nume}: nu am primit date ->", mt5.last_error())
            print(f"     (deschide chartul {sym} {tf_nume} in MT5 si deruleaza")
            print(f"      in stanga ca sa forteze descarcarea, apoi reruleaza)")
            continue

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")

        cale = os.path.join(DATA_DIR, f"{sym}_{tf_nume}.csv")
        df.to_csv(cale, index=False)

        print(f"  {sym} {tf_nume}: {len(df)} bare  ->  {cale}")
        print(f"     interval: {df['time'].min()}  ...  {df['time'].max()}")

mt5.shutdown()
print("\nGata. Datele sunt in folderul ./data/")