"""
Descarca date Session 6 — H1 + H4 + M30 pentru piete noi
=========================================================
Descarca H1 pentru EUR/GBP crosses (au M30 dar nu H1),
H4 pentru toate perechile majore, si M30+H1 pentru piete noi
(AUDNZD, AUDCAD, US100, XAGUSD).

Nu suprascrie fisiere mai bune existente.

Rulare: python scripts/research/descarca_s6.py
"""

import os
import sys
from datetime import datetime, timedelta

import MetaTrader5 as mt5
import pandas as pd

ROOT     = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Ce descarcam
# ---------------------------------------------------------------------------

# Perechi cu M30 dar fara H1 (16 ani M30 — avem nevoie de H1 ca trend TF)
H1_MISSING = [
    "EURAUD", "EURCAD", "GBPAUD", "GBPCAD", "GBPNZD", "EURNZD",
    "UK100",  "US30",
]

# Piete noi complet — descarca M30 + H1 + D1
NEW_MARKETS = [
    ("AUDNZD",  ["M30", "H1", "D1"]),
    ("AUDCAD",  ["M30", "H1", "D1"]),
    ("US100",   ["M30", "H1", "D1"]),   # NAS100 la unii brokeri
    ("NAS100",  ["M30", "H1", "D1"]),   # fallback
    ("XAGUSD",  ["M30", "H1", "D1"]),
]

# H4 pentru toate perechile majore (nevoie pentru H4+D1 combo)
H4_TARGETS = [
    "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY",
    "EURAUD", "EURCAD", "GBPAUD", "GBPCAD", "GBPNZD", "EURNZD",
    "EURGBP", "CHFJPY", "GBPJPY", "CADJPY", "AUDJPY", "NZDJPY",
    "AUDNZD", "AUDCAD", "GER40",  "UK100",  "US30",   "US500",
]

TF_MAP = {
    "M30": (mt5.TIMEFRAME_M30, 200_000),   # ~11 ani M30 24h
    "H1":  (mt5.TIMEFRAME_H1,   60_000),   # ~7 ani H1 24h
    "H4":  (mt5.TIMEFRAME_H4,   15_000),   # ~7 ani H4 24h
    "D1":  (mt5.TIMEFRAME_D1,    3_000),   # ~12 ani D1
}


def descarcare(sym: str, tf_name: str, n_req: int) -> tuple:
    """Descarca bare si returneaza df sau None."""
    tf_const = TF_MAP[tf_name][0]

    rates = mt5.copy_rates_from_pos(sym, tf_const, 0, n_req)
    if rates is None or len(rates) == 0:
        to  = datetime.now()
        frm = to - timedelta(days=365 * 12)
        rates = mt5.copy_rates_range(sym, tf_const, frm, to)

    if rates is None or len(rates) == 0:
        return None, 0

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df, len(df)


def salveaza(sym: str, tf_name: str, df: pd.DataFrame) -> bool:
    """Salveaza fisierul; nu suprascrie daca existent are mai multe bare."""
    path = os.path.join(DATA_DIR, f"{sym}_{tf_name}.csv")
    if os.path.exists(path):
        existing = sum(1 for _ in open(path)) - 1
        if existing >= len(df):
            return False   # existent mai bun, sarim
    df.to_csv(path, index=False)
    return True


if not mt5.initialize():
    print("EROARE la initialize():", mt5.last_error())
    sys.exit(1)

print("=" * 70)
print("  DESCARCARE S6 — H1 + H4 + M30 pentru 25+ simboluri")
print("=" * 70)

saved = 0
skipped = 0
failed = 0

# ---- 1. H1 pentru perechile cu M30 dar fara H1 ----
print("\n[1/3] H1 pentru EUR/GBP crosses si indici...")
for sym in H1_MISSING:
    if not mt5.symbol_select(sym, True):
        print(f"  {sym:10s} H1: simbol indisponibil la broker")
        failed += 1
        continue
    df, n = descarcare(sym, "H1", TF_MAP["H1"][1])
    if df is None:
        print(f"  {sym:10s} H1: ESUAT")
        failed += 1
        continue
    ani = (df["time"].max() - df["time"].min()).days / 365.25
    ok  = salveaza(sym, "H1", df)
    status = "SALVAT" if ok else "EXISTENT mai bun"
    print(f"  {sym:10s} H1: {n:6d} bare  {ani:.1f}a  [{status}]")
    if ok:
        saved += 1
    else:
        skipped += 1

    # D1 pentru aceleasi perechi (necesar ca trend TF pentru H1+D1)
    df_d1, nd1 = descarcare(sym, "D1", TF_MAP["D1"][1])
    if df_d1 is not None:
        ok_d1 = salveaza(sym, "D1", df_d1)
        ani_d1 = (df_d1["time"].max() - df_d1["time"].min()).days / 365.25
        print(f"  {sym:10s} D1: {nd1:6d} bare  {ani_d1:.1f}a  [{'SALVAT' if ok_d1 else 'EXISTENT'}]")
        if ok_d1: saved += 1
        else:     skipped += 1

# ---- 2. Piete noi (AUDNZD, AUDCAD, US100, XAGUSD) ----
print("\n[2/3] Piete noi (AUDNZD, AUDCAD, US100/NAS100, XAGUSD)...")
us100_found = False
for sym, tfs in NEW_MARKETS:
    if sym in ("US100", "NAS100") and us100_found:
        continue
    if not mt5.symbol_select(sym, True):
        print(f"  {sym:10s}: simbol indisponibil la broker")
        continue
    for tf_name in tfs:
        df, n = descarcare(sym, tf_name, TF_MAP[tf_name][1])
        if df is None:
            print(f"  {sym:10s} {tf_name}: ESUAT")
            failed += 1
            continue
        ani = (df["time"].max() - df["time"].min()).days / 365.25
        # Normalizeaza US100/NAS100 → US100
        save_sym = "US100" if sym == "NAS100" else sym
        ok = salveaza(save_sym, tf_name, df)
        status = "SALVAT" if ok else "EXISTENT"
        print(f"  {save_sym:10s} {tf_name}: {n:6d} bare  {ani:.1f}a  [{status}]")
        if ok:
            saved += 1
            if sym in ("US100", "NAS100"):
                us100_found = True
        else:
            skipped += 1

# ---- 3. H4 pentru toate tintele ----
print("\n[3/3] H4 pentru perechile majore...")
for sym in H4_TARGETS:
    if not mt5.symbol_select(sym, True):
        print(f"  {sym:10s} H4: indisponibil")
        failed += 1
        continue
    df, n = descarcare(sym, "H4", TF_MAP["H4"][1])
    if df is None:
        print(f"  {sym:10s} H4: ESUAT")
        failed += 1
        continue
    ani = (df["time"].max() - df["time"].min()).days / 365.25
    ok  = salveaza(sym, "H4", df)
    status = "SALVAT" if ok else "EXISTENT"
    print(f"  {sym:10s} H4: {n:6d} bare  {ani:.1f}a  [{status}]")
    if ok: saved += 1
    else:  skipped += 1

mt5.shutdown()
print(f"\n{'='*70}")
print(f"  GATA — Salvate: {saved}  |  Existente (sarite): {skipped}  |  Esuate: {failed}")
print(f"  Urmatorul pas: python scripts/research/session6_scan.py")
