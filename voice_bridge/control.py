"""
voice_bridge.control — starea de pauza/mut a lui EMA (fisier-flag, ca paused_sessions).

Un flag simplu in data/voice_bridge_control.json pe care il pot scrie DEOPOTRIVA:
  • UI-ul / API-ul (butonul „Pauza EMA")            → set_paused(True/False)
  • EMA insasi la comanda vocala „culca-te" / „pauza" → set_paused(True)

Bucla principala (bridge.py) citeste flag-ul la fiecare iteratie. Cand e pe pauza,
NU deschide microfonul deloc (mut total — ideal cand esti pe Discord cu prietenii);
revenirea se face din UI (recomandat) sau, optional, cu wake word (resume_by_voice).

Scris atomic (tmp + replace). Citire fail-safe: orice eroare → nu-e-pe-pauza.
"""

from __future__ import annotations

import json
import os

from . import config

CONTROL_PATH = os.path.join(config.DATA_DIR, "voice_bridge_control.json")


def read_control() -> dict:
    try:
        with open(CONTROL_PATH, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def is_paused() -> bool:
    return bool(read_control().get("paused"))


def set_paused(paused: bool) -> None:
    d = read_control()
    d["paused"] = bool(paused)
    _write(d)


def _write(d: dict) -> None:
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        tmp = CONTROL_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, CONTROL_PATH)
    except Exception:
        pass
