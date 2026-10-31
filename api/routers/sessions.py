import os
import json
import ctypes
import threading
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException

from api.config import DATA_DIR, SESSIONS, SESSION_MAP, get_profile_execute_map
from api.models import SessionStatus, Signal
from api.telegram import send_message as _tg_send
from api.csv_cache import read_csv_cached

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
    # Cache pe (mtime, size) — vezi api/csv_cache.py. NU muta frame-ul returnat in loc.
    return read_csv_cached(os.path.join(_session_dir(session_id), "signals.csv"))


def _read_outcomes(session_id: str) -> pd.DataFrame:
    return read_csv_cached(
        os.path.join(_session_dir(session_id), "outcomes.csv"), on_bad_lines="skip")


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


def _signal_status_map(session_id: str) -> dict[str, str]:
    """
    sig_id -> status din jurnalul de outcomes al Bot Engine (ai_reject, expirat,
    invalidat, TP, SL...). Doar eticheta de stare a semnalului — rezultatele in
    R/USD vin exclusiv din MT5 (/mt5/transactions), nu din acest jurnal.
    """
    df = _read_outcomes(session_id)
    if df.empty or "signal_id" not in df.columns or "status" not in df.columns:
        return {}
    return dict(zip(df["signal_id"].astype(str), df["status"].astype(str)))


_BACKTEST_JOBS_FILE = os.path.join(DATA_DIR, "backtest_jobs.json")
_ACTIVE_PROFILE_FILE = os.path.join(DATA_DIR, "active_profile.json")
_PROFILES_DIR = os.path.join(DATA_DIR, "profiles")


@router.get("/m0-verdicts")
def m0_verdicts():
    """
    Verdictele M0 (KEEP/OBSERVE/DEMOTE/INSUFF) per sesiune din data/m0_audit.csv
    (scris de `python -m m0.audit`). Read-only. Folosit de UI ca gate vizual:
    o sesiune DEMOTE pe executie LIVE e semnalata. {} daca auditul lipseste.
    TREBUIE inaintea rutelor /{session_id}.
    """
    path = os.path.join(DATA_DIR, "m0_audit.csv")
    if not os.path.exists(path):
        return {}
    try:
        df = pd.read_csv(path)
        mtime = datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="minutes")
        return {str(r["id"]): {"verdict": r["verdict"], "n": int(r["n"]),
                               "expectancy": None if pd.isna(r["expectancy"]) else round(float(r["expectancy"]), 3),
                               "prob_positive": None if pd.isna(r["prob_positive"]) else round(float(r["prob_positive"]), 2),
                               "audited_at": mtime}
                for _, r in df.iterrows()}
    except Exception:
        return {}


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

    # Incarca jobs finalizate si sorteaza pe started_at descrescator (cele mai noi primele)
    jobs_done: list[dict] = []
    try:
        all_jobs = json.load(open(_BACKTEST_JOBS_FILE, encoding="utf-8"))
        jobs_done = [j for j in all_jobs if j.get("status") == "done"]
        jobs_done.sort(key=lambda j: j.get("started_at", ""), reverse=True)
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
        execute_trades = ps.get("execute_trades", True)
        if not execute_trades:
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

    # DD mediu estimat din backteste (max_dd este deja un procent negativ)
    dd_values: list[float] = []
    for ps in profile.get("sessions", []):
        sess_key = ps.get("session_key", "")
        sess_id  = ps.get("id", "")
        if sess_key in paused:
            continue
        if not ps.get("execute_trades", True):
            continue
        job = latest_job.get(sess_id)
        if not job:
            continue
        r = job.get("results") or {}
        max_dd = r.get("max_dd")
        if max_dd is not None:
            try:
                dd_values.append(float(max_dd))
            except (TypeError, ValueError):
                pass

    avg_max_dd = round(sum(dd_values) / len(dd_values), 1) if dd_values else None

    return {
        "per_week":     round(total_per_week, 1) if has_any else None,
        "per_month":    round(total_per_week * (30.44 / 7), 0) if has_any else None,
        "avg_max_dd":   avg_max_dd,
        "missing":      missing,
    }


def _to_signal(row, status_map: dict[str, str]) -> Signal:
    sid = str(row.get("signal_id", ""))
    return Signal(
        signal_id=sid,
        time=str(row.get("time", "")),
        symbol=str(row.get("symbol", "")),
        direction=int(row.get("direction", 0)),
        dir_str=str(row.get("dir_str", "")),
        entry=float(row.get("entry", 0)),
        sl=float(row.get("sl", 0)),
        tp=float(row.get("tp", 0)),
        r_ratio=float(row.get("r_ratio", 0)),
        status=status_map.get(sid),
    )


@router.get("/all/signals", response_model=list[Signal])
def get_all_signals(limit: int = 50):
    """Semnale agregate din sesiunile live (execute=True), sortate cronologic."""
    execute_map = get_profile_execute_map()
    all_rows = []
    status_map: dict[str, str] = {}
    for s in SESSIONS:
        if not execute_map.get(s["id"], s["execute"]):
            continue
        df = _read_signals(s["id"])
        if df.empty:
            continue
        df = df.tail(limit)
        all_rows.append(df)
        status_map.update(_signal_status_map(s["id"]))
    if not all_rows:
        return []
    combined = pd.concat(all_rows, ignore_index=True)
    combined = combined.sort_values("time", ascending=False).head(limit)
    return [_to_signal(row, status_map) for _, row in combined.iterrows()]


@router.get("", response_model=list[SessionStatus])
def list_sessions():
    paused      = _load_paused()
    news_paused = _load_news_paused()
    execute_map = get_profile_execute_map()  # dynamic — reflects profile changes from UI
    result = []
    for s in SESSIONS:
        running, pid = _session_running(s["id"])
        sig  = _sig_stats(s["id"])
        np_entry  = news_paused.get(s["id"], {})
        execute   = execute_map.get(s["id"], s["execute"])
        result.append(SessionStatus(
            id=s["id"],
            label=s["label"],
            markets=s["markets"],
            direction=s["direction"],
            tf=s["tf"],
            hours=s["hours"],
            validated=s["validated"],
            execute=execute,
            capital_pct=s["capital_pct"],
            running=running,
            pid=pid,
            signals_today=sig["today"],
            signals_yesterday=sig["yesterday"],
            signals_total=sig["total"],
            last_signal_time=sig["last_time"],
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
    status_map = _signal_status_map(session_id)
    return [_to_signal(row, status_map) for _, row in df.iterrows()]
