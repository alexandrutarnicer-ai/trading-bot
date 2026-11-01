"""
Ce dispozitiv ruleaza engine-urile (PC <-> laptop pe branch-ul de date alex-live).

`data/device_owner.json` e sincronizat prin git de scripts/device_switch.py:
  {"owner": "<COMPUTERNAME>", "state": "running" | "released", "engines": [...], "time": "..."}
  • running  = engine-urile ruleaza (sau trebuie sa ruleze) pe `owner`
  • released = `owner` le-a oprit si a predat datele; oricine le poate prelua

Folosit ca plasa de siguranta: pe un dispozitiv care NU e proprietar, pornirea engine-urilor din UI
e refuzata (altfel ar rula pe ambele, cu ordine duble pe acelasi cont), iar rapoartele programate
se trimit doar de pe proprietar. Fisier lipsa / corupt => comportamentul de dinainte (nicio restrictie).
"""
from __future__ import annotations

import json
import os
import platform

ROOT = os.path.dirname(os.path.abspath(__file__))
OWNER_FILE = os.path.join(ROOT, "data", "device_owner.json")
OWNER_REL = "data/device_owner.json"


def this_machine() -> str:
    return (os.environ.get("COMPUTERNAME") or platform.node() or "?").upper()


def read_owner(path: str | None = None) -> dict | None:
    try:
        with open(path or OWNER_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) and d.get("owner") else None
    except Exception:
        return None


def other_device_running(path: str | None = None) -> str | None:
    """Numele celuilalt dispozitiv daca el detine engine-urile acum, altfel None."""
    d = read_owner(path)
    if d and d.get("state") == "running" and str(d["owner"]).upper() != this_machine():
        return str(d["owner"])
    return None


def is_reporting_machine(path: str | None = None) -> bool:
    """Rapoartele programate pleaca DOAR de pe dispozitivul proprietar (cel care ruleaza sau a rulat
    ultimul engine-urile) — si cand engine-urile sunt predate, ca sa nu plece de pe ambele."""
    d = read_owner(path)
    return d is None or str(d["owner"]).upper() == this_machine()
