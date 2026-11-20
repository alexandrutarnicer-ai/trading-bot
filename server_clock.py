"""Ora serverului MT5 detectata din tick — COMUNA Daily Engine + Noisy Engine (pura, fara MT5).

Offset = tick.time − UTC, rotunjit la ora intreaga; tick-ul e „proaspat” daca restul e sub 3 minute.

Bug reparat (20.11.2026, analiza Live Readiness): un tick VECHI de EXACT N ore trece si el testul. La 00:56 RO
indicii sunt in pauza zilnica, ultimul tick e de la ~23:56 (vechi de 60 min) → offset-ul detectat era cu −1h gresit →
barele zilei se mutau cu o ora, intervalul de deschidere se calcula din barele de pre-market si se inregistrau
re-intrari FANTOMA (Daily: DE40 / US500, 09.11, 17.11, 18.11 — +9,9R inexistent in shadow).

Regula: prima detectare ramane ca inainte (pornire); o SCHIMBARE a offset-ului cunoscut e acceptata DOAR daca
tick-ul s-a SCHIMBAT fata de observatia precedenta pe acelasi simbol (un tick inghetat in pauza ramane acelasi) si e
confirmata pe DOUA tick-uri noi consecutive (schimbarile reale = DST, in weekend → intarzierea nu conteaza).
"""
from __future__ import annotations

FRESH_S = 180


def candidate(tick_time: float, now_ts: float) -> int | None:
    """Offset-ul (secunde) daca tick-ul pare proaspat (rest < 3 min fata de o ora intreaga), altfel None."""
    diff = float(tick_time) - float(now_ts)
    hours = round(diff / 3600)
    return int(hours * 3600) if abs(diff - hours * 3600) < FRESH_S else None


class ServerClock:
    """Starea detectiei: ultimul tick vazut pe fiecare simbol + o schimbare in asteptarea confirmarii."""

    def __init__(self) -> None:
        self.last_tick: dict[str, float] = {}
        self.pending: int | None = None

    def update(self, symbol: str, tick_time: float, now_ts: float, current: int | None) -> int | None:
        prev = self.last_tick.get(symbol)
        self.last_tick[symbol] = tick_time
        cand = candidate(tick_time, now_ts)
        if cand is None:
            return current
        if current is None:                   # pornire: ca inainte
            self.pending = None
            return cand
        if cand == current:
            self.pending = None
            return current
        if prev is None or tick_time == prev:  # tick inghetat / primul vazut pe simbol → nu schimba nimic
            return current
        if self.pending == cand:               # a doua confirmare pe un tick nou
            self.pending = None
            return cand
        self.pending = cand
        return current
