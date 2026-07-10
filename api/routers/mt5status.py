"""
MT5 connection status endpoint.
GET /api/mt5/status — verifica daca MT5 este deschis si logat.
GET /api/mt5/stats  — statistici de tranzactionare calculate direct din history_deals_get.

Tot accesul MT5 trece prin api.mt5_pool: o singura conexiune persistenta,
protejata de lock, cu cache TTL scurt. Endpointurile de mai jos sunt doar
transformari peste lista de tranzactii inchise cache-uita (mt5_pool.get_closed_trades),
astfel incat cele ~9 endpointuri nu mai interogheaza MT5 fiecare separat.
Vezi api/mt5_pool.py pentru detalii despre izolarea fata de bot/AI si cache.
"""

import sys
import os
from datetime import date as _date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from fastapi import APIRouter

from api.config import SESSIONS
from api import mt5_pool

router = APIRouter(prefix="/mt5", tags=["mt5"])

# Mapare simbol -> session_id. Fiecare sesiune live tranzactioneaza o singura
# piata (vezi api/config.py), deci maparea e biunivoca — sigura pentru
# agregarea trade-urilor MT5 pe card de sesiune.
_SYMBOL_TO_SESSION: dict[str, str] = {
    m: s["id"] for s in SESSIONS for m in s["markets"]
}


@router.get("/status")
def mt5_status():
    return mt5_pool.get_status()


_EMPTY_TRADE_STATS = {
    "total_trades": 0, "wins": 0, "losses": 0,
    "trades_today": 0, "trades_yesterday": 0,
    "wins_today": 0, "wins_yesterday": 0,
    "losses_today": 0, "losses_yesterday": 0,
    "pnl_today": None, "pnl_yesterday": None, "pnl_total": None,
    "commission_total": None, "swap_total": None,
}


@router.get("/stats")
def mt5_trade_stats(days: int = 365):
    """
    Statistici de tranzactionare calculate direct din MT5 history_deals_get —
    sursa de adevar independenta de outcomes.csv.
    """
    try:
        trades = mt5_pool.get_closed_trades(days)
    except mt5_pool.Mt5Unavailable as e:
        return {"connected": False, "error": str(e), **_EMPTY_TRADE_STATS}

    today = _date.today()
    yesterday = today - timedelta(days=1)

    today_trades = [t for t in trades if t["close_time"].date() == today]
    yest_trades = [t for t in trades if t["close_time"].date() == yesterday]

    return {
        "connected": True,
        "total_trades": len(trades),
        "wins": sum(1 for t in trades if t["profit"] > 0),
        "losses": sum(1 for t in trades if t["profit"] < 0),
        "trades_today": len(today_trades),
        "trades_yesterday": len(yest_trades),
        "wins_today": sum(1 for t in today_trades if t["profit"] > 0),
        "wins_yesterday": sum(1 for t in yest_trades if t["profit"] > 0),
        "losses_today": sum(1 for t in today_trades if t["profit"] < 0),
        "losses_yesterday": sum(1 for t in yest_trades if t["profit"] < 0),
        "pnl_today": round(sum(t["profit"] for t in today_trades), 2),
        "pnl_yesterday": round(sum(t["profit"] for t in yest_trades), 2),
        "pnl_total": round(sum(t["profit"] for t in trades), 2),
        "commission_total": round(sum(t["commission"] for t in trades), 2),
        "swap_total": round(sum(t["swap"] for t in trades), 2),
        "error": None,
    }


@router.get("/equity-curve")
def mt5_equity_curve(days: int = 365, metric: str = "usd"):
    """
    Curba cumulata calculata direct din MT5, sortata cronologic dupa ora de
    inchidere. metric=usd -> P&L cumulat in $. metric=r -> R cumulat (din SL-ul
    original al ordinului) — sare pozitiile fara SL rezolvabil.
    """
    try:
        trades = mt5_pool.get_closed_trades(days)
    except mt5_pool.Mt5Unavailable as e:
        return {"connected": False, "error": str(e), "points": []}

    use_r = metric == "r"
    if use_r:
        trades = [t for t in trades if t["result_r"] is not None]
    trades = sorted(trades, key=lambda t: t["close_time"])

    points = []
    cum = 0.0
    for t in trades:
        cum += t["result_r"] if use_r else t["profit"]
        points.append({
            "date": t["close_time"].strftime("%Y-%m-%d %H:%M"),
            "value": round(cum, 3 if use_r else 2),
        })

    return {"connected": True, "metric": metric, "points": points, "error": None}


_EMPTY_PERIOD = {
    "start": "", "end": "", "trades": 0, "wins": 0, "losses": 0,
    "win_rate": 0.0, "pnl_usd": 0.0, "max_dd_usd": 0.0,
    "total_r": None, "max_dd_r": None,
}
_EMPTY_WEEKLY = {
    "current_week": _EMPTY_PERIOD, "previous_week": _EMPTY_PERIOD,
    "current_month": _EMPTY_PERIOD, "previous_month": _EMPTY_PERIOD,
}


@router.get("/weekly-stats")
def mt5_weekly_stats():
    """Saptamana/luna curenta vs precedenta, calculate din tranzactiile inchise MT5."""
    try:
        trades = mt5_pool.get_closed_trades(70)  # luna curenta + luna precedenta completa
    except mt5_pool.Mt5Unavailable as e:
        return {"connected": False, "error": str(e), **_EMPTY_WEEKLY}

    now = datetime.now()
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)
    prev_week_start = week_start - timedelta(weeks=1)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 1:
        prev_month_start = month_start.replace(year=month_start.year - 1, month=12)
    else:
        prev_month_start = month_start.replace(month=month_start.month - 1)

    def _aggregate(start: datetime, end: datetime) -> dict:
        sub = [t for t in trades if start <= t["close_time"] < end]
        sub.sort(key=lambda t: t["close_time"])
        n = len(sub)
        wins = sum(1 for t in sub if t["profit"] > 0)
        losses = sum(1 for t in sub if t["profit"] < 0)
        pnl_sum = round(sum(t["profit"] for t in sub), 2)
        win_rate = round(wins / n * 100, 1) if n else 0.0
        max_dd = 0.0
        cum = 0.0
        peak = 0.0
        for t in sub:
            cum += t["profit"]
            peak = max(peak, cum)
            max_dd = min(max_dd, cum - peak)

        r_sub = [t for t in sub if t["result_r"] is not None]
        total_r = None
        max_dd_r = None
        if r_sub:
            total_r = round(sum(t["result_r"] for t in r_sub), 3)
            cum_r = 0.0
            peak_r = 0.0
            max_dd_r = 0.0
            for t in r_sub:
                cum_r += t["result_r"]
                peak_r = max(peak_r, cum_r)
                max_dd_r = min(max_dd_r, cum_r - peak_r)
            max_dd_r = round(max_dd_r, 3)

        return {
            "trades": n, "wins": wins, "losses": losses,
            "win_rate": win_rate, "pnl_usd": pnl_sum,
            "max_dd_usd": round(max_dd, 2),
            "total_r": total_r, "max_dd_r": max_dd_r,
        }

    return {
        "connected": True,
        "current_week": {
            "start": week_start.date().isoformat(),
            "end": now.date().isoformat(),
            **_aggregate(week_start, now + timedelta(days=1)),
        },
        "previous_week": {
            "start": prev_week_start.date().isoformat(),
            "end": (week_start - timedelta(days=1)).date().isoformat(),
            **_aggregate(prev_week_start, week_start),
        },
        "current_month": {
            "start": month_start.date().isoformat(),
            "end": now.date().isoformat(),
            **_aggregate(month_start, now + timedelta(days=1)),
        },
        "previous_month": {
            "start": prev_month_start.date().isoformat(),
            "end": (month_start - timedelta(days=1)).date().isoformat(),
            **_aggregate(prev_month_start, month_start),
        },
        "error": None,
    }


@router.get("/top-markets")
def mt5_top_markets(period: str = "week", limit: int = 5):
    """Top piete dupa R cumulat, calculate direct din tranzactiile inchise MT5."""
    try:
        trades = mt5_pool.get_closed_trades(400)  # acopera si perioada "all"
    except mt5_pool.Mt5Unavailable as e:
        return {"connected": False, "error": str(e), "items": []}

    today = _date.today()
    if period == "day":
        cutoff = datetime.combine(today, datetime.min.time())
    elif period == "week":
        cutoff = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time())
    elif period == "month":
        cutoff = datetime.combine(today.replace(day=1), datetime.min.time())
    else:
        cutoff = None

    if cutoff is not None:
        trades = [t for t in trades if t["close_time"] >= cutoff]

    symbol_stats: dict[str, dict] = {}
    for t in trades:
        st = symbol_stats.setdefault(t["symbol"], {"trades": 0, "wins": 0, "total_r": 0.0, "pnl_usd": 0.0})
        st["trades"] += 1
        if t["profit"] > 0:
            st["wins"] += 1
        if t["result_r"] is not None:
            st["total_r"] += t["result_r"]
        st["pnl_usd"] += t["profit"]

    result = []
    for sym, st in symbol_stats.items():
        n = st["trades"]
        result.append({
            "symbol":     sym,
            "trades":     n,
            "wins":       st["wins"],
            "losses":     n - st["wins"],
            "total_r":    round(st["total_r"], 2),
            "win_rate":   round(st["wins"] / n * 100, 1) if n else 0.0,
            "expectancy": round(st["total_r"] / n, 3) if n else 0.0,
            "pnl_usd":    round(st["pnl_usd"], 2),
            "sessions":   [],  # fara concept de sesiune in MT5 — pastrat pentru compat. de tip
        })

    result.sort(key=lambda x: x["total_r"], reverse=True)
    return {"connected": True, "items": result[:limit], "error": None}


def _trade_status(t: dict) -> str:
    """Eticheta 'TP'/'SL' dupa semnul rezultatului (profit real daca R nu e rezolvabil)."""
    v = t["result_r"] if t["result_r"] is not None else t["profit"]
    if v > 0:
        return "TP"
    if v < 0:
        return "SL"
    return "—"


@router.get("/transactions")
def mt5_transactions(
    status: str = "",
    direction: str = "",
    symbol: str = "",
    limit: int = 200,
    offset: int = 0,
):
    """Lista tranzactiilor inchise, calculate direct din MT5 history_deals_get."""
    try:
        trades = mt5_pool.get_closed_trades(400)
    except mt5_pool.Mt5Unavailable as e:
        return {"connected": False, "error": str(e), "items": [], "total": 0}

    if symbol:
        trades = [t for t in trades if t["symbol"].upper() == symbol.upper()]
    if direction:
        want = 1 if direction.upper() == "LONG" else -1
        trades = [t for t in trades if t["direction"] == want]
    if status:
        trades = [t for t in trades if _trade_status(t) == status]

    trades = sorted(trades, key=lambda t: t["close_time"], reverse=True)
    total = len(trades)
    page = trades[offset: offset + limit]

    items = []
    for t in page:
        items.append({
            "ticket":      t["position_id"],
            "symbol":      t["symbol"],
            "direction":   t["direction"],
            "dir_str":     "LONG" if t["direction"] == 1 else "SHORT",
            "status":      _trade_status(t),
            "entry":       t["entry_price"],
            "sl":          t["sl"],
            "tp":          t["tp"],
            "r_ratio":     t["planned_r"],
            "entry_time":  t["entry_time"].strftime("%Y-%m-%d %H:%M") if t["entry_time"] else None,
            "exit_price":  t["exit_price"],
            "exit_time":   t["close_time"].strftime("%Y-%m-%d %H:%M") if t["close_time"] else None,
            "result_r":    t["result_r"],
            "pnl_usd":     round(t["profit"], 2),
            "commission_usd": round(t["commission"], 2),
            "swap_usd":    round(t["swap"], 2),
        })

    return {"connected": True, "items": items, "total": total, "error": None}


@router.get("/costs")
def mt5_costs():
    """Comisioane+swap per simbol, din tranzactiile inchise MT5."""
    try:
        trades = mt5_pool.get_closed_trades(400)
    except mt5_pool.Mt5Unavailable as e:
        return {"connected": False, "error": str(e), "items": []}

    by_symbol: dict[str, dict] = {}
    for t in trades:
        st = by_symbol.setdefault(t["symbol"], {
            "trades": 0, "commission_usd": 0.0, "swap_usd": 0.0, "pnl_gross": 0.0,
        })
        st["trades"] += 1
        st["commission_usd"] += t["commission"]
        st["swap_usd"] += t["swap"]
        st["pnl_gross"] += t["profit"]

    items = []
    for sym, st in by_symbol.items():
        total_costs = round(st["commission_usd"] + st["swap_usd"], 2)
        items.append({
            "symbol": sym,
            "trades": st["trades"],
            "trades_with_mt5": st["trades"],  # 100% din trades MT5 au date reale
            "commission_usd": round(st["commission_usd"], 2),
            "swap_usd": round(st["swap_usd"], 2),
            "total_costs": total_costs,
            "pnl_gross": round(st["pnl_gross"], 2),
            "pnl_net": round(st["pnl_gross"] + total_costs, 2),
            "has_cost_data": True,
            "sessions": [],
        })

    items.sort(key=lambda x: x["total_costs"])
    return {"connected": True, "items": items, "error": None}


@router.get("/costs-daily")
def mt5_costs_daily():
    """Comisioane+swap pe zi, din tranzactiile inchise MT5."""
    try:
        trades = mt5_pool.get_closed_trades(400)
    except mt5_pool.Mt5Unavailable as e:
        return {"connected": False, "error": str(e), "items": [],
                "total_commission": 0.0, "total_swap": 0.0, "total_costs": 0.0}

    by_day: dict[_date, dict] = {}
    for t in trades:
        day = t["close_time"].date()
        st = by_day.setdefault(day, {
            "trades": 0, "commission_usd": 0.0, "swap_usd": 0.0, "pnl_usd": 0.0, "total_r": 0.0,
        })
        st["trades"] += 1
        st["commission_usd"] += t["commission"]
        st["swap_usd"] += t["swap"]
        st["pnl_usd"] += t["profit"]
        if t["result_r"] is not None:
            st["total_r"] += t["result_r"]

    items = []
    for day, st in sorted(by_day.items()):
        comm = round(st["commission_usd"], 2)
        swap = round(st["swap_usd"], 2)
        items.append({
            "date": day.isoformat(),
            "trades": st["trades"],
            "trades_with_cost": st["trades"],
            "commission_usd": comm,
            "swap_usd": swap,
            "total_costs": round(comm + swap, 2),
            "pnl_usd": round(st["pnl_usd"], 2),
            "total_r": round(st["total_r"], 3),
            "has_cost_data": True,
        })

    total_comm = round(sum(x["commission_usd"] for x in items), 2)
    total_swap = round(sum(x["swap_usd"] for x in items), 2)
    return {
        "connected": True, "items": items, "error": None,
        "total_commission": total_comm, "total_swap": total_swap,
        "total_costs": round(total_comm + total_swap, 2),
    }


@router.get("/sessions")
def mt5_session_stats():
    """
    Statistici MT5-directe per sesiune, mapate prin simbol -> session_id
    (_SYMBOL_TO_SESSION, biunivoc). Trade-urile pe simboluri nemapate sunt ignorate.
    """
    try:
        trades = mt5_pool.get_closed_trades(400)
    except mt5_pool.Mt5Unavailable as e:
        return {"connected": False, "error": str(e), "items": []}

    today = _date.today()
    yesterday = today - timedelta(days=1)

    by_session: dict[str, dict] = {}
    for t in trades:
        session_id = _SYMBOL_TO_SESSION.get(t["symbol"])
        if session_id is None:
            continue
        st = by_session.setdefault(session_id, {
            "trades_today": 0, "trades_total": 0, "wins": 0, "losses": 0,
            "pnl_usd_today": 0.0, "pnl_usd_yesterday": 0.0, "last_trade_time": None,
        })
        st["trades_total"] += 1
        if t["profit"] > 0:
            st["wins"] += 1
        elif t["profit"] < 0:
            st["losses"] += 1
        day = t["close_time"].date()
        if day == today:
            st["trades_today"] += 1
            st["pnl_usd_today"] += t["profit"]
        elif day == yesterday:
            st["pnl_usd_yesterday"] += t["profit"]
        if st["last_trade_time"] is None or t["close_time"] > st["last_trade_time"]:
            st["last_trade_time"] = t["close_time"]

    items = []
    for s in SESSIONS:
        st = by_session.get(s["id"])
        if st is None:
            items.append({
                "session_id": s["id"], "symbol": s["markets"][0] if s["markets"] else "",
                "trades_today": 0, "trades_total": 0, "wins": 0, "losses": 0,
                "win_rate": 0.0, "pnl_usd_today": 0.0, "pnl_usd_yesterday": 0.0,
                "last_trade_time": None,
            })
            continue
        n = st["trades_total"]
        items.append({
            "session_id": s["id"], "symbol": s["markets"][0] if s["markets"] else "",
            "trades_today": st["trades_today"], "trades_total": n,
            "wins": st["wins"], "losses": st["losses"],
            "win_rate": round(st["wins"] / n * 100, 1) if n else 0.0,
            "pnl_usd_today": round(st["pnl_usd_today"], 2),
            "pnl_usd_yesterday": round(st["pnl_usd_yesterday"], 2),
            "last_trade_time": st["last_trade_time"].strftime("%H:%M") if st["last_trade_time"] else None,
        })

    return {"connected": True, "items": items, "error": None}


@router.get("/orders")
def mt5_active_orders():
    """
    Toate pozitiile deschise + ordinele pending din MT5, clasificate pe sursa
    (bot / ai / manual), plus sumar de capital. Sursa de adevar: exclusiv MT5.
    """
    return mt5_pool.get_orders()
