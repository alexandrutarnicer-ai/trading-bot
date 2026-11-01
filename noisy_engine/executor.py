"""
Noisy Engine — execuția REALĂ în MT5 (modul „execute”). SINGURUL fișier din noisy_engine/ care
trimite ordine; modul „shadow” nu îl apelează niciodată (verificat de selftest).

Reguli de siguranță:
  - cont DEMO → permis; cont REAL → DOAR dacă „noisy_engine” e deblocat în Settings → Trading LIVE
    (live_guard, fișier local mașinii; orice eroare de citire = BLOCAT)
  - magic 990001 + comment „N-<SIMBOL>-<HHMM>” → izolat de Custom (S<n>-), AI (770015), Daily (880001);
    atribuit „noisy” în Dashboard / rapoarte
  - o singură poziție odată, SL + țintă atașate la plasare, stop de timp închis de engine,
    nimic peste noapte (orice poziție Noisy mai veche decât stopul de timp e închisă)
"""
from __future__ import annotations

from noisy_engine.config import MAGIC

FILL_IOC, FILL_FOK, FILL_RETURN = 1, 0, 2       # mt5.ORDER_FILLING_*
RETRY_RETCODES = (10030, 10006)                 # filling incompatibil / reject (ICMarketsEU)


def tag(symbol: str, signal_t: str) -> str:
    return f"N-{symbol[:6]}-{signal_t[11:13]}{signal_t[14:16]}"[:16]


def execution_allowed(mt5, live_allowed_fn) -> tuple[bool, str]:
    acc = mt5.account_info()
    if acc is None:
        return False, "contul MT5 indisponibil"
    if getattr(acc, "trade_mode", None) == 0:
        return True, "cont DEMO"
    try:
        ok = bool(live_allowed_fn("noisy_engine"))
    except Exception:
        ok = False
    return (True, "cont REAL — deblocat în Trading LIVE") if ok else \
        (False, "cont REAL nedeblocat (Settings → Trading LIVE → Noisy Engine)")


def own(mt5, symbol: str | None = None) -> list:
    """Pozițiile Noisy Engine (magic 990001)."""
    kw = {"symbol": symbol} if symbol else {}
    return [p for p in (mt5.positions_get(**kw) or ()) if p.magic == MAGIC]


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


def place_market(mt5, symbol: str, side: int, lots: float, sl: float, tp: float, comment: str) -> tuple[bool, object]:
    info, tick = mt5.symbol_info(symbol), mt5.symbol_info_tick(symbol)
    if info is None or tick is None:
        return False, "tick/info indisponibil"
    price = tick.ask if side == 1 else tick.bid
    req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": lots,
           "type": mt5.ORDER_TYPE_BUY if side == 1 else mt5.ORDER_TYPE_SELL,
           "price": price, "sl": round(sl, info.digits), "tp": round(tp, info.digits), "deviation": 10,
           "magic": MAGIC, "comment": comment, "type_time": mt5.ORDER_TIME_GTC}
    return _send(mt5, req, info)


def close(mt5, pos) -> tuple[bool, object]:
    info, tick = mt5.symbol_info(pos.symbol), mt5.symbol_info_tick(pos.symbol)
    if info is None or tick is None:
        return False, "tick/info indisponibil"
    buy = pos.type == getattr(mt5, "POSITION_TYPE_BUY", 0)
    req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": pos.symbol, "volume": pos.volume,
           "type": mt5.ORDER_TYPE_SELL if buy else mt5.ORDER_TYPE_BUY, "position": pos.ticket,
           "price": tick.bid if buy else tick.ask, "deviation": 20, "magic": MAGIC,
           "comment": f"{pos.comment}"[:16], "type_time": mt5.ORDER_TIME_GTC}
    return _send(mt5, req, info)


def modify_sl(mt5, pos, sl: float) -> tuple[bool, object]:
    """Muta SL-ul unei pozitii Noisy (break-even); tinta ramane neschimbata."""
    info = mt5.symbol_info(pos.symbol)
    if info is None:
        return False, "info indisponibil"
    res = mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "position": pos.ticket, "symbol": pos.symbol,
                          "sl": round(sl, info.digits), "tp": pos.tp, "magic": MAGIC})
    return res is not None and res.retcode == getattr(mt5, "TRADE_RETCODE_DONE", 10009), res


def close_all(mt5, symbol: str | None = None) -> tuple[int, int]:
    """Închide TOATE pozițiile Noisy (Stop / Emergency Stop / buget). Întoarce (închise, eșuate)."""
    ok = bad = 0
    for p in own(mt5, symbol):
        done, _ = close(mt5, p)
        ok += done
        bad += not done
    return ok, bad


def realized_pnl(mt5, since_epoch: float, now_epoch: float) -> float:
    """P&L REALIZAT al Noisy din MT5 (profit + comision + swap, deal-urile cu magic 990001)."""
    from datetime import datetime, timezone
    a = datetime.fromtimestamp(since_epoch, tz=timezone.utc)
    b = datetime.fromtimestamp(now_epoch + 86400, tz=timezone.utc)
    deals = mt5.history_deals_get(a, b) or ()
    return float(sum((d.profit + d.commission + d.swap + getattr(d, "fee", 0.0))
                     for d in deals if d.magic == MAGIC))


def floating_pnl(mt5, symbol: str | None = None) -> float:
    return float(sum(p.profit + getattr(p, "swap", 0.0) for p in own(mt5, symbol)))
