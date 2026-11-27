"""Teste: calendarul burselor (NYSE / Xetra) + aplicarea lui in Daily si Special (27.11.2026) — offline, fara MT5.

Incident 26.11.2026 (Thanksgiving): DE40 inchis la broker la 22:55 RO, fereastra NY a Daily pana la 23:00 RO → pozitia
D-DE40-1126N a ramas peste noapte (inchisa abia la 01:05 de sweep_stale).

    python scripts/test_market_calendar.py
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import market_calendar as C  # noqa: E402

OK = FAIL = 0


def check(name, cond, info=None):
    global OK, FAIL
    OK += bool(cond)
    FAIL += not cond
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + ("" if cond or info is None else f"  → {info}"))


NY, DE = "America/New_York", "Europe/Berlin"
print("1. Calendarul NYSE")
check("Thanksgiving 26.11.2026 = închis", C.session_status(NY, date(2026, 11, 26))["closed"])
s = C.session_status(NY, date(2026, 11, 27))
check("ziua de după Thanksgiving = închidere 13:00", not s["closed"] and s["early_close"].hour == 13, s)
check("Ajunul Crăciunului 2026 (joi) = 13:00", C.session_status(NY, date(2026, 12, 24))["early_close"] is not None)
check("Crăciun 2026 = închis", C.session_status(NY, date(2026, 12, 25))["closed"])
check("4 iulie 2026 (sâmbătă) → închis vineri 3 iulie", C.session_status(NY, date(2026, 7, 3))["closed"])
check("Vinerea Mare 2026 (3 aprilie, din data Paștelui) = închis", C.session_status(NY, date(2026, 4, 3))["closed"])
check("Thanksgiving 2027 = 25.11", C.session_status(NY, date(2027, 11, 25))["closed"])
check("zi obișnuită (25.11.2026) = deschis, fără închidere devreme",
      C.session_status(NY, date(2026, 11, 25)) == {"known": True, "closed": False, "early_close": None, "name": ""})
print("2. Xetra + burse necunoscute")
check("Xetra: 24 / 25 / 26 / 31 decembrie închis", all(C.session_status(DE, date(2026, 12, d))["closed"] for d in (24, 25, 31)))
check("Xetra: Lunea Paștelui 2026 (6 aprilie) închis", C.session_status(DE, date(2026, 4, 6))["closed"])
check("Xetra: Thanksgiving = deschis (nu e sărbătoare germană)", not C.session_status(DE, date(2026, 11, 26))["closed"])
check("Tokyo: necunoscut → nu schimbă nimic", C.session_status("Asia/Tokyo", date(2026, 11, 26))["known"] is False)
print("3. Fereastra scurtată (15 min înainte de închiderea devreme)")
check("NY 15:55 → 12:40 (bara se închide la 12:45, 15 min înainte de 13:00)",
      C.capped_last_bar("15:55", NY, date(2026, 11, 27))[0] == "12:40")
check("zi obișnuită → neschimbat, fără motiv", C.capped_last_bar("15:55", NY, date(2026, 11, 25)) == ("15:55", ""))
check("Frankfurt în ziua de după Thanksgiving → neschimbat", C.capped_last_bar("17:25", DE, date(2026, 11, 27)) == ("17:25", ""))

print("4. Daily Engine: sesiunea NY pe Thanksgiving nu deschide nimic; în ziua cu închidere devreme fereastra e scurtată")
from daily_engine import engine as DE_  # noqa: E402
from daily_engine.config import DEFAULTS  # noqa: E402
from daily_engine.market_tools import PRESETS  # noqa: E402

eng = object.__new__(DE_.DailyEngine)            # doar _eval_session pana la verificarea calendarului (fara MT5)
ny = {**PRESETS["new_york"], "symbol": "DE40", "label": "", "role": "", "enabled": True, "_session": "new_york",
      "rr": None, "reentry": None, "slip": 0.1, "comm": 0.0}
t = datetime(2026, 11, 26, 11, 0, tzinfo=ZoneInfo(NY)).astimezone(timezone.utc)
r = eng._eval_session(ny, t)
check("26.11 (Thanksgiving): faza skipped, motivul în clar, fără evaluare / ordine",
      r.get("row", {}).get("phase") == "skipped" and "Thanksgiving" in r["row"].get("reason", ""), r.get("row"))
w_open, w_end = DE_.window_times({**ny, "last_bar": C.capped_last_bar(ny["last_bar"], NY, date(2026, 11, 27))[0]},
                                 date(2026, 11, 27))
check("27.11: sfârșitul ferestrei NY = 12:45 NY = 19:45 RO (înainte de 13:00 NY)",
      w_end.strftime("%H:%M") == "12:45" and w_end.astimezone(ZoneInfo("Europe/Bucharest")).strftime("%H:%M") == "19:45",
      w_end)
fr = {**PRESETS["frankfurt"], "symbol": "DE40", "label": "", "role": "", "enabled": True, "_session": "frankfurt",
      "rr": None, "reentry": None, "slip": 0.1, "comm": 0.0}
r2 = eng._eval_session(fr, datetime(2026, 12, 24, 10, 0, tzinfo=ZoneInfo(DE)).astimezone(timezone.utc))
check("24.12 (Xetra închis): sesiunea Frankfurt nu deschide nimic", r2.get("row", {}).get("phase") == "skipped", r2.get("row"))
check("configurația implicită are o sesiune NY (calendarul se aplică)", any(m.get("preset") == "new_york"
                                                                        for m in DEFAULTS["markets"]))

print(f"\n{OK} OK, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
