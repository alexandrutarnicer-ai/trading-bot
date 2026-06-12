"""
Descarcare date — Session 7 Research (H1+H4 scan)
==================================================
Date noi necesare pentru combo H1+H4 (netestata in S6):
  - XAUUSD: H1, H4, D1  (M15+M30 exista deja)
  - GER40:  H4           (H1+D1 exista deja, H4 lipsea din S6)
  - EURJPY: H4           (H1+D1 exista deja)

Nu suprascrie fisiere mai bune existente.

Rulare: python scripts/research/descarca_s7.py
"""

import os
import sys
from datetime import datetime, timedelta

import MetaTrader5 as mt5
import pandas as pd

ROOT     = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TF_MAP = {
    "M30": (mt5.TIMEFRAME_M30, 200_000),
    "H1":  (mt5.TIMEFRAME_H1,   60_000),   # ~7 ani H1 24h
    "H4":  (mt5.TIMEFRAME_H4,   15_000),   # ~7 ani H4 24h
    "D1":  (mt5.TIMEFRAME_D1,    3_000),   # ~12 ani D1
}

# ---------------------------------------------------------------------------
# Ce descarcam — exact ce lipseste pentru H1+H4 scan
# ---------------------------------------------------------------------------
TARGETS = [
    # XAUUSD — Gold: nevoie de H1 + H4 + D1 (M15+M30 exista deja)
    ("XAUUSD",  "H1"),
    ("XAUUSD",  "H4"),
    ("XAUUSD",  "D1"),
    # GER40 — lipsea H4 din S6 download
    ("GER40",   "H4"),
    # EURJPY — lipsea H4
    ("EURJPY",  "H4"),
]

# Fallback-uri per simbol (brokeri diferiti au denumiri diferite)
FALLBACKS = {
    "XAUUSD": ["XAUUSD", "GOLD", "XAUUSDm", "XAUUSD.c", "XAUUSDc"],
    "GER40":  ["GER40",  "GER40.cash", "DAX40", "DAX30", "DE30", "DE40"],
}


def resolve_symbol(sym: str) -> str | None:
    """Incearca simbolul si fallback-urile, returneaza primul valid."""
    for candidate in FALLBACKS.get(sym, [sym]):
        if mt5.symbol_select(candidate, True):
            info = mt5.symbol_info(candidate)
            if info is not None:
                return candidate
    return None


def descarcare(sym: str, tf_name: str) -> tuple:
    """Descarca bare si returneaza (df, n) sau (None, 0)."""
    tf_const, n_req = TF_MAP[tf_name]
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
            return False
    df.to_csv(path, index=False)
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if not mt5.initialize():
    print("EROARE la initialize():", mt5.last_error())
    sys.exit(1)

print("=" * 70)
print("  DESCARCARE S7 — XAUUSD (H1/H4/D1) + GER40/EURJPY (H4)")
print("=" * 70)

saved = 0
skipped = 0
failed = 0

sym_cache: dict[str, str | None] = {}  # sym -> resolved name

for sym, tf_name in TARGETS:
    # Rezolva simbolul
    if sym not in sym_cache:
        sym_cache[sym] = resolve_symbol(sym)
    real_sym = sym_cache[sym]

    if real_sym is None:
        print(f"  {sym:10s} {tf_name}: simbol indisponibil la broker")
        failed += 1
        continue

    df, n = descarcare(real_sym, tf_name)
    if df is None:
        print(f"  {sym:10s} {tf_name}: ESUAT (mt5={mt5.last_error()})")
        failed += 1
        continue

    ani = (df["time"].max() - df["time"].min()).days / 365.25
    ok  = salveaza(sym, tf_name, df)    # salvam cu numele canonical (XAUUSD, nu GOLD)
    status = "SALVAT" if ok else "EXISTENT mai bun"
    print(f"  {sym:10s} {tf_name}: {n:6d} bare  {ani:.1f}a  [{status}]")
    if ok:
        saved += 1
    else:
        skipped += 1

mt5.shutdown()

print(f"\n{'='*70}")
print(f"  GATA — Salvate: {saved}  |  Existente (sarite): {skipped}  |  Esuate: {failed}")
print(f"  Urmatorul pas: python scripts/research/session7_scan.py")
