"""
Test: ritmul de tranzactionare pe engine (api/routers/dashboard.py::pace) — offline, fara MT5.
    python scripts/test_trading_pace.py
"""
import os
import sys
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.routers.dashboard import pace, _week_start  # noqa: E402

PASS = FAIL = 0


def check(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {detail}")


NOW = datetime(2026, 11, 18, 15, 0)           # miercuri
WEEK = _week_start(NOW)                         # luni 16.11


def trades_per_week(counts: list[int]) -> list[datetime]:
    """counts[0] = saptamana trecuta, counts[1] = acum 2 saptamani, ..."""
    out = []
    for i, c in enumerate(counts, start=1):
        ws = WEEK - timedelta(days=7 * i)
        out += [ws + timedelta(days=1, hours=h) for h in range(c)]
    return out


print("1. Date insuficiente")
r = pace(trades_per_week([10]), NOW, WEEK - timedelta(days=7))
check(r["confidence"] == "insufficient" and r["per_week"] is None, "o singura saptamana completa -> insuficient", r)
r = pace(trades_per_week([1, 1, 1]), NOW, None)
check(r["confidence"] == "insufficient", "< 5 trade-uri -> insuficient", r)
r = pace([], NOW, NOW - timedelta(days=2))
check(r["weeks"] == 0 and r["confidence"] == "insufficient", "regim pornit azi -> 0 saptamani complete")

print("2. Regimul curent taie istoricul vechi")
tr = trades_per_week([2, 2, 2, 20, 20, 20])
since = WEEK - timedelta(days=7 * 3)            # schimbare la inceputul saptamanii -3
r = pace(tr, NOW, since)
check(r["weeks"] == 2, "doar saptamanile complete de DUPA schimbare (2)", r["weeks"])
check(r["trades_in_window"] == 4, "trade-urile din regimul vechi nu se numara", r["trades_in_window"])

print("3. Ponderare: recentul conteaza mai mult")
S6 = WEEK - timedelta(days=7 * 7)              # regim pornit inainte de cele 6 saptamani
up = pace(trades_per_week([10, 8, 6, 4, 2, 0]), NOW, S6)
dn = pace(trades_per_week([0, 2, 4, 6, 8, 10]), NOW, S6)
check(up["per_week"] > 5 > dn["per_week"], "media ponderata urmeaza tendinta recenta", (up["per_week"], dn["per_week"]))

print("4. Interval si saptamana curenta")
r = pace(trades_per_week([4, 5, 6, 5, 4, 6, 5, 4]) + [WEEK + timedelta(hours=10)] * 3, NOW, None)
check(r["current_week"] == 3, "saptamana curenta raportata separat (nu intra in medie)", r["current_week"])
check(r["low"] <= r["per_week"] <= r["high"], "media e in intervalul P20–P80", (r["low"], r["per_week"], r["high"]))
check(r["weekly"][-1] == 4, "seria saptamanala e cronologica (ultima = saptamana trecuta)", r["weekly"])

print("5. Incredere")
gaps = pace(trades_per_week([5, 4, 6, 5]), NOW, None)
check(gaps["weeks"] == 12, "fara inceput de regim: fereastra maxima (12 saptamani, apelantii dau mereu un inceput)")
stable = pace(trades_per_week([6] * 10), NOW, None)
check(stable["confidence"] == "high", "60 trade-uri, 10 saptamani stabile -> ridicata", stable["confidence"])
noisy = pace(trades_per_week([0, 12, 0, 12, 0, 12]), NOW, None)
check(noisy["confidence"] == "low", "saptamani foarte instabile -> scazuta", noisy["confidence"])
mid = pace(trades_per_week([5, 4, 6, 5]), NOW, WEEK - timedelta(days=7 * 5))
check(mid["confidence"] == "medium", "20 trade-uri, 4 saptamani -> medie", mid["confidence"])

print(f"\nREZULTAT: {PASS} PASS / {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
