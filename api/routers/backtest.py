"""
Backtest runner async — job-based.
POST /api/backtest/run   → { job_id }
GET  /api/backtest/{job_id} → { status, results }
"""

import os
import sys
import json
import uuid
import threading
import numpy as np
import pandas as pd
from typing import Optional
from fastapi import APIRouter, HTTPException

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol_tf
from engine.portfolio import run_portfolio

router = APIRouter(prefix="/backtest", tags=["backtest"])

# In-memory job store (suficient pentru uz local single-user)
_jobs: dict[str, dict] = {}


SPREAD_DEFAULTS = {
    "EURUSD": 0.5, "GBPUSD": 0.8, "EURJPY": 1.5,
    "USDJPY": 0.6, "AUDJPY": 1.2, "NZDJPY": 1.5,
    "USDCHF": 1.0, "USDCAD": 1.2, "AUDUSD": 0.7,
    "BTCUSD": 12.0,
    "GER40": 1.0, "US30": 2.0, "US500": 0.5, "XAUUSD": 0.3,
}


def _run_backtest_job(job_id: str, session_cfg: dict,
                      date_from: str | None = None,
                      date_to: str | None = None,
                      start_balance: float = 1000) -> None:
    _jobs[job_id]["status"] = "running"
    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)

        # Aplica parametrii profilului peste config standard
        cfg["reward_ladder"]["rr_if_3_criteria"]  = session_cfg["r_base"]
        cfg["reward_ladder"]["rr_if_4_criteria"]  = session_cfg["r_mid"]
        cfg["reward_ladder"]["rr_if_5_criteria"]  = session_cfg["r_top"]
        cfg["optional_criteria"]["rsi"]["enabled"]   = session_cfg["rsi_enabled"]
        cfg["optional_criteria"]["rsi"]["buy_min"]   = session_cfg["rsi_buy_min"]
        cfg["optional_criteria"]["rsi"]["buy_max"]   = session_cfg["rsi_buy_max"]
        cfg["optional_criteria"]["rsi"]["sell_min"]  = session_cfg["rsi_sell_min"]
        cfg["optional_criteria"]["rsi"]["sell_max"]  = session_cfg["rsi_sell_max"]
        cfg["optional_criteria"]["ema_alignment"]["enabled"] = session_cfg["ema_alignment_enabled"]

        src = CsvDataSource(DATA_DIR)
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

        if not data:
            _jobs[job_id].update({"status": "error", "error": "Nicio piata disponibila in date CSV"})
            return

        # Retine intervalul real al datelor inainte de filtrare date
        all_times_raw = pd.concat([df["time"] for df in data.values()])
        data_from_actual = str(all_times_raw.min().date())
        data_to_actual   = str(all_times_raw.max().date())

        # Filtreaza intervalul de date daca e specificat
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
                _jobs[job_id].update({"status": "error",
                                      "error": "Nicio piata cu date in intervalul selectat"})
                return

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
            _jobs[job_id].update({"status": "error", "error": "Niciun trade generat"})
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

        _jobs[job_id].update({
            "status": "done",
            "results": {
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
                "per_symbol": per_symbol,
                "markets":    session_cfg["markets"],
                "session_id": session_cfg.get("id", ""),
            },
        })

    except Exception as e:
        import traceback
        _jobs[job_id].update({"status": "error", "error": f"{e}\n{traceback.format_exc()}"})


@router.post("/run")
def run_backtest(body: dict):
    """
    body: { session: <session config dict>, date_from?: "YYYY-MM-DD", date_to?: "YYYY-MM-DD" }
    """
    session_cfg = body.get("session")
    if not session_cfg:
        raise HTTPException(400, "session lipsa in body")

    date_from     = body.get("date_from") or None
    date_to       = body.get("date_to")   or None
    start_balance = float(body.get("start_balance") or 1000)

    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {"status": "pending", "results": None, "error": None}

    t = threading.Thread(
        target=_run_backtest_job,
        args=(job_id, session_cfg, date_from, date_to, start_balance),
        daemon=True,
    )
    t.start()

    return {"job_id": job_id}


@router.get("/{job_id}")
def get_result(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job necunoscut: {job_id}")
    return job
