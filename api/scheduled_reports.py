"""
Rapoarte zilnice / saptamanale / lunare — trimise automat via Telegram + Notificari.

Toate orele sunt in FUSUL ORAR AL APLICATIEI (tz_helper.now_local — acelasi in care MT5 isi
converteste tranzactiile), configurabile in data/reports_config.json (GET/PUT /reports/config):
  Zilnic     : OPTIONAL (daily_enabled, implicit pornit) in fiecare zi la daily_time (23:30) — tranzactiile
               zilei; marcaj PERSISTENT (daily_sent in reports_state.json) → fara dubluri la restart /
               doua API-uri pornite (incident: 05.10 si 31.10 trimise de doua ori).
  Saptamanal : VINERI de la weekly_time (20:00, 2026-11-12: laptopul se inchide de obicei dupa 20:00) —
               ASTEAPTA intai inchiderea de vineri (pozitiile Custom pe piete ne-cripto, max
               WEEKLY_SETTLE_MAX_MIN) si istoricul MT5. Fereastra CONTINUA: de la sfarsitul raportului
               trecut (weekly_last_end) pana in momentul trimiterii — nimic nu cade intre doua rapoarte.
               Laptop inchis vineri → RECUPERARE la urmatoarea pornire, pana luni la 12:00.
  Lunar      : in ziua monthly_day (1) la monthly_time (09:00) — LUNA CALENDARISTICA completa
               precedenta (inclusiv weekendurile). Daca API-ul era oprit, se trimite la prima
               ocazie din PRIMELE 7 ZILE (marcaj in data/reports_state.json, fara dubluri);
               mai tarziu nu se mai trimite (ar fi un raport vechi de saptamani).
Continutul saptamanal / lunar: api/reports_builder.py (performanta per engine, comparatie,
conditii de piata, evenimente, weekend, probleme, analiza AI — fiecare sectiune izolata).

Sursa: exclusiv istoricul MT5 (api.mt5_pool), atribuit pe Bot Engine (pe sesiune +
strategie) / AI Engine / manual dupa magic + comment (mt5_pool.classify_trade).
"""

import os
import json
import time
import threading
from datetime import datetime, timedelta, date

from tz_helper import now_local

from api.config import SESSIONS
from api import telegram
from api.notifications import log_notification

_last_daily:  date | None = None
_STARTED = time.monotonic()
# Raport generat in primele minute dupa pornirea API-ului / a terminalului = istoric MT5 inca necitit
# (cont neautentificat) → raport GOL. Incident 2026-11-02: raportul lunar pe octombrie (recuperat la
# pornirea laptopului, dupa ce duminica 1.11 09:00 fusese ratat) a plecat fara date, desi MT5 are 67
# de tranzactii in octombrie. Acum: gratie la pornire + raportul ASTEAPTA pana MT5 e gata.
STARTUP_GRACE_S = 180
REPORT_DEFER_MAX_S = 3 * 3600          # dupa 3h de asteptare se trimite oricum, cu MT5 marcat indisponibil
_deferred: dict[str, float] = {}       # tip raport → momentul primei amanari (monotonic)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(_ROOT, "data", "reports_config.json")
STATE_FILE = os.path.join(_ROOT, "data", "reports_state.json")
DEFAULT_CONFIG = {
    "enabled_on_this_machine": True,   # pune False pe masina care NU ruleaza engine-urile (evita dubluri)
    "daily_enabled": True,             # raportul zilnic e OPTIONAL (implicit pornit)
    "daily_time": "23:30",
    "weekly_weekday": 4,               # 4 = vineri (fix: raportul saptamanal = finalul saptamanii de trading)
    "weekly_time": "20:00",
    "monthly_day": 1,
    "monthly_time": "09:00",
    "ai_analysis": True,
}


WEEKLY_OLD_DEFAULT = "23:30"           # vechiul implicit → migrat o singura data la 20:00 (cererea userului)
WEEKLY_SETTLE_MAX_MIN = 20             # vineri: asteapta inchiderea pozitiilor de weekend cel mult atat
WEEKLY_CATCHUP_DAYS = 3                # laptop inchis vineri → recuperare pana luni la 12:00


def load_reports_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    raw = {}
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            raw = json.load(f)
        cfg.update({k: v for k, v in raw.items() if k in DEFAULT_CONFIG})
    except Exception:
        pass
    # migrare o singura data: ora veche IMPLICITA a saptamanalului (23:30) → 20:00; o ora aleasa de user ramane
    if raw and not raw.get("weekly_time_v2"):
        if raw.get("weekly_time") == WEEKLY_OLD_DEFAULT:
            cfg["weekly_time"] = DEFAULT_CONFIG["weekly_time"]
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({**raw, **{k: cfg[k] for k in DEFAULT_CONFIG}, "weekly_time_v2": True}, f, indent=2)
        except OSError:
            pass
    cfg["weekly_weekday"] = 4          # saptamanalul ramane vineri (cerinta)
    cfg["daily_enabled"] = bool(cfg.get("daily_enabled", True))
    return cfg


def save_reports_config(new: dict) -> dict:
    cfg = load_reports_config()
    for k, v in new.items():
        if k not in DEFAULT_CONFIG or k == "weekly_weekday":
            continue
        if k.endswith("_time"):
            hh, mm = str(v).split(":")
            if not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
                raise ValueError(f"{k} invalid: {v}")
            v = f"{int(hh):02d}:{int(mm):02d}"
        if k == "monthly_day":
            v = max(1, min(28, int(v)))
        if k in ("daily_enabled", "enabled_on_this_machine", "ai_analysis"):
            v = bool(v)
        cfg[k] = v
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({**cfg, "weekly_time_v2": True}, f, indent=2)
    return cfg


def _state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(st: dict) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2)
    except OSError:
        pass


def _hm(s: str) -> tuple[int, int]:
    hh, mm = s.split(":")
    return int(hh), int(mm)


def weekly_window(now: datetime, cfg: dict) -> tuple[datetime, datetime]:
    """[vinerea trecuta la ora raportului, vinerea aceasta la ora raportului) — ferestre
    continue, fiecare tranzactie apare intr-un singur raport saptamanal (inclusiv weekendul)."""
    h, m = _hm(cfg["weekly_time"])
    days_since_fri = (now.weekday() - 4) % 7
    end = (now - timedelta(days=days_since_fri)).replace(hour=h, minute=m, second=0, microsecond=0)
    if end > now:
        end -= timedelta(days=7)
    return end - timedelta(days=7), end


def monthly_window(now: datetime) -> tuple[datetime, datetime]:
    """Luna calendaristica COMPLETA precedenta: [1 ale lunii trecute 00:00, 1 ale lunii curente 00:00)."""
    end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start = (end - timedelta(days=1)).replace(day=1)
    return start, end


def weekly_due(now: datetime, cfg: dict, st: dict) -> bool:
    """Raportul saptamanal al ultimei vineri e datorat? Vineri de la weekly_time; daca a fost ratat (laptop
    inchis), recuperat la prima pornire pana luni la 12:00 — o singura data (marcaj = data vinerii)."""
    _, end = weekly_window(now, cfg)
    if st.get("weekly_sent") == end.date().isoformat():
        return False
    deadline = datetime.combine(end.date() + timedelta(days=WEEKLY_CATCHUP_DAYS), datetime.min.time()).replace(hour=12)
    return end <= now < deadline


def weekly_send_window(now: datetime, cfg: dict, st: dict) -> tuple[datetime, datetime]:
    """Fereastra raportului saptamanal trimis ACUM: de la sfarsitul raportului trecut (weekly_last_end) pana
    acum — continua (tranzactiile inchise intre ora raportului si trimitere nu cad intre doua rapoarte)."""
    start, _ = weekly_window(now, cfg)
    try:
        last = datetime.fromisoformat(st["weekly_last_end"]) if st.get("weekly_last_end") else None
    except (TypeError, ValueError):
        last = None
    if last is not None and timedelta(0) < now - last <= timedelta(days=14):
        start = last
    return start, now


def friday_close_pending(now: datetime, positions=None) -> bool:
    """Vineri seara: mai sunt pozitii Custom (comment S<n>-) pe piete NE-cripto care urmeaza sa fie inchise de
    inchiderea de vineri? Raportul asteapta (cel mult WEEKLY_SETTLE_MAX_MIN). Orice eroare → nu asteapta."""
    if now.weekday() != 4:
        return False
    try:
        if positions is None:
            from api import mt5_pool
            positions = (mt5_pool.get_orders() or {}).get("positions") or []
        crypto = ("BTC", "ETH", "XRP", "LTC", "SOL", "ADA", "DOGE")
        import re as _re
        return any(_re.match(r"^S\d+-", str(p.get("comment") or "")) and not str(p.get("symbol", "")).upper().startswith(crypto)
                   for p in positions)
    except Exception:
        return False


MONTHLY_CATCHUP_DAYS = 7     # recuperare doar in prima saptamana dupa ziua programata


def monthly_due(now: datetime, cfg: dict, st: dict) -> bool:
    h, m = _hm(cfg["monthly_time"])
    if (now.day, now.hour, now.minute) < (cfg["monthly_day"], h, m):
        return False
    # API oprit mult timp / prima pornire la final de luna: NU trimite raportul lunii trecute cu
    # saptamani intarziere (incident 31.10: raportul pe septembrie a plecat pe 31 octombrie)
    if now.day >= cfg["monthly_day"] + MONTHLY_CATCHUP_DAYS:
        return False
    start, _ = monthly_window(now)
    return st.get("monthly_sent") != start.strftime("%Y-%m")

_STRATEGY_LABELS = {"pullback": "Pullback", "inside_bar": "Inside Bar",
                    "flag": "Flag", "smart_news": "Știri"}


def _mt5_ready() -> tuple[bool, str]:
    try:
        from api import mt5_pool
        return mt5_pool.history_status()
    except Exception as e:
        return False, str(e)


def report_ready(kind: str, now: datetime, mono: float | None = None, ready=None) -> bool:
    """Raportul `kind` poate fi generat ACUM? Nu in primele STARTUP_GRACE_S dupa pornirea API-ului si
    nu cat timp istoricul MT5 nu e de incredere — atunci se amana (marcajul de „trimis” NU se scrie,
    se reincearca la minutul urmator). Dupa REPORT_DEFER_MAX_S (sau la sfarsitul zilei pentru zilnic /
    saptamanal, care nu se recupereaza a doua zi) se trimite oricum: raportul spune explicit ca MT5 e
    indisponibil, nu pretinde „nicio tranzactie”."""
    mono = time.monotonic() if mono is None else mono
    if mono - _STARTED < STARTUP_GRACE_S:
        return False
    ok, why = (ready or _mt5_ready)()
    if ok:
        _deferred.pop(kind, None)
        return True
    first = _deferred.setdefault(kind, mono)
    if first == mono:
        log_notification(f"⏳ Raportul {kind} amânat: {why} — reîncerc automat (max {REPORT_DEFER_MAX_S // 3600}h).")
    end_of_day = kind in ("daily", "weekly") and (now.hour, now.minute) >= (23, 55)
    if mono - first >= REPORT_DEFER_MAX_S or end_of_day:
        _deferred.pop(kind, None)
        return True
    return False


def _mt5_trades_between(start: datetime, end: datetime) -> list[dict] | None:
    """Tranzactiile inchise in [start, end) (ora aplicatiei) din MT5. None = MT5 indisponibil
    (inclusiv cont neautentificat / istoric necitit — NU se confunda cu „nicio tranzactie”)."""
    try:
        from api import mt5_pool
        ok, _why = mt5_pool.history_status()
        if not ok:
            return None
        days = max(2, (now_local() - start).days + 2)
        return [t for t in mt5_pool.get_closed_trades(days)
                if t.get("close_time") is not None and start <= t["close_time"] < end]
    except Exception:
        return None


def _send_parts(parts: list[str]) -> str:
    for p in parts:
        telegram.send_message(p)          # send_message logheaza si in tab-ul Notificari
    return "\n\n".join(parts)


def send_period_report(kind: str, now: datetime | None = None, window: tuple[datetime, datetime] | None = None) -> str:
    """Raportul saptamanal / lunar complet (api/reports_builder). Nu ridica — o sursa lipsa
    apare marcata in raport, nu blocheaza trimiterea."""
    from api import reports_builder
    now = now or now_local()
    cfg = load_reports_config()
    start, end = window or (weekly_window(now, cfg) if kind == "weekly" else monthly_window(now))
    if kind == "monthly" and (end > now or end.day != 1 or start.month == now.month and start.year == now.year):
        # garda: un raport lunar acopera DOAR o luna calendaristica INCHEIATA (niciodata luna curenta)
        log_notification(f"⛔ Raportul lunar refuzat: perioada {start:%d.%m.%Y} → {end:%d.%m.%Y} nu e o lună încheiată.")
        return ""
    trades = _mt5_trades_between(start, end)
    parts = reports_builder.build_period_report(kind, start, end, now, trades, with_ai=cfg.get("ai_analysis", True))
    return _send_parts(parts)


def _mt5_trades(date_from: date, date_to: date) -> list[dict] | None:
    """
    Tranzactiile inchise in [date_from, date_to) din istoricul REAL MT5 — sursa
    unica de adevar (nu outcomes.csv). Prinde si tranzactiile plasate de alta
    masina pe acelasi cont. None = MT5 indisponibil.
    """
    try:
        from api import mt5_pool
        ok, _why = mt5_pool.history_status()
        if not ok:
            return None
        days = max(2, (now_local().date() - date_from).days + 2)
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
        lines.append(f"\n⚙️ <b>Custom Engine:</b> {_summary_line(bot)}")
        lines += _grouped(bot, lambda t: labels.get(t.get("session_id"), t["symbol"]))
        by_strat = _grouped(bot, lambda t: _STRATEGY_LABELS.get(t.get("strategy"), "—"))
        if len(by_strat) > 1:
            lines.append("  <i>pe strategie:</i>")
            lines += by_strat

    ai = [t for t in trades if t.get("source") == "ai"]
    if ai:
        lines.append(f"\n🤖 <b>AI Engine:</b> {_summary_line(ai)}")
        lines += _grouped(ai, lambda t: t["symbol"])

    daily = [t for t in trades if t.get("source") == "daily"]
    if daily:
        lines.append(f"\n🕘 <b>Daily Engine:</b> {_summary_line(daily)}")
        lines += _grouped(daily, lambda t: t["symbol"])

    noisy = [t for t in trades if t.get("source") == "noisy"]
    if noisy:
        lines.append(f"\n⚡ <b>Noisy Engine:</b> {_summary_line(noisy)}")

    manual =[t for t in trades if t.get("source") == "manual"]
    if manual:
        lines.append(f"\n✋ <b>Manual:</b> {_summary_line(manual)}")

    return "\n".join(lines)


def send_daily_report(target_date: date | None = None) -> str:
    """Trimite raportul zilnic. target_date = azi (fusul aplicatiei) daca None."""
    if target_date is None:
        target_date = now_local().date()
    trades = _mt5_trades(target_date, target_date + timedelta(days=1))
    label = target_date.strftime("%-d %B %Y") if os.name != "nt" else target_date.strftime("%d %B %Y")
    title = f"📅 Raport Zilnic — {label}"
    text  = _build_report(trades, title)
    telegram.send_message(text)           # logheaza si in Notificari (fara dublura)
    return text


def send_weekly_report(week_start: date | None = None) -> str:
    """Raportul saptamanal complet (fereastra vineri -> vineri). `week_start` ignorat (compat)."""
    return send_period_report("weekly")


def send_monthly_report() -> str:
    return send_period_report("monthly")


def scheduler_tick(now: datetime, *, ready=None, pending=None) -> list[str]:
    """Un pas al programatorului (apelat la 60 s). Intoarce rapoartele trimise acum (pentru teste).
    `ready(kind, now)` / `pending(now)` injectabile in teste; implicit report_ready / friday_close_pending."""
    global _last_daily
    ready = ready or report_ready
    pending = pending or friday_close_pending
    sent = []
    today = now.date()
    cfg = load_reports_config()
    if not cfg.get("enabled_on_this_machine", True):
        return sent
    st = _state()
    dh, dm = _hm(cfg["daily_time"])
    if (cfg.get("daily_enabled", True) and (now.hour, now.minute) >= (dh, dm)
            and (_last_daily is None or _last_daily < today)
            and st.get("daily_sent") != today.isoformat() and ready("daily", now)):
        _last_daily = today
        st["daily_sent"] = today.isoformat()
        _save_state(st)                 # marcaj PERSISTENT inainte de trimitere (restart / 2 API-uri)
        send_daily_report(today)
        sent.append("daily")
    st = _state()
    if weekly_due(now, cfg, st) and ready("weekly", now):
        _, nominal_end = weekly_window(now, cfg)
        if not (pending(now) and now - nominal_end < timedelta(minutes=WEEKLY_SETTLE_MAX_MIN)):
            win = weekly_send_window(now, cfg, st)
            st["weekly_sent"] = nominal_end.date().isoformat()
            st["weekly_last_end"] = win[1].isoformat(timespec="seconds")
            _save_state(st)             # marcaj INAINTE de trimitere: fara dubluri la restart
            send_period_report("weekly", now, window=win)
            sent.append("weekly")
    if monthly_due(now, cfg, st) and ready("monthly", now):
        st["monthly_sent"] = monthly_window(now)[0].strftime("%Y-%m")
        _save_state(st)
        send_period_report("monthly", now)
        sent.append("monthly")
    return sent


def _scheduler_loop() -> None:
    while True:
        try:
            scheduler_tick(now_local())             # fusul aplicatiei, nu ora sistemului
            # Curatare date AI fara trade: luni de la 12:00 (vezi api/data_cleanup.py)
            from api import data_cleanup
            if data_cleanup.due(datetime.now()):
                rep_ = data_cleanup.run_cleanup(apply=True, now=datetime.now(), local_only=True)
                if rep_["ledger"]["councils"] or rep_["ai_filter"]["verdicts"]:
                    text = data_cleanup.summary_text(rep_)
                    telegram.send_message(text)
        except Exception:
            pass  # nu oprim scheduler-ul la erori punctuale
        time.sleep(60)


def start_scheduler() -> None:
    t = threading.Thread(target=_scheduler_loop, name="ScheduledReports", daemon=True)
    t.start()
