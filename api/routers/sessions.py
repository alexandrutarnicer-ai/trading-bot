import os
import json
import ctypes
import threading
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException

from api.config import DATA_DIR, SESSIONS, SESSION_MAP
from api.models import SessionStatus, Signal, Outcome, EquityCurvePoint
from api.telegram import send_message as _tg_send

router = APIRouter(prefix="/sessions", tags=["sessions"])

PAUSED_FILE      = os.path.join(DATA_DIR, "paused_sessions.json")
NEWS_PAUSED_FILE = os.path.join(DATA_DIR, "news_auto_paused.json")


def _notify(text: str) -> None:
    threading.Thread(target=_tg_send, args=(text,), daemon=True).start()


def _load_paused() -> set[str]:
    try:
        if os.path.exists(PAUSED_FILE):
            with open(PAUSED_FILE, encoding="utf-8") as f:
                return set(json.load(f))
    except Exception:
        pass
    return set()


def _load_news_paused() -> dict:
    try:
        if os.path.exists(NEWS_PAUSED_FILE):
            with open(NEWS_PAUSED_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_paused(paused: set[str]) -> None:
    try:
        with open(PAUSED_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(paused), f)
    except Exception:
        pass


def _pid_alive(pid: int) -> bool:
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h:
            exit_code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(h)
            return exit_code.value == STILL_ACTIVE
    except Exception:
        pass
    return False


def _session_dir(session_id: str) -> str:
    return os.path.join(DATA_DIR, "live_signals", session_id)


def _read_pid(path: str) -> Optional[int]:
    try:
        return int(open(path).read().strip())
    except Exception:
        return None


def _session_running(session_id: str) -> tuple[bool, Optional[int]]:
    lock = os.path.join(_session_dir(session_id), "session.lock")
    if not os.path.exists(lock):
        return False, None
    pid = _read_pid(lock)
    if pid and _pid_alive(pid):
        return True, pid
    return False, None


def _read_signals(session_id: str) -> pd.DataFrame:
    f = os.path.join(_session_dir(session_id), "signals.csv")
    if not os.path.exists(f):
        return pd.DataFrame()
    try:
        return pd.read_csv(f)
    except Exception:
        return pd.DataFrame()


def _read_outcomes(session_id: str) -> pd.DataFrame:
    f = os.path.join(_session_dir(session_id), "outcomes.csv")
    if not os.path.exists(f):
        return pd.DataFrame()
    try:
        return pd.read_csv(f)
    except Exception:
        return pd.DataFrame()


def _sig_stats(session_id: str) -> dict:
    df = _read_signals(session_id)
    if df.empty:
        return {"today": 0, "yesterday": 0, "total": 0, "last_time": None}
    today     = str(date.today())
    yesterday = str(date.today() - timedelta(days=1))
    times = df["time"].astype(str)
    last_time = None
    if len(df):
        last = times.iloc[-1]
        last_time = last[11:16] if len(last) >= 16 else last
    return {
        "today":     int(times.str.startswith(today).sum()),
        "yesterday": int(times.str.startswith(yesterday).sum()),
        "total":     len(df),
        "last_time": last_time,
    }


def _outcome_stats(session_id: str) -> dict:
    df = _read_outcomes(session_id)
    if df.empty:
        return {"total": 0, "wins": 0, "losses": 0, "today": 0, "yesterday": 0}
    closed = df[df["status"].isin(["TP", "SL"])]
    today     = str(date.today())
    yesterday = str(date.today() - timedelta(days=1))
    if "exit_time" in closed.columns and len(closed):
        et = closed["exit_time"].astype(str)
        today_out     = int(et.str.startswith(today).sum())
        yesterday_out = int(et.str.startswith(yesterday).sum())
    else:
        today_out = yesterday_out = 0
    wins   = int((closed["result_r"] > 0).sum()) if len(closed) else 0
    losses = int((closed["result_r"] < 0).sum()) if len(closed) else 0
    return {
        "total":     len(closed),
        "wins":      wins,
        "losses":    losses,
        "today":     today_out,
        "yesterday": yesterday_out,
    }


@router.get("", response_model=list[SessionStatus])
def list_sessions():
    paused      = _load_paused()
    news_paused = _load_news_paused()
    result = []
    for s in SESSIONS:
        running, pid = _session_running(s["id"])
        sig  = _sig_stats(s["id"])
        out  = _outcome_stats(s["id"])
        np_entry  = news_paused.get(s["id"], {})
        result.append(SessionStatus(
            id=s["id"],
            label=s["label"],
            markets=s["markets"],
            direction=s["direction"],
            tf=s["tf"],
            hours=s["hours"],
            validated=s["validated"],
            execute=s["execute"],
            capital_pct=s["capital_pct"],
            running=running,
            pid=pid,
            signals_today=sig["today"],
            signals_yesterday=sig["yesterday"],
            signals_total=sig["total"],
            last_signal_time=sig["last_time"],
            outcomes_total=out["total"],
            outcomes_today=out["today"],
            outcomes_yesterday=out["yesterday"],
            wins=out["wins"],
            losses=out["losses"],
            paused=s["id"] in paused,
            news_paused=bool(np_entry),
            news_events=np_entry.get("events", []),
        ))
    return result


@router.post("/{session_id}/pause")
def pause_session(session_id: str):
    if session_id not in SESSION_MAP:
        raise HTTPException(404, f"Sesiune necunoscuta: {session_id}")
    paused = _load_paused()
    paused.add(session_id)
    _save_paused(paused)
    label = SESSION_MAP[session_id].get("label", session_id)
    _notify(
        f"⏸ <b>Sesiune pe pauză</b> — {label}\n"
        f"Oprită manual din Dashboard la {datetime.now().strftime('%H:%M')}.\n"
        f"Semnale noi suspendate. Pozițiile deschise continuă să fie monitorizate."
    )
    return {"ok": True, "session_id": session_id, "paused": True}


@router.post("/{session_id}/resume")
def resume_session(session_id: str):
    if session_id not in SESSION_MAP:
        raise HTTPException(404, f"Sesiune necunoscuta: {session_id}")
    paused = _load_paused()
    paused.discard(session_id)
    _save_paused(paused)
    label = SESSION_MAP[session_id].get("label", session_id)
    _notify(
        f"▶️ <b>Sesiune reluată</b> — {label}\n"
        f"Repornită manual din Dashboard la {datetime.now().strftime('%H:%M')}."
    )
    return {"ok": True, "session_id": session_id, "paused": False}


@router.get("/{session_id}/signals", response_model=list[Signal])
def get_signals(session_id: str, limit: int = 50):
    if session_id not in SESSION_MAP:
        raise HTTPException(404, f"Sesiune necunoscuta: {session_id}")
    df = _read_signals(session_id)
    if df.empty:
        return []
    df = df.tail(limit).iloc[::-1]
    result = []
    for _, row in df.iterrows():
        result.append(Signal(
            signal_id=str(row.get("signal_id", "")),
            time=str(row.get("time", "")),
            symbol=str(row.get("symbol", "")),
            direction=int(row.get("direction", 0)),
            dir_str=str(row.get("dir_str", "")),
            entry=float(row.get("entry", 0)),
            sl=float(row.get("sl", 0)),
            tp=float(row.get("tp", 0)),
            r_ratio=float(row.get("r_ratio", 0)),
        ))
    return result


@router.get("/{session_id}/outcomes", response_model=list[Outcome])
def get_outcomes(session_id: str, limit: int = 100):
    if session_id not in SESSION_MAP:
        raise HTTPException(404, f"Sesiune necunoscuta: {session_id}")
    df = _read_outcomes(session_id)
    if df.empty:
        return []
    df = df.tail(limit).iloc[::-1]
    result = []
    for _, row in df.iterrows():
        result.append(Outcome(
            signal_id=str(row.get("signal_id", "")),
            time_check=str(row.get("time_check", "")),
            symbol=str(row.get("symbol", "")),
            direction=int(row.get("direction", 0)),
            status=str(row.get("status", "")),
            entry=float(row.get("entry", 0)),
            sl=float(row.get("sl", 0)),
            tp=float(row.get("tp", 0)),
            r_ratio=float(row.get("r_ratio", 0)),
            triggered_at=str(row["triggered_at"]) if pd.notna(row.get("triggered_at")) else None,
            exit_price=float(row["exit_price"]) if pd.notna(row.get("exit_price")) else None,
            exit_time=str(row["exit_time"]) if pd.notna(row.get("exit_time")) else None,
            result_r=float(row.get("result_r", 0)),
        ))
    return result


@router.get("/all/equity-curve", response_model=list[EquityCurvePoint])
def equity_curve():
    """R cumulat per sesiune, sortat cronologic — pentru graficul de performanta."""
    points = []
    for s in SESSIONS:
        df = _read_outcomes(s["id"])
        if df.empty:
            continue
        closed = df[df["status"].isin(["TP", "SL"])].copy()
        if closed.empty:
            continue
        closed["exit_time"] = pd.to_datetime(closed["exit_time"], errors="coerce")
        closed = closed.dropna(subset=["exit_time"]).sort_values("exit_time")
        closed["cum_r"] = closed["result_r"].cumsum()
        for _, row in closed.iterrows():
            points.append(EquityCurvePoint(
                date=row["exit_time"].strftime("%Y-%m-%d %H:%M"),
                cumulative_r=round(float(row["cum_r"]), 3),
                session_id=s["id"],
            ))
    points.sort(key=lambda p: p.date)
    return points
