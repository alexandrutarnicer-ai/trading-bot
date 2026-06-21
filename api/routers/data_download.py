"""
GET    /api/data/check              — verifica daca fisierele CSV exista
POST   /api/data/download           — descarca date din MT5 (async job, persistent)
GET    /api/data/download/{job_id}  — status job descarcare
GET    /api/data/jobs               — lista toate joburile de descarcare
DELETE /api/data/jobs/{job_id}      — sterge un job finalizat
"""
import json
import os
import sys
import uuid
import threading
from datetime import datetime
from fastapi import APIRouter, HTTPException

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from backtest import DATA_DIR

import pandas as pd

router = APIRouter(prefix="/data", tags=["data"])

DOWNLOAD_JOBS_FILE = os.path.join(DATA_DIR, "download_jobs.json")
MAX_DOWNLOAD_JOBS  = 50

_jobs_lock = threading.Lock()
_mt5_lock  = threading.Lock()

# Variante de nume per indice — brokeri diferiti pot folosi denumiri diferite
SYMBOL_ALIASES: dict[str, list[str]] = {
    "GER40":  ["GER40",  "DE40",    "DAX40",    "GER40Cash", "DAX",    "GDAX"],
    "US30":   ["US30",   "DJ30",    "DJIA",     "US30Cash",  "WS30"],
    "US500":  ["US500",  "SP500",   "SPX500",   "US500Cash"],
    "UK100":  ["UK100",  "FTSE100", "UK100Cash", "FTSE"],
    "US100":  ["US100",  "NAS100",  "NASDAQ100", "US100Cash"],
    "XAUUSD": ["XAUUSD", "GOLD",    "XAUUSDm"],
    "BTCUSD": ["BTCUSD", "BTCUSDT", "BTCUSDm"],
}

try:
    import MetaTrader5 as _mt5
    _HAS_MT5 = True
except ImportError:
    _mt5 = None
    _HAS_MT5 = False

_N_BARS = {"M5": 80_000, "M15": 60_000, "M30": 60_000,
           "H1": 30_000, "H4": 10_000, "D1": 2_500}


# ── Persistenta ───────────────────────────────────────────────────────────────

def _load_jobs() -> list[dict]:
    try:
        if os.path.exists(DOWNLOAD_JOBS_FILE):
            with open(DOWNLOAD_JOBS_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_jobs(jobs: list[dict]) -> None:
    try:
        if len(jobs) > MAX_DOWNLOAD_JOBS:
            running  = [j for j in jobs if j["status"] in ("pending", "running")]
            finished = sorted(
                [j for j in jobs if j["status"] not in ("pending", "running")],
                key=lambda j: j.get("started_at", ""),
                reverse=True,
            )[:MAX_DOWNLOAD_JOBS - len(running)]
            jobs = running + finished
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(DOWNLOAD_JOBS_FILE, "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


_jobs_list: list[dict] = _load_jobs()
# Recuperare la startup: joburi intrerupte → error
for _j in _jobs_list:
    if _j.get("status") in ("pending", "running"):
        _j["status"]       = "error"
        _j["error"]        = "Descărcare întreruptă — API repornit."
        _j["completed_at"] = datetime.now().isoformat(timespec="seconds")
_save_jobs(_jobs_list)


def _find_job(job_id: str) -> dict | None:
    return next((j for j in _jobs_list if j["job_id"] == job_id), None)


def _update_job(job_id: str, **kwargs) -> None:
    with _jobs_lock:
        job = _find_job(job_id)
        if job:
            job.update(kwargs)
        _save_jobs(_jobs_list)


# ── Helpers ──────────────────────────────────────────────────────────────────

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
    tfs = list(dict.fromkeys([entry_tf, trend_tf]))
    results = [_file_info(sym, tf) for sym in symbols for tf in tfs]
    missing = [r for r in results if not r["exists"]]
    return {"results": results, "all_available": not missing, "missing": missing}


# ── Worker ────────────────────────────────────────────────────────────────────

def _download_job(job_id: str, symbols: list[str], timeframes: list[str]) -> None:
    _update_job(job_id, status="running")
    results: list[dict] = []

    if not _HAS_MT5:
        _update_job(job_id, status="error",
                    error="MetaTrader5 nu este instalat",
                    results=[],
                    completed_at=datetime.now().isoformat(timespec="seconds"))
        return

    with _mt5_lock:
        try:
            if not _mt5.initialize():
                _update_job(job_id,
                    status="error",
                    error="MT5 nu este disponibil — deschide MT5 si logheaza-te.",
                    results=[],
                    completed_at=datetime.now().isoformat(timespec="seconds"))
                return

            for sym in symbols:
                # Cauta aliasuri — incearca candidatii in ordine
                candidates = SYMBOL_ALIASES.get(sym, [sym])
                if candidates[0] != sym:
                    candidates = [sym] + [c for c in candidates if c != sym]

                mt5_sym = None
                for candidate in candidates:
                    if _mt5.symbol_select(candidate, True):
                        info = _mt5.symbol_info(candidate)
                        if info is not None:
                            mt5_sym = candidate
                            break

                if mt5_sym is None:
                    tried = ", ".join(candidates[:5])
                    # Cauta simboluri similare disponibile la broker
                    suggestions = []
                    try:
                        base = sym.upper()
                        # Incearca cautare partiala (ex: "EURUSD" poate fi "EURUSDm")
                        similar = _mt5.symbols_get(group=f"*{base}*") or []
                        suggestions = [s.name for s in similar if s.name not in candidates][:4]
                    except Exception:
                        pass
                    if not suggestions and len(sym) >= 6:
                        # Incearca cu primele 3 si ultimele 3 caractere separat
                        try:
                            prefix = _mt5.symbols_get(group=f"*{sym[:3]}*") or []
                            suggestions = [
                                s.name for s in prefix
                                if sym[:3] in s.name and s.name not in candidates
                            ][:3]
                        except Exception:
                            pass

                    error_msg = f"Simbolul nu există în MT5 (încercat: {tried})"
                    if suggestions:
                        error_msg += f". Variante găsite la broker: {', '.join(suggestions)}"
                    else:
                        error_msg += ". Verifică Market Watch în MT5 (View → Market Watch → Show All)."

                    results.append({
                        "symbol": sym, "mt5_symbol": None, "tf": "—",
                        "success": False, "bars": 0, "needs_scroll": False,
                        "suggestions": suggestions,
                        "error": error_msg,
                    })
                    continue

                for tf_name in timeframes:
                    tf_const = getattr(_mt5, f"TIMEFRAME_{tf_name}", None)
                    if tf_const is None:
                        continue

                    n = _N_BARS.get(tf_name, 30_000)
                    rates = _mt5.copy_rates_from_pos(mt5_sym, tf_const, 0, n)

                    if rates is None or len(rates) == 0:
                        results.append({
                            "symbol": sym, "mt5_symbol": mt5_sym,
                            "tf": tf_name, "success": False, "bars": 0,
                            "needs_scroll": True,
                            "error": (
                                f"Nu s-au primit date pentru {mt5_sym} {tf_name}. "
                                f"Deschide graficul {mt5_sym}/{tf_name} în MT5 și derulează "
                                f"complet spre stânga pentru a forța descărcarea istoricului."
                            ),
                        })
                        continue

                    df = pd.DataFrame(rates)
                    df["time"] = pd.to_datetime(df["time"], unit="s")
                    path = os.path.join(DATA_DIR, f"{sym}_{tf_name}.csv")
                    df.to_csv(path, index=False)
                    results.append({
                        "symbol": sym, "mt5_symbol": mt5_sym,
                        "tf": tf_name, "success": True,
                        "bars": len(df), "needs_scroll": False, "error": None,
                    })

            any_scroll = any(r["needs_scroll"] for r in results)
            _update_job(job_id,
                status="done",
                results=results,
                any_needs_scroll=any_scroll,
                error=None,
                completed_at=datetime.now().isoformat(timespec="seconds"))

        except Exception as e:
            _update_job(job_id,
                status="error", error=str(e), results=results,
                completed_at=datetime.now().isoformat(timespec="seconds"))
        finally:
            try:
                _mt5.shutdown()
            except Exception:
                pass


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/jobs")
def list_download_jobs():
    return sorted(_jobs_list, key=lambda j: j.get("started_at", ""), reverse=True)


@router.delete("/jobs/{job_id}")
def delete_download_job(job_id: str):
    with _jobs_lock:
        job = _find_job(job_id)
        if not job:
            raise HTTPException(404, f"Job necunoscut: {job_id}")
        if job["status"] in ("pending", "running"):
            raise HTTPException(400, "Nu se poate șterge un job în rulare")
        _jobs_list.remove(job)
        _save_jobs(_jobs_list)
    return {"deleted": True}


@router.post("/download")
def start_download(body: dict):
    symbols    = body.get("markets", [])
    timeframes = body.get("timeframes", [])
    label      = body.get("label", "")
    if not symbols or not timeframes:
        raise HTTPException(400, "markets si timeframes sunt necesare")

    job_id = str(uuid.uuid4())[:8]
    now    = datetime.now().isoformat(timespec="seconds")
    if not label:
        label = f"{' · '.join(symbols)} — {'+'.join(timeframes)}"

    job: dict = {
        "job_id":          job_id,
        "status":          "pending",
        "label":           label,
        "markets":         symbols,
        "timeframes":      timeframes,
        "started_at":      now,
        "completed_at":    None,
        "results":         [],
        "any_needs_scroll": False,
        "error":           None,
    }
    with _jobs_lock:
        _jobs_list.append(job)
        _save_jobs(_jobs_list)

    t = threading.Thread(target=_download_job, args=(job_id, symbols, timeframes), daemon=True)
    t.start()
    return {"job_id": job_id}


@router.get("/download/{job_id}")
def get_download_status(job_id: str):
    job = _find_job(job_id)
    if not job:
        raise HTTPException(404, f"Job necunoscut: {job_id}")
    return job
