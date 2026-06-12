"""
Descarcare M15 pentru AUDNZD si AUDCAD
=======================================
Aceste perechi au M30/H1/H4/D1 dar nu au M15 (necesar pentru scan M15+M30).

Rulare: python scripts/research/descarca_audcross_m15.py
"""

import os, sys
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import pandas as pd

ROOT     = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(ROOT, "data")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TARGETS = ["AUDNZD", "AUDCAD"]

if not mt5.initialize():
    print("EROARE initialize():", mt5.last_error())
    sys.exit(1)

print("=" * 60)
print("  DESCARCARE M15 — AUDNZD + AUDCAD")
print("=" * 60)

for sym in TARGETS:
    if not mt5.symbol_select(sym, True):
        print(f"  {sym}: indisponibil la broker")
        continue

    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 300_000)
    if rates is None or len(rates) == 0:
        to  = datetime.now()
        frm = to - timedelta(days=365 * 12)
        rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M15, frm, to)

    if rates is None or len(rates) == 0:
        print(f"  {sym} M15: ESUAT")
        continue

    df  = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    ani = (df["time"].max() - df["time"].min()).days / 365.25

    path = os.path.join(DATA_DIR, f"{sym}_M15.csv")
    if os.path.exists(path):
        existing = sum(1 for _ in open(path)) - 1
        if existing >= len(df):
            print(f"  {sym} M15: {len(df):,} bare  {ani:.1f}a  [EXISTENT mai bun]")
            continue

    df.to_csv(path, index=False)
    print(f"  {sym} M15: {len(df):,} bare  {ani:.1f}a  [SALVAT]")

mt5.shutdown()
print("\n  Gata. Urmatorul pas: python scripts/research/scan_audcross.py")
