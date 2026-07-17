"""
live_guard — deblocarea EXPLICITA a contului LIVE, per componenta, per masina.

Default (fara fisier / fisier corupt / componenta absenta): totul BLOCAT pe
conturi non-DEMO — exact comportamentul istoric. Deblocarea e o decizie
constienta: din UI (Profil → sectiunea "Trading LIVE") sau scriind manual
data/live_trading.json:

    {"bot": false, "ai_engine": false}

Proprietati de siguranta:
  - fisierul sta in data/ (gitignored) → deblocarea NU se propaga intre masini
    prin git; fiecare masina trebuie deblocata explicit.
  - switch-uri SEPARATE pentru botul pe reguli ("bot") si motorul AI
    ("ai_engine") — se pot porni independent.
  - orice eroare de citire → BLOCAT (fail-safe).
  - la prima conectare reala pe cont LIVE, componenta trimite Telegram + log
    WARNING (o singura data per proces) — nu exista conectare live "tacuta".

Consumatori: adapters/mt5_source.py (bot + AI, sursa de date) si
ai_engine/executor.py (ordinele motorului AI).
"""

from __future__ import annotations

import json
import os
import threading

ROOT = os.path.dirname(os.path.abspath(__file__))
LIVE_FILE = os.path.join(ROOT, "data", "live_trading.json")

COMPONENTS = ("bot", "ai_engine")

# Componentele care au notificat deja conectarea live in acest proces.
_notified: set = set()


def live_flags() -> dict:
    """{componenta: bool} — absent/corupt = False (fail-safe: blocat)."""
    try:
        with open(LIVE_FILE, encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError("format invalid")
        return {c: bool(raw.get(c, False)) for c in COMPONENTS}
    except Exception:
        return {c: False for c in COMPONENTS}


def live_allowed(component: str) -> bool:
    """True DOAR daca utilizatorul a deblocat explicit componenta pe aceasta masina."""
    return live_flags().get(component, False)


def set_live(component: str, allowed: bool) -> dict:
    """Seteaza flag-ul unei componente si returneaza starea completa."""
    if component not in COMPONENTS:
        raise ValueError(f"componenta necunoscuta: {component!r} "
                         f"(valide: {', '.join(COMPONENTS)})")
    flags = live_flags()
    flags[component] = bool(allowed)
    os.makedirs(os.path.dirname(LIVE_FILE), exist_ok=True)
    with open(LIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(flags, f, indent=2)
    return flags


def notify_live_connection(component: str, login, server: str) -> None:
    """
    Anunta (Telegram + stdout) ca o componenta S-A CONECTAT la un cont REAL.
    O singura data per componenta per proces; best-effort — esecul notificarii
    nu blocheaza niciodata conectarea.
    """
    if component in _notified:
        return
    _notified.add(component)
    text = (f"⚠️🔴 <b>CONT LIVE — {component}</b>\n"
            f"Conectat la contul REAL {login} ({server}).\n"
            f"Ordinele se plasează cu BANI REALI. Dezactivare: Profil → Trading LIVE.")
    try:
        print(f"[LIVE] {component}: conectat la cont REAL {login} ({server})")
    except Exception:
        pass
    try:
        from api.telegram import send_message
        threading.Thread(target=send_message, args=(text,), daemon=True).start()
    except Exception:
        pass
