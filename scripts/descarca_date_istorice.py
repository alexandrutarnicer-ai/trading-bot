"""
Descarca date istorice din MT5 -> CSV
--------------------------------------
Trage barele OHLC pentru perechile alese, pe H1 si Daily,
si le salveaza ca fisiere CSV in folderul curent.

Inainte sa rulezi:
  - MT5 desktop deschis si logat.
  - pip install MetaTrader5 pandas

Rulare:  python descarca_date_istorice.py
"""

import MetaTrader5 as mt5
import pandas as pd

if not mt5.initialize():
    print("EROARE la initialize():", mt5.last_error())
    quit()

simboluri = ["EURUSD", "GBPUSD", "GBPJPY"]

# Timeframe-urile pe care le testam si cate bare tragem din fiecare
timeframes = {
    "H1": (mt5.TIMEFRAME_H1, 30000),   # ~ multi ani de ore
    "D1": (mt5.TIMEFRAME_D1,  2500),   # ~ 8-9 ani de zile
}

print("Descarc date...\n")

for sym in simboluri:
    # ne asiguram ca simbolul e activ in Market Watch
    if not mt5.symbol_select(sym, True):
        print(f"  {sym}: nu am putut selecta simbolul")
        continue

    for tf_nume, (tf, n_bare) in timeframes.items():
        rates = mt5.copy_rates_from_pos(sym, tf, 0, n_bare)

        if rates is None or len(rates) == 0:
            print(f"  {sym} {tf_nume}: nu am primit date ->", mt5.last_error())
            print(f"     (sfat: deschide chartul {sym} {tf_nume} in MT5 si")
            print(f"      deruleaza in stanga ca sa forteze descarcarea istoricului)")
            continue

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")

        fisier = f"{sym}_{tf_nume}.csv"
        df.to_csv(fisier, index=False)

        print(f"  {sym} {tf_nume}: {len(df)} bare  ->  {fisier}")
        print(f"     interval: {df['time'].min()}  ...  {df['time'].max()}")

mt5.shutdown()
print("\nGata. Cauta fisierele CSV in folderul curent.")
