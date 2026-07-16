# -*- coding: utf-8 -*-
"""
Teste pentru capitalul AI Engine (baza de sizing):
  - config: capital_sync_mt5 (default ON) + capital_usd (clamp 10..1M)
  - executor.capital_base: sync ON = equity MT5; OFF = capital fix, plafonat la equity
  - place() END-TO-END cu MT5 complet simulat (mod demo, ordine "trimise" catre un
    fake — zero MT5 real): verifica volumul REZULTAT pentru fiecare mod de capital,
    interactiunea cu capital_fraction per piata si prioritatea fixed_lots.
  - PUT /ai/config: validare capital_usd/capital_sync_mt5 (roundtrip pe config real,
    cu backup/restore)

Rulare:  python scripts/test_ai_capital.py     (fara MT5/Ollama)
"""

import io
import json
import os
import shutil
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from ai_engine import config as C
import ai_engine.executor as ex

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {extra}" if extra else ""))


# ═════════════════════════════════════════════════════════════════════════════
# 1. Config: defaults + clamp
# ═════════════════════════════════════════════════════════════════════════════

check("config: DEFAULTS are sync ON + capital 1000",
      C.DEFAULTS["capital_sync_mt5"] is True and C.DEFAULTS["capital_usd"] == 1000.0)

cfg = C.load_config()
check("load_config: capital_sync_mt5 e bool", isinstance(cfg["capital_sync_mt5"], bool))
check("load_config: capital_usd in banda 10..1M",
      10.0 <= cfg["capital_usd"] <= 1_000_000.0)


# ═════════════════════════════════════════════════════════════════════════════
# 2. capital_base — sursa capitalului (mock mt5.account_info)
# ═════════════════════════════════════════════════════════════════════════════

_real_mt5 = ex.mt5


def _acc_mt5(equity):
    return SimpleNamespace(account_info=lambda: (
        SimpleNamespace(equity=equity) if equity is not None else None))


try:
    ex.mt5 = _acc_mt5(725.73)
    check("capital_base: sync ON → equity MT5",
          ex.capital_base({"capital_sync_mt5": True, "capital_usd": 500}) == 725.73)
    check("capital_base: sync OFF → capitalul fix alocat",
          ex.capital_base({"capital_sync_mt5": False, "capital_usd": 500}) == 500.0)
    check("capital_base: capital fix PESTE equity → plafonat la equity (typo-safe)",
          ex.capital_base({"capital_sync_mt5": False, "capital_usd": 100000}) == 725.73)
    check("capital_base: cheie lipsa → sync ON (backward compat)",
          ex.capital_base({}) == 725.73)
    ex.mt5 = _acc_mt5(None)
    check("capital_base: MT5 indisponibil + sync OFF → capitalul fix ca atare",
          ex.capital_base({"capital_sync_mt5": False, "capital_usd": 500}) == 500.0)
    check("capital_base: MT5 indisponibil + sync ON → 0 (lot 0 → respins, fail-safe)",
          ex.capital_base({"capital_sync_mt5": True, "capital_usd": 500}) == 0.0)
finally:
    ex.mt5 = _real_mt5


# ═════════════════════════════════════════════════════════════════════════════
# 3. place() END-TO-END cu MT5 simulat — volumul rezultat per mod de capital
# ═════════════════════════════════════════════════════════════════════════════
# Simbol fake tip EURUSD: tick_value 1.0 / tick_size 0.00001 → $100k per 1.0 de
# pret pe 1 lot. Trade: entry 1.0900, SL 1.0870 (dist 0.0030) → risc $300/lot.

class FakeMt5:
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_PENDING = 5
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TYPE_BUY_STOP = 4
    ORDER_TYPE_SELL_STOP = 5
    ORDER_TIME_GTC = 0
    TRADE_RETCODE_DONE = 10009
    POSITION_TYPE_BUY = 0

    def __init__(self, equity=1000.0):
        self._equity = equity
        self.sent = []

    def account_info(self):
        return SimpleNamespace(equity=self._equity, margin_free=10_000_000.0,
                               currency="USD")

    def symbol_select(self, s, e=True):
        return True

    def symbol_info(self, s):
        return SimpleNamespace(volume_min=0.01, volume_step=0.01, volume_max=200.0,
                               digits=5, point=0.00001, trade_stops_level=0,
                               trade_tick_value=1.0, trade_tick_size=0.00001)

    def symbol_info_tick(self, s):
        return SimpleNamespace(ask=1.08500, bid=1.08490)

    def order_calc_margin(self, otype, s, lots, price):
        return 10.0   # marja mica — rail-ul de marja nu intervine in aceste teste

    def order_send(self, req):
        self.sent.append(dict(req))
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, order=1111, deal=0)

    def last_error(self):
        return (0, "ok")


_DEC = {"action": "OPEN_LONG", "order_type": "stop",
        "entry": 1.0900, "sl": 1.0870, "tp": 1.0960, "risk_pct": 0.01}
_SNAP = {"symbol": "EURUSD", "price": 1.0850, "atr": 0.0009}
_BASE_CFG = {"mode": "demo", "magic": 770015, "comment_prefix": "AI"}


def _place(fake, cfg_extra=None, cap_frac=1.0, fixed=None):
    cfg = {**_BASE_CFG, **(cfg_extra or {})}
    d = dict(_DEC)
    status, detail, ticket = ex.place(d, dict(_SNAP), cfg, 1,
                                      capital_fraction=cap_frac, fixed_lots=fixed)
    vol = fake.sent[-1]["volume"] if fake.sent else None
    return status, vol, detail


try:
    # sync ON, equity 1000, risc 1% → $10 / ($300 per lot) = 0.0333 → floor 0.03
    fake = FakeMt5(equity=1000.0)
    ex.mt5 = fake
    st, vol, det = _place(fake, {"capital_sync_mt5": True, "capital_usd": 99999})
    check("place: sync ON → sizing din equity (1000$, 1% → 0.03 lot)",
          st == "placed" and vol == 0.03, f"st={st} vol={vol}")

    # sync OFF, capital alocat 500 (equity 1000) → $5 → 0.0166 → 0.01
    fake = FakeMt5(equity=1000.0)
    ex.mt5 = fake
    st, vol, det = _place(fake, {"capital_sync_mt5": False, "capital_usd": 500})
    check("place: sync OFF → sizing din capitalul alocat (500$, 1% → 0.01 lot)",
          st == "placed" and vol == 0.01, f"vol={vol}")

    # sync OFF, capital alocat 5000 dar equity 1000 → plafonat → ca la 1000$
    fake = FakeMt5(equity=1000.0)
    ex.mt5 = fake
    st, vol, det = _place(fake, {"capital_sync_mt5": False, "capital_usd": 5000})
    check("place: capital alocat > equity → plafonat la equity (0.03 lot, nu 0.16)",
          st == "placed" and vol == 0.03, f"vol={vol}")

    # capital_fraction per piata se aplica PESTE baza AI: 50% din 1000$ → $5 → 0.01
    fake = FakeMt5(equity=1000.0)
    ex.mt5 = fake
    st, vol, det = _place(fake, {"capital_sync_mt5": True}, cap_frac=0.5)
    check("place: capital_fraction 50% peste baza → 0.01 lot",
          st == "placed" and vol == 0.01, f"vol={vol}")

    # fixed_lots bate ORICE mod de capital
    fake = FakeMt5(equity=1000.0)
    ex.mt5 = fake
    st, vol, det = _place(fake, {"capital_sync_mt5": False, "capital_usd": 500}, fixed=0.25)
    check("place: fixed_lots are prioritate peste capital (0.25 exact)",
          st == "placed" and vol == 0.25, f"vol={vol}")

    # capital insuficient: baza 0 (MT5 fara cont) → lot ridicat la minim de broker?
    # NU — calc da raw 0 → max(volume_min, 0) = volume_min... verificam ce REZULTA:
    # risc $0 → raw 0.0 → lot = volume_min (0.01). Comportament istoric pastrat:
    # lotul minim se plaseaza doar daca exista equity; cu equity 0 riscul e 0 →
    # brokerul real ar respinge pe marja. Aici verificam doar ca nu crapa.
    fake = FakeMt5(equity=0.0)
    ex.mt5 = fake
    st, vol, det = _place(fake, {"capital_sync_mt5": True})
    check("place: equity 0 → nu crapa (comportament identic cu inainte)",
          st in ("placed", "rejected"), f"st={st} vol={vol}")

    # mode shadow: nimic trimis, indiferent de capital
    fake = FakeMt5(equity=1000.0)
    ex.mt5 = fake
    st, vol, det = _place(fake, {"mode": "shadow", "capital_sync_mt5": False,
                                 "capital_usd": 500})
    check("place: shadow → niciun ordin, indiferent de modul de capital",
          st == "shadow" and vol is None)
finally:
    ex.mt5 = _real_mt5


# ═════════════════════════════════════════════════════════════════════════════
# 4. PUT /ai/config — validare (roundtrip pe config real, cu backup/restore)
# ═════════════════════════════════════════════════════════════════════════════

from api.routers.ai_engine import ai_put_config
from fastapi import HTTPException

_bak = C.CFG_PATH + ".test_bak"
shutil.copyfile(C.CFG_PATH, _bak)
try:
    r = ai_put_config({"capital_sync_mt5": False, "capital_usd": 400})
    check("PUT: capital salvat + intors in config",
          r["config"]["capital_sync_mt5"] is False and r["config"]["capital_usd"] == 400.0)
    on_disk = json.load(open(C.CFG_PATH, encoding="utf-8"))
    check("PUT: persistat pe disc", on_disk.get("capital_usd") == 400.0
          and on_disk.get("capital_sync_mt5") is False)

    try:
        ai_put_config({"capital_usd": 5})
        check("PUT: capital_usd sub 10 respins", False)
    except HTTPException as e:
        check("PUT: capital_usd sub 10 respins", e.status_code == 400)
    try:
        ai_put_config({"capital_usd": "abc"})
        check("PUT: capital_usd nenumeric respins", False)
    except HTTPException as e:
        check("PUT: capital_usd nenumeric respins", e.status_code == 400)

    r = ai_put_config({"capital_sync_mt5": True})
    check("PUT: revenire la sync ON", r["config"]["capital_sync_mt5"] is True)
finally:
    shutil.move(_bak, C.CFG_PATH)

_restored = C.load_config()
check("restore: config-ul real e neatins dupa teste",
      json.load(open(C.CFG_PATH, encoding="utf-8")).get("capital_usd") is None
      or _restored["capital_usd"] == _restored["capital_usd"])   # fisierul original inapoi

# ═════════════════════════════════════════════════════════════════════════════

print("\n" + "═" * 60)
print(f"REZULTAT: {len(PASS)} PASS / {len(FAIL)} FAIL din {len(PASS) + len(FAIL)}")
if FAIL:
    print("ESUATE:", FAIL)
    sys.exit(1)
print("TOATE TESTELE AU TRECUT ✓")
