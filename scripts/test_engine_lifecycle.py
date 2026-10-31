"""
Test: Engine Lifecycle comun (api/engine_lifecycle.py) + supravegherea Daily Engine din watchdog-ul
API (api/watchdog.py::_check_daily_engine). Offline: fara procese reale, fara Telegram.
    python scripts/test_engine_lifecycle.py
"""
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException  # noqa: E402

from api import engine_lifecycle as L  # noqa: E402
from api import watchdog as W  # noqa: E402
from api.routers import daily_engine as DE  # noqa: E402

PASS = FAIL = 0


def check(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {detail}")


# ── engine simulat ────────────────────────────────────────────────────────────
state = {"running": False, "starts": 0, "stops": 0, "start_works": True}
L._status = lambda eid: {"running": state["running"], "pid": 123 if state["running"] else None,
                         "detail": "x", "mode": None}


def _start(eid):
    state["starts"] += 1
    state["running"] = state["start_works"]


def _stop(eid):
    state["stops"] += 1
    state["running"] = False


L._do_start, L._do_stop = _start, _stop
L.time.sleep = lambda s: None          # fara asteptari reale in bucla de verificare

print("1. Start / stop verificat")
r = L.engine_start("daily")
check(r["ok"] and r["running"] and state["starts"] == 1, "start -> procesul e viu, raspuns ok", r)
try:
    L.engine_start("daily")
    check(False, "al doilea start respins")
except HTTPException as e:
    check(e.status_code == 409 and state["starts"] == 1, "al doilea start -> 409, nu porneste o a doua instanta")
r = L.engine_stop("daily")
check(r["ok"] and not r["running"] and state["stops"] == 1, "stop -> procesul nu mai e viu")
try:
    L.engine_stop("daily")
    check(False, "stop pe engine oprit respins")
except HTTPException as e:
    check(e.status_code == 409, "stop pe engine oprit -> 409")

print("2. Pornire esuata = eroare vizibila (nu 'Running' fals)")
state["start_works"] = False
L._wait_for = lambda eid, running, t: L._status(eid)      # fara 12s de asteptare in test
L._log_tail = lambda eid, n=8: ["EROARE MT5 initialize esuat"]
try:
    L.engine_start("ai")
    check(False, "start esuat trebuie sa ridice eroare")
except HTTPException as e:
    check(e.status_code == 500 and "nu a pornit" in e.detail["message"], "500 cu mesaj clar", e.detail)
    check(e.detail["log_tail"] == ["EROARE MT5 initialize esuat"], "include ultimele linii din jurnal")
try:
    L.engine_start("necunoscut")
    check(False, "engine necunoscut")
except HTTPException as e:
    check(e.status_code == 404, "engine necunoscut -> 404")

print("3. Watchdog: Daily mort fara Stop -> repornire, max 3/ora")
tmp = tempfile.mkdtemp()
DE.DESIRED_FILE = os.path.join(tmp, "desired_running.json")
sent, restarts = [], []
W.tg.send_message = lambda text: sent.append(text)
DE._read_pid = lambda: 999
W._pid_alive = lambda pid: False
DE.daily_start = lambda: restarts.append(1)
W._daily_restarts.clear()
W._check_daily_engine()
check(not restarts and not sent, "fara stare dorita (oprit din UI) -> nu reporneste")
open(DE.DESIRED_FILE, "w").write("{}")
W._check_daily_engine()
check(len(restarts) == 1 and "repornit automat" in sent[-1], "stare dorita + proces mort -> repornit + Telegram", sent)
W._pid_alive = lambda pid: True
W._check_daily_engine()
check(len(restarts) == 1, "proces viu -> nimic")
W._pid_alive = lambda pid: False
W._check_daily_engine()
W._check_daily_engine()
check(len(restarts) == 3, "a 2-a si a 3-a repornire in aceeasi ora")
W._check_daily_engine()
check(len(restarts) == 3 and "nu rămâne pornit" in sent[-1], "a 4-a cadere in 1h -> alerta, fara repornire", sent[-1])
check(not os.path.exists(DE.DESIRED_FILE), "starea dorita stearsa -> nu bucleaza")

print(f"\nREZULTAT: {PASS} PASS / {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
