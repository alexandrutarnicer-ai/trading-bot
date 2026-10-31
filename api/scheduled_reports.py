"""
Rapoarte zilnice si saptamanale — trimise automat via Telegram + Notificari.

Zilnic: azi la 23:30 — tranzactii din ziua respectiva
Saptamanal: vineri la 23:30 — tranzactii din saptamana curenta (luni-vineri)

Sursa: exclusiv istoricul MT5 (api.mt5_pool), atribuit pe Bot Engine (pe sesiune +
strategie) / AI Engine / manual dupa magic + comment (mt5_pool.classify_trade).
"""

import os
import time
import threading
from datetime import datetime, timedelta, date

from api.config import SESSIONS
from api import telegram
from api.notifications import log_notification

_last_daily:  date | None = None
_last_weekly: date | None = None

_STRATEGY_LABELS = {"pullback": "Pullback", "inside_bar": "Inside Bar",
                    "flag": "Flag", "smart_news": "Știri"}


def _mt5_trades(date_from: date, date_to: date) -> list[dict] | None:
    """
    Tranzactiile inchise in [date_from, date_to) din istoricul REAL MT5 — sursa
    unica de adevar (nu outcomes.csv). Prinde si tranzactiile plasate de alta
    masina pe acelasi cont. None = MT5 indisponibil.
    """
    try:
        from api import mt5_pool
        days = max(2, (date.today() - date_from).days + 2)
        return [t for t in mt5_pool.get_closed_trades(days)
                if t.get("close_time") is not None
                and date_from <= t["close_time"].date() < date_to]
    except Exception:
        return None


def _net(t: dict) -> float:
    return (t.get("profit") or 0) + (t.get("commission") or 0) + (t.get("swap") or 0)


def _sgn(v: float, nd: int = 2) -> str:
    return f"+{v:.{nd}f}" if v >= 0 else f"{v:.{nd}f}"


def _summary_line(trades: list[dict]) -> str:
    wins   = sum(1 for t in trades if (t.get("profit") or 0) > 0)
    losses = sum(1 for t in trades if (t.get("profit") or 0) < 0)
    pnl    = round(sum(_net(t) for t in trades), 2)
    rs     = [t["result_r"] for t in trades if t.get("result_r") is not None]
    r_part = f" · {_sgn(sum(rs))}R" if rs else ""
    return f"{len(trades)} trades ({wins}W/{losses}L){r_part} · P&amp;L {_sgn(pnl)} $"


def _grouped(trades: list[dict], key) -> list[str]:
    groups: dict = {}
    for t in trades:
        g = groups.setdefault(key(t), [])
        g.append(t)
    rows = sorted(groups.items(), key=lambda kv: -sum(_net(t) for t in kv[1]))
    return [f"  • {name}: {_sgn(sum(_net(t) for t in ts))} $ ({len(ts)}t)" for name, ts in rows]


def _build_report(trades: list[dict] | None, title: str) -> str:
    """Construieste textul raportului HTML pentru Telegram, din tranzactiile MT5."""
    if trades is None:
        return f"<b>{title}</b>\n\n⚠️ MT5 indisponibil — raportul nu a putut fi generat."
    if not trades:
        return f"<b>{title}</b>\n\nNicio tranzacție în această perioadă."

    pnl   = round(sum(_net(t) for t in trades), 2)
    comm  = round(sum(t.get("commission") or 0 for t in trades), 2)
    swap  = round(sum(t.get("swap") or 0 for t in trades), 2)
    lines = [f"<b>{title}</b>\n",
             f"💵 <b>Cont (MT5):</b> {len(trades)} trades · P&amp;L net {_sgn(pnl)} $"]
    if comm:
        lines.append(f"💸 <b>Comisioane:</b> {_sgn(comm)} $")
    if swap:
        lines.append(f"🔄 <b>Swap:</b> {_sgn(swap)} $")

    labels = {s["id"]: s["label"] for s in SESSIONS}
    bot = [t for t in trades if t.get("source") == "bot"]
    if bot:
        lines.append(f"\n⚙️ <b>Bot Engine:</b> {_summary_line(bot)}")
        lines += _grouped(bot, lambda t: labels.get(t.get("session_id"), t["symbol"]))
        by_strat = _grouped(bot, lambda t: _STRATEGY_LABELS.get(t.get("strategy"), "—"))
        if len(by_strat) > 1:
            lines.append("  <i>pe strategie:</i>")
            lines += by_strat

    ai = [t for t in trades if t.get("source") == "ai"]
    if ai:
        lines.append(f"\n🤖 <b>AI Engine:</b> {_summary_line(ai)}")
        lines += _grouped(ai, lambda t: t["symbol"])

    manual = [t for t in trades if t.get("source") == "manual"]
    if manual:
        lines.append(f"\n✋ <b>Manual:</b> {_summary_line(manual)}")

    return "\n".join(lines)


def send_daily_report(target_date: date | None = None) -> str:
    """Trimite raportul zilnic. target_date = azi daca None. Returneaza textul trimis."""
    if target_date is None:
        target_date = date.today()
    trades = _mt5_trades(target_date, target_date + timedelta(days=1))
    label = target_date.strftime("%-d %B %Y") if os.name != "nt" else target_date.strftime("%d %B %Y")
    title = f"📅 Raport Zilnic — {label}"
    text  = _build_report(trades, title)
    telegram.send_message(text)
    log_notification(text)
    return text


def send_weekly_report(week_start: date | None = None) -> str:
    """Trimite raportul saptamanal (luni-duminica). Returneaza textul trimis."""
    today = date.today()
    if week_start is None:
        week_start = today - timedelta(days=today.weekday())  # luni
    week_end = week_start + timedelta(days=7)
    trades = _mt5_trades(week_start, week_end)
    w_from = week_start.strftime("%d.%m")
    w_to   = (week_end - timedelta(days=1)).strftime("%d.%m.%Y")
    title  = f"📆 Raport Săptămânal — {w_from}–{w_to}"
    text   = _build_report(trades, title)
    telegram.send_message(text)
    log_notification(text)
    return text


def _scheduler_loop() -> None:
    global _last_daily, _last_weekly
    while True:
        try:
            now = datetime.now()
            today = now.date()

            # Daily: in fiecare zi la 23:30
            if now.hour == 23 and now.minute >= 30:
                if _last_daily is None or _last_daily < today:
                    _last_daily = today
                    send_daily_report(today)

            # Weekly: vineri la 23:30
            if now.weekday() == 4 and now.hour == 23 and now.minute >= 30:
                week_start = today - timedelta(days=today.weekday())
                if _last_weekly is None or _last_weekly < week_start:
                    _last_weekly = week_start
                    send_weekly_report(week_start)

            # Curatare date AI fara trade: luni de la 12:00 (vezi api/data_cleanup.py)
            from api import data_cleanup
            if data_cleanup.due(now):
                rep = data_cleanup.run_cleanup(apply=True, now=now)
                if rep["ledger"]["councils"] or rep["ai_filter"]["verdicts"]:
                    text = data_cleanup.summary_text(rep)
                    telegram.send_message(text)
                    log_notification(text)

        except Exception:
            pass  # nu oprim scheduler-ul la erori punctuale

        time.sleep(60)


def start_scheduler() -> None:
    t = threading.Thread(target=_scheduler_loop, name="ScheduledReports", daemon=True)
    t.start()
