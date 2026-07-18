"""
Rapoarte zilnice si saptamanale — trimise automat via Telegram + Notificari.

Zilnic: azi la 23:30 — tranzactii din ziua respectiva
Saptamanal: vineri la 23:30 — tranzactii din saptamana curenta (luni-vineri)
"""

import os
import time
import threading
from datetime import datetime, timedelta, date

import pandas as pd

from api.config import DATA_DIR, SESSIONS, get_profile_execute_map
from api import telegram
from api.notifications import log_notification

_CLOSED_STATUSES = ["TP", "SL", "vineri_close", "news_close", "be_lock", "be_lock2"]

_last_daily:  date | None = None
_last_weekly: date | None = None


def _read_all_outcomes(date_from: date, date_to: date) -> pd.DataFrame:
    """Citeste outcomes din sesiunile live (execute_trades=True din profil activ) pentru [date_from, date_to)."""
    session_map  = {s["id"]: s for s in SESSIONS}
    execute_map  = get_profile_execute_map()
    frames = []
    base = os.path.join(DATA_DIR, "live_signals")
    for name in sorted(os.listdir(base)):
        path = os.path.join(base, name, "outcomes.csv")
        if not os.path.isfile(path):
            continue
        s = session_map.get(name, {})
        if not execute_map.get(name, s.get("execute", True)):
            continue
        try:
            df = pd.read_csv(path, on_bad_lines="skip")
        except Exception:
            continue
        if df.empty:
            continue
        df["session_id"] = name
        df["session_label"] = s.get("label", name)
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    all_df = pd.concat(frames, ignore_index=True)
    closed = all_df[all_df["status"].isin(_CLOSED_STATUSES)].copy()
    if closed.empty:
        return pd.DataFrame()

    closed["exit_dt"] = pd.to_datetime(closed["exit_time"], errors="coerce")
    dt_from = datetime.combine(date_from, datetime.min.time())
    dt_to   = datetime.combine(date_to,   datetime.min.time())
    mask = (closed["exit_dt"] >= dt_from) & (closed["exit_dt"] < dt_to)
    return closed[mask].copy()


def _build_report(df: pd.DataFrame, title: str) -> str:
    """Construieste textul raportului HTML pentru Telegram."""
    if df.empty:
        return f"<b>{title}</b>\n\nNicio tranzacție în această perioadă."

    total   = len(df)
    wins    = int((pd.to_numeric(df["result_r"], errors="coerce") > 0).sum())
    losses  = int((pd.to_numeric(df["result_r"], errors="coerce") < 0).sum())
    winrate = round(wins / total * 100) if total > 0 else 0
    total_r = round(float(pd.to_numeric(df["result_r"], errors="coerce").sum()), 3)

    pnl_series = pd.to_numeric(df["pnl_usd"], errors="coerce").dropna()
    com_series  = pd.to_numeric(df.get("commission_usd", pd.Series()), errors="coerce").dropna()
    swp_series  = pd.to_numeric(df.get("swap_usd",       pd.Series()), errors="coerce").dropna()
    pnl_total   = round(float(pnl_series.sum()),  2) if len(pnl_series) else None
    com_total   = round(float(com_series.sum()),  2) if len(com_series)  else None
    swp_total   = round(float(swp_series.sum()),  2) if len(swp_series)  else None

    def _sgn(v: float) -> str:
        return f"+{v:.2f}" if v >= 0 else f"{v:.2f}"

    lines = [f"<b>{title}</b>\n"]
    lines.append(f"📊 <b>Trades:</b> {total} ({wins}W/{losses}L — {winrate}% WR)")
    lines.append(f"📈 <b>Total R:</b> {_sgn(total_r)}R")

    if pnl_total is not None:
        pnl_note = f" ({len(pnl_series)}/{total})" if len(pnl_series) < total else ""
        lines.append(f"💵 <b>P&amp;L USD:</b> {_sgn(pnl_total)} ${pnl_note}")
    if com_total is not None and com_total != 0:
        lines.append(f"💸 <b>Comisioane:</b> {_sgn(com_total)} $")
    if swp_total is not None and swp_total != 0:
        lines.append(f"🔄 <b>Swap:</b> {_sgn(swp_total)} $")

    # Top 3 simboluri dupa R
    if "symbol" in df.columns:
        sym_r = (
            df.assign(result_r_num=pd.to_numeric(df["result_r"], errors="coerce"))
            .groupby("symbol")["result_r_num"]
            .agg(trades="count", total_r="sum")
            .sort_values("total_r", ascending=False)
        )
        if not sym_r.empty:
            lines.append("\n🏆 <b>Top simboluri:</b>")
            for rank, (sym, row) in enumerate(sym_r.head(3).iterrows(), 1):
                medal = ["🥇", "🥈", "🥉"][rank - 1]
                lines.append(f"  {medal} {sym}: {_sgn(row['total_r'])}R ({int(row['trades'])} trades)")

    # Breakdown per sesiune (scurt)
    if "session_label" in df.columns:
        by_sess = (
            df.assign(result_r_num=pd.to_numeric(df["result_r"], errors="coerce"))
            .groupby("session_label")["result_r_num"]
            .agg(trades="count", total_r="sum")
            .sort_values("total_r", ascending=False)
        )
        if len(by_sess) > 1:
            lines.append("\n📋 <b>Per sesiune:</b>")
            for sess, row in by_sess.iterrows():
                lines.append(f"  • {sess}: {_sgn(row['total_r'])}R ({int(row['trades'])}t)")

    return "\n".join(lines)


AI_MAGIC = 770015   # namespace-ul MT5 al motorului AI (ai_engine/config.py)


def _ai_engine_section(date_from: date, date_to: date) -> str:
    """
    Sectiunea AI Engine a raportului — din istoricul REAL MT5 (magic 770015),
    nu din ledger: prinde si tranzactiile plasate de alta masina (ex: laptop) pe
    acelasi cont, unde ledger-ul local nu are decizia. Fail-safe: MT5 indisponibil
    → sectiune goala (raportul botului pleaca oricum).
    Fara aceasta sectiune, raportul zilnic acoperea DOAR sesiunile botului si
    "pierdea" tranzactiile AI (vazut 17.07: raport 2 trades, real 6 — 4 erau AI).
    """
    try:
        from api import mt5_pool
        days = max(2, (date.today() - date_from).days + 2)
        trades = [t for t in mt5_pool.get_closed_trades(days)
                  if t.get("magic") == AI_MAGIC and t.get("close_time") is not None
                  and date_from <= t["close_time"].date() < date_to]
    except Exception:
        return ""
    if not trades:
        return ""
    wins   = sum(1 for t in trades if (t.get("profit") or 0) > 0)
    losses = sum(1 for t in trades if (t.get("profit") or 0) < 0)
    pnl    = round(sum((t.get("profit") or 0) + (t.get("commission") or 0)
                       + (t.get("swap") or 0) for t in trades), 2)
    sgn = f"+{pnl:.2f}" if pnl >= 0 else f"{pnl:.2f}"
    lines = [f"\n🤖 <b>AI Engine:</b> {len(trades)} trades ({wins}W/{losses}L) · P&amp;L {sgn} $"]
    per_sym: dict = {}
    for t in trades:
        s = per_sym.setdefault(t["symbol"], {"n": 0, "pnl": 0.0})
        s["n"] += 1
        s["pnl"] += (t.get("profit") or 0) + (t.get("commission") or 0) + (t.get("swap") or 0)
    for sym, s in sorted(per_sym.items(), key=lambda kv: -kv[1]["pnl"]):
        ps = f"+{s['pnl']:.2f}" if s["pnl"] >= 0 else f"{s['pnl']:.2f}"
        lines.append(f"  • {sym}: {ps} $ ({s['n']}t)")
    return "\n".join(lines)


def send_daily_report(target_date: date | None = None) -> str:
    """Trimite raportul zilnic. target_date = azi daca None. Returneaza textul trimis."""
    if target_date is None:
        target_date = date.today()
    df = _read_all_outcomes(target_date, target_date + timedelta(days=1))
    label = target_date.strftime("%-d %B %Y") if os.name != "nt" else target_date.strftime("%d %B %Y")
    title = f"📅 Raport Zilnic — {label}"
    text  = _build_report(df, title)
    text += _ai_engine_section(target_date, target_date + timedelta(days=1))
    telegram.send_message(text)
    log_notification(text)
    return text


def send_weekly_report(week_start: date | None = None) -> str:
    """Trimite raportul saptamanal (luni-duminica). Returneaza textul trimis."""
    today = date.today()
    if week_start is None:
        week_start = today - timedelta(days=today.weekday())  # luni
    week_end = week_start + timedelta(days=7)
    df = _read_all_outcomes(week_start, week_end)
    w_from = week_start.strftime("%d.%m")
    w_to   = (week_end - timedelta(days=1)).strftime("%d.%m.%Y")
    title  = f"📆 Raport Săptămânal — {w_from}–{w_to}"
    text   = _build_report(df, title)
    text  += _ai_engine_section(week_start, week_end)
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

        except Exception:
            pass  # nu oprim scheduler-ul la erori punctuale

        time.sleep(60)


def start_scheduler() -> None:
    t = threading.Thread(target=_scheduler_loop, name="ScheduledReports", daemon=True)
    t.start()
