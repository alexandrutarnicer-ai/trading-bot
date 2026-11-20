"""Teste: ora serverului detectata din tick (server_clock) — bug-ul re-intrarilor fantoma de la 00:56 (20.11.2026).

    python scripts/test_server_clock.py            # unitare (offline) + reproducere pe barele REALE MT5 (doar citire)
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server_clock import ServerClock, candidate  # noqa: E402

OK = FAIL = 0


def check(name, cond):
    global OK, FAIL
    OK += bool(cond)
    FAIL += not cond
    print(f"  {'OK  ' if cond else 'FAIL'} {name}")


H = 3600
now = datetime(2026, 11, 18, 22, 56, tzinfo=timezone.utc).timestamp()   # 00:56 RO
print("1. candidate()")
check("tick proaspat → offset", candidate(now + 2 * H + 5, now) == 2 * H)
check("tick la 2 min peste ora → offset", candidate(now + 2 * H - 110, now) == 2 * H)
check("tick vechi de 30 min → nimic", candidate(now + 2 * H - 1800, now) is None)
check("tick vechi de EXACT 60 min arata ca un offset (de aici bug-ul)", candidate(now + H, now) == H)

print("2. ServerClock — incidentul 18.11")
c = ServerClock()
off = c.update("US500", now - 3 * H + 2 * H, now - 3 * H, None)                 # in timpul sesiunii: tick viu
check("pornire: prima detectare acceptata", off == 2 * H)
stale = now - H + 2 * H                                                         # ultimul tick 23:56 RO, inghetat
off = c.update("US500", stale, now - 61 * 60, off)                              # 23:57
check("23:57 tick inghetat, rest 1 min → offset neschimbat", off == 2 * H)
for k in range(5):                                                              # 00:56 … 01:00: ACELASI tick
    off = c.update("US500", stale, now + k * 15, off)
check("00:56 tick inghetat de 60 min → offset RAMANE 2h (inainte devenea 1h)", off == 2 * H)

print("3. Schimbare reala de offset (DST) — confirmata pe doua tick-uri noi")
c = ServerClock()
t0 = now
off = c.update("EURUSD", t0 + 3 * H, t0, None)
check("offset initial 3h", off == 3 * H)
off = c.update("EURUSD", t0 + 100 + 2 * H, t0 + 100, off)
check("primul tick nou cu 2h → inca 3h (asteapta confirmarea)", off == 3 * H)
off = c.update("EURUSD", t0 + 115 + 2 * H, t0 + 115, off)
check("al doilea tick nou cu 2h → 2h", off == 2 * H)
c = ServerClock()
off = c.update("EURUSD", t0 + 3 * H, t0, None)
off = c.update("EURUSD", t0 + 100 + 2 * H, t0 + 100, off)
off = c.update("EURUSD", t0 + 110 + 3 * H, t0 + 110, off)
off = c.update("EURUSD", t0 + 120 + 2 * H, t0 + 120, off)
check("o singura abatere izolata nu schimba offset-ul", off == 3 * H)
c = ServerClock()
off = c.update("US500", t0 + 2 * H, t0, None)
off = c.update("DE40", t0 + 30 + H, t0 + 30, off)
off = c.update("DE40", t0 + 45 + H, t0 + 45, off)
check("primul tick vazut pe alt simbol nu poate schimba offset-ul", off == 2 * H)

print("4. Daily + Noisy folosesc aceeasi regula")
import importlib
de = importlib.import_module("daily_engine.engine")
ne = importlib.import_module("noisy_engine.engine")
from types import SimpleNamespace  # noqa: E402


class _M:
    def __init__(self, t):
        self.t = t

    def symbol_info_tick(self, s):
        return SimpleNamespace(time=self.t, bid=1.0, ask=1.0)


for name, cls, attr in (("Daily", de.DailyEngine, "server_offset_s"), ("Noisy", ne.NoisyEngine, "offset_s")):
    eng = cls.__new__(cls)
    setattr(eng, attr, None)
    eng.mt5 = _M(now - 3 * H + 2 * H)
    eng._refresh_offset("US500", datetime.fromtimestamp(now - 3 * H, timezone.utc))
    eng.mt5 = _M(now - H + 2 * H)
    eng._refresh_offset("US500", datetime.fromtimestamp(now - 61 * 60, timezone.utc))
    eng._refresh_offset("US500", datetime.fromtimestamp(now, timezone.utc))
    check(f"{name}: tick inghetat la 00:56 nu muta ora serverului", getattr(eng, attr) == 2 * H)

print("5. Reproducere pe barele REALE (US500 18.11, MT5 doar citire)")
try:
    import MetaTrader5 as mt5
    import pandas as pd
    if not mt5.initialize():
        raise RuntimeError("MT5 indisponibil")
    from daily_engine.config import ENTRY_MODES, hm_to_min, load_config
    from daily_engine.engine import bars_today
    from daily_engine.market_tools import market_sessions
    from daily_engine.strategy import evaluate_day_multi
    m = [s for s in market_sessions(next(x for x in load_config()["markets"] if x["symbol"] == "US500"))][0]
    r = mt5.copy_rates_range("US500", mt5.TIMEFRAME_M5, datetime(2026, 11, 18), datetime(2026, 11, 19, 3))
    if r is None or not len(r):
        raise RuntimeError("fara bare")
    pt = mt5.symbol_info("US500").point
    at = datetime(2026, 11, 18, 22, 56, tzinfo=timezone.utc)                    # 00:56 RO

    def run(off):
        b = bars_today(r, off, m, at)
        st = evaluate_day_multi(b.open, b.high, b.low, b.close, b.spread * pt, b.mins, open_min=hm_to_min(m["open"]),
                                or_minutes=m["or_minutes"], mode=ENTRY_MODES[m["entry"]], rr=m.get("rr"), slip=m["slip"],
                                comm=m["comm"], day_complete=True, reentry=m.get("reentry"), plock=m.get("profit_lock"))
        return [(t.get("k"), round(t["R"], 2), round(st.get("or_hi") or 0, 1)) for t in st["trades"]]
    good, bad = run(2 * H), run(H)
    print("     offset corect 2h :", good)
    print("     offset gresit 1h :", bad)
    check("offset corect = trade-ul real (LONG −1,01R)", len(good) >= 1 and good[0][1] == -1.01)
    check("offset gresit = alta zi (de aici fantoma)", bad != good)
except Exception as e:  # noqa: BLE001
    print(f"     sarit: {e}")

print(f"\n{OK} OK, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
