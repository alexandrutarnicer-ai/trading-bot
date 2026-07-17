"""
Centralized MT5 access for the API process — o singura conexiune persistenta,
protejata de lock, cu cache TTL scurt.

De ce exista:
    Fiecare endpoint din api/routers/mt5status.py facea `mt5.initialize()` +
    `mt5.shutdown()` la FIECARE request, si 9 endpointuri distincte interogau
    fiecare independent `history_deals_get` pe 400 zile pentru EXACT aceleasi
    date. Dashboard-ul + Rapoartele declanseaza 6-9 astfel de interogari la
    fiecare ciclu de polling. In plus, endpointurile sync ruleaza in threadpool-ul
    FastAPI (concurent) — un `shutdown()` dintr-un request putea taia conexiunea
    altui request in curs (race latent).

Solutia:
    1. O singura conexiune persistenta (fara init/shutdown per-request).
    2. Un singur lock global serializeaza tot accesul MT5 (modulul MetaTrader5
       NU e thread-safe).
    3. Cache TTL scurt: interogarea de istoric pe 400 zile se face O SINGURA DATA
       per fereastra TTL si e reutilizata de toate endpointurile.

Izolare totala fata de bot si AI:
    Acest pool traieste DOAR in procesul API. Sesiunile live (subprocese
    run_all.py) si motorul AI au fiecare propria conexiune MT5 in propriul
    proces — pool-ul asta nu le atinge niciodata. `mt5.initialize()` este
    idempotent si per-proces: mai multi clienti IPC pot fi conectati simultan
    la acelasi terminal (asa functioneaza deja cele 20 de sesiuni live).
"""

import atexit
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from tz_helper import get_configured_tz_name

# Reentrant: un getter poate apela altul sub acelasi lock fara deadlock.
_LOCK = threading.RLock()

# ── TTL-uri (secunde) ────────────────────────────────────────────────────────
_STATUS_TTL = 5.0     # cont/balance/equity — se schimba lent
_ORDERS_TTL = 6.0     # pozitii + pending
_TRADES_TTL = 15.0    # istoric tranzactii inchise (cel mai scump)
_OFFSET_TTL = 1800.0  # offset fus server — se schimba doar la DST (~2x/an)
_FETCH_DAYS = 400     # fereastra maxima folosita de orice endpoint

# ── Cache: fiecare = (expiry_monotonic, value) sau None ──────────────────────
_status_cache: tuple[float, dict] | None = None
_orders_cache: tuple[float, dict] | None = None
_trades_cache: tuple[float, list] | None = None
_offset_cache: tuple[float, int] | None = None


class Mt5Unavailable(Exception):
    """Terminalul MT5 nu poate fi contactat (neinstalat / neinitializat)."""


def _ensure_mt5():
    """
    Returneaza modulul MetaTrader5 cu o conexiune vie. Trebuie apelat cu _LOCK tinut.

    Apeleaza `mt5.initialize()` la fiecare acces necache-uit: cand conexiunea e
    deja vie e o revalidare ieftina (sub-ms); daca alt modul din API a facut
    `shutdown()` intre timp (markets/data_download/mt5_sync), reconecteaza
    automat. NU face niciodata shutdown — conexiunea ramane calda.
    """
    try:
        import MetaTrader5 as mt5
    except ImportError:
        raise Mt5Unavailable("MetaTrader5 nu este instalat")
    if not mt5.initialize():
        raise Mt5Unavailable(f"MT5 nu s-a putut initializa: {mt5.last_error()}")
    return mt5


@atexit.register
def _shutdown() -> None:
    try:
        import MetaTrader5 as mt5
        mt5.shutdown()
    except Exception:
        pass


# ── Timezone server (offset broker fata de UTC) ──────────────────────────────

def _detect_server_offset_h(mt5, symbol: str = "EURUSD") -> int:
    """
    Identic cu adapters/mt5_source.py::_detect_server_offset_h. Compara
    timestamp-ul ultimei bare M15/M1 inchise cu ora UTC reala pentru a deduce
    offset-ul serverului (tipic 2 sau 3 ore pentru brokeri EU).
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


def _server_offset(mt5) -> int:
    """Offset server cu cache lung (se schimba doar la DST). _LOCK tinut."""
    global _offset_cache
    now = time.monotonic()
    if _offset_cache and _offset_cache[0] > now:
        return _offset_cache[1]
    off = _detect_server_offset_h(mt5)
    _offset_cache = (now + _OFFSET_TTL, off)
    return off


def _mt5_ts_to_local(ts: int, offset_h: int, tz_name: str) -> datetime:
    """Epoch MT5 (ora serverului, naiv) → ora locala configurata (naiv)."""
    server_naive = datetime.utcfromtimestamp(ts)
    if offset_h == 0:
        return server_naive
    true_utc = server_naive - timedelta(hours=offset_h)
    return true_utc.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz_name)).replace(tzinfo=None)


# ── Istoric tranzactii inchise ───────────────────────────────────────────────

def _fetch_closed_trades_raw(mt5, days: int) -> list[dict]:
    """
    Interogheaza history_deals_get/history_orders_get si grupeaza pe position_id.
    Logica IDENTICA cu vechiul mt5status._fetch_closed_trades — vezi acolo pentru
    detalii despre profit/commission/swap, close_time (conversie fus) si result_r
    (din SL-ul original al ordinului). _LOCK tinut.
    """
    date_to = datetime.now() + timedelta(days=1)
    date_from = date_to - timedelta(days=days + 1)
    deals = mt5.history_deals_get(date_from, date_to) or []
    orders = mt5.history_orders_get(date_from, date_to) or []
    order_by_ticket = {o.ticket: o for o in orders}

    offset_h = _server_offset(mt5)
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


def get_closed_trades(days: int) -> list[dict]:
    """
    Tranzactiile inchise din ultimele `days` zile. Interogarea MT5 pe intreaga
    fereastra (_FETCH_DAYS) se face o singura data per _TRADES_TTL si e partajata
    de toate endpointurile; aici doar filtram lista cache-uita la fereastra ceruta.

    Ridica Mt5Unavailable daca terminalul nu poate fi contactat SI cache-ul e gol.
    """
    global _trades_cache
    now = time.monotonic()
    with _LOCK:
        if _trades_cache and _trades_cache[0] > now:
            trades = _trades_cache[1]
        else:
            mt5 = _ensure_mt5()
            trades = _fetch_closed_trades_raw(mt5, _FETCH_DAYS)
            _trades_cache = (now + _TRADES_TTL, trades)
    cutoff = datetime.now() - timedelta(days=days + 1)
    return [t for t in trades if t["close_time"] and t["close_time"] >= cutoff]


# ── Status cont ──────────────────────────────────────────────────────────────

def _status_disconnected(error: str) -> dict:
    return {
        "connected": False,
        "account": None, "server": None,
        "balance": None, "equity": None, "currency": None,
        "algo_trading_enabled": None,
        "is_demo": None,
        "error": error,
    }


def get_status() -> dict:
    """Cont/balance/equity/algo-trading (cache scurt). Nu ridica — intoarce dict."""
    global _status_cache
    now = time.monotonic()
    with _LOCK:
        if _status_cache and _status_cache[0] > now:
            return _status_cache[1]
        try:
            mt5 = _ensure_mt5()
            info = mt5.account_info()
            term = mt5.terminal_info()
            if info is None:
                result = _status_disconnected("Nu ești logat pe niciun cont MT5")
            else:
                algo_ok = bool(term and getattr(term, "trade_allowed", False))
                result = {
                    "connected": True,
                    "account": str(info.login),
                    "server": info.server,
                    "balance": round(info.balance, 2),
                    "equity": round(info.equity, 2),
                    "currency": info.currency,
                    "algo_trading_enabled": algo_ok,
                    # tipul contului — folosit de deblocarea Trading LIVE (UI)
                    "is_demo": info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO,
                    "error": None,
                }
        except Mt5Unavailable as e:
            result = _status_disconnected(str(e))
        # Esecurile se cache-uiesc scurt (max 3s) ca recuperarea sa apara repede.
        ttl = _STATUS_TTL if result["connected"] else min(3.0, _STATUS_TTL)
        _status_cache = (now + ttl, result)
        return result


def get_equity() -> float | None:
    """Equity curent (reutilizeaza cache-ul de status). None daca deconectat."""
    st = get_status()
    return st.get("equity") if st.get("connected") else None


# ── Ordine active (pozitii + pending) ────────────────────────────────────────

_AI_MAGIC = 770015   # namespace-ul motorului AI (ai_engine/config.py)


def _classify_source(magic: int, comment: str) -> str:
    """Clasifica originea unui ordin/pozitii: bot (sesiuni reguli) / ai / manual."""
    if magic == _AI_MAGIC or (comment or "").startswith("AI-"):
        return "ai"
    c = (comment or "").strip()
    if c.startswith("S") and "-" in c:
        return "bot"
    return "manual"


def get_orders() -> dict:
    """Pozitii deschise + ordine pending + sumar cont (cache scurt). Nu ridica."""
    global _orders_cache
    now = time.monotonic()
    with _LOCK:
        if _orders_cache and _orders_cache[0] > now:
            return _orders_cache[1]
        try:
            mt5 = _ensure_mt5()
        except Mt5Unavailable as e:
            result = {"connected": False, "error": str(e),
                      "positions": [], "pending": [], "account": None}
            _orders_cache = (now + min(3.0, _ORDERS_TTL), result)
            return result

        acc = mt5.account_info()
        positions = []
        for p in (mt5.positions_get() or []):
            positions.append({
                "ticket":   p.ticket,
                "symbol":   p.symbol,
                "type":     "LONG" if p.type == mt5.POSITION_TYPE_BUY else "SHORT",
                "volume":   p.volume,
                "entry":    p.price_open,
                "current":  p.price_current,
                "sl":       p.sl or None,
                "tp":       p.tp or None,
                "profit":   round(p.profit, 2),
                "swap":     round(p.swap, 2),
                "source":   _classify_source(p.magic, p.comment),
                "comment":  p.comment,
                "margin":   round(mt5.order_calc_margin(
                    mt5.ORDER_TYPE_BUY if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_SELL,
                    p.symbol, p.volume, p.price_open) or 0, 2),
            })

        pending = []
        for o in (mt5.orders_get() or []):
            otype = {
                mt5.ORDER_TYPE_BUY_STOP: "BUY_STOP", mt5.ORDER_TYPE_SELL_STOP: "SELL_STOP",
                mt5.ORDER_TYPE_BUY_LIMIT: "BUY_LIMIT", mt5.ORDER_TYPE_SELL_LIMIT: "SELL_LIMIT",
            }.get(o.type, str(o.type))
            pending.append({
                "ticket":  o.ticket,
                "symbol":  o.symbol,
                "type":    otype,
                "volume":  o.volume_current,
                "entry":   o.price_open,
                "sl":      o.sl or None,
                "tp":      o.tp or None,
                "source":  _classify_source(o.magic, o.comment),
                "comment": o.comment,
            })

        account = None
        if acc:
            account = {
                "equity":       round(acc.equity, 2),
                "balance":      round(acc.balance, 2),
                "margin_used":  round(acc.margin, 2),
                "margin_free":  round(acc.margin_free, 2),
                "margin_level": round(acc.margin_level, 1) if acc.margin else None,
                "currency":     acc.currency,
                "floating_pnl": round(acc.equity - acc.balance, 2),
            }

        result = {"connected": True, "error": None,
                  "positions": positions, "pending": pending, "account": account}
        _orders_cache = (now + _ORDERS_TTL, result)
        return result


def invalidate() -> None:
    """Forteaza reinterogarea MT5 la urmatorul apel (ex: dupa un sync manual)."""
    global _status_cache, _orders_cache, _trades_cache
    with _LOCK:
        _status_cache = None
        _orders_cache = None
        _trades_cache = None
