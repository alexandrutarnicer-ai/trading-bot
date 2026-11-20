"""Teste: filtrul NR4 al Special Engine decide DOAR pe bare D1 INCHISE (bug 20.11.2026: JP225 10.11 / 18.11).

    python scripts/test_special_nr4.py        # offline (D1 simulat) + bare REALE MT5 daca terminalul e pornit
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from special_engine import engine as SE  # noqa: E402

OK = FAIL = 0
_ORIG_FETCH = SE.D.fetch_d1


def check(name, cond, info=None):
    global OK, FAIL
    OK += bool(cond)
    FAIL += not cond
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + ("" if cond or info is None else f"  → {info}"))


# range-urile D1 reale JP225 (server): 12.11 1396 · 13.11 1784 · 16.11 2721 · 17.11 1442 (final)
D1 = pd.DataFrame({"time": pd.to_datetime(["2026-11-11", "2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18"]),
                   "high": [62264, 61792, 61915, 61541, 59389, 60173.0], "low": [60030, 60396, 60131, 58820, 57947, 58200.0]})


class FakeMt5:
    def __init__(self, d1):
        self.d1 = d1

    def symbol_select(self, *a):
        return True


def engine_with(d1_now):
    e = SE.SpecialEngine.__new__(SE.SpecialEngine)
    e._d1 = {}
    e.mt5 = FakeMt5(d1_now)
    SE.D.fetch_d1 = lambda mt5, sym, n=40: mt5.d1.copy()
    return e


print("1. Incidentul 18.11 (Tokyo) — decizia la 00:05 Tokyo = 17:05 server 17.11")
partial = D1[D1.time <= "2026-11-17"].copy()
partial.loc[partial.time == "2026-11-17", "low"] = 58500.0          # bara 17.11 IN FORMARE: range partial 889 (< 1396)
e = engine_with(partial)
now = datetime(2026, 11, 17, 15, 5, tzinfo=timezone.utc)            # = 17:05 server (NY+7) = 00:05 Tokyo 18.11
d = e._d1_for("JP225", pd.Timestamp("2026-11-18").date(), now)
check("bara 17.11 in formare → decizia NR4 AMANATA (inainte: NR4 = da, din range-ul partial)", d.attrs.get("pending") is True)
check("... bara in formare nu e folosita", d.time.max() < pd.Timestamp("2026-11-17"))
e = engine_with(D1[D1.time <= "2026-11-17"])
now = datetime(2026, 11, 17, 22, 30, tzinfo=timezone.utc)           # = 00:30 server 18.11 → bara 17.11 INCHISA
d = e._d1_for("JP225", pd.Timestamp("2026-11-18").date(), now)
check("dupa 00:00 server: bara 17.11 inchisa → decizie", d.attrs.get("pending") is False)
check("18.11 NU e NR4 (17.11: 1442 > 1396 pe 12.11)", SE.nr_flag(d, pd.Timestamp("2026-11-18"), 4) is False)
e = engine_with(D1[D1.time <= "2026-11-10"].assign() if False else pd.DataFrame({
    "time": pd.to_datetime(["2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10"]),
    "high": [63159, 58795, 60979, 60946.0], "low": [56929, 56406, 57685, 59563.0]}))
d = e._d1_for("JP225", pd.Timestamp("2026-11-11").date(), datetime(2026, 11, 10, 22, 30, tzinfo=timezone.utc))
check("11.11 E NR4 (10.11: 1383 = minimul) — singura zi NR4 reala din saptamana", SE.nr_flag(d, pd.Timestamp("2026-11-11"), 4) is True)
e = engine_with(D1)
d1 = e._d1_for("JP225", pd.Timestamp("2026-11-18").date(), datetime(2026, 11, 17, 15, 5, tzinfo=timezone.utc))
d2 = e._d1_for("JP225", pd.Timestamp("2026-11-18").date(), datetime(2026, 11, 17, 22, 30, tzinfo=timezone.utc))
check("cache-ul se reimprospateaza la schimbarea zilei serverului", d1.attrs["pending"] and not d2.attrs["pending"])

print("2. Bare REALE MT5 (doar citire)")
try:
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError("MT5 indisponibil")
    real = _ORIG_FETCH(mt5, "JP225", 60)
    for day, exp in (("2026-11-10", False), ("2026-11-11", True), ("2026-11-18", False)):
        prev = real[real.time < day]
        check(f"{day}: NR4 = {exp} pe barele finale", SE.nr_flag(prev, pd.Timestamp(day), 4) is exp)
except Exception as ex:  # noqa: BLE001
    print(f"     sarit: {ex}")

print(f"\n{OK} OK, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
