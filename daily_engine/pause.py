"""Daily Engine — PAUZA PER PIATA (2026-11-05). Functii PURE, testate in daily_engine.selftest (sectiunea 8).

Regula: Pause Market = STOP la intrari NOI; ce e deja deschis continua sa fie gestionat (SL, inchiderea la final de
fereastra, protectiile globale). Config: `markets[i].paused` + `paused_at` (ISO UTC) in daily_engine/config.json —
persista peste restart; nimic automat (scheduler / autostart / watchdog) nu scrie aceste campuri, doar butoanele
Pause / Resume din UI (API `POST /daily/markets/{slot}/pause|resume`).

Ziua se recalculeaza de la zero la fiecare iteratie (evaluate_day_multi, pura), deci pauza se aplica tot ca filtru pur:
trade-urile al caror minut de INTRARE (ora bursei) e >= momentul pauzei dispar; cele intrate inainte raman."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

_PENDING_PHASES = ("waiting_open", "forming_or", "waiting_entry")


def pause_cut_min(m: dict, day: date) -> int | None:
    """None = piata activa. Altfel minutul zilei (ora BURSEI) de la care nu mai intra nimic: 0 = toata ziua."""
    if not m.get("paused"):
        return None
    try:
        t = datetime.fromisoformat(str(m.get("paused_at"))).astimezone(ZoneInfo(m["tz"]))
    except Exception:
        return 0                                   # pauza fara moment valid → toata ziua (sigur)
    if t.date() != day:                            # pus pe pauza intr-o zi anterioara → toata ziua
        return 0
    return t.hour * 60 + t.minute


def apply_pause(st: dict, cut: int | None) -> dict:
    """Starea zilei dupa pauza: intrarile de la `cut` incolo sunt eliminate; pozitia intrata inainte ramane."""
    if cut is None:
        return st
    trades = [t for t in (st.get("trades") or []) if int(t.get("entry_min", 10 ** 6)) < cut]
    out = {**st, "trades": trades, "paused": True}
    ph = st.get("phase")
    entered_after = int(st.get("entry_min", -1)) >= cut if st.get("entry_min") is not None else False
    if ph in _PENDING_PHASES:
        out["phase"] = "paused"
    elif ph == "in_position" and entered_after:
        out["phase"] = "paused"
        for k in ("side", "entry", "sl", "tp", "risk", "entry_bar", "entry_min", "last", "open_R"):
            out.pop(k, None)
    elif ph in ("closed", "skipped") and entered_after:
        out["phase"] = "paused"
    if out["phase"] == "paused":
        out["reason"] = "piață pe pauză — fără intrări noi"
    return out
