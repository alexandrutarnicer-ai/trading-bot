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
    # Forex major — pips standard
    "EURUSD": 0.5, "GBPUSD": 0.8, "EURJPY": 1.5,
    "USDJPY": 0.6, "AUDJPY": 1.2, "NZDJPY": 1.5,
    "USDCHF": 1.0, "USDCAD": 1.2, "AUDUSD": 0.7,
    # Forex crosses (estimate ICMarketsEU)
    "EURCAD": 1.5, "GBPCAD": 1.8, "EURAUD": 1.5,
    "GBPAUD": 2.0, "AUDCAD": 1.5, "AUDNZD": 1.5,
    "CHFJPY": 1.5, "GBPJPY": 1.5,
    # Indici
    "GER40": 1.0, "US30": 2.0, "US500": 0.5, "XAUUSD": 0.3,
    # Crypto — spreads in TICKS (pip_size mic, trebuie mai multi ticks)
    # BTCUSD: pip=0.01, spread real ~$12 = 1200 ticks → 12.0 in pips (pip=1.0 pt BTC dupa PIP_SIZE?)
    "BTCUSD": 12.0,
    # XRPUSD: pip=0.00001, spread real ~0.0003 price = 30 ticks (era 1.0 = practic 0 → backteste optimiste!)
    "XRPUSD": 30.0,
    # ETHUSD: similar cu BTC
    "ETHUSD": 5.0,
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
        import logging
        _log = logging.getLogger("backtest.job")
        _log.warning(
            "[BACKTEST DEBUG] job=%s flag_enabled=%s inside_bar_enabled=%s",
            job_id,
            session_cfg.get("flag_enabled"),
            session_cfg.get("inside_bar_enabled"),
        )
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

        # Task 3: aplica risk% din sesiune (nu din legacy config)
        risk_base = session_cfg.get("risk_base", session_cfg.get("risk_pct", 0.01))
        risk_top  = session_cfg.get("risk_top", risk_base)
        cfg["account"]["risk_per_trade_pct"] = risk_base * 100
        cfg["account"]["risk_per_trade_pct_all_criteria"] = risk_top * 100

        # Ore sesiune din profil (altfel hardcodat 10-18 din standard_profile.json)
        cfg["session"]["start_hour"] = session_cfg.get("session_start", cfg["session"]["start_hour"])
        cfg["session"]["end_hour"]   = session_cfg.get("session_end",   cfg["session"]["end_hour"])

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
        # Daca inchiderea vineri e activa, skip automat Sambata (5) si Duminica (6)
        if session_cfg.get("friday_close_enabled", True):
            skip_wd |= {5, 6}

        params = {
            "spread_pips":                {s: SPREAD_DEFAULTS.get(s, 1.0) for s in data},
            "leverage":                   30,
            "start_balance":              start_balance,
            "expire_bars":                session_cfg["expire_bars"],
            "pullback_window":            session_cfg["pullback_window"],
            "depth_range":                None,
            "skip_monday":                0 in skip_wd,
            "skip_weekdays":              skip_wd,
            "skip_hours":                 skip_hours,
            "atr_max_pips":               session_cfg.get("atr_max_pips", {}),
            "max_day_consec_losses":      session_cfg.get("circuit_breaker", 3),
            "corr_pairs":                 {},
            # Task 7: max_concurrent_per_market si min_bars_between_trades din sesiune
            "max_pos_per_symbol":         session_cfg.get("max_concurrent_per_market", 1),
            "min_bars_between_same_symbol": session_cfg.get("min_bars_between_trades", 0),
            "symbol_sessions":            {},
            "symbol_skip_hours":          {},
            "only_long":                  session_cfg["direction"] == "LONG",
            "be_cfg": {
                "enabled":         session_cfg.get("break_even_enabled", False),
                "phase2_enabled":  session_cfg.get("be_phase2_enabled",  True),
                "trigger_pct":     session_cfg.get("be_trigger_pct",    80),
                "lock1_pct":       session_cfg.get("be_lock1_pct",      30),
                "lock2_pct":       session_cfg.get("be_lock2_pct",      50),
                "phase2_zone_pct": session_cfg.get("be_phase2_zone_pct", 40),
            },
            "flag_cfg": {
                "enabled":   session_cfg.get("flag_enabled",   False),
                "r_ratio":   session_cfg.get("flag_r_ratio",   2.0),
                "risk_pct":  session_cfg.get("flag_risk_pct",  0.01),
            },
            "inside_bar_cfg": {
                "enabled":   session_cfg.get("inside_bar_enabled",   False),
                "r_ratio":   session_cfg.get("inside_bar_r_ratio",   2.0),
                "risk_pct":  session_cfg.get("inside_bar_risk_pct",  0.01),
            },
        }

        trades, equity, balance, max_concurrent, skipped_margin, halted_days, split_time = \
            run_portfolio(data, cfg, params)

        _HIGH_PV_SYMBOLS = {"XAUUSD", "GER40", "US30", "UK100", "NAS100"}
        if not trades:
            if skipped_margin and skipped_margin > 0:
                err_msg = (
                    f"Capital insuficient pentru marjă — {skipped_margin} trade-uri respinse. "
                    f"Mărește capitalul sesiunii (cel puțin 100 USD per piață pentru lot minim 0.01)."
                )
            elif any(s in _HIGH_PV_SYMBOLS for s in session_cfg.get("markets", [])):
                min_needed = max(
                    1000 if "XAUUSD" in session_cfg.get("markets", []) else 400,
                    400,
                )
                err_msg = (
                    f"Niciun trade generat. Probabil capitalul alocat este prea mic pentru lot minim "
                    f"(0.01 loturi). {', '.join(session_cfg.get('markets', []))} necesită minim "
                    f"~{min_needed} USD capital per piață. Mărește account_fraction în profil."
                )
            else:
                err_msg = "Niciun trade generat"
            _update_job(
                job_id,
                status="error",
                error=err_msg,
                completed_at=datetime.now().isoformat(timespec="seconds"),
            )
            return

        df_t = pd.DataFrame(trades)
        df_t["R"] = df_t["pnl_usd"] / df_t["risk_usd"]
        df_t["entry_t"] = pd.to_datetime(df_t["time"])

        wins  = int(df_t["outcome"].isin(["win", "be_lock", "be_lock2"]).sum())
        be_lock_count  = int((df_t["outcome"] == "be_lock").sum())
        be_lock2_count = int((df_t["outcome"] == "be_lock2").sum())
        total = len(df_t)

        # Statistici per tip semnal
        def _sig_type_stats(type_name: str) -> dict:
            if "signal_type" not in df_t.columns:
                return {"trades": 0, "win_rate": 0.0, "expectancy": 0.0}
            sub = df_t[df_t["signal_type"] == type_name]
            if len(sub) == 0:
                return {"trades": 0, "win_rate": 0.0, "expectancy": 0.0}
            w = int(sub["outcome"].isin(["win", "be_lock", "be_lock2"]).sum())
            return {
                "trades":     len(sub),
                "win_rate":   round(w / len(sub) * 100, 1),
                "expectancy": round(float(sub["R"].mean()), 3),
            }
        flag_stats       = _sig_type_stats("flag")
        inside_bar_stats = _sig_type_stats("inside_bar")

        eq_arr = np.array([e["balance"] for e in equity])
        peak   = np.maximum.accumulate(eq_arr)
        dd     = float(((eq_arr - peak) / peak).min() * 100)

        train = df_t[df_t["entry_t"] < split_time]
        test  = df_t[df_t["entry_t"] >= split_time]

        per_symbol = {}
        for sym in df_t["symbol"].unique():
            sub = df_t[df_t["symbol"] == sym]
            w   = int(sub["outcome"].isin(["win", "be_lock", "be_lock2"]).sum())
            per_symbol[sym] = {
                "trades":     len(sub),
                "win_rate":   round(w / len(sub) * 100, 1) if len(sub) else 0,
                "expectancy": round(float(sub["R"].mean()), 3),
            }

        # Statistici per directie (LONG vs SHORT) — doar pentru sesiuni BOTH
        direction_stats: dict = {}
        if "dir" in df_t.columns and not params.get("only_long"):
            for dir_val, dir_name in [(1, "LONG"), (-1, "SHORT")]:
                sub = df_t[df_t["dir"] == dir_val]
                if len(sub) > 0:
                    w = int(sub["outcome"].isin(["win", "be_lock", "be_lock2"]).sum())
                    direction_stats[dir_name] = {
                        "trades":     len(sub),
                        "wins":       w,
                        "losses":     int((sub["outcome"] == "loss").sum()),
                        "win_rate":   round(w / len(sub) * 100, 1),
                        "expectancy": round(float(sub["R"].mean()), 3),
                    }

        final_balance = float(eq_arr[-1]) if len(eq_arr) else start_balance

        # Task 4: Analiza pierderi per zi a saptamanii si per ora
        _WD_NAMES = ["Luni", "Marți", "Miercuri", "Joi", "Vineri", "Sâmbătă", "Duminică"]
        weekday_stats: dict = {}
        for wd in range(7):
            sub = df_t[df_t["entry_t"].dt.weekday == wd]
            if len(sub) == 0:
                continue
            losses = int((sub["outcome"] == "loss").sum())
            weekday_stats[wd] = {
                "name":       _WD_NAMES[wd],
                "trades":     len(sub),
                "losses":     losses,
                "loss_rate":  round(losses / len(sub) * 100, 1),
                "expectancy": round(float(sub["R"].mean()), 3),
            }

        hour_stats: dict = {}
        for h in sorted(df_t["entry_t"].dt.hour.unique()):
            sub = df_t[df_t["entry_t"].dt.hour == int(h)]
            losses = int((sub["outcome"] == "loss").sum())
            hour_stats[int(h)] = {
                "trades":     len(sub),
                "losses":     losses,
                "loss_rate":  round(losses / len(sub) * 100, 1),
                "expectancy": round(float(sub["R"].mean()), 3),
            }

        _update_job(job_id,
            status="done",
            completed_at=datetime.now().isoformat(timespec="seconds"),
            results={
                "total_trades":    total,
                "win_rate":        round(wins / total * 100, 1) if total else 0,
                "flag_was_enabled":        bool(session_cfg.get("flag_enabled", False)),
                "inside_bar_was_enabled":  bool(session_cfg.get("inside_bar_enabled", False)),
                "expectancy":      round(float(df_t["R"].mean()), 3),
                "max_dd":          round(dd, 1),
                "split_date":      str(split_time.date()),
                "date_from":       data_from_actual,
                "date_to":         data_to_actual,
                "start_balance":   start_balance,
                "final_balance":   round(final_balance, 2),
                "be_lock_count":   be_lock_count,
                "be_lock2_count":  be_lock2_count,
                "skipped_margin":  skipped_margin,
                "flag_stats":       flag_stats,
                "inside_bar_stats": inside_bar_stats,
                "train": {
                    "trades":     len(train),
                    "expectancy": round(float(train["R"].mean()), 3) if len(train) else 0,
                },
                "test": {
                    "trades":     len(test),
                    "expectancy": round(float(test["R"].mean()), 3) if len(test) else 0,
                },
                "per_symbol":       per_symbol,
                "direction_stats":  direction_stats,
                "markets":          session_cfg["markets"],
                "skipped_markets":  skipped_markets,
                "session_id":       session_cfg.get("id", ""),
                # Task 4: analiza pierderi per zi/ora
                "weekday_stats":    weekday_stats,
                "hour_stats":       hour_stats,
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_session_snapshot(cfg: dict, frontend_snap: dict | None = None) -> dict:
    """Construieste snapshot complet al configuratiei sesiunii din session_cfg.
    Parametrii de capital/alocare vin din frontend_snap daca exista."""
    snap: dict = {}
    for key in (
        # Identitate sesiune (necesara pentru Apply Config)
        "direction",
        # Strategie
        "pullback_window", "expire_bars", "circuit_breaker",
        # Ore
        "session_start", "session_end", "skip_hours", "skip_weekdays",
        # R-ladder
        "r_base", "r_mid", "r_top", "r_max",
        "r_mid_threshold", "r_top_threshold", "r_max_threshold",
        # Risk
        "risk_base", "risk_mid", "risk_top", "risk_max",
        # Criterii optionale
        "rsi_enabled", "rsi_buy_min", "rsi_buy_max", "rsi_sell_min", "rsi_sell_max",
        "ema_alignment_enabled",
        "body_strength_enabled", "body_strength_min_atr_ratio",
        # Break-even
        "break_even_enabled", "be_trigger_pct", "be_lock1_pct", "be_lock2_pct",
        "be_phase2_enabled", "be_phase2_zone_pct",
        # Vineri
        "friday_close_enabled", "friday_close_hour",
        # Stiri
        "news_protection_enabled", "news_impact_level", "news_pre_minutes", "news_post_minutes",
        # Tranzactionare
        "max_concurrent_per_market", "min_bars_between_trades",
        # Strategii optionale (flag / inside bar)
        "flag_enabled", "flag_r_ratio", "flag_risk_pct",
        "inside_bar_enabled", "inside_bar_r_ratio", "inside_bar_risk_pct",
    ):
        if cfg.get(key) is not None:
            snap[key] = cfg[key]
    # Capital/alocare vine din frontend
    fs = frontend_snap or {}
    for key in ("market_allocations", "start_balance"):
        if fs.get(key) is not None:
            snap[key] = fs[key]
    return snap


# ── Endpoints ─────────────────────────────────────────────────────────────────

def _create_and_start_backtest_job(config: dict) -> str:
    """Creează și pornește un job de backtest. Returnează job_id. Apelabil din cod."""
    session_cfg  = config["session_cfg"]
    date_from    = config.get("date_from")
    date_to      = config.get("date_to")
    start_balance = float(config.get("start_balance", 1000))
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
        "session_snapshot": _build_session_snapshot(session_cfg),
        "auto_triggered":  True,
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
    return job_id


@router.post("/run")
def run_backtest(body: dict):
    session_cfg = body.get("session")
    if not session_cfg:
        raise HTTPException(400, "session lipsa in body")

    import logging
    _log = logging.getLogger("backtest.endpoint")
    _log.warning(
        "[BACKTEST ENDPOINT] markets=%s flag_enabled=%s inside_bar_enabled=%s",
        session_cfg.get("markets"),
        session_cfg.get("flag_enabled"),
        session_cfg.get("inside_bar_enabled"),
    )

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
        "session_snapshot": _build_session_snapshot(session_cfg, body.get("session_snapshot")),
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


@router.post("/run-missing")
def run_missing_backtests(body: dict = {}):
    """Triggerează backteste pentru sesiunile fără backtest recent.
    Cu force=True, rerulează TOATE sesiunile (inclusiv cele cu backtest existent).
    Verifică dacă datele CSV există; dacă nu, pornește descărcarea întâi."""
    from api.routers.data_download import (
        csv_exists_for_session, start_download_job, register_pending_backtest
    )

    profile_id = body.get("profile_id", "")
    force      = bool(body.get("force", False))
    _PROFILES_DIR = os.path.join(DATA_DIR, "profiles")
    _ACTIVE_FILE  = os.path.join(DATA_DIR, "active_profile.json")
    _PAUSED_FILE  = os.path.join(DATA_DIR, "paused_sessions.json")

    if not profile_id:
        try:
            if os.path.exists(_ACTIVE_FILE):
                profile_id = json.load(open(_ACTIVE_FILE, encoding="utf-8")).get("id", "")
        except Exception:
            pass
    if not profile_id:
        profile_id = "standard"

    pfile = os.path.join(_PROFILES_DIR, f"{profile_id}.json")
    if not os.path.exists(pfile):
        return {"job_ids": [], "triggered": 0, "downloads_triggered": 0}
    profile = json.load(open(pfile, encoding="utf-8"))
    start_balance = float(profile.get("start_balance", 1000))

    paused: list = []
    try:
        if os.path.exists(_PAUSED_FILE):
            paused = json.load(open(_PAUSED_FILE, encoding="utf-8"))
    except Exception:
        pass

    with _jobs_lock:
        jobs_done = [j for j in reversed(_jobs_list) if j.get("status") == "done"]
    latest_job: dict[str, dict] = {}
    for j in jobs_done:
        sid = j.get("session_id", "")
        if sid and sid not in latest_job:
            latest_job[sid] = j

    job_ids = []
    downloads_triggered = 0

    for ps in profile.get("sessions", []):
        sess_id  = ps.get("id", "")
        sess_key = ps.get("session_key", "")
        if not ps.get("execute_trades", True):
            continue
        if sess_key in paused:
            continue
        if not force and sess_id in latest_job:
            continue

        # Construieste session_cfg din profil
        session_cfg = {
            "id":              sess_id,
            "session_key":     sess_key,
            "label":           ps.get("label", sess_id),
            "markets":         ps.get("markets", []),
            "entry_tf":        ps.get("entry_tf", "M15"),
            "trend_tf":        ps.get("trend_tf", "M30"),
            "direction":       ps.get("direction", "LONG"),
            "pullback_window": ps.get("pullback_window", 8),
            "session_start":   ps.get("session_start", 8),
            "session_end":     ps.get("session_end", 18),
            "skip_hours":      ps.get("skip_hours", []),
            "skip_weekdays":   ps.get("skip_weekdays", []),
            "expire_bars":     ps.get("expire_bars", 4),
            "execute_trades":  True,
            "only_long":       ps.get("direction", "LONG") == "LONG",
            "rsi_enabled":     ps.get("rsi_enabled", True),
            "rsi_buy_min":     ps.get("rsi_buy_min", 40),
            "rsi_buy_max":     ps.get("rsi_buy_max", 65),
            "rsi_sell_min":    ps.get("rsi_sell_min", 35),
            "rsi_sell_max":    ps.get("rsi_sell_max", 60),
            "ema_alignment_enabled":    ps.get("ema_alignment_enabled", True),
            "body_strength_enabled":    ps.get("body_strength_enabled", False),
            "body_strength_min_atr_ratio": ps.get("body_strength_min_atr_ratio", 0.15),
            "r_base": ps.get("r_base", 2.5), "r_mid": ps.get("r_mid", 3.5),
            "r_top":  ps.get("r_top",  4.5), "r_max": ps.get("r_max", 5.5),
            "r_mid_threshold": ps.get("r_mid_threshold", 1),
            "r_top_threshold": ps.get("r_top_threshold", 2),
            "r_max_threshold": ps.get("r_max_threshold", 3),
            "account_fraction": ps.get("account_fraction", 0.1),
            "risk_pct":  ps.get("risk_pct",  0.01),
            "break_even_enabled":   ps.get("break_even_enabled", False),
            "be_trigger_pct":       ps.get("be_trigger_pct",  80),
            "be_lock1_pct":         ps.get("be_lock1_pct",    30),
            "be_lock2_pct":         ps.get("be_lock2_pct",    50),
            "be_phase2_zone_pct":   ps.get("be_phase2_zone_pct", 40),
            "be_phase2_enabled":    ps.get("be_phase2_enabled", True),
            "flag_enabled":         ps.get("flag_enabled", False),
            "inside_bar_enabled":   ps.get("inside_bar_enabled", False),
            "min_bars_between_trades":  ps.get("min_bars_between_trades", 0),
            "max_concurrent_per_market": ps.get("max_concurrent_per_market", 1),
        }

        date_from = "2021-01-01"
        date_to   = datetime.now().strftime("%Y-%m-%d")
        markets   = session_cfg["markets"]
        entry_tf  = session_cfg["entry_tf"]
        trend_tf  = session_cfg["trend_tf"]

        bt_config = {
            "session_cfg":   session_cfg,
            "date_from":     date_from,
            "date_to":       date_to,
            "start_balance": start_balance,
        }

        if csv_exists_for_session(markets, entry_tf, trend_tf):
            # Date CSV există → pornește backtest direct
            jid = _create_and_start_backtest_job(bt_config)
            job_ids.append(jid)
        else:
            # Date CSV lipsesc → pornește descărcarea, înregistrează backtest pending
            tfs = list(dict.fromkeys([entry_tf, trend_tf]))
            label = f"Auto: {sess_id} — {'+'.join(markets)}"
            dl_job_id = start_download_job(markets, tfs, label)
            register_pending_backtest(dl_job_id, bt_config)
            downloads_triggered += 1

    return {
        "job_ids": job_ids,
        "triggered": len(job_ids),
        "downloads_triggered": downloads_triggered,
    }


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
