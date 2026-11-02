"""
Scriere ATOMICA de JSON, rezistenta la blocarile de fisier din Windows.

Incident 2026-11-02 (Noisy pe laptop): „iteratie esuata: PermissionError [WinError 5] Access denied:
status.json.tmp -> status.json”. Pe Windows, `os.replace` peste un fisier pe care alt proces il are deschis in acel
moment (API-ul citeste status.json la fiecare 5 s pentru dashboard; antivirusul / indexarea / sync-ul il pot deschide si
ei) e refuzat cu WinError 5 / 32. Inainte, exceptia pica TOATA iteratia engine-ului (iar la 3 la rand, reconectarea MT5).

write_json_atomic: reincearca mutarea de cateva ori (blocarea dureaza milisecunde); daca tot nu merge:
  - critical=False (fisiere de AFISARE, ex. status.json) → intoarce False, fara exceptie: iteratia continua, urmatoarea
    il rescrie (fisierul vechi ramane intact si complet — scrierea e tot atomica);
  - critical=True (stare, ex. state.json) → ridica exceptia, ca pana acum (apelantul trebuie sa stie).
"""
from __future__ import annotations

import json
import logging
import os
import time

log = logging.getLogger("safe_io")
RETRIES = 8
DELAY_S = 0.05


def write_json_atomic(path: str, data, critical: bool = True, retries: int = RETRIES, delay_s: float = DELAY_S,
                      _replace=None) -> bool:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    _replace = _replace or os.replace          # rezolvat la apel (testabil)
    last: Exception | None = None
    for k in range(max(1, retries)):
        try:
            _replace(tmp, path)
            return True
        except PermissionError as e:          # WinError 5 / 32: fisier tinut deschis de alt proces
            last = e
            time.sleep(delay_s * (k + 1))
    if critical:
        raise last                             # type: ignore[misc]
    log.warning(f"{os.path.basename(path)} nu a putut fi actualizat (blocat de alt proces) — se rescrie la iteratia urmatoare")
    return False
