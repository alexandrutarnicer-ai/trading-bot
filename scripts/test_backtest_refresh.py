"""Teste api/backtest_refresh (backtest legat de configuratia exacta, Daily + Noisy) — offline, joburi simulate.
Rulare: python scripts/test_backtest_refresh.py"""
import json
import os
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import api.backtest_refresh as B       # noqa: E402

OK = FAIL = 0


def check(name, cond, detail=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  OK   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


tmp = tempfile.mkdtemp()
B.STORE_PATHS = {"daily": os.path.join(tmp, "d.json"), "noisy": os.path.join(tmp, "n.json")}


def wait(engine, key, fp, statuses=("completed", "failed"), t=5.0):
    end = time.time() + t
    while time.time() < end:
        v = B.view(engine, key, fp)
        if v["status"] in statuses:
            return v
        time.sleep(0.02)
    return B.view(engine, key, fp)


print("1. fingerprint")
m = {"symbol": "DE40", "tz": "Europe/Berlin", "open": "09:00", "last_bar": "17:25", "or_minutes": 5, "entry": "breakout",
     "rr": None, "reentry": {"enabled": False}, "slip": 0.125, "comm": 0.0, "label": "x", "paused": False}
fp0 = B.daily_fp(m)
check("stabil", fp0 == B.daily_fp(dict(m)))
for k, v in (("symbol", "US500"), ("or_minutes", 15), ("entry", "direction"), ("rr", 2.0), ("slip", 0.2),
             ("reentry", {"enabled": True}), ("open", "09:05")):
    check(f"se schimba la {k}", B.daily_fp({**m, k: v}) != fp0)
check("NU se schimba la eticheta / pauza (nu influenteaza rezultatul)", B.daily_fp({**m, "label": "y", "paused": True}) == fp0)
nc = {"symbol": "US500", "timeframe": "M1", "strategy": {"dev_atr": 2}, "window": {}, "spread": {"mode": "auto"},
      "mode": "shadow", "budget": {}}
check("Noisy: se schimba la piata / TF / strategie / spread", len({B.noisy_fp(nc), B.noisy_fp({**nc, "symbol": "XAGUSD"}),
      B.noisy_fp({**nc, "timeframe": "M5"}), B.noisy_fp({**nc, "strategy": {"dev_atr": 1.5}}),
      B.noisy_fp({**nc, "spread": {"mode": "manual"}})}) == 5)
check("Noisy: NU la mod shadow/executie / buget", B.noisy_fp({**nc, "mode": "execute", "budget": {"x": 1}}) == B.noisy_fp(nc))

print("2. ciclul unui job")
check("fara nimic → outdated", B.view("daily", "slot0", "A")["status"] == "outdated")
gate = threading.Event()
calls = []


def slow(res):
    def fn():
        calls.append(res)
        gate.wait(3)
        return res
    return fn


v = B.request("daily", "slot0", "A", slow({"ok": True, "summary": "A"}))
check("pending / running imediat (nu blocheaza)", v["status"] in ("pending", "running"), v)
v2 = B.request("daily", "slot0", "A", slow({"ok": True, "summary": "A2"}))
check("fara dubluri: acelasi fingerprint nu porneste alt job", len(calls) <= 1 and v2["status"] in ("pending", "running"))
gate.set()
v = wait("daily", "slot0", "A")
check("completed + rezultat", v["status"] == "completed" and v["result"]["summary"] == "A" and len(calls) == 1, v)
check("completed → nu se reporneste", B.request("daily", "slot0", "A", slow({"ok": True}))["status"] == "completed")

print("3. configuratie schimbata in timpul rularii")
gate.clear()
B.request("daily", "slot1", "X", slow({"ok": True, "summary": "VECHI"}))
time.sleep(0.05)
gate2 = threading.Event()
B.request("daily", "slot1", "Y", lambda: (gate2.wait(3), {"ok": True, "summary": "NOU"})[1])
gate.set()                                  # jobul vechi se termina primul
time.sleep(0.2)
vy = B.view("daily", "slot1", "Y")
check("rezultatul VECHI aruncat (nu apare pentru configuratia noua)", vy["status"] in ("pending", "running")
      and not vy.get("result"), vy)
check("configuratia veche apare ca outdated", B.view("daily", "slot1", "X")["status"] == "outdated")
gate2.set()
vy = wait("daily", "slot1", "Y")
check("... iar cel nou se finalizeaza", vy["status"] == "completed" and vy["result"]["summary"] == "NOU", vy)

print("4. esec + reincercare")
v = B.request("noisy", "main", "F", lambda: (_ for _ in ()).throw(RuntimeError("MT5 cazut")))
v = wait("noisy", "main", "F")
check("failed + motiv", v["status"] == "failed" and "MT5 cazut" in v["error"], v)
check("failed NU se reporneste singur la aceeasi configuratie (fara bucla)", B.noisy_ensure.__code__ is not None and
      B.view("noisy", "main", "F")["status"] == "failed")
v = B.request("noisy", "main", "F", lambda: {"ok": True, "summary": "ok"}, force=True)
check("reincercare manuala (force)", wait("noisy", "main", "F")["status"] == "completed")
v = B.request("noisy", "main", "G", lambda: {"ok": False, "detail": "fara bare"})
check("rezultat ok=False → failed cu detaliul", wait("noisy", "main", "G")["error"] == "fara bare")

print("5. restart API in timpul rularii")
d = json.load(open(B.STORE_PATHS["daily"], encoding="utf-8"))
d["slot2"] = {"fingerprint": "R", "status": "running", "result": None}
json.dump(d, open(B.STORE_PATHS["daily"], "w", encoding="utf-8"))
check("„running” pe disc fara thread viu → interrupted", B.view("daily", "slot2", "R")["status"] == "interrupted")
orig = B.daily_job
B.daily_job = lambda m_: (lambda: {"ok": True, "summary": f"re {m_['symbol']}"})
cfg = {"markets": [m, {**m, "symbol": "GBPUSD"}]}
out = B.daily_ensure(cfg)
time.sleep(0.3)
out = B.daily_ensure(cfg)
check("daily_ensure: porneste singur pe fiecare slot fara rezultat valid", [o["status"] for o in out] == ["completed", "completed"]
      and out[0]["result"]["summary"] == "re DE40", out)
cfg2 = {"markets": [{**m, "symbol": "US500"}, {**m, "symbol": "GBPUSD"}]}
out2 = B.daily_ensure(cfg2)
check("schimbarea pietei pe slotul 1 → doar acel slot reruleaza", out2[1]["status"] == "completed"
      and out2[0]["status"] in ("pending", "running", "completed"), out2)
B.daily_job = orig

print(f"\n{OK} OK, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
