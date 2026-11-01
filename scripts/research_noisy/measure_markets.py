"""
Noisy Engine — research: masuratori REALE din MT5 (read-only, ZERO ordine).

Pentru fiecare piata candidata, pe ultima saptamana de trading din tick-urile reale ale brokerului:
  • spread (ask-bid) median / P90 / P99, pe ora (ora RO)
  • frecventa tick-urilor (tick-uri / minut)
  • range-ul tipic pe M1 si M5 (high-low) din tick-uri
  • costul unei tranzactii dus-intors (spread + comision real din istoricul contului) raportat la range
  • specificatii: lot minim, pas, stops level, freeze level, tick value, filling, marja la lot minim
  • disponibilitate: Depth of Market (market_book), real volume, adancimea istoricului de tick-uri,
    latenta apelurilor Python -> terminal

    python scripts/research_noisy/measure_markets.py   ->  data/research_noisy/market_metrics.json
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import MetaTrader5 as mt5

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "research_noisy")
sys.stdout.reconfigure(encoding="utf-8")

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", "XAGUSD", "USTEC", "US500", "US30", "DE40",
           "BTCUSD", "ETHUSD"]
if os.environ.get("SYMBOLS"):                 # ex: SYMBOLS=XRPUSD,USDCAD  OUT_NAME=market_metrics_extra.json
    SYMBOLS = os.environ["SYMBOLS"].split(",")
OUT_NAME = os.environ.get("OUT_NAME", "market_metrics.json")
# ultima saptamana de trading inainte de 1 nov 2026 (ora serverului ICMarkets = UTC+3 in acea saptamana,
# SUA inca pe ora de vara; RO = UTC+2 dupa 25 oct) -> RO = server - 1h
WEEK_START = datetime(2026, 10, 26, 0, 0, tzinfo=timezone.utc)
WEEK_END = datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc)
SERVER_TO_RO_H = -1


def commission_per_lot() -> dict:
    """Comisionul REAL per lot (dus-intors) pe simbol, din istoricul dealurilor contului."""
    deals = mt5.history_deals_get(datetime(2025, 1, 1), datetime.now() + timedelta(days=1)) or []
    acc: dict = {}
    for d in deals:
        if d.type not in (0, 1) or d.volume <= 0:
            continue
        a = acc.setdefault(d.symbol, [0.0, 0.0])
        a[0] += d.commission
        a[1] += d.volume
    # comisionul se percepe la intrare si la iesire -> per lot dus-intors = 2 x (comision / volum) per deal
    return {s: round(abs(c) / v * 2, 3) for s, (c, v) in acc.items() if v > 0}


def call_latency_ms(sym: str, n: int = 200) -> dict:
    t = []
    for _ in range(n):
        t0 = time.perf_counter()
        mt5.symbol_info_tick(sym)
        t.append((time.perf_counter() - t0) * 1000)
    return {"median_ms": round(st.median(t), 3), "p99_ms": round(float(np.percentile(t, 99)), 3)}


def measure(sym: str, comm: dict) -> dict:
    info = mt5.symbol_info(sym)
    if info is None:
        return {"symbol": sym, "error": "inexistent"}
    mt5.symbol_select(sym, True)
    out = {"symbol": sym, "description": info.description, "digits": info.digits, "point": info.point,
           "tick_size": info.trade_tick_size, "tick_value": info.trade_tick_value,
           "contract_size": info.trade_contract_size, "vol_min": info.volume_min, "vol_step": info.volume_step,
           "stops_level_pts": info.trade_stops_level, "freeze_level_pts": info.trade_freeze_level,
           "filling_mode": info.filling_mode, "trade_mode": info.trade_mode,
           "swap_long": info.swap_long, "swap_short": info.swap_short}
    tick = mt5.symbol_info_tick(sym)
    price = (tick.ask + tick.bid) / 2 if tick and tick.ask else None
    try:
        out["margin_min_lot"] = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, sym, info.volume_min, price) if price else None
    except Exception:
        out["margin_min_lot"] = None
    # valoarea unei unitati de pret pentru lotul minim (USD)
    usd_per_price_unit_min_lot = info.trade_tick_value / info.trade_tick_size * info.volume_min
    out["usd_per_price_unit_min_lot"] = usd_per_price_unit_min_lot
    out["commission_rt_per_lot_usd"] = comm.get(sym)
    comm_rt_min_lot = (comm.get(sym) or 0.0) * info.volume_min
    comm_price = comm_rt_min_lot / usd_per_price_unit_min_lot if usd_per_price_unit_min_lot else 0.0

    # Depth of Market
    try:
        ok = mt5.market_book_add(sym)
        time.sleep(0.5)
        book = mt5.market_book_get(sym) if ok else None
        out["dom_available"] = bool(book)
        out["dom_levels"] = len(book) if book else 0
        mt5.market_book_release(sym)
    except Exception as e:
        out["dom_available"] = False
        out["dom_error"] = str(e)

    # adancimea istoricului de tick-uri
    first = None
    for y in (2018, 2020, 2022, 2024, 2025, 2026):
        tk = mt5.copy_ticks_from(sym, datetime(y, 1, 2, tzinfo=timezone.utc), 1, mt5.COPY_TICKS_ALL)
        if tk is not None and len(tk):
            first = datetime.fromtimestamp(int(tk[0]["time"]), tz=timezone.utc).date().isoformat()
            break
    out["tick_history_from"] = first

    ticks = mt5.copy_ticks_range(sym, WEEK_START, WEEK_END, mt5.COPY_TICKS_ALL)
    if ticks is None or len(ticks) < 1000:
        out["error"] = f"tick-uri insuficiente ({0 if ticks is None else len(ticks)})"
        return out
    df = pd.DataFrame(ticks)
    df = df[(df["bid"] > 0) & (df["ask"] > 0)]
    df["t"] = pd.to_datetime(df["time_msc"], unit="ms") + pd.Timedelta(hours=SERVER_TO_RO_H)
    df["spread"] = df["ask"] - df["bid"]
    df["mid"] = (df["ask"] + df["bid"]) / 2
    df["hour"] = df["t"].dt.hour
    out["ticks_week"] = int(len(df))
    out["real_volume_present"] = bool((df.get("volume_real", pd.Series([0])) > 0).any())

    # bare M1 / M5 din mid
    m1 = df.set_index("t")["mid"].resample("1min").agg(["max", "min", "count"]).dropna()
    m1 = m1[m1["count"] > 0]
    m1["range"] = m1["max"] - m1["min"]
    m5 = df.set_index("t")["mid"].resample("5min").agg(["max", "min"]).dropna()
    m5["range"] = m5["max"] - m5["min"]
    sp1 = df.set_index("t")["spread"].resample("1min").median().dropna()

    out["spread_median"] = float(df["spread"].median())
    out["spread_p90"] = float(df["spread"].quantile(0.9))
    out["spread_p99"] = float(df["spread"].quantile(0.99))
    out["ticks_per_min_median"] = float(m1["count"].median())
    out["m1_range_median"] = float(m1["range"].median())
    out["m5_range_median"] = float(m5["range"].median())
    cost_rt = out["spread_median"] + comm_price          # cost dus-intors in unitati de pret (fara slippage)
    out["comm_in_price"] = comm_price
    out["cost_rt_price"] = cost_rt
    out["cost_rt_usd_min_lot"] = cost_rt * usd_per_price_unit_min_lot
    out["cost_vs_m1_range"] = cost_rt / out["m1_range_median"] if out["m1_range_median"] else None
    out["cost_vs_m5_range"] = cost_rt / out["m5_range_median"] if out["m5_range_median"] else None

    # profil pe ora (RO): spread median, P90, tick-uri/min, range M1, cost/range
    hours = []
    for h in range(24):
        dh = df[df["hour"] == h]
        if len(dh) < 200:
            continue
        r1 = m1[m1.index.hour == h]
        s_med = float(dh["spread"].median())
        rng = float(r1["range"].median()) if len(r1) else None
        hours.append({"hour": h, "spread_med": s_med, "spread_p90": float(dh["spread"].quantile(0.9)),
                      "ticks_per_min": float(r1["count"].median()) if len(r1) else 0,
                      "m1_range": rng, "cost_vs_m1": ((s_med + comm_price) / rng) if rng else None})
    out["by_hour_ro"] = hours
    best = [h for h in hours if h["cost_vs_m1"] is not None]
    if best:
        b = min(best, key=lambda h: h["cost_vs_m1"])
        out["best_hour_ro"] = b["hour"]
        out["best_hour_cost_vs_m1"] = b["cost_vs_m1"]
    # spread maxim pe minut (pentru expansiuni la stiri / deschideri)
    out["spread_minute_p99_over_median"] = float(sp1.quantile(0.99) / sp1.median()) if sp1.median() else None
    out["call_latency"] = call_latency_ms(sym)
    return out


def main() -> None:
    assert mt5.initialize(), mt5.last_error()
    acc = mt5.account_info()
    os.makedirs(OUT, exist_ok=True)
    comm = commission_per_lot()
    res = {"account": {"login": acc.login, "server": acc.server, "is_demo": acc.trade_mode == 0,
                       "equity": acc.equity, "leverage": acc.leverage, "currency": acc.currency},
           "window_ro": [str(WEEK_START + timedelta(hours=SERVER_TO_RO_H)), str(WEEK_END + timedelta(hours=SERVER_TO_RO_H))],
           "commission_rt_per_lot_from_history": comm, "symbols": []}
    for s in SYMBOLS:
        t0 = time.time()
        r = measure(s, comm)
        res["symbols"].append(r)
        print(f"{s:8s} {time.time() - t0:5.1f}s  ticks={r.get('ticks_week')}  spread_med={r.get('spread_median')}  "
              f"m1={r.get('m1_range_median')}  cost/M1={r.get('cost_vs_m1_range')}  cost/M5={r.get('cost_vs_m5_range')}  "
              f"DOM={r.get('dom_available')}  {r.get('error', '')}", flush=True)
    with open(os.path.join(OUT, OUT_NAME), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, default=str)
    print("->", os.path.join(OUT, OUT_NAME))


if __name__ == "__main__":
    main()
