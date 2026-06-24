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
        return pd.read_csv(f, on_bad_lines="skip")
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


_CLOSED_STATUSES = ["TP", "SL", "vineri_close", "news_close"]


def _outcome_stats(session_id: str) -> dict:
    df = _read_outcomes(session_id)
    if df.empty:
        return {"total": 0, "wins": 0, "losses": 0, "today": 0, "yesterday": 0}
    closed = df[df["status"].isin(_CLOSED_STATUSES)]
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


@router.get("/weekly_stats")
def weekly_stats():
    """Statistici agregate pentru saptamana curenta vs precedenta (toate sesiunile)."""
    now       = datetime.now()
    # Inceputul saptamanii curente (luni la 00:00)
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)
    prev_start = week_start - timedelta(weeks=1)

    def _aggregate(start: datetime, end: datetime) -> dict:
        totals = {"trades": 0, "wins": 0, "losses": 0, "total_r": 0.0}
        all_slices: list[pd.DataFrame] = []
        for s in SESSIONS:
            df = _read_outcomes(s["id"])
            if df.empty or "exit_time" not in df.columns:
                continue
            closed = df[df["status"].isin(_CLOSED_STATUSES)].copy()
            if closed.empty:
                continue
            closed["_et"] = pd.to_datetime(closed["exit_time"], errors="coerce")
            mask = (closed["_et"] >= start) & (closed["_et"] < end)
            sub  = closed[mask]
            if sub.empty:
                continue
            totals["trades"] += len(sub)
            totals["wins"]   += int((sub["result_r"] > 0).sum())
            totals["losses"] += int((sub["result_r"] < 0).sum())
            totals["total_r"] += float(sub["result_r"].fillna(0).sum())
            all_slices.append(sub[["_et", "result_r"]].copy())
        n = totals["trades"]
        totals["total_r"]  = round(totals["total_r"], 3)
        totals["win_rate"] = round(totals["wins"] / n * 100, 1) if n else 0.0
        # Drawdown maxim in R pentru perioada (cel mai adanc jgheab de la peak)
        max_dd_r = 0.0
        if all_slices:
            combined = pd.concat(all_slices).sort_values("_et")
            cum_r = combined["result_r"].fillna(0).cumsum()
            peak  = cum_r.cummax()
            dd    = cum_r - peak
            max_dd_r = round(float(dd.min()), 3)
        totals["max_dd_r"] = max_dd_r
        return totals

    return {
        "current_week": {
            "start": week_start.date().isoformat(),
            "end":   now.date().isoformat(),
            **_aggregate(week_start, now + timedelta(days=1)),
        },
        "previous_week": {
            "start": prev_start.date().isoformat(),
            "end":   (week_start - timedelta(days=1)).date().isoformat(),
            **_aggregate(prev_start, week_start),
        },
    }


_BACKTEST_JOBS_FILE = os.path.join(DATA_DIR, "backtest_jobs.json")
_ACTIVE_PROFILE_FILE = os.path.join(DATA_DIR, "active_profile.json")
_PROFILES_DIR = os.path.join(DATA_DIR, "profiles")


@router.get("/frequency-estimate")
def frequency_estimate(profile_id: str = ""):
    """
    Calculeaza frecventa estimata trades/saptamana si trades/luna
    din cele mai recente backtest-uri finalizate ale sesiunilor active.
    Sesiunile pe pauza sunt excluse.
    """
    # Determina profile_id activ
    if not profile_id:
        try:
            if os.path.exists(_ACTIVE_PROFILE_FILE):
                profile_id = json.load(open(_ACTIVE_PROFILE_FILE, encoding="utf-8")).get("id", "")
        except Exception:
            pass
    if not profile_id:
        profile_id = "standard"

    # Incarca profilul
    pfile = os.path.join(_PROFILES_DIR, f"{profile_id}.json")
    if not os.path.exists(pfile):
        return {"per_week": None, "per_month": None}
    try:
        profile = json.load(open(pfile, encoding="utf-8"))
    except Exception:
        return {"per_week": None, "per_month": None}

    paused = _load_paused()

    # Incarca jobs finalizate, sortate descrescator (cele mai noi primele)
    jobs_done: list[dict] = []
    try:
        all_jobs = json.load(open(_BACKTEST_JOBS_FILE, encoding="utf-8"))
        jobs_done = [j for j in reversed(all_jobs) if j.get("status") == "done"]
    except Exception:
        pass

    # Index: session_id (ex: "S2") -> cel mai recent job done
    latest_job: dict[str, dict] = {}
    for j in jobs_done:
        sid = j.get("session_id", "")
        if sid and sid not in latest_job:
            latest_job[sid] = j

    total_per_week = 0.0
    has_any = False
    missing: list[dict] = []   # sesiuni fara backtest

    for ps in profile.get("sessions", []):
        sess_key = ps.get("session_key", "")
        sess_id  = ps.get("id", "")           # ex: "S2"
        markets  = ps.get("markets", [])

        # Sesiunile pe pauza sau non-live (execute_trades=False) nu contribuie si nu apar ca "lipsa"
        if sess_key in paused:
            continue
        if not ps.get("execute_trades", True):
            continue

        job = latest_job.get(sess_id)
        if not job:
            missing.append({"id": sess_id, "markets": markets})
            continue

        r = job.get("results") or {}
        total_trades = r.get("total_trades")
        date_from    = r.get("date_from")
        date_to      = r.get("date_to")

        if not total_trades or not date_from or not date_to:
            missing.append({"id": sess_id, "markets": markets})
            continue

        try:
            d_from = datetime.strptime(date_from, "%Y-%m-%d")
            d_to   = datetime.strptime(date_to,   "%Y-%m-%d")
            days   = (d_to - d_from).days
            if days <= 0:
                missing.append({"id": sess_id, "markets": markets})
                continue
            total_per_week += total_trades / (days / 7)
            has_any = True
        except Exception:
            missing.append({"id": sess_id, "markets": markets})
            continue

    return {
        "per_week":  round(total_per_week, 1) if has_any else None,
        "per_month": round(total_per_week * (30.44 / 7), 0) if has_any else None,
        "missing":   missing,
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
            pnl_usd=float(row["pnl_usd"]) if pd.notna(row.get("pnl_usd")) else None,
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
        closed = df[df["status"].isin(_CLOSED_STATUSES)].copy()
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
