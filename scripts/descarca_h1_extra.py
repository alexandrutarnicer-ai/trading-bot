"""
Descarca date istorice extinse — USDCAD, USDCHF, AUDJPY, CADJPY
================================================================
Aceste simboluri au date H1/D1 limitate in data/ (1-2 ani insuficienti).
Scriptul cere maxim disponibil de la broker: M15+M30+H1+D1.

INAINTE DE RULARE:
  1. MT5 deschis si logat.
  2. Recomandat: deschide charturi ale simbolurilor in MT5 si deruleaza
     complet in stanga (Ctrl+Home) pentru a forta incarcarea istoricului.
  3. Rulare: python scripts/descarca_h1_extra.py

Date descarcate vor suprascrie fisierele existente in data/.
Dupa download, ruleaza:  python scripts/research/tf_scan_targeted.py
"""

import os
import sys
from datetime import datetime, timedelta

import MetaTrader5 as mt5
import pandas as pd

ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Simboluri cu date insuficiente — target: >5 ani H1
SIMBOLURI = ["USDCAD", "USDCHF", "AUDJPY", "CADJPY"]

# Cate bare cerem per timeframe (broker limiteaza la ce are disponibil)
TIMEFRAMES = {
    "M15": (mt5.TIMEFRAME_M15, 100_000),   # ~2.5 ani M15 24/7
    "M30": (mt5.TIMEFRAME_M30, 100_000),   # ~5 ani M30 24/7
    "H1":  (mt5.TIMEFRAME_H1,   50_000),   # ~5.7 ani H1 24/7
    "D1":  (mt5.TIMEFRAME_D1,    2_500),   # ~10 ani D1
}

if not mt5.initialize():
    print("EROARE la initialize():", mt5.last_error())
    print("Asigura-te ca MT5 e deschis si logat.")
    sys.exit(1)

print("=" * 60)
print(f"  Descarcare date extinse: {SIMBOLURI}")
print(f"  Target: minim 5 ani H1 per simbol")
print(f"  Output: {DATA_DIR}")
print("=" * 60)

summary = []

for sym in SIMBOLURI:
    print(f"\n  {sym}")
    if not mt5.symbol_select(sym, True):
        print(f"    EROARE: nu am putut selecta simbolul — sarit")
        continue

    for tf_name, (tf, n_max) in TIMEFRAMES.items():
        # Metoda 1: numar maxim de bare din pozitia curenta
        rates = mt5.copy_rates_from_pos(sym, tf, 0, n_max)

        # Metoda 2: fallback cu interval de date (10 ani)
        if rates is None or len(rates) == 0:
            to  = datetime.now()
            frm = to - timedelta(days=365 * 10)
            rates = mt5.copy_rates_range(sym, tf, frm, to)

        if rates is None or len(rates) == 0:
            err = mt5.last_error()
            print(f"    {tf_name}: ESUAT ({err})")
            print(f"      Sfat: deschide chartul {sym} {tf_name} in MT5,")
            print(f"            apasa Ctrl+Home pentru a incarca istoricul.")
            summary.append((sym, tf_name, 0, None, None))
            continue

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")

        path = os.path.join(DATA_DIR, f"{sym}_{tf_name}.csv")
        df.to_csv(path, index=False)

        n_bars = len(df)
        t_min  = df["time"].min().date()
        t_max  = df["time"].max().date()
        years  = (df["time"].max() - df["time"].min()).days / 365.25

        flag = " OK" if years >= 4 else f" !! (numai {years:.1f} ani)"
        print(f"    {tf_name}: {n_bars:7d} bare  [{t_min} .. {t_max}]  {years:.1f}a{flag}")
        summary.append((sym, tf_name, n_bars, t_min, t_max))

# Sumar final
print("\n" + "=" * 60)
print("  SUMAR FINAL")
print("=" * 60)
for sym, tf, n, t1, t2 in summary:
    if n == 0:
        print(f"  {sym:8s} {tf:4s}: LIPSA")
    else:
        years = (t2 - t1).days / 365.25 if t1 and t2 else 0
        status = "OK" if years >= 4 else "LIMITAT"
        print(f"  {sym:8s} {tf:4s}: {n:7d} bare  {years:.1f}a  [{status}]")

mt5.shutdown()
print("\nGata. Urmatorul pas:")
print("  python scripts/research/tf_scan_targeted.py")
