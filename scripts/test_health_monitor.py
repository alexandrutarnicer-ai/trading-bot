"""Teste: monitorizarea centrala (api/health_monitor.py) — offline, fara MT5 / Ollama / Telegram reale, incidente izolate.

    python scripts/test_health_monitor.py
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import tempfile
from datetime import datetime, timedelta
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import incidents  # noqa: E402

SENT: list[str] = []
incidents.isolate_for_tests(SENT)
from api import health_monitor as H  # noqa: E402

TMP = tempfile.mkdtemp(prefix="health_test_")
H.HEARTBEAT_FILE = os.path.join(TMP, "app_heartbeat.json")
OK = FAIL = 0


def check(name, cond, info=None):
    global OK, FAIL
    OK += bool(cond)
    FAIL += not cond
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + ("" if cond or info is None else f"  → {info}"))


def age(key, sec):
    s = incidents._load()
    if key in s["active"]:
        s["active"][key]["first_seen"] -= sec
        incidents._save(s)


def eng(**over):
    base = {k: {"expected": False, "running": False, "heartbeat_age": None, "stale_after": 300} for k in ("custom", "ai", "daily")}
    for k, v in over.items():
        base[k].update(v)
    return base


print("1. Pornire: oprire NECURATA / restart Windows / pornire normala")
json.dump({"ts": (datetime.now() - timedelta(minutes=42)).isoformat(timespec="seconds"), "clean_shutdown": False},
          open(H.HEARTBEAT_FILE, "w"))
H.boot_time = lambda: datetime.now() - timedelta(minutes=10)
H.engines_expected = lambda: eng(daily={"expected": True})
ev = H.startup_checks()
check("heartbeat fara oprire curata → eveniment „oprire NECURATA” cu durata + restart Windows",
      ev and ev["rebooted"] and any("oprire NECURATĂ" in s and "Windows a repornit" in s for s in SENT), SENT[-1:])
check("... mentioneaza engine-urile care ar trebui sa ruleze", "Daily Engine" in SENT[-1])
SENT.clear()
H.mark_clean_shutdown()
H.boot_time = lambda: datetime.now() - timedelta(days=3)
check("oprire curata, fara reboot → niciun mesaj", H.startup_checks() is None and SENT == [])
H.mark_clean_shutdown()
json.dump({"ts": (datetime.now() - timedelta(minutes=30)).isoformat(timespec="seconds"), "clean_shutdown": True},
          open(H.HEARTBEAT_FILE, "w"))
H.boot_time = lambda: datetime.now() - timedelta(minutes=5)
H.startup_checks()
check("oprire curata + Windows repornit intre timp → „Windows a repornit”", any("Windows a repornit" in s for s in SENT))

print("2. Sleep / Hibernate (ceasul sare)")
SENT.clear()
H.engines_expected = lambda: eng(ai={"expected": True})
check("gap normal (30 s) → nimic", H.sleep_check(31) is False and SENT == [])
check("gap 47 min → eveniment Sleep cu engine-urile afectate", H.sleep_check(47 * 60) and "suspendat ~47 min" in SENT[-1]
      and "AI Engine" in SENT[-1])

print("3. Internet: confirmare 90 s, recuperare")
SENT.clear()
real_conn, real_gai = socket.create_connection, socket.getaddrinfo
socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(OSError("down"))
socket.getaddrinfo = lambda *a, **k: (_ for _ in ()).throw(OSError("dns"))
H.check_internet()
check("internet cazut, prima verificare → fara mesaj (confirmare)", SENT == [] and incidents.is_active("internet"))
age("internet", 120)
c = H.check_internet()
check("dupa 90 s → incident notificat, stare unavailable", c["status"] == "unavailable" and "Internet indisponibil" in SENT[-1])


class _S:
    def __enter__(self): return self
    def __exit__(self, *a): pass


socket.create_connection = lambda *a, **k: _S()
socket.getaddrinfo = real_gai
H.check_internet()
check("internet revenit → mesaj de recuperare cu durata", "Rezolvat: Internet indisponibil" in SENT[-1])
socket.create_connection = real_conn

print("4. Engine-uri: oprit neasteptat / blocat / oprit normal")
SENT.clear()
H.check_engines(eng(daily={"expected": True, "running": False}))
age("engine:daily", 100)
H.check_engines(eng(daily={"expected": True, "running": False}))
check("Daily dorit + proces mort → incident critic (dupa confirmare)", any("Daily Engine oprit neașteptat" in s for s in SENT))
H.check_engines(eng(daily={"expected": True, "running": True, "heartbeat_age": 30}))
check("Daily viu + heartbeat proaspat → recuperare", any("Rezolvat: Daily Engine oprit" in s for s in SENT))
SENT.clear()
H.check_engines(eng(ai={"expected": True, "running": True, "heartbeat_age": 3600, "stale_after": 2700}))
check("AI viu dar heartbeat vechi de 60 min → „pare blocat”", any("AI Engine pare blocat" in s for s in SENT))
SENT.clear()
H.check_engines(eng())
check("engine-uri oprite din UI (nedorite) → niciun incident nou", SENT == [] or all("Rezolvat" in s for s in SENT))

print("5. Ollama (doar cu AI Engine pornit) — pornire automata limitata")
SENT.clear()
starts = []
H.start_ollama = lambda: (starts.append(1) or True)
H.ollama_reachable = lambda *a, **k: (False, "ConnectionRefusedError")
H._read_json = lambda p: {}
H.check_ai_sources(eng(ai={"expected": False, "running": False}))
check("AI oprit → Ollama doar informativ, fara incident / pornire", starts == [] and not incidents.is_active("ollama"))
H.check_ai_sources(eng(ai={"expected": True, "running": True}))
check("AI pornit + Ollama mort → incerc pornirea automata", starts == [1] and incidents.is_active("ollama"))
age("ollama", 200)
H.check_ai_sources(eng(ai={"expected": True, "running": True}))
check("... incident notificat dupa confirmare: AI nu deschide trade-uri noi, pozitiile raman pe SL / TP",
      any("Ollama indisponibil" in s and "SL / TP" in s for s in SENT))
H.ollama_reachable = lambda *a, **k: (True, "qwen3:8b")
H.check_ai_sources(eng(ai={"expected": True, "running": True}))
check("Ollama revenit → recuperare", any("Rezolvat: Ollama indisponibil" in s for s in SENT))
H._read_json = lambda p: {"providers": {"gemini": {"status": "paused", "reason": "quota"}}} if p.endswith("status.json") else {}
SENT.clear()
H.check_ai_sources(eng(ai={"expected": True, "running": True}))
age("gemini", 100)
H.check_ai_sources(eng(ai={"expected": True, "running": True}))
H.check_ai_sources(eng(ai={"expected": True, "running": True}))
check("Gemini cota epuizata → componenta „degradat” (mesajul il trimite registrul surselor, nu monitorul — fara dublura)",
      H._state["components"]["gemini"]["status"] == "degraded" and not any("Gemini" in s for s in SENT))

print("6. MT5 (pool simulat)")
SENT.clear()
from api import mt5_pool  # noqa: E402
state = {"ti": SimpleNamespace(connected=True, trade_allowed=True), "acc": SimpleNamespace(login=1, server="ICMarketsEU")}
mt5_pool._ensure_mt5 = lambda: SimpleNamespace(terminal_info=lambda: state["ti"], account_info=lambda: state["acc"],
                                               positions_get=lambda: ())
check("MT5 conectat → healthy", H.check_mt5(eng())["status"] == "healthy")
state["ti"] = SimpleNamespace(connected=False, trade_allowed=True)
H.check_mt5(eng(daily={"running": True}))
check("deconectat de broker, sub prag (5 min) → fara mesaj", SENT == [])
age("mt5:disconnected", 400)
H.check_mt5(eng(daily={"running": True}))
check("peste 5 min → incident critic (engine-uri pornite)", any("deconectat de la serverul brokerului" in s for s in SENT))
state["ti"] = SimpleNamespace(connected=True, trade_allowed=True)
H.check_mt5(eng(daily={"running": True}))
check("reconectat → recuperare cu contul verificat", any("Rezolvat" in s and "cont #1" in s for s in SENT))

print("7. Alimentare (doar citire powercfg)")
SENT.clear()
H._powercfg = lambda sub, s: {"STANDBYIDLE": 1800, "HIBERNATEIDLE": 0, "LIDACTION": 1}[s]
H._last_power_check["t"] = 0
c = H.check_power(eng(daily={"running": True}))
check("Sleep 30 min + capac = Sleep, cu engine pornit → avertisment (o data / zi)",
      c["status"] == "degraded" and any("Sleep automat după 30 min" in s for s in SENT))
H._last_power_check["t"] = 0
H.check_power(eng(daily={"running": True}))
check("... fara mesaj repetat in aceeasi zi", len([s for s in SENT if "suspenda engine-urile" in s]) == 1)
H._last_power_check["t"] = 0
check("fara engine pornit → doar informativ", H.check_power(eng())["status"] == "healthy")

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{OK} OK, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
