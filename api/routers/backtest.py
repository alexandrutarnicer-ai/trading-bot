"""
Backtest runner async — job-based cu persistenta pe disc.
POST /api/backtest/run   → { job_id }
GET  /api/backtest/jobs  → [ { job_id, status, ... } ]
GET  /api/backtest/{job_id} → { status, results, error }
DELETE /api/backtest/jobs/{job_id}
"""

import os
import sys
import json
import uuid
import threading
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol_tf
from engine.portfolio import run_portfolio

router = APIRouter(prefix="/backtest", tags=["backtest"])

JOBS_FILE  = os.path.join(DATA_DIR, "backtest_jobs.json")
MAX_JOBS   = 150

_jobs_lock = threading.Lock()

# ── Persistenta ──────────────────────────────────────────────────────────────

def _load_from_file() -> list[dict]:
    try:
        if os.path.exists(JOBS_FILE):
            with open(JOBS_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_to_file(jobs: list[dict]) -> None:
    """Salveaza lista de joburi pe disc. Apeleaza cu _jobs_lock tinut."""
    try:
        # Prune: pastreaza max MAX_JOBS, cele mai noi mai intai
        if len(jobs) > MAX_JOBS:
            running  = [j for j in jobs if j["status"] in ("pending", "running")]
            finished = sorted(
                [j for j in jobs if j["status"] not in ("pending", "running")],
                key=lambda j: j.get("started_at", ""),
                reverse=True,
            )[: MAX_JOBS - len(running)]
            jobs = running + finished
        with open(JOBS_FILE, "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# Incarcare la startup si recuperare joburi intrerupte
_jobs_list: list[dict] = _load_from_file()
for _j in _jobs_list:
    if _j.get("status") in ("pending", "running"):
        _j["status"]       = "error"
        _j["error"]        = "Job întrerupt — serverul API a fost repornit."
        _j["completed_at"] = datetime.now().isoformat(timespec="seconds")
_save_to_file(_jobs_list)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_job(job_id: str) -> dict | None:
    return next((j for j in _jobs_list if j["job_id"] == job_id), None)


def _update_job(job_id: str, **kwargs) -> None:
    with _jobs_lock:
        job = _find_job(job_id)
        if job:
            job.update(kwargs)
        _save_to_file(_jobs_list)


SPREAD_DEFAULTS = {
    "EURUSD": 0.5, "GBPUSD": 0.8, "EURJPY": 1.5,
    "USDJPY": 0.6, "AUDJPY": 1.2, "NZDJPY": 1.5,
    "USDCHF": 1.0, "USDCAD": 1.2, "AUDUSD": 0.7,
    "BTCUSD": 12.0,
    "GER40": 1.0, "US30": 2.0, "US500": 0.5, "XAUUSD": 0.3,
}


# ── Runner ────────────────────────────────────────────────────────────────────

def _run_backtest_job(
    job_id: str,
    session_cfg: dict,
    date_from:    str | None = None,
    date_to:      str | None = None,
    start_balance: float = 1000,
) -> None:
    _update_job(job_id, status="running")
    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)

        cfg["reward_ladder"]["rr_if_3_criteria"]  = session_cfg["r_base"]
        cfg["reward_ladder"]["rr_if_4_criteria"]  = session_cfg["r_mid"]
        cfg["reward_ladder"]["rr_if_5_criteria"]  = session_cfg["r_top"]
        if "r_max" in session_cfg:
            cfg["reward_ladder"]["rr_if_6_criteria"] = session_cfg["r_max"]
        cfg["optional_criteria"]["rsi"]["enabled"]   = session_cfg["rsi_enabled"]
        cfg["optional_criteria"]["rsi"]["buy_min"]   = session_cfg["rsi_buy_min"]
        cfg["optional_criteria"]["rsi"]["buy_max"]   = session_cfg["rsi_buy_max"]
        cfg["optional_criteria"]["rsi"]["sell_min"]  = session_cfg["rsi_sell_min"]
        cfg["optional_criteria"]["rsi"]["sell_max"]  = session_cfg["rsi_sell_max"]
        cfg["optional_criteria"]["ema_alignment"]["enabled"] = session_cfg["ema_alignment_enabled"]
        cfg["optional_criteria"]["body_strength"] = {
            "enabled":       session_cfg.get("body_strength_enabled", False),
            "min_atr_ratio": session_cfg.get("body_strength_min_atr_ratio", 0.15),
        }
        cfg["reward_ladder"]["threshold_mid"] = session_cfg.get("r_mid_threshold", 1)
        cfg["reward_ladder"]["threshold_top"] = session_cfg.get("r_top_threshold", 2)
        cfg["reward_ladder"]["threshold_max"] = session_cfg.get("r_max_threshold", 3)
        if "r_max" in session_cfg:
            cfg["reward_ladder"]["rr_if_6_criteria"] = session_cfg["r_max"]

        src  = CsvDataSource(DATA_DIR)
        data = {}
        for symbol in session_cfg["markets"]:
            try:
                df = prepare_symbol_tf(
                    src, symbol, cfg,
                    session_cfg["entry_tf"],
                    session_cfg["trend_tf"],
                )
                if df is not None and len(df) > 100:
                    data[symbol] = df
            except Exception:
                pass

        skipped_markets = [s for s in session_cfg["markets"] if s not in data]

        if not data:
            _update_job(
                job_id,
                status="error",
                error="Nicio piata disponibila in date CSV. Piete lipsa: " +
                      ", ".join(skipped_markets),
                completed_at=datetime.now().isoformat(timespec="seconds"),
            )
            return

        if date_from or date_to:
            filtered = {}
            for sym, df in data.items():
                df_f = df
                if date_from:
                    df_f = df_f[df_f["time"] >= pd.Timestamp(date_from)]
                if date_to:
                    df_f = df_f[df_f["time"] <= pd.Timestamp(date_to)]
                if len(df_f) > 100:
                    filtered[sym] = df_f.reset_index(drop=True)
            data = filtered
            if not data:
                _update_job(
                    job_id,
                    status="error",
                    error="Nicio piata cu date in intervalul selectat",
                    completed_at=datetime.now().isoformat(timespec="seconds"),
                )
                return

        all_times_raw   = pd.concat([df["time"] for df in data.values()])
        data_from_actual = str(all_times_raw.min().date())
        data_to_actual   = str(all_times_raw.max().date())

        skip_hours = tuple(session_cfg.get("skip_hours", []))
        skip_wd    = set(session_cfg.get("skip_weekdays", []))

        params = {
            "spread_pips":                {s: SPREAD_DEFAULTS.get(s, 1.0) for s in data},
            "leverage":                   30,
            "start_balance":              start_balance,
            "expire_bars":                session_cfg["expire_bars"],
            "pullback_window":            session_cfg["pullback_window"],
            "depth_range":                None,
            "skip_monday":                0 in skip_wd,
            "skip_hours":                 skip_hours,
            "atr_max_pips":               session_cfg.get("atr_max_pips", {}),
            "max_day_consec_losses":      session_cfg.get("circuit_breaker", 3),
            "corr_pairs":                 {},
            "max_pos_per_symbol":         1,
            "min_bars_between_same_symbol": 0,
            "symbol_sessions":            {},
            "symbol_skip_hours":          {},
            "only_long":                  session_cfg["direction"] == "LONG",
        }

        trades, equity, balance, max_concurrent, skipped_margin, halted_days, split_time = \
            run_portfolio(data, cfg, params)

        if not trades:
            _update_job(
                job_id,
                status="error",
                error="Niciun trade generat",
                completed_at=datetime.now().isoformat(timespec="seconds"),
            )
            return

        df_t = pd.DataFrame(trades)
        df_t["R"] = df_t["pnl_usd"] / df_t["risk_usd"]
        df_t["entry_t"] = pd.to_datetime(df_t["time"])

        wins  = int((df_t["outcome"] == "win").sum())
        total = len(df_t)

        eq_arr = np.array([e["balance"] for e in equity])
        peak   = np.maximum.accumulate(eq_arr)
        dd     = float(((eq_arr - peak) / peak).min() * 100)

        train = df_t[df_t["entry_t"] < split_time]
        test  = df_t[df_t["entry_t"] >= split_time]

        per_symbol = {}
        for sym in df_t["symbol"].unique():
            sub = df_t[df_t["symbol"] == sym]
            w   = int((sub["outcome"] == "win").sum())
            per_symbol[sym] = {
                "trades":     len(sub),
                "win_rate":   round(w / len(sub) * 100, 1) if len(sub) else 0,
                "expectancy": round(float(sub["R"].mean()), 3),
            }

        _update_job(job_id,
            status="done",
            completed_at=datetime.now().isoformat(timespec="seconds"),
            results={
                "total_trades": total,
                "win_rate":     round(wins / total * 100, 1) if total else 0,
                "expectancy":   round(float(df_t["R"].mean()), 3),
                "max_dd":       round(dd, 1),
                "split_date":   str(split_time.date()),
                "date_from":    data_from_actual,
                "date_to":      data_to_actual,
                "start_balance": start_balance,
                "train": {
                    "trades":     len(train),
                    "expectancy": round(float(train["R"].mean()), 3) if len(train) else 0,
                },
                "test": {
                    "trades":     len(test),
                    "expectancy": round(float(test["R"].mean()), 3) if len(test) else 0,
                },
                "per_symbol":      per_symbol,
                "markets":         session_cfg["markets"],
                "skipped_markets": skipped_markets,
                "session_id":      session_cfg.get("id", ""),
            },
        )

    except Exception as e:
        import traceback
        _update_job(
            job_id,
            status="error",
            error=f"{e}\n{traceback.format_exc()}",
            completed_at=datetime.now().isoformat(timespec="seconds"),
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/run")
def run_backtest(body: dict):
    session_cfg = body.get("session")
    if not session_cfg:
        raise HTTPException(400, "session lipsa in body")

    date_from     = body.get("date_from") or None
    date_to       = body.get("date_to")   or None
    start_balance = float(body.get("start_balance") or 1000)

    job_id = str(uuid.uuid4())[:8]
    new_job = {
        "job_id":          job_id,
        "status":          "pending",
        "session_id":      session_cfg.get("id", ""),
        "session_label":   session_cfg.get("label", session_cfg.get("id", "")),
        "markets":         session_cfg.get("markets", []),
        "entry_tf":        session_cfg.get("entry_tf", "M15"),
        "trend_tf":        session_cfg.get("trend_tf", "M30"),
        "direction":       session_cfg.get("direction", "LONG"),
        "started_at":      datetime.now().isoformat(timespec="seconds"),
        "completed_at":    None,
        "date_from":       date_from,
        "date_to":         date_to,
        "start_balance":   start_balance,
        "error":           None,
        "results":         None,
        "session_snapshot": body.get("session_snapshot"),
    }

    with _jobs_lock:
        _jobs_list.insert(0, new_job)
        _save_to_file(_jobs_list)

    t = threading.Thread(
        target=_run_backtest_job,
        args=(job_id, session_cfg, date_from, date_to, start_balance),
        daemon=True,
    )
    t.start()

    return {"job_id": job_id}


@router.get("/jobs")
def list_jobs():
    with _jobs_lock:
        return list(_jobs_list)


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    global _jobs_list
    with _jobs_lock:
        job = _find_job(job_id)
        if not job:
            raise HTTPException(404, f"Job necunoscut: {job_id}")
        if job["status"] in ("pending", "running"):
            raise HTTPException(400, "Nu poti sterge un job in curs de rulare")
        _jobs_list = [j for j in _jobs_list if j["job_id"] != job_id]
        _save_to_file(_jobs_list)
    return {"ok": True}


@router.get("/{job_id}")
def get_result(job_id: str):
    with _jobs_lock:
        job = _find_job(job_id)
    if not job:
        raise HTTPException(404, f"Job necunoscut: {job_id}")
    return job
