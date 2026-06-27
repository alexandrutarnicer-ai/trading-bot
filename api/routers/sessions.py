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
        return {"total": 0, "wins": 0, "losses": 0,
                "wins_today": 0, "wins_yesterday": 0, "losses_today": 0, "losses_yesterday": 0,
                "today": 0, "yesterday": 0,
                "pnl_usd_today": None, "pnl_usd_yesterday": None, "pnl_usd_total": None}
    closed = df[df["status"].isin(_CLOSED_STATUSES)]
    today     = str(date.today())
    yesterday = str(date.today() - timedelta(days=1))
    pnl_today = pnl_yest = None
    wins_today = wins_yest = losses_today = losses_yest = 0
    if "exit_time" in closed.columns and len(closed):
        et = closed["exit_time"].astype(str)
        today_out     = int(et.str.startswith(today).sum())
        yesterday_out = int(et.str.startswith(yesterday).sum())
        sub_today = closed[et.str.startswith(today)]
        sub_yest  = closed[et.str.startswith(yesterday)]
        if len(sub_today):
            wins_today   = int((sub_today["result_r"] > 0).sum())
            losses_today = int((sub_today["result_r"] < 0).sum())
        if len(sub_yest):
            wins_yest   = int((sub_yest["result_r"] > 0).sum())
            losses_yest = int((sub_yest["result_r"] < 0).sum())
        if "pnl_usd" in closed.columns:
            _t = pd.to_numeric(sub_today["pnl_usd"], errors="coerce").dropna()
            _y = pd.to_numeric(sub_yest["pnl_usd"],  errors="coerce").dropna()
            if len(_t): pnl_today = round(float(_t.sum()), 2)
            if len(_y): pnl_yest  = round(float(_y.sum()), 2)
    else:
        today_out = yesterday_out = 0
    wins   = int((closed["result_r"] > 0).sum()) if len(closed) else 0
    losses = int((closed["result_r"] < 0).sum()) if len(closed) else 0
    pnl_total = None
    if "pnl_usd" in closed.columns:
        all_pnl = pd.to_numeric(closed["pnl_usd"], errors="coerce").dropna()
        if len(all_pnl):
            pnl_total = round(float(all_pnl.sum()), 2)
    return {
        "total":            len(closed),
        "wins":             wins,
        "losses":           losses,
        "wins_today":       wins_today,
        "wins_yesterday":   wins_yest,
        "losses_today":     losses_today,
        "losses_yesterday": losses_yest,
        "today":            today_out,
        "yesterday":        yesterday_out,
        "pnl_usd_today":    pnl_today,
        "pnl_usd_yesterday": pnl_yest,
        "pnl_usd_total":    pnl_total,
    }


@router.get("/weekly_stats")
def weekly_stats():
    """Statistici agregate pentru saptamana / luna curenta vs precedenta (toate sesiunile)."""
    now = datetime.now()
    # Saptamana curenta (luni 00:00)
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)
    prev_week_start = week_start - timedelta(weeks=1)
    # Luna curenta (prima zi 00:00)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 1:
        prev_month_start = month_start.replace(year=month_start.year - 1, month=12)
    else:
        prev_month_start = month_start.replace(month=month_start.month - 1)

    def _aggregate(start: datetime, end: datetime) -> dict:
        totals = {"trades": 0, "wins": 0, "losses": 0, "total_r": 0.0, "pnl_usd": None}
        all_slices: list[pd.DataFrame] = []
        pnl_sum = 0.0
        pnl_any = False
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
            if "pnl_usd" in sub.columns:
                pnl_vals = pd.to_numeric(sub["pnl_usd"], errors="coerce").dropna()
                if len(pnl_vals):
                    pnl_sum += float(pnl_vals.sum())
                    pnl_any = True
            all_slices.append(sub[["_et", "result_r"]].copy())
        n = totals["trades"]
        totals["total_r"]  = round(totals["total_r"], 3)
        totals["win_rate"] = round(totals["wins"] / n * 100, 1) if n else 0.0
        totals["pnl_usd"]  = round(pnl_sum, 2) if pnl_any else None
        # Drawdown maxim in R
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
            "start": prev_week_start.date().isoformat(),
            "end":   (week_start - timedelta(days=1)).date().isoformat(),
            **_aggregate(prev_week_start, week_start),
        },
        "current_month": {
            "start": month_start.date().isoformat(),
            "end":   now.date().isoformat(),
            **_aggregate(month_start, now + timedelta(days=1)),
        },
        "previous_month": {
            "start": prev_month_start.date().isoformat(),
            "end":   (month_start - timedelta(days=1)).date().isoformat(),
            **_aggregate(prev_month_start, month_start),
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


@router.get("/all/outcomes", response_model=list[Outcome])
def get_all_outcomes(limit: int = 200):
    """Outcomes agregate din toate sesiunile — pentru SignalFeed in modul ALL."""
    all_rows = []
    for s in SESSIONS:
        df = _read_outcomes(s["id"])
        if df.empty:
            continue
        all_rows.append(df.tail(limit))
    if not all_rows:
        return []
    combined = pd.concat(all_rows, ignore_index=True)
    result = []
    for _, row in combined.iterrows():
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


@router.get("/all/signals", response_model=list[Signal])
def get_all_signals(limit: int = 50):
    """Semnale agregate din toate sesiunile, sortate cronologic (cele mai noi primele)."""
    all_rows = []
    for s in SESSIONS:
        df = _read_signals(s["id"])
        if df.empty:
            continue
        df = df.tail(limit)
        all_rows.append(df)
    if not all_rows:
        return []
    combined = pd.concat(all_rows, ignore_index=True)
    combined = combined.sort_values("time", ascending=False).head(limit)
    result = []
    for _, row in combined.iterrows():
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


@router.get("/top-markets")
def get_top_markets(period: str = "week", limit: int = 5):
    """Top piete dupa R cumulat, filtrate dupa perioada (day/week/month/all)."""
    today = date.today()
    if period == "day":
        cutoff = datetime.combine(today, datetime.min.time())
    elif period == "week":
        cutoff = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time())
    elif period == "month":
        cutoff = datetime.combine(today.replace(day=1), datetime.min.time())
    else:
        cutoff = None

    symbol_stats: dict = {}

    for s in SESSIONS:
        df = _read_outcomes(s["id"])
        if df.empty:
            continue
        closed = df[df["status"].isin(_CLOSED_STATUSES)].copy()
        if closed.empty:
            continue

        if cutoff is not None:
            closed["_et"] = pd.to_datetime(closed["exit_time"], errors="coerce")
            closed = closed[closed["_et"] >= cutoff]

        if closed.empty:
            continue

        for _, row in closed.iterrows():
            sym = str(row.get("symbol", ""))
            if not sym:
                continue
            if sym not in symbol_stats:
                symbol_stats[sym] = {
                    "trades": 0, "wins": 0, "total_r": 0.0,
                    "pnl_usd": 0.0, "pnl_has": False, "sessions": set(),
                }
            r = float(row.get("result_r", 0) or 0)
            symbol_stats[sym]["trades"] += 1
            if r > 0:
                symbol_stats[sym]["wins"] += 1
            symbol_stats[sym]["total_r"] += r
            symbol_stats[sym]["sessions"].add(s["id"])
            p = row.get("pnl_usd")
            if p is not None and not pd.isna(p):
                symbol_stats[sym]["pnl_usd"] += float(p)
                symbol_stats[sym]["pnl_has"] = True

    result = []
    for sym, st in symbol_stats.items():
        t = st["trades"]
        w = st["wins"]
        result.append({
            "symbol":      sym,
            "trades":      t,
            "wins":        w,
            "losses":      t - w,
            "total_r":     round(st["total_r"], 2),
            "win_rate":    round(w / t * 100, 1) if t > 0 else 0.0,
            "expectancy":  round(st["total_r"] / t, 3) if t > 0 else 0.0,
            "pnl_usd":     round(st["pnl_usd"], 2) if st["pnl_has"] else None,
            "sessions":    sorted(st["sessions"]),
        })

    result.sort(key=lambda x: x["total_r"], reverse=True)
    return result[:limit]


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
            wins_today=out["wins_today"],
            wins_yesterday=out["wins_yesterday"],
            losses_today=out["losses_today"],
            losses_yesterday=out["losses_yesterday"],
            paused=s["id"] in paused,
            news_paused=bool(np_entry),
            news_events=np_entry.get("events", []),
            pnl_usd_today=out["pnl_usd_today"],
            pnl_usd_yesterday=out["pnl_usd_yesterday"],
            pnl_usd_total=out["pnl_usd_total"],
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
