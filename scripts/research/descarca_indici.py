"""
Descarca date istorice pentru indici din MT5 -> CSV
----------------------------------------------------
Incearca mai multe variante de nume de simbol per indice
(numele difera intre brokeri).

Rulare (din folderul trading-bot):  python scripts/descarca_indici.py
"""

import os
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import pandas as pd

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# Variante de nume per indice — se opreste la primul care functioneaza
SYMBOL_CANDIDATES = {
    "US500": ["US500", "SP500", "SPX500", "US500Cash", "SP500m", "US.500"],
    "US100": ["US100", "NAS100", "NASDAQ100", "US100Cash", "NQ100m", "NDX100"],
    "GER40": ["GER40", "DAX40", "GER40Cash", "DE40", "DAX", "GDAX", "GER40."],
}

TIMEFRAMES = {
    "M15": (mt5.TIMEFRAME_M15, 60000),
    "M30": (mt5.TIMEFRAME_M30, 60000),
    "H1":  (mt5.TIMEFRAME_H1,  30000),
    "D1":  (mt5.TIMEFRAME_D1,   2500),
}

if not mt5.initialize():
    print("EROARE la initialize():", mt5.last_error())
    quit()

print("Descarc date indici...\n")

for index_name, candidates in SYMBOL_CANDIDATES.items():
    sym_found = None
    for candidate in candidates:
        info = mt5.symbol_info(candidate)
        if info is not None:
            if mt5.symbol_select(candidate, True):
                sym_found = candidate
                print(f"  {index_name}: simbol gasit ca '{candidate}'")
                break
    if sym_found is None:
        print(f"  {index_name}: NU am gasit simbolul. Incercat: {candidates}")
        print(f"     -> Deschide MT5, cauta manual simbolul si adauga-l in Market Watch,")
        print(f"        apoi editeaza SYMBOL_CANDIDATES in acest script cu numele corect.")
        continue

    for tf_name, (tf, n_bars) in TIMEFRAMES.items():
        rates = mt5.copy_rates_from_pos(sym_found, tf, 0, n_bars)

        if rates is None or len(rates) == 0:
            to = datetime.now()
            frm = to - timedelta(days=365 * 4)
            rates = mt5.copy_rates_range(sym_found, tf, frm, to)

        if rates is None or len(rates) == 0:
            print(f"    {tf_name}: nu am primit date -> {mt5.last_error()}")
            print(f"    -> Deschide chartul {sym_found} {tf_name} in MT5 si deruleaza")
            print(f"       in stanga, apoi reruleaza scriptul.")
            continue

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")

        # salveaza sub numele de indice standard (nu varianta broker)
        cale = os.path.join(DATA_DIR, f"{index_name}_{tf_name}.csv")
        df.to_csv(cale, index=False)
        print(f"    {tf_name}: {len(df)} bare -> {cale}")
        print(f"           interval: {df['time'].min()} ... {df['time'].max()}")

mt5.shutdown()
print("\nGata. Datele sunt in folderul ./data/")
