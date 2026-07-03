"""
MT5 connection status endpoint.
GET /api/mt5/status — verifica daca MT5 este deschis si logat.
GET /api/mt5/stats  — statistici de tranzactionare calculate direct din history_deals_get (fara outcomes.csv).
"""

import sys
import os
from datetime import date as _date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from fastapi import APIRouter

from tz_helper import get_configured_tz_name
from api.config import SESSIONS

router = APIRouter(prefix="/mt5", tags=["mt5"])

# Mapare simbol -> session_id. Fiecare sesiune live tranzactioneaza o singura
# piata (vezi api/config.py), deci maparea e biunivoca — sigura pentru
# agregarea trade-urilor MT5 pe card de sesiune.
_SYMBOL_TO_SESSION: dict[str, str] = {
    m: s["id"] for s in SESSIONS for m in s["markets"]
}


def _detect_server_offset_h(mt5, symbol: str = "EURUSD") -> int:
    """
    Acelasi mecanism ca adapters/mt5_source.py::_detect_server_offset_h —
    detecteaza offset-ul (in ore) al serverului broker fata de UTC real,
    comparand timestamp-ul unei bare M15/M1 inchise cu ora UTC curenta.
    Necesar deoarece history_deals_get().time e in ora serverului (naiv,
    codificat ca si cum ar fi epoch UTC), nu UTC real — fara aceasta
    detectie, clasificarea trade-urilor in azi/ieri poate fi gresita cu
    2-3 ore (exact offsetul serverului), mutand trade-uri de langa miezul
    noptii in ziua gresita.
    """
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    for tf in (mt5.TIMEFRAME_M15, mt5.TIMEFRAME_M1):
        rates = mt5.copy_rates_from_pos(symbol, tf, 1, 1)
        if rates is None or len(rates) == 0:
            continue
        bar_naive = datetime.fromtimestamp(int(rates[0]["time"]), tz=timezone.utc).replace(tzinfo=None)
        diff_s = (bar_naive - now_utc).total_seconds()
        for candidate in (3, 2, 1, 0):
            if abs(diff_s - candidate * 3600) < 1800:  # ±30 min
                return candidate
    return 0


def _mt5_ts_to_local(ts: int, offset_h: int, tz_name: str) -> datetime:
    """Converteste un epoch MT5 (ora serverului, naiv) la ora locala configurata (naiv)."""
    server_naive = datetime.utcfromtimestamp(ts)
    if offset_h == 0:
        return server_naive
    true_utc = server_naive - timedelta(hours=offset_h)
    return true_utc.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz_name)).replace(tzinfo=None)


@router.get("/status")
def mt5_status():
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            err = mt5.last_error()
            mt5.shutdown()
            return {
                "connected": False,
                "account": None, "server": None,
                "balance": None, "equity": None, "currency": None,
                "algo_trading_enabled": None,
                "error": f"MT5 nu s-a putut initializa: {err}",
            }
        info = mt5.account_info()
        term = mt5.terminal_info()
        mt5.shutdown()
        if info is None:
            return {
                "connected": False,
                "account": None, "server": None,
                "balance": None, "equity": None, "currency": None,
                "algo_trading_enabled": None,
                "error": "Nu ești logat pe niciun cont MT5",
            }
        algo_ok = bool(term and getattr(term, "trade_allowed", False))
        return {
            "connected": True,
            "account": str(info.login),
            "server": info.server,
            "balance": round(info.balance, 2),
            "equity": round(info.equity, 2),
            "currency": info.currency,
            "algo_trading_enabled": algo_ok,
            "error": None,
        }
    except ImportError:
        return {
            "connected": False,
            "account": None, "server": None,
            "balance": None, "equity": None, "currency": None,
            "algo_trading_enabled": None,
            "error": "MetaTrader5 nu este instalat",
        }
    except Exception as e:
        return {
            "connected": False,
            "account": None, "server": None,
            "balance": None, "equity": None, "currency": None,
            "algo_trading_enabled": None,
            "error": str(e),
        }


_EMPTY_TRADE_STATS = {
    "total_trades": 0, "wins": 0, "losses": 0,
    "trades_today": 0, "trades_yesterday": 0,
    "wins_today": 0, "wins_yesterday": 0,
    "losses_today": 0, "losses_yesterday": 0,
    "pnl_today": None, "pnl_yesterday": None, "pnl_total": None,
    "commission_total": None, "swap_total": None,
}


def _fetch_closed_trades(mt5, days: int) -> list[dict]:
    """
    Interogheaza history_deals_get si grupeaza deal-urile pe position_id.
    profit = suma profit deal-urilor OUT (acopera si close partial),
    commission/swap = suma pe toate deal-urile pozitiei (IN + OUT).
    Exclude deal-urile de tip balance/credit (type not in 0,1).
    Returneaza doar pozitiile care au fost efectiv inchise (has_out).

    close_time: datetime naiv, convertit din ora serverului broker la fusul
    orar configurat (Europe/Bucharest by default) — vezi _detect_server_offset_h.
    Fara aceasta conversie, clasificarea azi/ieri si limitele saptamana/luna
    pot fi gresite cu offsetul serverului (2-3 ore).

    result_r: calculat din SL-ul ORIGINAL al ordinului care a deschis pozitia
    (history_orders_get — pending order-ul BUY_STOP/SELL_STOP plasat de bot),
    nu din SL-ul curent al pozitiei (care poate fi mutat de break-even).
    Formula identica cu cea din live/signal_generator.py:
    result_r = (exit_price - entry_price) * directie / |entry_price - sl_original|.
    None daca ordinul de deschidere nu are SL setat (ex: tranzactie manuala).
    """
    date_to = datetime.now() + timedelta(days=1)
    date_from = date_to - timedelta(days=days + 1)
    deals = mt5.history_deals_get(date_from, date_to) or []
    orders = mt5.history_orders_get(date_from, date_to) or []
    order_by_ticket = {o.ticket: o for o in orders}

    offset_h = _detect_server_offset_h(mt5)
    tz_name = get_configured_tz_name()

    by_position: dict[int, dict] = {}
    for d in deals:
        if d.type not in (0, 1):  # doar BUY/SELL — exclude balance/credit/etc
            continue
        pos = by_position.setdefault(d.position_id, {
            "profit": 0.0, "commission": 0.0, "swap": 0.0,
            "has_out": False, "close_time": None, "symbol": d.symbol,
            "entry_price": None, "entry_time": None, "direction": None, "sl": None, "tp": None,
            "_out_px_vol": 0.0, "_out_vol": 0.0,
        })
        pos["commission"] += float(d.commission or 0)
        pos["swap"] += float(d.swap or 0)
        if d.entry == 0:  # DEAL_ENTRY_IN
            pos["entry_price"] = float(d.price)
            pos["entry_time"] = _mt5_ts_to_local(d.time, offset_h, tz_name)
            pos["direction"] = 1 if d.type == 0 else -1
            order = order_by_ticket.get(d.order)
            if order is not None:
                if getattr(order, "sl", 0):
                    pos["sl"] = float(order.sl)
                if getattr(order, "tp", 0):
                    pos["tp"] = float(order.tp)
        else:  # OUT / OUT_BY
            pos["profit"] += float(d.profit or 0)
            pos["has_out"] = True
            local_dt = _mt5_ts_to_local(d.time, offset_h, tz_name)
            if pos["close_time"] is None or local_dt > pos["close_time"]:
                pos["close_time"] = local_dt
            vol = float(d.volume or 0)
            pos["_out_px_vol"] += float(d.price) * vol
            pos["_out_vol"] += vol

    trades = []
    for position_id, pos in by_position.items():
        if not pos["has_out"]:
            continue
        result_r = None
        risk_dist = None
        exit_price = pos["_out_px_vol"] / pos["_out_vol"] if pos["_out_vol"] > 0 else None
        if pos["sl"] is not None and pos["entry_price"] is not None and exit_price is not None:
            risk_dist = abs(pos["entry_price"] - pos["sl"])
            if risk_dist > 0:
                result_r = round((exit_price - pos["entry_price"]) * pos["direction"] / risk_dist, 3)
        planned_r = None
        if risk_dist and pos["tp"] is not None and pos["entry_price"] is not None:
            planned_r = round(abs(pos["tp"] - pos["entry_price"]) / risk_dist, 2)
        trades.append({
            "position_id": position_id, "symbol": pos["symbol"],
            "profit": pos["profit"], "commission": pos["commission"], "swap": pos["swap"],
            "entry_price": pos["entry_price"], "entry_time": pos["entry_time"],
            "exit_price": exit_price, "close_time": pos["close_time"],
            "direction": pos["direction"], "sl": pos["sl"], "tp": pos["tp"],
            "result_r": result_r, "planned_r": planned_r,
        })
    return trades


@router.get("/stats")
def mt5_trade_stats(days: int = 365):
    """
    Statistici de tranzactionare calculate direct din MT5 history_deals_get —
    sursa de adevar independenta de outcomes.csv (care poate avea intarzieri
    sau lipsuri daca sesiunea a crapat / state.pkl corupt).
    """
    try:
        import MetaTrader5 as mt5

        if not mt5.initialize():
            err = mt5.last_error()
            mt5.shutdown()
            return {"connected": False, "error": f"MT5 nu s-a putut initializa: {err}", **_EMPTY_TRADE_STATS}

        trades = _fetch_closed_trades(mt5, days)
        mt5.shutdown()

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
    except ImportError:
        return {"connected": False, "error": "MetaTrader5 nu este instalat", **_EMPTY_TRADE_STATS}
    except Exception as e:
        return {"connected": False, "error": str(e), **_EMPTY_TRADE_STATS}


@router.get("/equity-curve")
def mt5_equity_curve(days: int = 365, metric: str = "usd"):
    """
    Curba cumulata calculata direct din MT5 history_deals_get, sortata cronologic
    dupa ora de inchidere a fiecarei pozitii — echivalentul MT5-direct al
    graficului de Performanta. metric=usd -> P&L cumulat in $ (profit brut).
    metric=r -> R cumulat, calculat din SL-ul original al ordinului (vezi
    _fetch_closed_trades) — sare pozitiile fara SL rezolvabil.
    """
    try:
        import MetaTrader5 as mt5

        if not mt5.initialize():
            err = mt5.last_error()
            mt5.shutdown()
            return {"connected": False, "error": f"MT5 nu s-a putut initializa: {err}", "points": []}

        trades = _fetch_closed_trades(mt5, days)
        mt5.shutdown()

        use_r = metric == "r"
        if use_r:
            trades = [t for t in trades if t["result_r"] is not None]
        trades.sort(key=lambda t: t["close_time"])

        points = []
        cum = 0.0
        for t in trades:
            cum += t["result_r"] if use_r else t["profit"]
            points.append({
                "date": t["close_time"].strftime("%Y-%m-%d %H:%M"),
                "value": round(cum, 3 if use_r else 2),
            })

        return {"connected": True, "metric": metric, "points": points, "error": None}
    except ImportError:
        return {"connected": False, "error": "MetaTrader5 nu este instalat", "points": []}
    except Exception as e:
        return {"connected": False, "error": str(e), "points": []}


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
    """
    Echivalentul MT5-direct al /sessions/weekly_stats — saptamana/luna curenta vs
    precedenta, calculate din history_deals_get. total_r/max_dd_r calculate din
    SL-ul original al ordinelor (vezi _fetch_closed_trades) — None daca nicio
    pozitie din perioada nu are SL rezolvabil.
    """
    try:
        import MetaTrader5 as mt5

        if not mt5.initialize():
            err = mt5.last_error()
            mt5.shutdown()
            return {"connected": False, "error": f"MT5 nu s-a putut initializa: {err}", **_EMPTY_WEEKLY}

        trades = _fetch_closed_trades(mt5, days=70)  # acopera luna curenta + luna precedenta completa
        mt5.shutdown()

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
    except ImportError:
        return {"connected": False, "error": "MetaTrader5 nu este instalat", **_EMPTY_WEEKLY}
    except Exception as e:
        return {"connected": False, "error": str(e), **_EMPTY_WEEKLY}


@router.get("/top-markets")
def mt5_top_markets(period: str = "week", limit: int = 5):
    """
    Echivalentul MT5-direct al /sessions/top-markets — top piete dupa R cumulat,
    calculate direct din history_deals_get (vezi _fetch_closed_trades pentru
    modul de calcul al result_r din SL-ul original al ordinului).
    """
    try:
        import MetaTrader5 as mt5

        if not mt5.initialize():
            err = mt5.last_error()
            mt5.shutdown()
            return {"connected": False, "error": f"MT5 nu s-a putut initializa: {err}", "items": []}

        trades = _fetch_closed_trades(mt5, days=400)  # acopera si perioada "all"
        mt5.shutdown()

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
                "sessions":   [],  # fara concept de sesiune in MT5 — pastrat pentru compat. de tip cu MarketStat
            })

        result.sort(key=lambda x: x["total_r"], reverse=True)
        return {"connected": True, "items": result[:limit], "error": None}
    except ImportError:
        return {"connected": False, "error": "MetaTrader5 nu este instalat", "items": []}
    except Exception as e:
        return {"connected": False, "error": str(e), "items": []}


def _trade_status(t: dict) -> str:
    """Eticheta afisata in tab-ul Tranzactii — 'TP'/'SL' dupa semnul rezultatului
    (profit real daca R nu e rezolvabil), pastrand codul de culoare existent in UI.
    Nu reflecta neaparat ca pretul a atins literal nivelul TP/SL (poate fi si
    inchidere manuala) — e o eticheta de castig/pierdere, nu un motiv de inchidere."""
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
    """
    Echivalentul MT5-direct al /reports/transactions — lista tranzactiilor
    inchise, calculate direct din history_deals_get (vezi _fetch_closed_trades).
    status: TP/SL (dupa semnul rezultatului) — MT5 nu are conceptul de
    expirat/vineri_close/news_close (acelea sunt clasificari ale botului).
    """
    try:
        import MetaTrader5 as mt5

        if not mt5.initialize():
            err = mt5.last_error()
            mt5.shutdown()
            return {"connected": False, "error": f"MT5 nu s-a putut initializa: {err}", "items": [], "total": 0}

        trades = _fetch_closed_trades(mt5, days=400)
        mt5.shutdown()

        if symbol:
            trades = [t for t in trades if t["symbol"].upper() == symbol.upper()]
        if direction:
            want = 1 if direction.upper() == "LONG" else -1
            trades = [t for t in trades if t["direction"] == want]
        if status:
            trades = [t for t in trades if _trade_status(t) == status]

        trades.sort(key=lambda t: t["close_time"], reverse=True)
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
    except ImportError:
        return {"connected": False, "error": "MetaTrader5 nu este instalat", "items": [], "total": 0}
    except Exception as e:
        return {"connected": False, "error": str(e), "items": [], "total": 0}


@router.get("/costs")
def mt5_costs():
    """Echivalentul MT5-direct al /reports/costs — comisioane+swap per simbol, din history_deals_get."""
    try:
        import MetaTrader5 as mt5

        if not mt5.initialize():
            err = mt5.last_error()
            mt5.shutdown()
            return {"connected": False, "error": f"MT5 nu s-a putut initializa: {err}", "items": []}

        trades = _fetch_closed_trades(mt5, days=400)
        mt5.shutdown()

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
                "sessions": [],  # fara concept de sesiune in MT5 — pastrat pentru compat. de tip cu CostStat
            })

        items.sort(key=lambda x: x["total_costs"])
        return {"connected": True, "items": items, "error": None}
    except ImportError:
        return {"connected": False, "error": "MetaTrader5 nu este instalat", "items": []}
    except Exception as e:
        return {"connected": False, "error": str(e), "items": []}


@router.get("/costs-daily")
def mt5_costs_daily():
    """Echivalentul MT5-direct al /reports/costs-daily — comisioane+swap pe zi, din history_deals_get."""
    try:
        import MetaTrader5 as mt5

        if not mt5.initialize():
            err = mt5.last_error()
            mt5.shutdown()
            return {"connected": False, "error": f"MT5 nu s-a putut initializa: {err}", "items": [],
                     "total_commission": 0.0, "total_swap": 0.0, "total_costs": 0.0}

        trades = _fetch_closed_trades(mt5, days=400)
        mt5.shutdown()

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
    except ImportError:
        return {"connected": False, "error": "MetaTrader5 nu este instalat", "items": [],
                 "total_commission": 0.0, "total_swap": 0.0, "total_costs": 0.0}
    except Exception as e:
        return {"connected": False, "error": str(e), "items": [],
                 "total_commission": 0.0, "total_swap": 0.0, "total_costs": 0.0}


@router.get("/sessions")
def mt5_session_stats():
    """
    Statistici MT5-directe per sesiune (Dashboard → Sesiuni active), mapate
    prin simbol -> session_id (_SYMBOL_TO_SESSION, biunivoc — o piata per
    sesiune). Echivalentul MT5 pentru signals_today/signals_total/wins din
    /sessions (care sunt calculate din outcomes.csv). Trade-urile pe simboluri
    nemapate la nicio sesiune (ex. simbol scos din profil) sunt ignorate.
    """
    try:
        import MetaTrader5 as mt5

        if not mt5.initialize():
            err = mt5.last_error()
            mt5.shutdown()
            return {"connected": False, "error": f"MT5 nu s-a putut initializa: {err}", "items": []}

        trades = _fetch_closed_trades(mt5, days=400)
        mt5.shutdown()

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
    except ImportError:
        return {"connected": False, "error": "MetaTrader5 nu este instalat", "items": []}
    except Exception as e:
        return {"connected": False, "error": str(e), "items": []}
