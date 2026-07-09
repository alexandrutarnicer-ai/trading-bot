"""
m0.session_runner — ruleaza un backtest de sesiune si returneaza seria de trade-uri.

Mapping-ul profil-sesiune -> parametri run_portfolio este COPIAT VERBATIM din
api/routers/backtest.py::_run_backtest_job, ca sa reproducem exact ce ruleaza
dashboard-ul (aceleasi costuri, aceleasi filtre, acelasi split). Diferenta unica:
aici nu depindem de FastAPI/MT5 si acceptam optional o fereastra de date
(date_from/date_to) pentru evaluarea pe fold-uri (CPCV/walk-forward).

Contract:
    run_profile_session(session_cfg, data_dir=DATA_DIR, config_path=CONFIG,
                        start_balance=..., date_from=None, date_to=None)
      -> (trades_df, meta)

    trades_df: DataFrame cu coloanele din run_portfolio + coloana derivata "R"
               (= pnl_usd / risk_usd) si "entry_t" (datetime intrare).
               Gol daca nu s-a generat niciun trade.
    meta:      dict cu total_trades, split_time, data_from_actual, data_to_actual,
               skipped_markets, skipped_margin.

Validare: run_with_params(...) reproduce exact baseline-urile documentate
(portfolio_backtest.py -> 284 trade-uri). Vezi m0/validate_runner.py.
"""

import os
import json
import copy

import numpy as np
import pandas as pd

from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol_tf
from engine.portfolio import run_portfolio


# Tabel de spread-uri — copiat verbatim din api/routers/backtest.py (SPREAD_DEFAULTS).
# Trebuie tinut sincronizat manual daca cel din API se schimba.
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
    # Crypto — spreads in TICKS
    "BTCUSD": 12.0, "XRPUSD": 30.0, "ETHUSD": 5.0,
}

# Simboluri cu pip value mare — au nevoie de balanta de start mai mare ca sa
# treaca de lotul minim 0.01 (altfel 0 trade-uri din cauza marjei).
_HIGH_PV_SYMBOLS = {"XAUUSD", "GER40", "US30", "UK100", "NAS100"}


def _load_base_cfg(config_path: str = CONFIG) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def _apply_session_to_cfg(cfg: dict, s: dict) -> dict:
    """Suprascrie cfg (strategy) cu parametrii sesiunii — verbatim din API."""
    cfg = copy.deepcopy(cfg)
    cfg["reward_ladder"]["rr_if_3_criteria"] = s["r_base"]
    cfg["reward_ladder"]["rr_if_4_criteria"] = s["r_mid"]
    cfg["reward_ladder"]["rr_if_5_criteria"] = s["r_top"]
    if "r_max" in s:
        cfg["reward_ladder"]["rr_if_6_criteria"] = s["r_max"]
    cfg["optional_criteria"]["rsi"]["enabled"]  = s["rsi_enabled"]
    cfg["optional_criteria"]["rsi"]["buy_min"]  = s["rsi_buy_min"]
    cfg["optional_criteria"]["rsi"]["buy_max"]  = s["rsi_buy_max"]
    cfg["optional_criteria"]["rsi"]["sell_min"] = s["rsi_sell_min"]
    cfg["optional_criteria"]["rsi"]["sell_max"] = s["rsi_sell_max"]
    cfg["optional_criteria"]["ema_alignment"]["enabled"] = s["ema_alignment_enabled"]
    cfg["optional_criteria"]["body_strength"] = {
        "enabled":       s.get("body_strength_enabled", False),
        "min_atr_ratio": s.get("body_strength_min_atr_ratio", 0.15),
    }
    cfg["optional_criteria"]["adx_d1"] = {"enabled": s.get("adx_d1_enabled", False)}
    cfg["reward_ladder"]["threshold_mid"] = s.get("r_mid_threshold", 1)
    cfg["reward_ladder"]["threshold_top"] = s.get("r_top_threshold", 2)
    cfg["reward_ladder"]["threshold_max"] = s.get("r_max_threshold", 3)
    if "r_max" in s:
        cfg["reward_ladder"]["rr_if_6_criteria"] = s["r_max"]

    risk_base = s.get("risk_base", s.get("risk_pct", 0.01))
    risk_top  = s.get("risk_top", risk_base)
    cfg["account"]["risk_per_trade_pct"] = risk_base * 100
    cfg["account"]["risk_per_trade_pct_all_criteria"] = risk_top * 100

    cfg["session"]["start_hour"] = s.get("session_start", cfg["session"]["start_hour"])
    cfg["session"]["end_hour"]   = s.get("session_end",   cfg["session"]["end_hour"])
    return cfg


def _build_params(s: dict, data: dict, start_balance: float) -> dict:
    """Construieste dict-ul de params pentru run_portfolio — verbatim din API."""
    skip_hours = tuple(s.get("skip_hours", []))
    skip_wd    = set(s.get("skip_weekdays", []))
    if s.get("friday_close_enabled", True):
        skip_wd |= {5, 6}
    return {
        "spread_pips":                {sym: SPREAD_DEFAULTS.get(sym, 1.0) for sym in data},
        "leverage":                   30,
        "start_balance":              start_balance,
        "expire_bars":                s["expire_bars"],
        "pullback_window":            s["pullback_window"],
        "depth_range":                None,
        "skip_monday":                0 in skip_wd,
        "skip_weekdays":              skip_wd,
        "skip_hours":                 skip_hours,
        "atr_max_pips":               s.get("atr_max_pips", {}),
        "max_day_consec_losses":      s.get("circuit_breaker", 3),
        "corr_pairs":                 {},
        "max_pos_per_symbol":         s.get("max_concurrent_per_market", 1),
        "min_bars_between_same_symbol": s.get("min_bars_between_trades", 0),
        "symbol_sessions":            {},
        "symbol_skip_hours":          {},
        "only_long":                  s["direction"] == "LONG",
        "pullback_enabled":           s.get("pullback_enabled", True),
        "be_cfg": {
            "enabled":         s.get("break_even_enabled", False),
            "phase2_enabled":  s.get("be_phase2_enabled",  True),
            "trigger_pct":     s.get("be_trigger_pct",    80),
            "lock1_pct":       s.get("be_lock1_pct",      30),
            "lock2_pct":       s.get("be_lock2_pct",      50),
            "phase2_zone_pct": s.get("be_phase2_zone_pct", 40),
        },
        "flag_cfg": {
            "enabled":  s.get("flag_enabled",  False),
            "r_ratio":  s.get("flag_r_ratio",  2.0),
            "risk_pct": s.get("flag_risk_pct", 0.01),
        },
        "inside_bar_cfg": {
            "enabled":  s.get("inside_bar_enabled",  False),
            "r_ratio":  s.get("inside_bar_r_ratio",  2.0),
            "risk_pct": s.get("inside_bar_risk_pct", 0.01),
        },
    }


def _default_start_balance(markets: list[str]) -> float:
    """Balanta de start suficient de mare pentru lot minim (evita 0-trade pe pip mare)."""
    if "XAUUSD" in markets:
        return 2000.0
    if any(m in _HIGH_PV_SYMBOLS for m in markets):
        return 1500.0
    return 1000.0


def run_profile_session(session_cfg: dict,
                        data_dir: str = DATA_DIR,
                        config_path: str = CONFIG,
                        start_balance: float | None = None,
                        date_from: str | None = None,
                        date_to: str | None = None,
                        base_cfg: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """Ruleaza backtestul pentru o sesiune din profil. Vezi docstring modul."""
    s = session_cfg
    markets = s["markets"]
    if start_balance is None:
        start_balance = _default_start_balance(markets)

    cfg = _apply_session_to_cfg(base_cfg or _load_base_cfg(config_path), s)

    src  = CsvDataSource(data_dir)
    data = {}
    for symbol in markets:
        try:
            df = prepare_symbol_tf(src, symbol, cfg, s["entry_tf"], s["trend_tf"])
            if df is not None and len(df) > 100:
                data[symbol] = df
        except Exception:
            pass

    skipped_markets = [m for m in markets if m not in data]
    meta = {"skipped_markets": skipped_markets, "total_trades": 0,
            "split_time": None, "data_from_actual": None, "data_to_actual": None,
            "skipped_margin": 0}
    if not data:
        return pd.DataFrame(), meta

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
            return pd.DataFrame(), meta

    all_times = pd.concat([df["time"] for df in data.values()])
    meta["data_from_actual"] = str(all_times.min().date())
    meta["data_to_actual"]   = str(all_times.max().date())

    params = _build_params(s, data, start_balance)
    trades, equity, balance, max_conc, skipped_margin, halted_days, split_time = \
        run_portfolio(data, cfg, params, verbose=False)

    meta["skipped_margin"] = skipped_margin
    meta["split_time"]     = split_time
    if not trades:
        return pd.DataFrame(), meta

    df_t = pd.DataFrame(trades)
    df_t["R"]       = df_t["pnl_usd"] / df_t["risk_usd"]
    df_t["entry_t"] = pd.to_datetime(df_t["time"])
    df_t = df_t.sort_values("entry_t").reset_index(drop=True)
    meta["total_trades"] = len(df_t)
    return df_t, meta


def run_with_params(cfg: dict, params: dict, symbols: list[str],
                    data_dir: str = DATA_DIR,
                    entry_tf: str = "M15", trend_tf: str = "M30") -> pd.DataFrame:
    """
    Runner low-level pentru VALIDARE: primeste direct cfg + params (ca in
    portfolio_backtest.py) si returneaza trade-urile. Folosit ca sa dovedim
    ca apelul de engine reproduce baseline-urile documentate.
    """
    src  = CsvDataSource(data_dir)
    data = {}
    for sym in symbols:
        try:
            data[sym] = prepare_symbol_tf(src, sym, cfg, entry_tf, trend_tf)
        except FileNotFoundError:
            pass
    if not data:
        return pd.DataFrame()
    trades, *_ = run_portfolio(data, cfg, params, verbose=False)
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame(trades)
    df["R"] = df["pnl_usd"] / df["risk_usd"]
    return df
