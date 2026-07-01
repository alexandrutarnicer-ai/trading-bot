"""
Reports router — tranzactii, statistici piete, uptime bot, istoricul modificarilor, system logs.
"""

import json
import os
import re
from collections import deque
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Query

from api.config import DATA_DIR, SESSIONS, get_profile_execute_map

router = APIRouter(prefix="/reports", tags=["reports"])

UPTIME_LOG_FILE   = os.path.join(DATA_DIR, "bot_uptime_log.json")
CHANGES_LOG_FILE  = os.path.join(DATA_DIR, "session_changes_log.json")

_CLOSED_STATUSES = ["TP", "SL", "vineri_close", "news_close", "be_lock", "be_lock2"]


def _read_outcomes(session_id: str) -> pd.DataFrame:
    f = os.path.join(DATA_DIR, "live_signals", session_id, "outcomes.csv")
    if not os.path.exists(f):
        return pd.DataFrame()
    try:
        return pd.read_csv(f, on_bad_lines="skip")
    except Exception:
        return pd.DataFrame()


def _session_label(session_id: str) -> str:
    for s in SESSIONS:
        if s["id"] == session_id:
            return s["label"]
    return session_id


def _discover_outcome_sessions(live_only: bool = True) -> list[dict]:
    """
    Descopera dinamic sesiunile cu outcomes.csv pe disk.
    Merge cu lista statica SESSIONS pentru metadata (label, markets).
    Cand live_only=True (default), exclude sesiunile OBS (execute_trades=False din profil activ).
    """
    base = os.path.join(DATA_DIR, "live_signals")
    static_map = {s["id"]: s for s in SESSIONS}
    execute_map = get_profile_execute_map() if live_only else {}
    result: list[dict] = []
    seen: set[str] = set()

    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            outcomes_path = os.path.join(base, name, "outcomes.csv")
            if os.path.isfile(outcomes_path):
                sess = static_map.get(name, {"id": name, "label": name, "markets": [], "execute": True})
                if live_only and not execute_map.get(name, sess.get("execute", True)):
                    # Sesiunea e marcata OBS in profil — dar daca are pnl_usd real (MT5 e legea),
                    # o includem in rapoarte. Exclude doar sesiunile cu 0 tranzactii reale.
                    try:
                        _df = pd.read_csv(outcomes_path, usecols=["pnl_usd"])
                        _pnl_ser = pd.to_numeric(_df["pnl_usd"], errors="coerce").dropna()
                        # pnl=0.0 apare la expirat/invalidat — nu e trade real MT5
                        _has_real = bool((_pnl_ser != 0).any())
                    except Exception:
                        _has_real = False
                    if not _has_real:
                        continue
                result.append(sess)
                seen.add(name)

    # Include sesiunile statice fara outcomes (pentru consistenta, doar live)
    for s in SESSIONS:
        if s["id"] not in seen:
            if live_only and not execute_map.get(s["id"], s["execute"]):
                continue
            result.append(s)

    return result


def _discover_obs_sessions() -> list[dict]:
    """Returneaza doar sesiunile OBS (execute_trades=False) cu outcomes.csv."""
    base = os.path.join(DATA_DIR, "live_signals")
    static_map = {s["id"]: s for s in SESSIONS}
    execute_map = get_profile_execute_map()
    result: list[dict] = []
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            if os.path.isfile(os.path.join(base, name, "outcomes.csv")):
                sess = static_map.get(name, {"id": name, "label": name, "markets": [], "execute": True})
                if not execute_map.get(name, sess.get("execute", True)):
                    result.append(sess)
    return result


@router.get("/transactions")
def get_transactions(
    status:    Optional[str] = Query(None, description="TP,SL,open,vineri_close,news_close"),
    symbol:    Optional[str] = Query(None),
    direction: Optional[str] = Query(None, description="LONG,SHORT"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to:   Optional[str] = Query(None, description="YYYY-MM-DD"),
    session_id: Optional[str] = Query(None),
    obs_only:  bool = Query(False, description="Returneaza doar sesiunile OBS (execute=False)"),
    limit:     int = Query(200, le=1000),
    offset:    int = Query(0),
):
    """Tranzactiile sesiunilor live (sau OBS cand obs_only=True). Descopera dinamic sesiunile."""
    all_sessions = _discover_obs_sessions() if obs_only else _discover_outcome_sessions()
    rows = []
    sessions_to_check = (
        [s for s in all_sessions if s["id"] == session_id]
        if session_id else all_sessions
    )
    for s in sessions_to_check:
        df = _read_outcomes(s["id"])
        if df.empty:
            continue
        df["session_id"]    = s["id"]
        df["session_label"] = s["label"]
        rows.append(df)

    if not rows:
        return {"items": [], "total": 0}

    all_df = pd.concat(rows, ignore_index=True)

    # Filtre
    if status:
        statuses = [x.strip() for x in status.split(",")]
        all_df = all_df[all_df["status"].isin(statuses)]
    if symbol:
        all_df = all_df[all_df["symbol"].str.upper() == symbol.upper()]
    if direction:
        dir_val = 1 if direction.upper() == "LONG" else -1
        all_df = all_df[all_df["direction"] == dir_val]
    if date_from or date_to:
        et = pd.to_datetime(all_df.get("exit_time", pd.Series(dtype=str)), errors="coerce")
        tc = pd.to_datetime(all_df.get("time_check", pd.Series(dtype=str)), errors="coerce")
        ts = et.fillna(tc)
        if date_from:
            all_df = all_df[ts >= pd.Timestamp(date_from)]
        if date_to:
            all_df = all_df[ts <= pd.Timestamp(date_to) + pd.Timedelta(days=1)]

    # Sorteaza dupa timp descrescator (cele mai noi primele)
    sort_col = "exit_time" if "exit_time" in all_df.columns else "time_check"
    try:
        all_df["_sort"] = pd.to_datetime(all_df[sort_col], errors="coerce")
        all_df = all_df.sort_values("_sort", ascending=False, na_position="last")
    except Exception:
        pass

    total = len(all_df)
    page  = all_df.iloc[offset: offset + limit]

    items = []
    for _, row in page.iterrows():
        items.append({
            "signal_id":     str(row.get("signal_id", "")),
            "session_id":    str(row.get("session_id", "")),
            "session_label": str(row.get("session_label", "")),
            "time_check":    str(row.get("time_check", "")),
            "symbol":        str(row.get("symbol", "")),
            "direction":     int(row.get("direction", 0)),
            "dir_str":       "LONG" if int(row.get("direction", 0)) == 1 else "SHORT",
            "status":        str(row.get("status", "")),
            "entry":         float(row.get("entry", 0)),
            "sl":            float(row.get("sl", 0)),
            "tp":            float(row.get("tp", 0)),
            "r_ratio":       float(row.get("r_ratio", 0)),
            "triggered_at":  str(row["triggered_at"]) if pd.notna(row.get("triggered_at")) else None,
            "exit_price":    float(row["exit_price"]) if pd.notna(row.get("exit_price")) else None,
            "exit_time":     str(row["exit_time"]) if pd.notna(row.get("exit_time")) else None,
            "result_r":      float(row.get("result_r", 0)),
            "pnl_usd":       float(row["pnl_usd"]) if pd.notna(row.get("pnl_usd")) else None,
        })
    return {"items": items, "total": total}


@router.get("/market-stats")
def get_market_stats():
    """Statistici agregate per piata (simbol) din toate sesiunile. Descopera dinamic sesiunile noi."""
    market_stats: dict[str, dict] = {}

    for s in _discover_outcome_sessions():
        df = _read_outcomes(s["id"])
        if df.empty:
            continue
        closed = df[df["status"].isin(_CLOSED_STATUSES)].copy()
        if closed.empty:
            continue
        for sym, grp in closed.groupby("symbol"):
            sym = str(sym)
            if sym not in market_stats:
                market_stats[sym] = {
                    "symbol":     sym,
                    "trades":     0,
                    "wins":       0,
                    "losses":     0,
                    "total_r":    0.0,
                    "pnl_usd":    None,
                    "sessions":   [],
                }
            st = market_stats[sym]
            st["trades"]  += len(grp)
            st["wins"]    += int((grp["result_r"] > 0).sum())
            st["losses"]  += int((grp["result_r"] < 0).sum())
            st["total_r"] += float(grp["result_r"].fillna(0).sum())
            if s["label"] not in st["sessions"]:
                st["sessions"].append(s["label"])
            if "pnl_usd" in grp.columns:
                pnl_vals = pd.to_numeric(grp["pnl_usd"], errors="coerce").dropna()
                if len(pnl_vals):
                    st["pnl_usd"] = round((st["pnl_usd"] or 0) + float(pnl_vals.sum()), 2)

    results = []
    for st in market_stats.values():
        n = st["trades"]
        st["win_rate"]   = round(st["wins"] / n * 100, 1) if n else 0.0
        st["expectancy"] = round(st["total_r"] / n, 3) if n else 0.0
        st["total_r"]    = round(st["total_r"], 3)
        results.append(st)

    results.sort(key=lambda x: x["total_r"], reverse=True)
    return {"items": results}


@router.get("/costs")
def get_costs():
    """Comisioane si swap agregate per piata (simbol) din toate sesiunile.
    Returneaza doar randurile care au date reale MT5 (commission_usd sau swap_usd nenule)."""
    cost_stats: dict[str, dict] = {}

    for s in _discover_outcome_sessions():
        df = _read_outcomes(s["id"])
        if df.empty:
            continue
        closed = df[df["status"].isin(_CLOSED_STATUSES)].copy()
        if closed.empty:
            continue
        # Coloane optionale — prezente doar in outcomes cu date MT5 reale
        if "commission_usd" not in closed.columns:
            closed["commission_usd"] = float("nan")
        if "swap_usd" not in closed.columns:
            closed["swap_usd"] = float("nan")
        for sym, grp in closed.groupby("symbol"):
            sym = str(sym)
            if sym not in cost_stats:
                cost_stats[sym] = {
                    "symbol":         sym,
                    "trades":         0,
                    "trades_with_mt5": 0,
                    "commission_usd": 0.0,
                    "swap_usd":       0.0,
                    "pnl_gross":      0.0,
                    "pnl_net":        None,
                    "sessions":       [],
                }
            st = cost_stats[sym]
            st["trades"] += len(grp)
            if s["label"] not in st["sessions"]:
                st["sessions"].append(s["label"])
            # Calculeaza comisioane si swap unde exista date MT5
            comm_vals = pd.to_numeric(grp["commission_usd"], errors="coerce").dropna()
            swap_vals = pd.to_numeric(grp["swap_usd"],       errors="coerce").dropna()
            pnl_vals  = pd.to_numeric(grp.get("pnl_usd", pd.Series(dtype=float)), errors="coerce").dropna()
            st["commission_usd"] = round(st["commission_usd"] + float(comm_vals.sum()), 4)
            st["swap_usd"]       = round(st["swap_usd"]       + float(swap_vals.sum()), 4)
            if len(pnl_vals):
                st["pnl_gross"]  = round(st["pnl_gross"] + float(pnl_vals.sum()), 4)
                st["trades_with_mt5"] += len(pnl_vals)

    results = []
    for st in cost_stats.values():
        has_cost_data = st["commission_usd"] != 0.0 or st["swap_usd"] != 0.0
        total_costs = round(st["commission_usd"] + st["swap_usd"], 4)
        pnl_net = round(st["pnl_gross"] + total_costs, 4) if st["trades_with_mt5"] else None
        results.append({
            **st,
            "total_costs": total_costs,
            "pnl_net":     pnl_net,
            "has_cost_data": has_cost_data,
        })

    results.sort(key=lambda x: x["total_costs"])  # cel mai scump primul (total_costs negativ)
    return {"items": results}


@router.get("/costs-daily")
def get_costs_daily():
    """Comisioane + swap grupate per zi calendaristica. Include toate zilele cu tranzactii inchise."""
    frames = []
    for s in _discover_outcome_sessions():
        df = _read_outcomes(s["id"])
        if df.empty:
            continue
        closed = df[df["status"].isin(_CLOSED_STATUSES)].copy()
        if closed.empty:
            continue
        if "commission_usd" not in closed.columns:
            closed["commission_usd"] = float("nan")
        if "swap_usd" not in closed.columns:
            closed["swap_usd"] = float("nan")
        frames.append(closed)

    if not frames:
        return {"items": [], "total_commission": 0.0, "total_swap": 0.0}

    all_df = pd.concat(frames, ignore_index=True)
    all_df["exit_dt"] = pd.to_datetime(all_df["exit_time"], errors="coerce")
    all_df["day"] = all_df["exit_dt"].dt.date
    all_df["comm_n"] = pd.to_numeric(all_df["commission_usd"], errors="coerce")
    all_df["swap_n"]  = pd.to_numeric(all_df["swap_usd"],      errors="coerce")
    all_df["pnl_n"]   = pd.to_numeric(all_df.get("pnl_usd", float("nan")), errors="coerce")
    all_df["rr_n"]    = pd.to_numeric(all_df["result_r"],      errors="coerce")

    items = []
    for day, grp in all_df.groupby("day"):
        comm_vals = grp["comm_n"].dropna()
        swap_vals = grp["swap_n"].dropna()
        pnl_vals  = grp["pnl_n"].dropna()
        rr_vals   = grp["rr_n"].dropna()
        comm = round(float(comm_vals.sum()), 4) if len(comm_vals) else 0.0
        swap = round(float(swap_vals.sum()), 4) if len(swap_vals) else 0.0
        pnl  = round(float(pnl_vals.sum()), 4)  if len(pnl_vals)  else None
        rr   = round(float(rr_vals.sum()), 3)   if len(rr_vals)   else None
        items.append({
            "date":          str(day),
            "trades":        int(len(grp)),
            "trades_with_cost": int(len(comm_vals)),
            "commission_usd": comm,
            "swap_usd":       swap,
            "total_costs":    round(comm + swap, 4),
            "pnl_usd":        pnl,
            "total_r":        rr,
            "has_cost_data":  len(comm_vals) > 0 or len(swap_vals) > 0,
        })

    items.sort(key=lambda x: x["date"])
    total_comm = round(sum(x["commission_usd"] for x in items), 4)
    total_swap = round(sum(x["swap_usd"] for x in items), 4)
    return {
        "items": items,
        "total_commission": total_comm,
        "total_swap": total_swap,
        "total_costs": round(total_comm + total_swap, 4),
    }


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
def trigger_weekly_report(week_start: Optional[str] = None):
    """
    Trimite manual raportul saptamanal via Telegram + Notificari.
    week_start: YYYY-MM-DD (default: luni din saptamana curenta)
    """
    from api.scheduled_reports import send_weekly_report
    today = date.today()
    ws = date.fromisoformat(week_start) if week_start else today - timedelta(days=today.weekday())
    text = send_weekly_report(ws)
    return {"sent": True, "week_start": str(ws), "preview": text[:200]}
