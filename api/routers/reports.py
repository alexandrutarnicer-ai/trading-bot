"""
Reports router — uptime bot, istoricul modificarilor, system logs, rapoarte Telegram.

Tranzactiile / pietele / costurile NU mai sunt calculate aici din outcomes.csv:
sursa unica pentru datele de trading e MT5 (/mt5/transactions, /mt5/top-markets,
/mt5/costs, /mt5/costs-daily).
"""

import json
import os
import re
from collections import deque
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.config import DATA_DIR

router = APIRouter(prefix="/reports", tags=["reports"])

UPTIME_LOG_FILE   = os.path.join(DATA_DIR, "bot_uptime_log.json")
CHANGES_LOG_FILE  = os.path.join(DATA_DIR, "session_changes_log.json")

@router.get("/uptime")
def get_uptime():
    """Istoricul pornirilor/opririlor botului."""
    try:
        if not os.path.exists(UPTIME_LOG_FILE):
            return {"items": []}
        with open(UPTIME_LOG_FILE, encoding="utf-8") as f:
            items = json.load(f)
        # Cele mai recente primele
        items = list(reversed(items))
        return {"items": items[:100]}
    except Exception:
        return {"items": []}


@router.get("/audit-log")
def get_audit_log(limit: int = 300, engine: Optional[str] = None):
    """Jurnalul de audit al engine-urilor (Daily / Special): moduri Live / Shadow / Pauza, configurare,
    pornire / oprire, ordine blocate. Cele mai noi primele."""
    from api import audit_log
    return {"items": audit_log.read(limit, engine)}


@router.get("/session-changes")
def get_session_changes():
    """Istoricul modificarilor de profil/sesiune."""
    try:
        if not os.path.exists(CHANGES_LOG_FILE):
            return {"items": []}
        with open(CHANGES_LOG_FILE, encoding="utf-8") as f:
            items = json.load(f)
        items = list(reversed(items))
        return {"items": items[:200]}
    except Exception:
        return {"items": []}


# Format log: "2026-06-30 09:29:45  mesaj" sau cu prefix level
_LOG_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s{1,4}(.+)$"
)
_LEVEL_RE = re.compile(r"\b(ERROR|WARNING|CRITICAL)\b", re.IGNORECASE)


def _classify_level(msg: str) -> str:
    m = _LEVEL_RE.search(msg)
    if m:
        return m.group(1).upper()
    lower = msg.lower()
    if any(w in lower for w in ["error", "esuata", "esuata", "eroare", "critical", "traceback", "exception"]):
        return "ERROR"
    if any(w in lower for w in ["warning", "warn", "orfan", "orphan", "corupt", "migrare", "reconcil", "netrackuit"]):
        return "WARNING"
    return "INFO"


def _tail_lines(path: str, n: int) -> list[str]:
    """Citeste ultimele n linii dintr-un fisier fara a-l incarca complet in memorie."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return list(deque(f, maxlen=n))
    except Exception:
        return []


def _discover_log_sessions() -> list[str]:
    """Descopera dinamic sesiunile care au generator.log pe disk."""
    base = os.path.join(DATA_DIR, "live_signals")
    if not os.path.isdir(base):
        return []
    result = []
    for name in sorted(os.listdir(base)):
        log_path = os.path.join(base, name, "generator.log")
        if os.path.isfile(log_path):
            result.append(name)
    return result


@router.get("/system-logs/sessions")
def get_log_sessions():
    """Lista sesiunilor care au generator.log disponibil."""
    return {"sessions": _discover_log_sessions()}


@router.get("/system-logs")
def get_system_logs(
    session: str = Query("all", description="session_id sau 'all'"),
    level: str = Query("all", description="INFO / WARNING / ERROR / all"),
    lines_per_session: int = Query(200, ge=10, le=2000),
):
    """
    Ultimele N linii din generator.log per sesiune, parsate si clasificate.
    Sesiunile sunt descoperite dinamic de pe disk — sesiunile noi apar automat.
    Returneaza lista de intrari {time, session, level, message} sortate DESC.
    """
    all_sessions = _discover_log_sessions()
    if session == "all":
        target_sessions = [{"session_id": s} for s in all_sessions]
    else:
        target_sessions = [{"session_id": session}] if session in all_sessions or session else []

    entries = []
    for s in target_sessions:
        sid = s["session_id"]
        log_path = os.path.join(DATA_DIR, "live_signals", sid, "generator.log")
        raw_lines = _tail_lines(log_path, lines_per_session)

        current_time = None
        current_msg_parts: list[str] = []

        def _flush():
            nonlocal current_time, current_msg_parts
            if current_time and current_msg_parts:
                msg = " ".join(current_msg_parts).strip()
                lvl = _classify_level(msg)
                entries.append({
                    "time":    current_time,
                    "session": sid,
                    "level":   lvl,
                    "message": msg,
                })
            current_time = None
            current_msg_parts = []

        for raw in raw_lines:
            raw = raw.rstrip("\n")
            m = _LOG_RE.match(raw)
            if m:
                _flush()
                current_time = m.group(1)
                current_msg_parts = [m.group(2)]
            else:
                # Continuare linie (ex: traceback)
                if current_time:
                    current_msg_parts.append(raw.strip())
        _flush()

    # Filtru nivel
    level_up = level.upper()
    if level_up != "ALL":
        _order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
        _min = _order.get(level_up, 2)
        entries = [e for e in entries if _order.get(e["level"], 2) <= _min]

    # Sortat descrescator (cele mai noi primele)
    entries.sort(key=lambda e: e["time"], reverse=True)

    # Max 500 intrari total
    return {
        "items": entries[:500],
        "total": len(entries),
    }


@router.post("/send-daily")
def trigger_daily_report(target_date: Optional[str] = None):
    """
    Trimite manual raportul zilnic via Telegram + Notificari.
    target_date: YYYY-MM-DD (default: azi)
    """
    from api.scheduled_reports import send_daily_report
    d = date.fromisoformat(target_date) if target_date else date.today()
    text = send_daily_report(d)
    return {"sent": True, "date": str(d), "preview": text[:200]}


@router.post("/send-weekly")
def trigger_weekly_report():
    """Trimite ACUM raportul saptamanal complet (fereastra: vinerea trecuta la ora raportului ->
    cea mai recenta vineri la ora raportului). Trimiterea automata ramane doar vineri."""
    from api.scheduled_reports import send_period_report
    text = send_period_report("weekly")
    return {"sent": True, "preview": text[:300]}


@router.post("/send-monthly")
def trigger_monthly_report():
    """Trimite ACUM raportul lunar al lunii calendaristice precedente (complete)."""
    from api.scheduled_reports import send_period_report
    text = send_period_report("monthly")
    return {"sent": True, "preview": text[:300]}


@router.get("/config")
def reports_config():
    from api.scheduled_reports import load_reports_config, weekly_window, monthly_window
    from tz_helper import now_local, get_configured_tz_name
    cfg = load_reports_config()
    now = now_local()
    ws, we = weekly_window(now, cfg)
    ms, me = monthly_window(now)
    return {**cfg, "timezone": get_configured_tz_name(),
            "last_weekly_window": [ws.isoformat(), we.isoformat()],
            "last_monthly_window": [ms.isoformat(), me.isoformat()]}


@router.put("/config")
def reports_config_save(body: dict):
    from api.scheduled_reports import save_reports_config
    try:
        return save_reports_config(body)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))


@router.post("/ai-data-cleanup")
def ai_data_cleanup(apply: bool = False):
    """Curatarea datelor AI fara trade (> 28 zile): implicit DRY-RUN (doar raport).
    Ruleaza automat luni de la 12:00 din scheduler. Vezi api/data_cleanup.py."""
    from api import data_cleanup
    return data_cleanup.run_cleanup(apply=apply)
