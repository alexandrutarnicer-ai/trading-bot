"""Teste: incidente centrale (incidents.py) — confirmare, fara spam, reamintiri, recuperare cu durata, outbox persistent,
deduplicare intre procese. Offline (Telegram simulat, fisiere temporare).

    python scripts/test_incidents.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import incidents as I  # noqa: E402

TMP = tempfile.mkdtemp(prefix="incidents_test_")
I.STATE_FILE = os.path.join(TMP, "incidents.json")
I.LOCK_FILE = I.STATE_FILE + ".lock"
I.CONFIG_FILE = os.path.join(TMP, "cfg.json")
I._log_ui = lambda text: None
SENT: list[str] = []
UP = {"ok": True}
I._send_override = lambda text: (SENT.append(text) or True) if UP["ok"] else False
OK = FAIL = 0


def check(name, cond, info=None):
    global OK, FAIL
    OK += bool(cond)
    FAIL += not cond
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + ("" if cond or info is None else f"  → {info}"))


T0 = 1_000_000.0
print("1. Confirmare + fara spam")
I.report("mt5", "MT5 deconectat", "terminalul nu răspunde", "critical", confirm_s=120, now=T0)
check("blip (sub pragul de confirmare) → niciun mesaj", SENT == [])
I.report("mt5", "MT5 deconectat", "terminalul nu răspunde", "critical", confirm_s=120, now=T0 + 60)
check("tot sub prag → niciun mesaj", SENT == [])
I.report("mt5", "MT5 deconectat", "terminalul nu răspunde", "critical", confirm_s=120, now=T0 + 125)
check("confirmat dupa 2 min → PRIMA notificare", len(SENT) == 1 and "MT5 deconectat" in SENT[0])
for k in range(1, 60):                                          # verificari la 5 s timp de ~5 min
    I.report("mt5", "MT5 deconectat", "", "critical", confirm_s=120, now=T0 + 125 + 5 * k)
check("verificari repetate in urmatoarele 5 min → niciun mesaj nou", len(SENT) == 1)

print("2. Reamintiri rare (10, 30, apoi 60 min, max 6)")
I.report("mt5", "MT5 deconectat", "", "critical", confirm_s=120, now=T0 + 125 + 601)
check("dupa 10 min → reamintire 1 (cu durata)", len(SENT) == 2 and "Încă activ" in SENT[1])
I.report("mt5", "MT5 deconectat", "", "critical", confirm_s=120, now=T0 + 125 + 601 + 600)
check("10 min mai tarziu → nimic (urmatoarea la 30 min)", len(SENT) == 2)
I.report("mt5", "MT5 deconectat", "", "critical", confirm_s=120, now=T0 + 125 + 601 + 1801)
check("dupa 30 min → reamintire 2", len(SENT) == 3)
t = T0 + 125 + 601 + 1801
for k in range(20):
    t += 3601
    I.report("mt5", "MT5 deconectat", "", "critical", confirm_s=120, now=t)
check("plafon: maxim 6 reamintiri", len(SENT) == 1 + 6, len(SENT))

print("3. Recuperare")
SENT.clear()
sent = I.resolve("mt5", "pozițiile re-sincronizate", checks=["terminal", "cont #1"], now=t + 10)
check("recuperare → mesaj cu durata + verificari", sent and "Rezolvat" in SENT[0] and "Verificat: terminal" in SENT[0])
check("incidentul nu mai e activ + intra in istoric", not I.is_active("mt5") and I._load()["history"][-1]["key"] == "mt5")
SENT.clear()
I.report("internet", "Internet indisponibil", "", confirm_s=60, now=T0)
check("resolve pe un blip NENOTIFICAT → niciun mesaj de recuperare", I.resolve("internet", now=T0 + 20) is False and SENT == [])
check("resolve pe un incident inexistent → nimic", I.resolve("nimic") is False)

print("4. Telegram indisponibil → outbox persistent, retrimis o singura data, fara furtuna")
SENT.clear()
UP["ok"] = False
I.report("ollama", "Ollama indisponibil", "conexiune refuzată", "warning", now=T0)
s = I._load()
check("mesajul ramane in outbox (persistat pe disc)", len(s["outbox"]) == 1 and s["active"]["ollama"]["notified"])
UP["ok"] = True
s["outbox_next"] = 0
I._save(s)
n = I.flush_outbox()
check("conectivitatea revine → retrimis, marcat „intarziat”", n == 1 and "întârziat" in SENT[-1])
check("outbox gol dupa trimitere (fara dubluri)", I._load()["outbox"] == [] and I.flush_outbox() == 0)
UP["ok"] = False
for k in range(5):
    I.event(f"e{k}", f"eveniment {k}", dedup_min=0)
calls = {"n": 0}
I._send_override = lambda text: (calls.__setitem__("n", calls["n"] + 1) or False)
s = I._load()
s["outbox_next"] = 0
I._save(s)
I.flush_outbox()
check("flush cu Telegram picat: o SINGURA incercare (se opreste la primul esec)", calls["n"] == 1, calls)
I.flush_outbox()
check("... si nu reincearca mai des de o data / minut", calls["n"] == 1, calls)
I._send_override = lambda text: (SENT.append(text) or True) if UP["ok"] else False
UP["ok"] = True

print("5. Evenimente unice deduplicate + persistenta peste restart (alt proces = acelasi fisier)")
SENT.clear()
s = I._load(); s["outbox"] = []; I._save(s)
I.event("app_restart", "Aplicația a repornit", now=T0)
I.event("app_restart", "Aplicația a repornit", now=T0 + 60)
check("acelasi eveniment in fereastra de deduplicare → o singura data", len(SENT) == 1)
I.report("engine:daily", "Daily Engine oprit", "", "critical", now=T0)
import importlib  # noqa: E402
_paths = (I.STATE_FILE, I.LOCK_FILE, I.CONFIG_FILE)              # reload reseteaza caile la cele REALE → salvate inainte
J = importlib.reload(I)                                          # „restart”: modul nou, starea din fisier
J.STATE_FILE, J.LOCK_FILE, J.CONFIG_FILE = _paths
J._send_override = lambda text: (SENT.append(text) or True)
J._log_ui = lambda text: None
check("dupa restart incidentul activ e regasit (nu se retrimite prima notificare)",
      J.is_active("engine:daily") and len([x for x in SENT if "Daily Engine oprit" in x]) == 1)
J.report("engine:daily", "Daily Engine oprit", "", "critical", now=T0 + 5)
check("... raportat din nou dupa restart → fara mesaj dublu", len([x for x in SENT if "Daily Engine oprit" in x]) == 1)
check("fisier JSON valid", isinstance(json.load(open(J.STATE_FILE, encoding="utf-8")), dict))
open(J.STATE_FILE, "w").write("{corupt")
check("fisier corupt → stare goala, fara exceptie", J.active() == {})

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{OK} OK, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
