"""Teste offline: ai_engine.triggers + disabled_triggers (config).  python scripts/test_ai_triggers.py"""
import os, sys, itertools
try:
    sys.stdout.reconfigure(encoding="utf-8")   # consola Windows cp1252 nu afiseaza → / diacritice
except Exception:
    pass
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_engine import triggers
from ai_engine.config import DEFAULTS

PASS = FAIL = 0
def check(n, c, d=""):
    global PASS, FAIL
    PASS, FAIL = (PASS + 1, FAIL) if c else (PASS, FAIL + 1)
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else f"  {d}"))

cfg = dict(DEFAULTS)
def snap(**k):
    s = {"news": [], "trend_m30": 1, "trend_d1": 1, "atr": 1.0, "high_20": 110, "low_20": 90,
         "price": 100, "atr_pctile": 50}
    s.update(k); return s
old = (datetime.now() - timedelta(hours=30)).isoformat()
cases = [
    (snap(), None, None, False),
    (snap(trend_m30=-1), snap(), old, False),
    (snap(price=109.8), snap(), old, False),
    (snap(atr_pctile=95), snap(), old, False),
    (snap(news=[{"impact": "High", "in_min": 30, "currency": "USD", "title": "NFP"}]), snap(), old, False),
    (snap(), snap(), old, True),
    (snap(trend_m30=-1, price=109.8), snap(), old, False),
]
names = [triggers.evaluate(*c, cfg) for c in cases]
check("default: fiecare caz produce trigger-ul asteptat",
      [n.split(":")[0] if n else None for n in names] ==
      ["heartbeat", "regime_flip", "breakout_tension", "vol_spike", "news_window", "position_review", "regime_flip"], names)
off = dict(cfg, disabled_triggers=["breakout_tension", "heartbeat", "vol_spike"])
check("breakout dezactivat → None (heartbeat dezactivat si el)", triggers.evaluate(*cases[2], off) is None)
check("regime_flip ramane activ", triggers.evaluate(*cases[1], off).startswith("regime_flip"))
check("regime+breakout simultan → regime_flip", triggers.evaluate(*cases[6], off).startswith("regime_flip"))
check("news_window ramane activ", triggers.evaluate(*cases[4], off).startswith("news_window"))
only_hb = dict(cfg, disabled_triggers=["breakout_tension"])
check("breakout dezactivat → cade pe heartbeat (urmatorul)", triggers.evaluate(snap(price=109.8), None, None, False, only_hb) == "heartbeat")
from ai_engine import config as C
import json, tempfile
p = os.path.join(tempfile.mkdtemp(), "c.json"); json.dump({"disabled_triggers": ["breakout_tension", "xxx"]}, open(p, "w"))
orig = C.CFG_PATH; C.CFG_PATH = p
try:
    check("config: valori necunoscute eliminate", C.load_config()["disabled_triggers"] == ["breakout_tension"])
    json.dump({"disabled_triggers": "corupt"}, open(p, "w"))
    check("config: corupt → []", C.load_config()["disabled_triggers"] == [])
finally:
    C.CFG_PATH = orig
print(f"\nREZULTAT: {PASS} PASS / {FAIL} FAIL"); sys.exit(1 if FAIL else 0)
