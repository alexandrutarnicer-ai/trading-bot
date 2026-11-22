"""Teste: pornirea automata conditionata (startup_gate.py) — offline: dependente + pornire simulate, incidente izolate.

    python scripts/test_startup_gate.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import incidents  # noqa: E402

SENT: list[str] = []
incidents.isolate_for_tests(SENT)
import startup_gate as G  # noqa: E402

TMP = tempfile.mkdtemp(prefix="gate_test_")
for e in G.ENGINES.values():
    e["log"] = os.path.join(TMP, "autostart.log")
G.CONFIG_FILE = os.path.join(TMP, "autostart_config.json")
CLOCK = {"t": 0.0}
G._sleep = lambda s: CLOCK.__setitem__("t", CLOCK["t"] + s)
G.time.time = lambda: CLOCK["t"]
OK = FAIL = 0


def check(name, cond, info=None):
    global OK, FAIL
    OK += bool(cond)
    FAIL += not cond
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + ("" if cond or info is None else f"  → {info}"))


def setup(net=True, mt5=True, ollama=True, cfg=True, alive=False, starts_ok=True):
    st = {"launched": 0, "alive": alive, "ollama_start": 0}
    G.check_internet = lambda: (net, "internet" if net else "internet indisponibil")
    G.check_mt5 = lambda: (mt5 if not callable(mt5) else mt5(), "MT5 cont #1 conectat (REAL)" if (mt5 if not callable(mt5) else True) else "MT5 neconectat")
    G.check_ollama = lambda: (ollama, "Ollama (2 modele)" if ollama else "Ollama nu răspunde")
    G.check_config = lambda eid: (cfg, "configurație validă" if cfg else "configurație invalidă: JSON corupt")
    G.running = lambda eid: 123 if st["alive"] else None

    def launch(eid):
        st["launched"] += 1
        st["alive"] = starts_ok
    G.launch = launch
    import api.health_monitor as H
    H.start_ollama = lambda: (st.__setitem__("ollama_start", st["ollama_start"] + 1) or True)
    SENT.clear()
    CLOCK["t"] = 0.0
    incidents.isolate_for_tests(SENT)
    return st


print("1. Totul gata → pornire o singura data, cu verificarile in mesaj")
st = setup()
rc = G.run("daily", min_delay=60, max_wait=600)
check("rc 0, pornit o data", rc == 0 and st["launched"] == 1)
check("intarzierea minima respectata (60 s inainte de orice)", CLOCK["t"] >= 60)
check("mesaj: pornit automat + ce s-a verificat", any("Daily Engine pornit automat" in s and "MT5 cont #1" in s for s in SENT))

print("2. Deja pornit (UI / watchdog) → nimic, fara dublura")
st = setup(alive=True)
check("rc 0, zero porniri, zero mesaje", G.run("daily", 1, 60) == 0 and st["launched"] == 0 and SENT == [])

print("3. MT5 indisponibil → NU porneste doar pentru ca a expirat intarzierea; incident dupa max_wait")
st = setup(mt5=False)
rc = G.run("daily", min_delay=60, max_wait=900)
check("rc 1, zero porniri (stare sigura)", rc == 1 and st["launched"] == 0)
check("incident critic cu motivul", any("NU a pornit automat" in s and "MT5 neconectat" in s for s in SENT))
check("a asteptat ~max_wait (cu reincercari tot mai rare, nu bucla stransa)", 900 <= CLOCK["t"] <= 1100, CLOCK["t"])

print("4. MT5 apare dupa cateva minute → pornire, incidentul anterior rezolvat")
calls = {"n": 0}


def mt5_late():
    calls["n"] += 1
    return calls["n"] >= 4


st = setup(mt5=mt5_late)
incidents.report("autostart:daily", "Daily Engine NU a pornit automat după restart", "test", "critical")
rc = G.run("daily", min_delay=0, max_wait=900)
check("rc 0 dupa ce MT5 a devenit disponibil", rc == 0 and st["launched"] == 1)
check("incidentul vechi de autostart → rezolvat", any("Rezolvat" in s for s in SENT) and not incidents.is_active("autostart:daily"))

print("5. AI: Ollama oprit → pornit automat O SINGURA data; asteapta raspunsul")
st = setup(ollama=False)
G.run("ai", min_delay=0, max_wait=300)
check("pornire Ollama incercata o singura data", st["ollama_start"] == 1, st)
check("Ollama tot mort → AI NU porneste (incident)", st["launched"] == 0 and any("AI Engine NU a pornit" in s for s in SENT))

print("6. Configuratie corupta → nu porneste")
st = setup(cfg=False)
check("rc 1, zero porniri", G.run("daily", 0, 120) == 1 and st["launched"] == 0)

print("7. Procesul nu ramane pornit → incident (nu „pornit”)")
st = setup(starts_ok=False)
check("rc 1 + incident „NU a rămas pornit”", G.run("daily", 0, 60) == 1 and any("NU a rămas pornit" in s for s in SENT))

print("8. Noisy refuzat; engine necunoscut refuzat")
check("noisy → refuzat (rc 2), zero mesaje", G.run("noisy") == 2)
check("necunoscut → rc 2", G.run("xyz") == 2)

print("9. Aplicatia (API) nu cere MT5")
st = setup(mt5=False, net=False)
check("app porneste fara MT5 / internet", G.run("app", 0, 60) == 0 and st["launched"] == 1)

print(f"\n{OK} OK, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
