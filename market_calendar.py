"""
Calendarul burselor (2026-11-27) — zile INCHISE si inchideri DEVREME, calculate din reguli (fara fisiere, fara retea).

De ce: 26.11.2026 (Thanksgiving) bursa NY a fost inchisa, CFD-urile pe indicii SUA s-au oprit la 19:55 RO, iar DE40 la
22:55 RO (in loc de 23:55). Sesiunea New York a DE40 din Daily Engine se inchide la 16:00 NY = 23:00 RO → la ora
inchiderii piata era deja inchisa, ordinul de inchidere a esuat, iar pozitia a ramas peste noapte pana la redeschidere
(01:05 RO, prinsa de `sweep_stale`). In zilele cu inchidere devreme (ziua de dupa Thanksgiving, Ajunul Craciunului,
3 iulie: 13:00 NY) fereastra de 16:00 NY ar fi depasit piata cu 3 ore.

Doar functii PURE. Acoperire: NYSE (America/New_York) si Xetra (Europe/Berlin). Alte burse → necunoscut (None).
"""
from __future__ import annotations

from datetime import date, time, timedelta

EARLY_CLOSE_NY = time(13, 0)


def _easter(y: int) -> date:
    """Duminica Pastelui (calendarul gregorian, algoritmul anonim)."""
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = ((h + l_ - 7 * m + 114) % 31) + 1
    return date(y, month, day)


def _nth_weekday(y: int, month: int, weekday: int, n: int) -> date:
    d = date(y, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(y: int, month: int, weekday: int) -> date:
    d = date(y + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _observed(d: date) -> date:
    """Regula NYSE: sambata → vinerea de dinainte, duminica → lunea de dupa."""
    return d - timedelta(days=1) if d.weekday() == 5 else (d + timedelta(days=1) if d.weekday() == 6 else d)


def nyse_holidays(y: int) -> dict[date, str]:
    h = {
        _observed(date(y, 1, 1)): "Anul Nou",
        _nth_weekday(y, 1, 0, 3): "Martin Luther King Day",
        _nth_weekday(y, 2, 0, 3): "Presidents Day",
        _easter(y) - timedelta(days=2): "Vinerea Mare",
        _last_weekday(y, 5, 0): "Memorial Day",
        _observed(date(y, 6, 19)): "Juneteenth",
        _observed(date(y, 7, 4)): "Ziua Independenței SUA",
        _nth_weekday(y, 9, 0, 1): "Labor Day",
        _nth_weekday(y, 11, 3, 4): "Thanksgiving",
        _observed(date(y, 12, 25)): "Crăciun",
    }
    return {d: n for d, n in h.items() if d.year == y and d.weekday() < 5}


def nyse_early_closes(y: int) -> dict[date, str]:
    tg = _nth_weekday(y, 11, 3, 4)
    out = {tg + timedelta(days=1): "ziua de după Thanksgiving",
           date(y, 12, 24): "Ajunul Crăciunului",
           date(y, 7, 3): "ziua dinaintea Zilei Independenței"}
    hol = nyse_holidays(y)
    return {d: n for d, n in out.items() if d.weekday() < 5 and d not in hol}


def xetra_holidays(y: int) -> dict[date, str]:
    e = _easter(y)
    h = {date(y, 1, 1): "Anul Nou", e - timedelta(days=2): "Vinerea Mare", e + timedelta(days=1): "Lunea Paștelui",
         date(y, 5, 1): "Ziua Muncii", date(y, 12, 24): "Ajunul Crăciunului", date(y, 12, 25): "Crăciun",
         date(y, 12, 26): "A doua zi de Crăciun", date(y, 12, 31): "Revelion"}
    return {d: n for d, n in h.items() if d.weekday() < 5}


def session_status(tz: str, day: date) -> dict:
    """{"known": bool, "closed": bool, "early_close": time | None, "name": str} pentru bursa din fusul `tz`."""
    if tz == "America/New_York":
        if day in (hol := nyse_holidays(day.year)):
            return {"known": True, "closed": True, "early_close": None, "name": hol[day]}
        if day in (ec := nyse_early_closes(day.year)):
            return {"known": True, "closed": False, "early_close": EARLY_CLOSE_NY, "name": ec[day]}
        return {"known": True, "closed": False, "early_close": None, "name": ""}
    if tz == "Europe/Berlin":
        if day in (hol := xetra_holidays(day.year)):
            return {"known": True, "closed": True, "early_close": None, "name": hol[day]}
        return {"known": True, "closed": False, "early_close": None, "name": ""}
    return {"known": False, "closed": False, "early_close": None, "name": ""}


def capped_last_bar(last_bar: str, tz: str, day: date, margin_min: int = 15) -> tuple[str, str]:
    """Ultima bara M5 a ferestrei (HH:MM, inceputul barei) limitata la `margin_min` minute inainte de inchiderea
    devreme a bursei. Intoarce (last_bar, motiv) — motiv gol daca nu s-a schimbat nimic."""
    st = session_status(tz, day)
    ec = st.get("early_close")
    if not ec:
        return last_bar, ""
    lim = ec.hour * 60 + ec.minute - margin_min - 5          # bara care se INCHIDE cu margin_min inainte
    h, m = map(int, last_bar.split(":"))
    if h * 60 + m <= lim:
        return last_bar, ""
    return f"{lim // 60:02d}:{lim % 60:02d}", f"închidere devreme a bursei ({st['name']}, {ec:%H:%M})"
