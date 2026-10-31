"""
Daily Engine — execuția REALĂ în MT5 (modul „execute”). SINGURUL fișier din daily_engine/ care
trimite ordine; modul „shadow” nu îl apelează niciodată (verificat de selftest).

Reguli de siguranță:
  - cont DEMO → permis; cont REAL → DOAR dacă „daily_engine” e deblocat în Settings → Trading
    LIVE (live_guard, fișier local mașinii; orice eroare de citire = BLOCAT)
  - magic 880001 + comment „D-<SIMBOL>-<MMDD>” → izolat de Custom (comment S<n>-) și AI (770015);
    atribuit „daily” în Dashboard / rapoarte
  - un singur trade / zi / piață, SL atașat la plasare, închidere forțată la finalul ferestrei,
    nimic peste noapte (orice poziție daily din altă zi e închisă imediat)
"""
from __future__ import annotations

from daily_engine.config import MAGIC

FILL_IOC, FILL_FOK, FILL_RETURN = 1, 0, 2       # mt5.ORDER_FILLING_*
RETRY_RETCODES = (10030, 10006)                 # filling incompatibil / reject (ICMarketsEU)


def day_tag(symbol: str, day) -> str:
    return f"D-{symbol[:8]}-{day:%m%d}"[:16]


def execution_allowed(mt5, live_allowed_fn) -> tuple[bool, str]:
    acc = mt5.account_info()
    if acc is None:
        return False, "contul MT5 indisponibil"
    if getattr(acc, "trade_mode", None) == 0:
        return True, "cont DEMO"
    try:
        ok = bool(live_allowed_fn("daily_engine"))
    except Exception:
        ok = False
    return (True, "cont REAL — deblocat în Trading LIVE") if ok else \
        (False, "cont REAL nedeblocat (Settings → Trading LIVE → Daily Engine)")


def own(mt5, symbol: str | None = None) -> tuple[list, list]:
    """(poziții, ordine pending) ale Daily Engine (magic 880001)."""
    kw = {"symbol": symbol} if symbol else {}
    pos = [p for p in (mt5.positions_get(**kw) or ()) if p.magic == MAGIC]
    ords = [o for o in (mt5.orders_get(**kw) or ()) if o.magic == MAGIC]
    return pos, ords


def _fillings(mt5, info) -> list:
    fm = int(getattr(info, "filling_mode", 0) or 0)
    order = []
    if fm & 2:
        order.append(getattr(mt5, "ORDER_FILLING_IOC", FILL_IOC))
    if fm & 1:
        order.append(getattr(mt5, "ORDER_FILLING_FOK", FILL_FOK))
    order.append(getattr(mt5, "ORDER_FILLING_RETURN", FILL_RETURN))
    return order + [None]


def _send(mt5, req: dict, info) -> tuple[bool, object]:
    last = None
    for f in _fillings(mt5, info):
        r = dict(req)
        if f is not None:
            r["type_filling"] = f
        res = mt5.order_send(r)
        last = res
        done = getattr(mt5, "TRADE_RETCODE_DONE", 10009)
        if res is not None and res.retcode in (done, getattr(mt5, "TRADE_RETCODE_PLACED", 10008)):
            return True, res
        if res is None or res.retcode not in RETRY_RETCODES:
            break
    return False, last


def place_market(mt5, symbol: str, side: int, lots: float, sl: float, comment: str) -> tuple[bool, object]:
    info, tick = mt5.symbol_info(symbol), mt5.symbol_info_tick(symbol)
    if info is None or tick is None:
        return False, "tick/info indisponibil"
    price = tick.ask if side == 1 else tick.bid
    req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": lots,
           "type": mt5.ORDER_TYPE_BUY if side == 1 else mt5.ORDER_TYPE_SELL,
           "price": price, "sl": round(sl, info.digits), "deviation": 20, "magic": MAGIC,
           "comment": comment, "type_time": mt5.ORDER_TIME_GTC}
    return _send(mt5, req, info)


def place_stop(mt5, symbol: str, side: int, level: float, lots: float, sl: float, comment: str) -> tuple[bool, object]:
    info = mt5.symbol_info(symbol)
    if info is None:
        return False, "info indisponibil"
    req = {"action": mt5.TRADE_ACTION_PENDING, "symbol": symbol, "volume": lots,
           "type": mt5.ORDER_TYPE_BUY_STOP if side == 1 else mt5.ORDER_TYPE_SELL_STOP,
           "price": round(level, info.digits), "sl": round(sl, info.digits), "magic": MAGIC,
           "comment": comment, "type_time": mt5.ORDER_TIME_GTC}     # ICMarketsEU refuză ORDER_TIME_SPECIFIED
    return _send(mt5, req, info)


def cancel(mt5, order) -> bool:
    res = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": order.ticket})
    return res is not None and res.retcode == getattr(mt5, "TRADE_RETCODE_DONE", 10009)


def close(mt5, pos) -> tuple[bool, object]:
    info, tick = mt5.symbol_info(pos.symbol), mt5.symbol_info_tick(pos.symbol)
    if info is None or tick is None:
        return False, "tick/info indisponibil"
    buy = pos.type == getattr(mt5, "POSITION_TYPE_BUY", 0)
    req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": pos.symbol, "volume": pos.volume,
           "type": mt5.ORDER_TYPE_SELL if buy else mt5.ORDER_TYPE_BUY, "position": pos.ticket,
           "price": tick.bid if buy else tick.ask, "deviation": 30, "magic": MAGIC,
           "comment": f"{pos.comment}"[:16], "type_time": mt5.ORDER_TIME_GTC}
    return _send(mt5, req, info)
