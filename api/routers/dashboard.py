"""
Ritmul de tranzactionare pe engine — inlocuieste vechea „Frecventa estimata" (2026-10-31).

Vechea metrica: suma trades/saptamana din BACKTESTE, doar pentru botul pe reguli, recitita la 60s
(~0,2 s / apel). Comparata cu MT5 supraestima de ~4,5x (21/sapt estimat vs ~4,7/sapt real) si
ignora complet AI Engine (motorul cu cele mai multe trade-uri).

Metrica noua, per engine:
  - REAL: trade-uri INCHISE in MT5 pe saptamana, media ponderata exponential a ultimelor
    saptamani COMPLETE (timp de injumatatire 3 saptamani — recentul conteaza mai mult), cu
    intervalul tipic P20–P80 al saptamanilor. Doar dupa ultima schimbare de configuratie care
    afecteaza frecventa (piete, ore, strategii, executie) — istoricul de dinainte nu mai
    descrie comportamentul actual.
  - REPER: Custom = backtest (vechea estimare, ca sa se vada abaterea); Daily = structural
    (zile de bursa x piete x rata de zile tranzactionate din backtest); AI = fara reper.
  - INCREDERE: insuficient (< 2 saptamani complete sau < 5 trade-uri) / scazuta / medie / ridicata
    (dupa numarul de trade-uri si stabilitatea saptamanilor).
Calcul: din cache-ul MT5 al pool-ului (zero interogari MT5 in plus), rezultat cache-uit 15 min.
"""
from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timedelta

from fastapi import APIRouter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
router = APIRouter(prefix="/dashboard", tags=["dashboard"])

HALF_LIFE_WEEKS = 3.0
MAX_WEEKS = 12
CACHE_TTL_S = 900
_cache: dict = {"ts": 0.0, "data": None}

# Campuri de profil care schimba FRECVENTA (nu doar dimensiunea) trade-urilor
FREQ_FIELDS = {"execute_trades", "markets", "session_start", "session_end", "skip_hours",
               "skip_weekdays", "pullback_enabled", "inside_bar_enabled", "flag_enabled",
               "expire_bars", "pullback_window", "trend_tf", "entry_tf", "direction", "only_long"}

# Daily Engine — rata zilelor cu trade din backtestul M5 (docs/DAILY_ENGINE_PLAN.md sect. 8)
DAILY_DAY_RATE = {"GBPUSD": 3974 / 4335, "US500": 2464 / 2470}


def _week_start(d: datetime) -> datetime:
    d = d.replace(hour=0, minute=0, second=0, microsecond=0)
    return d - timedelta(days=d.weekday())


def pace(close_times: list[datetime], now: datetime, since: datetime | None) -> dict:
    """Ritm saptamanal din orele de inchidere (PUR, testabil).
    Foloseste doar saptamanile COMPLETE de dupa `since` (inceputul regimului curent)."""
    this_week = _week_start(now)
    start = _week_start(since) + timedelta(days=7) if since else None   # prima saptamana completa
    weeks = []
    for i in range(1, MAX_WEEKS + 1):
        ws = this_week - timedelta(days=7 * i)
        if start and ws < start:
            break
        we = ws + timedelta(days=7)
        weeks.append(sum(1 for t in close_times if ws <= t < we))
    current = sum(1 for t in close_times if t >= this_week)
    n_trades = sum(weeks)
    out = {"weeks": len(weeks), "trades_in_window": n_trades, "current_week": current,
           "per_week": None, "low": None, "high": None, "confidence": "insufficient",
           "weekly": list(reversed(weeks))}
    if len(weeks) < 2 or n_trades < 5:
        return out
    w = [0.5 ** (i / HALF_LIFE_WEEKS) for i in range(len(weeks))]      # i=0 = saptamana trecuta
    ewma = sum(c * wi for c, wi in zip(weeks, w)) / sum(w)
    srt = sorted(weeks)
    q = lambda p: srt[min(len(srt) - 1, max(0, round(p * (len(srt) - 1))))]
    mean = sum(weeks) / len(weeks)
    cv = (math.sqrt(sum((c - mean) ** 2 for c in weeks) / len(weeks)) / mean) if mean else 9.0
    conf = "high" if n_trades >= 40 and len(weeks) >= 6 and cv < 0.6 else \
           "medium" if n_trades >= 15 and len(weeks) >= 3 and cv < 0.9 else "low"
    out.update(per_week=round(ewma, 1), low=q(0.2), high=q(0.8), confidence=conf, cv=round(cv, 2))
    return out


def _custom_regime_since() -> tuple[datetime | None, str | None]:
    """Ultima salvare de profil care a atins un camp de frecventa (session_changes_log)."""
    try:
        with open(os.path.join(ROOT, "data", "session_changes_log.json"), encoding="utf-8") as f:
            log = json.load(f)
    except Exception:
        return None, None
    for e in reversed(log):
        fields = {c.get("field") for s in e.get("sessions", []) for c in s.get("changes", [])}
        hit = sorted(fields & FREQ_FIELDS)
        if hit:
            return datetime.fromisoformat(e["time"][:19]), ", ".join(hit[:4])
    return None, None


def _ai_regime_since() -> tuple[datetime | None, str | None]:
    """ai_engine/config.json (piete, trigger-e, limite) — mtime = ultima schimbare."""
    p = os.path.join(ROOT, "ai_engine", "config.json")
    try:
        return datetime.fromtimestamp(os.path.getmtime(p)), "config AI Engine (piețe / trigger-e / limite)"
    except OSError:
        return None, None


def _with_previous(cur: dict, times: list[datetime], now: datetime, first: datetime | None) -> dict:
    """Cand regimul curent e prea nou, ritmul de dinainte de schimbare ramane vizibil ca
    REFERINTA (etichetat), nu ca estimare — e singura informatie reala disponibila."""
    if cur["confidence"] == "insufficient" and first is not None:
        prev = pace(times, now, first)
        if prev["confidence"] != "insufficient":
            cur["previous"] = {k: prev[k] for k in ("per_week", "low", "high", "weeks", "trades_in_window", "confidence")}
    return cur


def _daily_started() -> datetime | None:
    try:
        with open(os.path.join(ROOT, "data", "daily_engine", "engine.log"), encoding="utf-8") as f:
            return datetime.fromisoformat(f.readline()[:19])
    except Exception:
        return None


def _compute() -> dict:
    from api import mt5_pool
    from api.routers.sessions import frequency_estimate
    now = datetime.now()
    out: dict = {"computed_at": now.isoformat(timespec="seconds"), "half_life_weeks": HALF_LIFE_WEEKS}
    try:
        trades = mt5_pool.get_closed_trades(MAX_WEEKS * 7 + 14)
        connected = True
    except Exception as e:
        trades, connected = [], False
        out["error"] = str(e)
    out["connected"] = connected

    # Custom Engine
    since, why = _custom_regime_since()
    ct = [t["close_time"] for t in trades if t.get("source") == "bot"]
    first = min(ct, default=None)
    eff = max([d for d in (since, first) if d], default=None)
    ref = None
    try:
        fe = frequency_estimate()
        ref = fe.get("per_week")
    except Exception:
        pass
    out["custom"] = {**_with_previous(pace(ct, now, eff), ct, now, first), "regime_since": since.date().isoformat() if since else None,
                     "regime_reason": why, "reference": ref, "reference_kind": "backtest"}

    # AI Engine
    since, why = _ai_regime_since()
    at = [t["close_time"] for t in trades if t.get("source") == "ai"]
    first = min(at, default=None)
    eff = max([d for d in (since, first) if d], default=None)
    out["ai"] = {**_with_previous(pace(at, now, eff), at, now, first), "regime_since": since.date().isoformat() if since else None,
                 "regime_reason": why, "reference": None, "reference_kind": None}

    # Daily Engine — trade-uri VIRTUALE (shadow) din jurnalul propriu + reper structural
    try:
        from daily_engine.config import load_config
        from daily_engine.engine import load_trades
        dcfg = load_config()
        dtr = load_trades()
        dt = [datetime.fromisoformat(t["recorded_at"][:19]) for t in dtr]
        mk = [m["symbol"] for m in dcfg["markets"] if m.get("enabled", True)]
        ref = round(5 * sum(DAILY_DAY_RATE.get(s, 0.9) for s in mk), 1)
        first = _daily_started() or min(dt, default=None) or now
        out["daily"] = {**pace(dt, now, first), "regime_since": first.date().isoformat(),
                        "regime_reason": "pornirea Daily Engine (shadow)",
                        "reference": ref, "reference_kind": "reguli (1 trade/zi/piață × rata zilelor din backtest)",
                        "virtual": True, "markets": mk}
    except Exception as e:
        out["daily"] = {"confidence": "insufficient", "per_week": None, "error": str(e), "virtual": True}
    return out


@router.get("/trading-pace")
def trading_pace(refresh: bool = False):
    if refresh or _cache["data"] is None or time.time() - _cache["ts"] > CACHE_TTL_S:
        _cache.update(ts=time.time(), data=_compute())
    return _cache["data"]


# ── Piete active + semnale GLOBALE (toate engine-urile) — vezi api/market_overview.py ──

@router.get("/markets")
def dashboard_markets(refresh: bool = False):
    from api import market_overview
    return market_overview.get_markets(refresh)


@router.get("/signals")
def dashboard_signals(symbol: str | None = None, engine: str | None = None, limit: int = 100):
    from api import market_overview
    return market_overview.signals(symbol or None, engine or None, max(1, min(int(limit), 500)))
