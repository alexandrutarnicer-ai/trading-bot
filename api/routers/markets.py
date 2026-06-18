"""
GET /api/markets/mt5  — simboluri disponibile in contul MT5 curent.
GET /api/markets/atr  — ATR curent per simbol (ultimele 14 bare).
"""
import threading
import numpy as np
from datetime import datetime
from fastapi import APIRouter, Query

router = APIRouter(prefix="/markets", tags=["markets"])

_cache: dict = {"symbols": None, "cached_at": None}
_lock = threading.Lock()

try:
    import MetaTrader5 as _mt5
    _HAS_MT5 = True
except ImportError:
    _mt5 = None
    _HAS_MT5 = False


@router.get("/mt5")
def get_mt5_symbols():
    global _cache

    # Cache 5 minute
    if _cache["symbols"] is not None and _cache["cached_at"]:
        age = (datetime.now() - _cache["cached_at"]).total_seconds()
        if age < 300:
            return {"symbols": _cache["symbols"], "error": None}

    if not _HAS_MT5:
        return {"symbols": [], "error": "MetaTrader5 nu este instalat"}

    with _lock:
        try:
            if not _mt5.initialize():
                return {
                    "symbols": [],
                    "error": f"MT5 nu este disponibil — asigura-te ca MT5 desktop este deschis si logat",
                }
            syms = _mt5.symbols_get()
            if syms is None:
                return {"symbols": [], "error": "symbols_get() nu a returnat date"}
            names = sorted(s.name for s in syms)
            _cache = {"symbols": names, "cached_at": datetime.now()}
            return {"symbols": names, "error": None}
        except Exception as e:
            return {"symbols": [], "error": str(e)}
        finally:
            try:
                _mt5.shutdown()
            except Exception:
                pass


_TF_MAP = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 16385, "H4": 16388, "D1": 16408,
}


@router.get("/atr")
def get_atr(
    symbols: str = Query(..., description="Simboluri separate prin virgula, ex: EURUSD,GBPUSD"),
    tf: str = Query("M15"),
    period: int = Query(14),
):
    """ATR(period) pe ultimele 14+10 bare, per simbol. Returneaza ATR in unitati de pret."""
    if not _HAS_MT5:
        return {"error": "MetaTrader5 nu este instalat", "data": {}}

    sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
    tf_id    = _TF_MAP.get(tf.upper(), 15)
    result   = {}

    try:
        if not _mt5.initialize():
            return {"error": "MT5 offline — deschide MT5 desktop", "data": {}}

        for sym in sym_list:
            rates = _mt5.copy_rates_from_pos(sym, tf_id, 0, period + 10)
            if rates is None or len(rates) < 2:
                result[sym] = None
                continue
            high  = np.array([r[2] for r in rates])
            low   = np.array([r[3] for r in rates])
            close = np.array([r[4] for r in rates])
            prev  = np.roll(close, 1); prev[0] = close[0]
            tr    = np.maximum.reduce([high - low, np.abs(high - prev), np.abs(low - prev)])
            atr   = float(tr[-period:].mean())

            # Calculeaza pip_size
            info  = _mt5.symbol_info(sym)
            point = info.point if info else 0.00001
            digits = info.digits if info else 5
            pip_size = point * 10 if digits in (3, 5) else point
            atr_pips = round(atr / pip_size, 1) if pip_size > 0 else None

            result[sym] = {
                "atr":      round(atr, max(digits, 2)),
                "atr_pips": atr_pips,
                "pip_size": pip_size,
                "digits":   digits,
            }

    except Exception as e:
        return {"error": str(e), "data": {}}
    finally:
        try:
            _mt5.shutdown()
        except Exception:
            pass

    return {"error": None, "data": result}
