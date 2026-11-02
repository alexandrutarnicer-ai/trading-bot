"""
Backtest Noisy Engine — EXACT functia folosita de engine (`noisy_engine.strategy.run_day`), zi cu zi,
pe istoricul M5 din MT5 (doar citire). Da referinta „shadow vs backtest” pentru configurarea curenta.

    python scripts/research_noisy/noisy_backtest.py                 # config curent (noisy_engine/config.json)
    python scripts/research_noisy/noisy_backtest.py --raw           # fara filtre / limite = strategia MR din research
    -> data/research_noisy/noisy_backtest[_raw].json

Diferente fata de engine-ul live (documentate): fara blocajele de stiri (nu exista istoric de calendar)
si fara protectiile globale (depind de starea contului la momentul respectiv).
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import MetaTrader5 as mt5

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

from noisy_engine.config import load_config, resolve_spread  # noqa: E402
from noisy_engine.engine import rates_to_bars, scorecard  # noqa: E402
from noisy_engine.strategy import run_day  # noqa: E402

START = datetime(2025, 11, 1, tzinfo=timezone.utc)
END = datetime(2026, 10, 31, tzinfo=timezone.utc)
OUT = os.path.join(ROOT, "data", "research_noisy")


def raw_cfg(cfg: dict) -> dict:
    c = copy.deepcopy(cfg)
    s = c["strategy"]
    s.update(cooldown_bars=0, cooldown_after_sl_bars=0, max_flips_per_hour=0, trend_filter=False,
             spread_max_mult=0, spread_max=0, min_atr_over_cost=0)
    for k in c["limits"]:
        c["limits"][k]["enabled"] = False
    return c


def backtest(cfg: dict, bars) -> list[dict]:
    days = sorted({t.date() for t in bars["t"]})
    trades = []
    # fiecare zi: aceleasi date pe care le-ar vedea engine-ul la sfarsitul zilei (istoric + ziua)
    tdates = np.array([t.date() for t in bars["t"]])
    for d in days:
        end = np.searchsorted(tdates, d, side="right")
        start = max(0, end - (2000 if cfg["timeframe"] == "M5" else 2400))   # >= o zi intreaga + istoric
        r = run_day(bars.iloc[start:end], d, cfg)
        tf_min = 1 if cfg.get("timeframe") == "M1" else 5
        trades += [{**t, "day": str(d), "hold_min": t["bars"] * tf_min} for t in r["trades"]]
    return trades


def stats(trades: list[dict]) -> dict:
    sc = scorecard(trades)
    x = np.array([t["R"] for t in trades])
    if len(x) > 2:
        sc["t_stat"] = round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2)
        days = len({t["day"] for t in trades})
        sc["per_day_active"] = round(len(x) / days, 2)
        split = int(len(x) * 0.7)
        sc["train_R"] = round(float(x[:split].mean()), 3)
        sc["test_R"] = round(float(x[split:].mean()), 3)
    return sc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", action="store_true")
    ap.add_argument("--tf", choices=["M1", "M5"], help="suprascrie timeframe-ul din config")
    ap.add_argument("--set", action="append", default=[], help="strategy.cheie=valoare / limits.cheie=valoare (enabled)")
    ap.add_argument("--spread-points", type=float, default=None,
                    help="spread TIPIC in points MT5 (ex. 9 = USDJPY live pe contul Standard). Fara el: sectiunea `spread` "
                         "din config; in mod auto (fara tick-uri live) = rezerva strategy.spread_floor (studiul initial)")
    a = ap.parse_args()
    assert mt5.initialize()
    cfg = load_config()
    if a.tf:
        cfg["timeframe"] = a.tf
    si = mt5.symbol_info(cfg["symbol"])
    if a.spread_points is not None:
        cfg["spread"]["mode"] = "auto"
    print("spread:", json.dumps(resolve_spread(cfg, si.point if si else None, a.spread_points, si.digits if si else None),
                                ensure_ascii=False))
    for kv in a.set:
        k, v = kv.split("=")
        sec, key = k.split(".")
        if sec == "limits":
            cfg["limits"][key] = {"enabled": v != "off", "value": int(v) if v != "off" else 1}
        else:
            cfg[sec][key] = float(v)
    if a.raw:
        cfg = raw_cfg(cfg)
    sym = cfg["symbol"]
    mt5.symbol_select(sym, True)
    rates = mt5.copy_rates_range(sym, getattr(mt5, f"TIMEFRAME_{cfg['timeframe']}"), START, END)
    bars = rates_to_bars(rates, None, mt5.symbol_info(sym).point)
    trades = backtest(cfg, bars)
    sc = stats(trades)
    trading_days = len({t.date() for t in bars["t"] if t.weekday() < 5})
    sc["per_day"] = round(len(trades) / max(1, trading_days), 2)
    sc["period"] = f"{START:%Y-%m-%d} → {END:%Y-%m-%d}"
    sc["config"] = ("raw (fara filtre/limite)" if a.raw else "configurarea curenta") + f" · {cfg['timeframe']} · {a.set}"
    print(json.dumps(sc, indent=1, ensure_ascii=False))
    os.makedirs(OUT, exist_ok=True)
    tag = ("_raw" if a.raw else "") + f"_{cfg['timeframe']}"
    with open(os.path.join(OUT, f"noisy_backtest{tag}.json"), "w", encoding="utf-8") as f:
        json.dump({"summary": sc, "trades": trades}, f, indent=1, default=str)


if __name__ == "__main__":
    main()
