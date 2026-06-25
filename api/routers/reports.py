"""
Reports router — tranzactii, statistici piete, uptime bot, istoricul modificarilor.
"""

import json
import os
from datetime import date, timedelta
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Query

from api.config import DATA_DIR, SESSIONS

router = APIRouter(prefix="/reports", tags=["reports"])

UPTIME_LOG_FILE   = os.path.join(DATA_DIR, "bot_uptime_log.json")
CHANGES_LOG_FILE  = os.path.join(DATA_DIR, "session_changes_log.json")

_CLOSED_STATUSES = ["TP", "SL", "vineri_close", "news_close"]


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


@router.get("/transactions")
def get_transactions(
    status:    Optional[str] = Query(None, description="TP,SL,open,vineri_close,news_close"),
    symbol:    Optional[str] = Query(None),
    direction: Optional[str] = Query(None, description="LONG,SHORT"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to:   Optional[str] = Query(None, description="YYYY-MM-DD"),
    session_id: Optional[str] = Query(None),
    limit:     int = Query(200, le=1000),
    offset:    int = Query(0),
):
    """Toate tranzactiile din toate sesiunile, cu filtre."""
    rows = []
    sessions_to_check = (
        [s for s in SESSIONS if s["id"] == session_id]
        if session_id else SESSIONS
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
    """Statistici agregate per piata (simbol) din toate sesiunile."""
    market_stats: dict[str, dict] = {}

    for s in SESSIONS:
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
