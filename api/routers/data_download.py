"""
GET  /api/data/check            — verifica daca fisierele CSV exista
POST /api/data/download         — descarca date din MT5 (async job)
GET  /api/data/download/{job_id} — status job descarcare
"""
import os
import sys
import uuid
import threading
from fastapi import APIRouter, HTTPException

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from backtest import DATA_DIR

import pandas as pd

router = APIRouter(prefix="/data", tags=["data"])

_jobs: dict[str, dict] = {}
_lock = threading.Lock()

try:
    import MetaTrader5 as _mt5
    _HAS_MT5 = True
except ImportError:
    _mt5 = None
    _HAS_MT5 = False

# Cate bare se descarca per timeframe
_N_BARS = {"M5": 80_000, "M15": 60_000, "M30": 60_000,
           "H1": 30_000, "H4": 10_000, "D1": 2_500}


def _file_info(symbol: str, tf: str) -> dict:
    path = os.path.join(DATA_DIR, f"{symbol}_{tf}.csv")
    if not os.path.exists(path):
        return {"symbol": symbol, "tf": tf, "exists": False, "bars": 0, "last_date": None}
    try:
        df = pd.read_csv(path, usecols=["time"], parse_dates=["time"])
        return {
            "symbol":    symbol,
            "tf":        tf,
            "exists":    True,
            "bars":      len(df),
            "last_date": str(df["time"].max().date()) if len(df) else None,
        }
    except Exception:
        return {"symbol": symbol, "tf": tf, "exists": False, "bars": 0, "last_date": None}


@router.get("/check")
def check_data(markets: str, entry_tf: str, trend_tf: str):
    symbols = [s.strip() for s in markets.split(",") if s.strip()]
    tfs = list(dict.fromkeys([entry_tf, trend_tf]))      # unic, in ordine
    results = [_file_info(sym, tf) for sym in symbols for tf in tfs]
    missing = [r for r in results if not r["exists"]]
    return {"results": results, "all_available": not missing, "missing": missing}


def _download_job(job_id: str, symbols: list[str], timeframes: list[str]) -> None:
    _jobs[job_id]["status"] = "running"
    results: list[dict] = []

    if not _HAS_MT5:
        _jobs[job_id].update({"status": "error",
                              "error": "MetaTrader5 nu este instalat", "results": []})
        return

    with _lock:
        try:
            if not _mt5.initialize():
                _jobs[job_id].update({
                    "status": "error",
                    "error": "MT5 nu este disponibil — deschide MT5 si logheaza-te.",
                    "results": [],
                })
                return

            for sym in symbols:
                if not _mt5.symbol_select(sym, True):
                    results.append({
                        "symbol": sym, "tf": "—", "success": False, "bars": 0,
                        "needs_scroll": False,
                        "error": f"Simbolul {sym} nu exista in MT5",
                    })
                    continue

                for tf_name in timeframes:
                    tf_const = getattr(_mt5, f"TIMEFRAME_{tf_name}", None)
                    if tf_const is None:
                        continue

                    n = _N_BARS.get(tf_name, 30_000)
                    rates = _mt5.copy_rates_from_pos(sym, tf_const, 0, n)

                    if rates is None or len(rates) == 0:
                        results.append({
                            "symbol": sym, "tf": tf_name, "success": False, "bars": 0,
                            "needs_scroll": True,
                            "error": (
                                f"Nu s-au primit date pentru {sym} {tf_name}. "
                                "Istoricul nu este descarcat in MT5."
                            ),
                        })
                        continue

                    df = pd.DataFrame(rates)
                    df["time"] = pd.to_datetime(df["time"], unit="s")
                    path = os.path.join(DATA_DIR, f"{sym}_{tf_name}.csv")
                    df.to_csv(path, index=False)
                    results.append({
                        "symbol": sym, "tf": tf_name, "success": True,
                        "bars": len(df), "needs_scroll": False, "error": None,
                    })

            any_scroll = any(r["needs_scroll"] for r in results)
            _jobs[job_id].update({
                "status":      "done",
                "results":     results,
                "any_needs_scroll": any_scroll,
                "error":       None,
            })

        except Exception as e:
            _jobs[job_id].update({"status": "error", "error": str(e), "results": results})
        finally:
            try:
                _mt5.shutdown()
            except Exception:
                pass


@router.post("/download")
def start_download(body: dict):
    symbols    = body.get("markets", [])
    timeframes = body.get("timeframes", [])
    if not symbols or not timeframes:
        raise HTTPException(400, "markets si timeframes sunt necesare")

    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {"status": "pending", "results": [], "any_needs_scroll": False, "error": None}
    t = threading.Thread(target=_download_job, args=(job_id, symbols, timeframes), daemon=True)
    t.start()
    return {"job_id": job_id}


@router.get("/download/{job_id}")
def get_download_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job necunoscut: {job_id}")
    return job
