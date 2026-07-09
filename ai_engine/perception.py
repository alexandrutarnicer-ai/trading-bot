"""
ai_engine.perception — ochii motorului: snapshot numeric al pietei.

Ruleaza la fiecare bara M15, gratuit (pura matematica, fara LLM). Reutilizeaza
strategy.preparation._enrich (aceiasi indicatori ca botul pe reguli) + calendarul
ForexFactory din live.news_guard. Produce:
  - snapshot dict (persistat in ledger)
  - render_text(snapshot) — briefing compact pe care il citesc agentii AI
"""

from __future__ import annotations

import os
import json
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from backtest import CONFIG
from strategy.preparation import _enrich
from live.news_guard import _fetch_forexfactory, SYMBOL_CURRENCIES


def _load_strategy_cfg() -> dict:
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


_STRAT_CFG = _load_strategy_cfg()

# Cache calendar cu TTL — fara el, 5 piete/bara = 10 fetch-uri HTTP identice
# la fiecare 15 min. Cu el: 1 fetch / 10 min pentru toate pietele.
_CAL_TTL_S = 600
_cal_cache: list = []
_cal_time:  datetime | None = None


def _calendar() -> list[dict]:
    global _cal_cache, _cal_time
    now = datetime.utcnow()
    if _cal_time is None or (now - _cal_time).total_seconds() > _CAL_TTL_S:
        try:
            _cal_cache = _fetch_forexfactory()
            _cal_time  = now
        except Exception:
            # pastram cache-ul vechi (chiar expirat) — mai bun decat nimic
            _cal_time = now
    return _cal_cache


def build_snapshot(src, symbol: str, n_news_hours: int = 24) -> dict:
    """
    Construieste snapshot-ul de piata pentru `symbol` din sursa MT5 `src`.
    Foloseste DOAR bare inchise (ultimul rand complet inainte de bara curenta).
    """
    m15 = src.load_bars(symbol, "M15")
    m30 = src.load_bars(symbol, "M30")
    df = _enrich(m15.copy(), m30.copy(), _STRAT_CFG)

    # ultima bara INCHISA: -2 (ultima e bara in formare)
    row  = df.iloc[-2]
    hist = df.iloc[:-1]           # tot ce e inchis

    price = float(row["close"])
    atr   = float(row["atr"])
    atr_series = hist["atr"].tail(500).dropna()
    atr_pctile = float((atr_series < atr).mean() * 100) if len(atr_series) > 20 else None

    # structura: ultimele swinguri confirmate (S/R naturale)
    sw_h = hist[hist["swing_high"]]["high"].tail(3).tolist()
    sw_l = hist[hist["swing_low"]]["low"].tail(3).tolist()

    # range recent
    h20 = float(hist["high"].tail(20).max())
    l20 = float(hist["low"].tail(20).min())

    def _ret(bars: int) -> float | None:
        if len(hist) <= bars:
            return None
        prev = float(hist["close"].iloc[-1 - bars])
        return round((price - prev) / prev * 100, 3)

    # stiri urmatoare pentru valutele simbolului
    currencies = SYMBOL_CURRENCIES.get(symbol, [])
    events = []
    try:
        now_utc = datetime.utcnow()
        for ev in _calendar():
            if ev["currency"] not in currencies:
                continue
            dt_min = (ev["event_time"] - now_utc).total_seconds() / 60
            if -30 <= dt_min <= n_news_hours * 60 and ev["impact"] in ("High", "Medium"):
                events.append({
                    "title":    ev["title"],
                    "currency": ev["currency"],
                    "impact":   ev["impact"],
                    "in_min":   int(dt_min),
                    "forecast": ev.get("forecast", ""),
                    "actual":   ev.get("actual", ""),
                })
        events.sort(key=lambda e: e["in_min"])
        events = events[:8]
    except Exception:
        events = []   # calendarul e best-effort; snapshot-ul ramane valid

    bar_time = pd.Timestamp(row["time"])
    return {
        "symbol":       symbol,
        "bar_time":     str(bar_time),
        "price":        price,
        "trend_m30":    int(row["trend"]),           # EMA200 M30: 1/-1/0
        "trend_d1":     int(row["daily_trend"]),     # EMA200 D1: 1/-1
        "adx_d1_gt25":  int(row["f2_adx"]),          # trend puternic pe D1
        "weekly_up":    int(row["f1_weekly"]),       # EMA50 W1
        "rsi":          round(float(row["rsi"]), 1),
        "ema_align":    _ema_alignment(row),
        "atr":          round(atr, 6),
        "atr_pctile":   round(atr_pctile, 1) if atr_pctile is not None else None,
        "swing_highs":  [round(x, 5) for x in sw_h],
        "swing_lows":   [round(x, 5) for x in sw_l],
        "high_20":      round(h20, 5),
        "low_20":       round(l20, 5),
        "ret_1h_pct":   _ret(4),
        "ret_4h_pct":   _ret(16),
        "ret_1d_pct":   _ret(96),
        "weekday":      int(bar_time.weekday()),     # 0=Luni
        "hour":         int(bar_time.hour),          # ora RO
        "news":         events,
    }


def _ema_alignment(row) -> str:
    if row["ema_fast"] > row["ema_mid"] > row["ema_slow"]:
        return "bullish"
    if row["ema_fast"] < row["ema_mid"] < row["ema_slow"]:
        return "bearish"
    return "mixed"


_WD = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_TREND = {1: "UP", -1: "DOWN", 0: "FLAT"}


def render_text(s: dict) -> str:
    """Briefing compact, citibil de LLM. Doar fapte, zero interpretare."""
    lines = [
        f"MARKET BRIEFING — {s['symbol']} @ {s['price']} ({_WD[s['weekday']]}, {s['hour']:02d}:00 Romania time, bar close {s['bar_time']})",
        f"Trend M30 (EMA200): {_TREND[s['trend_m30']]} | Trend D1 (EMA200): {_TREND[s['trend_d1']]} | "
        f"Weekly (EMA50): {'UP' if s['weekly_up'] else 'DOWN/FLAT'} | D1 ADX>25: {'YES' if s['adx_d1_gt25'] else 'no'}",
        f"EMA 8/20/50 alignment: {s['ema_align']} | RSI(14): {s['rsi']}",
        f"ATR(14): {s['atr']} (percentile vs last 500 bars: {s['atr_pctile']}%)",
        f"Recent swing highs (resistance): {s['swing_highs']} | swing lows (support): {s['swing_lows']}",
        f"20-bar range: {s['low_20']} .. {s['high_20']}",
        f"Returns: 1h {s['ret_1h_pct']}% | 4h {s['ret_4h_pct']}% | 1d {s['ret_1d_pct']}%",
    ]
    if s["news"]:
        lines.append("Upcoming economic events (minutes from now):")
        for ev in s["news"]:
            extra = f" forecast={ev['forecast']}" if ev.get("forecast") else ""
            lines.append(f"  - in {ev['in_min']}min [{ev['impact']}] {ev['currency']}: {ev['title']}{extra}")
    else:
        lines.append("Upcoming economic events: none relevant in the next 24h.")
    return "\n".join(lines)
