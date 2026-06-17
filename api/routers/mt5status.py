"""
MT5 connection status endpoint.
GET /api/mt5/status — verifica daca MT5 este deschis si logat.
"""

import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from fastapi import APIRouter

router = APIRouter(prefix="/mt5", tags=["mt5"])


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
                "error": f"MT5 nu s-a putut initializa: {err}",
            }
        info = mt5.account_info()
        mt5.shutdown()
        if info is None:
            return {
                "connected": False,
                "account": None, "server": None,
                "balance": None, "equity": None, "currency": None,
                "error": "Nu ești logat pe niciun cont MT5",
            }
        return {
            "connected": True,
            "account": str(info.login),
            "server": info.server,
            "balance": round(info.balance, 2),
            "equity": round(info.equity, 2),
            "currency": info.currency,
            "error": None,
        }
    except ImportError:
        return {
            "connected": False,
            "account": None, "server": None,
            "balance": None, "equity": None, "currency": None,
            "error": "MetaTrader5 nu este instalat",
        }
    except Exception as e:
        return {
            "connected": False,
            "account": None, "server": None,
            "balance": None, "equity": None, "currency": None,
            "error": str(e),
        }
