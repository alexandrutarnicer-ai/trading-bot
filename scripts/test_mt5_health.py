# -*- coding: utf-8 -*-
"""
Teste pentru alerta MT5-HEALTH cu PRAG DE PERSISTENTA (2026-07-21).

Cerinta: o deconectare SCURTA (blip de reconectare pe partea brokerului) NU trebuie
sa trimita alerta Telegram; alerta pleaca DOAR daca deconectarea persista peste
_MT5_DISCONNECT_GRACE_S. Fara spam: doar session1 notifica, max 2/incident.

MT5 complet simulat (FakeMt5), _send_telegram mock-uit (fara Telegram real),
fisier de alerta izolat, timpul simulat prin editarea `first_seen` din fisier.

Rulare:  python scripts/test_mt5_health.py
"""

import io
import json
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from live import signal_generator as sg

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {extra}" if extra else ""))


class _Log:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


LOGIN = 52906593


class FakeMt5:
    """Terminal MT5 simulat cu stare de conexiune controlabila."""
    def __init__(self, connected=True, ipc=True, trade_allowed=True):
        self._connected = connected
        self._ipc = ipc
        self._trade = trade_allowed

    def terminal_info(self):
        if not self._ipc:
            return None
        return SimpleNamespace(connected=self._connected, trade_allowed=self._trade)

    def account_info(self):
        return SimpleNamespace(login=LOGIN, server="ICMarketsEU-Demo")


# ── harness ──────────────────────────────────────────────────────────────────

_sent: list[str] = []
_alert_file = tempfile.mktemp(suffix=".json")
sg._MT5_HEALTH_ALERT_FILE = _alert_file
sg._send_telegram = lambda text: _sent.append(text)


def _reset():
    _sent.clear()
    try: os.remove(_alert_file)
    except OSError: pass


def _check(connected=True, ipc=True, session="session1"):
    sg._mt5_exec = FakeMt5(connected=connected, ipc=ipc)
    sg._check_mt5_health(_Log(), session, LOGIN)


def _age_first_seen(key, seconds):
    """Simuleaza trecerea timpului: da first_seen inapoi cu `seconds`."""
    with open(_alert_file, encoding="utf-8") as f:
        d = json.load(f)
    d[key]["first_seen"] -= seconds
    if "last_sent" in d[key]:
        d[key]["last_sent"] -= seconds
    with open(_alert_file, "w", encoding="utf-8") as f:
        json.dump(d, f)


print("=== MT5-HEALTH: prag de persistenta (anti-spam pentru blip-uri) ===\n")

# 1. BLIP: deconectare scurta care se rezolva inainte de prag → ZERO alerte
_reset()
_check(connected=False)                      # detectare, sub prag → fara alerta
check("blip: prima detectare (sub prag) → fara alerta", _sent == [])
_check(connected=True)                        # revenire rapida (blip)
check("blip: revenire rapida → TOT fara alerta (nu spam)", _sent == [])

# 2. SUSTINUT: deconectare care depaseste pragul → 1 alerta, cu durata
_reset()
_check(connected=False)                       # t=0: detectare, fara alerta
check("sustinut: la detectare inca fara alerta", _sent == [])
_age_first_seen("disconnected", 900)          # simuleaza 15 min scurse
_check(connected=False)                        # inca deconectat, peste prag → ALERTA
check("sustinut: peste prag → o alerta 'Deconectat'",
      len(_sent) == 1 and "Deconectat de la server broker" in _sent[0])
check("sustinut: alerta mentioneaza durata (min)", "min" in _sent[0])

# 3. Reconectare dupa alerta → mesaj de confirmare
_check(connected=True)
check("recuperare dupa alerta → 'Reconectat'",
      any("Reconectat" in s for s in _sent))

# 4. Reminder: daca persista, a 2-a alerta dupa _MT5_HEALTH_REPEAT_S, apoi STOP
_reset()
_check(connected=False); _age_first_seen("disconnected", 900); _check(connected=False)  # alerta #1
_age_first_seen("disconnected", 700)          # +>10 min de la ultima
_check(connected=False)                        # reminder #2
check("reminder: a 2-a alerta dupa persistenta (#2)", len(_sent) == 2)
_age_first_seen("disconnected", 700)
_check(connected=False)                        # peste MAX → nimic
check("anti-spam: dupa 2 alerte, gata (max/incident)", len(_sent) == 2)

# 5. Doar session1 notifica (celelalte sesiuni NU trimit)
_reset()
_check(connected=False, session="session7")
_age_first_seen_ok = os.path.exists(_alert_file)
check("non-notifier (session7) nu creeaza/trimite nimic", _sent == [] and not _age_first_seen_ok)

# 6. IPC pierdut (terminal inchis) — acelasi prag
_reset()
_check(ipc=False)                              # terminal_info None, sub prag → fara alerta
check("IPC pierdut sub prag → fara alerta", _sent == [])
_age_first_seen("ipc_lost", 900)
_check(ipc=False)
check("IPC pierdut sustinut → alerta 'IPC pierduta'",
      len(_sent) == 1 and "IPC pierduta" in _sent[0])

try: os.remove(_alert_file)
except OSError: pass

print("\n" + "=" * 55)
print(f"REZULTAT: {len(PASS)} PASS / {len(FAIL)} FAIL din {len(PASS) + len(FAIL)}")
if FAIL:
    print("PICATE:", FAIL); sys.exit(1)
print("TOATE TESTELE AU TRECUT")
