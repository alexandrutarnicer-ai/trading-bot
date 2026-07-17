# -*- coding: utf-8 -*-
"""
Teste pentru deblocarea Trading LIVE (live_guard + guard-urile din
adapters/mt5_source.py si ai_engine/executor.py).

Contract de siguranta verificat:
  - DEFAULT (fara fisier / corupt / componenta absenta) = BLOCAT pe cont real
  - cont DEMO functioneaza mereu, indiferent de flag-uri
  - deblocarea e per componenta: bot ON nu deblocheaza ai_engine si invers
  - component=None (scripturi research) = strict DEMO chiar cu ambele flag-uri ON
  - endpoint-ul API valideaza componenta si persista flag-urile

Rulare:  python scripts/test_live_guard.py     (fara MT5 real — totul simulat)
"""

import io
import json
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import live_guard

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {extra}" if extra else ""))


# Izolare: mutam LIVE_FILE intr-un temp dir ca sa nu atingem data/ real.
_td = tempfile.mkdtemp()
live_guard.LIVE_FILE = os.path.join(_td, "live_trading.json")

# ═════════════════════════════════════════════════════════════════════════════
# 1. live_guard — fail-safe defaults + persistare
# ═════════════════════════════════════════════════════════════════════════════

check("default: fara fisier → totul blocat",
      live_guard.live_flags() == {"bot": False, "ai_engine": False}
      and not live_guard.live_allowed("bot") and not live_guard.live_allowed("ai_engine"))

with open(live_guard.LIVE_FILE, "w") as f:
    f.write("{corupt")
check("fisier corupt → totul blocat (fail-safe)",
      live_guard.live_flags() == {"bot": False, "ai_engine": False})

flags = live_guard.set_live("bot", True)
check("set_live bot=True → doar bot deblocat",
      flags == {"bot": True, "ai_engine": False}
      and live_guard.live_allowed("bot") and not live_guard.live_allowed("ai_engine"))

flags = live_guard.set_live("ai_engine", True)
check("set_live ai_engine=True → ambele deblocate", flags == {"bot": True, "ai_engine": True})

flags = live_guard.set_live("bot", False)
check("set_live bot=False → revine blocat, ai_engine ramane",
      flags == {"bot": False, "ai_engine": True})

try:
    live_guard.set_live("hacker", True)
    check("componenta necunoscuta → ValueError", False)
except ValueError:
    check("componenta necunoscuta → ValueError", True)

check("componenta necunoscuta in live_allowed → False",
      live_guard.live_allowed("altceva") is False)

# ═════════════════════════════════════════════════════════════════════════════
# 2. Mt5DataSource.connect — guard-ul pe cont real (mt5 simulat)
# ═════════════════════════════════════════════════════════════════════════════

import adapters.mt5_source as ms

DEMO_MODE = 0
REAL_MODE = 2


class _FakeMt5:
    ACCOUNT_TRADE_MODE_DEMO = DEMO_MODE

    def __init__(self, trade_mode):
        self._mode = trade_mode
        self.shutdowns = 0

    def initialize(self):
        return True

    def account_info(self):
        return SimpleNamespace(trade_mode=self._mode, login=123456,
                               server="ICMarketsEU-Live", equity=1000.0)

    def shutdown(self):
        self.shutdowns += 1

    def last_error(self):
        return (0, "ok")


_real_ms_mt5 = ms.mt5


def _try_connect(trade_mode, component):
    ms.mt5 = _FakeMt5(trade_mode)
    src = ms.Mt5DataSource(n_bars=100, component=component)
    try:
        src.connect()
        return "OK"
    except RuntimeError as e:
        return "BLOCAT" if "BLOCAT" in str(e) else f"alta eroare: {e}"


try:
    live_guard.set_live("bot", False)
    live_guard.set_live("ai_engine", False)
    live_guard._notified.clear()

    check("DEMO + fara flag-uri → conectat (comportament istoric)",
          _try_connect(DEMO_MODE, "bot") == "OK")
    check("REAL + bot blocat → REFUZAT", _try_connect(REAL_MODE, "bot") == "BLOCAT")
    check("REAL + component=None → REFUZAT (research demo-only)",
          _try_connect(REAL_MODE, None) == "BLOCAT")

    live_guard.set_live("bot", True)
    live_guard._notified.clear()
    check("REAL + bot DEBLOCAT → conectat", _try_connect(REAL_MODE, "bot") == "OK")
    check("REAL + bot deblocat dar componenta=ai_engine → REFUZAT (per componenta)",
          _try_connect(REAL_MODE, "ai_engine") == "BLOCAT")
    check("REAL + component=None chiar cu flag-uri ON → REFUZAT",
          _try_connect(REAL_MODE, None) == "BLOCAT")
    check("notificarea live s-a inregistrat o data", "bot" in live_guard._notified)

    # DEMO ramane OK si cu flag-urile pornite (flag-ul nu strica nimic)
    live_guard.set_live("ai_engine", True)
    check("DEMO + flag-uri ON → conectat normal", _try_connect(DEMO_MODE, "ai_engine") == "OK")
finally:
    ms.mt5 = _real_ms_mt5

# ═════════════════════════════════════════════════════════════════════════════
# 3. ai_engine.executor.connect — acelasi contract
# ═════════════════════════════════════════════════════════════════════════════

import ai_engine.executor as ex


class _FakeMt5Exec(_FakeMt5):
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_FOK = 2
    ORDER_FILLING_RETURN = 3


_real_ex_mt5 = ex.mt5


def _try_engine_connect(trade_mode):
    ex.mt5 = _FakeMt5Exec(trade_mode)
    try:
        ex.connect()
        return "OK"
    except RuntimeError as e:
        return "BLOCAT" if "BLOCAT" in str(e) else f"alta eroare: {e}"


try:
    live_guard.set_live("ai_engine", False)
    live_guard._notified.clear()
    check("executor: DEMO → conectat", _try_engine_connect(DEMO_MODE) == "OK")
    check("executor: REAL + ai_engine blocat → REFUZAT",
          _try_engine_connect(REAL_MODE) == "BLOCAT")

    live_guard.set_live("bot", True)   # flag-ul BOT nu deblocheaza motorul AI
    check("executor: REAL + doar bot deblocat → REFUZAT (per componenta)",
          _try_engine_connect(REAL_MODE) == "BLOCAT")

    live_guard.set_live("ai_engine", True)
    live_guard._notified.clear()
    check("executor: REAL + ai_engine DEBLOCAT → conectat",
          _try_engine_connect(REAL_MODE) == "OK")
    check("executor: notificarea live inregistrata", "ai_engine" in live_guard._notified)
finally:
    ex.mt5 = _real_ex_mt5

# ═════════════════════════════════════════════════════════════════════════════
# 4. API — validare + persistare (fara HTTP, functii direct)
# ═════════════════════════════════════════════════════════════════════════════

from api.routers.settings import set_live_trading, get_live_trading
from fastapi import HTTPException

live_guard.set_live("bot", False)
live_guard.set_live("ai_engine", False)

r = set_live_trading({"component": "bot", "allowed": True})
check("API: PUT bot=True → flags corecte", r["ok"] and r["flags"]["bot"] is True)
check("API: persistat pe disc",
      json.load(open(live_guard.LIVE_FILE))["bot"] is True)

r = set_live_trading({"component": "bot", "allowed": False})
check("API: PUT bot=False → revine blocat", r["flags"]["bot"] is False)

try:
    set_live_trading({"component": "sistem", "allowed": True})
    check("API: componenta invalida → 400", False)
except HTTPException as e:
    check("API: componenta invalida → 400", e.status_code == 400)

try:
    set_live_trading({"component": "bot"})
    check("API: fara 'allowed' → 400", False)
except HTTPException as e:
    check("API: fara 'allowed' → 400", e.status_code == 400)

g = get_live_trading()
check("API: GET intoarce flags + account", "flags" in g and "account" in g)

# ═════════════════════════════════════════════════════════════════════════════

print("\n" + "═" * 60)
print(f"REZULTAT: {len(PASS)} PASS / {len(FAIL)} FAIL din {len(PASS) + len(FAIL)}")
if FAIL:
    print("ESUATE:", FAIL)
    sys.exit(1)
print("TOATE TESTELE AU TRECUT ✓")
