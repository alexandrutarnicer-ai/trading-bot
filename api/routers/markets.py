"""
GET /api/markets/mt5  — simboluri disponibile in contul MT5 curent.
"""
import threading
from datetime import datetime
from fastapi import APIRouter

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
