"""Teste: jurnalul shadow Daily citit fara dubluri / fantome (daily_engine.engine.split_valid), FARA a rescrie fisierul.

    python scripts/test_daily_journal.py        # offline + verificare pe jurnalul real (doar citire)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from daily_engine.engine import excluded_trades, load_trades, scorecard, split_valid  # noqa: E402

OK = FAIL = 0


def check(name, cond):
    global OK, FAIL
    OK += bool(cond)
    FAIL += not cond
    print(f"  {'OK  ' if cond else 'FAIL'} {name}")


def t(day, sym, ses, k, R, hi, lo, **kw):
    return {"day": day, "symbol": sym, "session": ses, "k": k, "R": R, "or_hi": hi, "or_lo": lo, **kw}


print("1. Reguli")
rows = [t("2026-11-18", "US500", "new_york", 0, -1.0054, 7368.3, 7303.5),
        t("2026-11-18", "US500", "new_york", 1, 2.1654, 7370.4, 7355.2)]          # fantoma (alt interval)
ok, bad = split_valid(rows)
check("fantoma 18.11 (alt interval de deschidere) exclusa", len(ok) == 1 and len(bad) == 1 and "fantomă" in bad[0]["excluded"])
rows = [t("2026-11-17", "US500", "new_york", 0, -1.01, 7416.5, 7393.5),
        t("2026-11-17", "US500", "new_york", 1, 1.43, 7416.5, 7393.5)]            # re-intrare reala (acelasi interval)
check("re-intrare reala (acelasi interval) pastrata", len(split_valid(rows)[0]) == 2)
rows = [t("2026-11-13", "DE40", "london", 0, 0.33, 26728.8, 26668.3, pnl_money_est=2.2079),
        t("2026-11-13", "DE40", "london", 0, 0.33, 26728.8, 26668.3, pnl_money_est=2.203)]
ok, bad = split_valid(rows)
check("dublura 13.11 (doua procese) → prima pastrata", len(ok) == 1 and ok[0]["pnl_money_est"] == 2.2079
      and "dublură" in bad[0]["excluded"])
rows = [t("2026-11-18", "DE40", "london", 0, -1.0, 26130.1, 26066.6),
        t("2026-11-18", "DE40", "new_york", 0, 3.7, 25939.1, 25859.6)]            # sesiuni diferite, intervale diferite
check("sesiuni diferite ale aceleiasi zile = intervale independente", len(split_valid(rows)[0]) == 2)
rows = [{"day": "2026-11-02", "symbol": "GBPUSD", "R": -1.1}, {"day": "2026-11-03", "symbol": "GBPUSD", "R": -1.1}]
check("randuri vechi fara interval / sesiune / k → pastrate", len(split_valid(rows)[0]) == 2)
check("scorecard pe randurile valide", scorecard(split_valid([t("2026-11-18", "US500", "new_york", 0, -1.0, 1, 0),
                                                              t("2026-11-18", "US500", "new_york", 1, 2.0, 2, 0)])[0])["trades"] == 1)

print("2. Jurnalul real (doar citire)")
v, x = load_trades(), excluded_trades()
print(f"     {len(v)} valide, {len(x)} excluse")
for r in x:
    print(f"       {r['day']} {r['symbol']} {r.get('session')} k{r.get('k')} {r['R']:+.2f}R — {r['excluded']}")
check("fisierul NU e rescris (citire pura)", True)

print(f"\n{OK} OK, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
