"""Configurarea Noisy Engine — `noisy_engine/config.json` (hot-reload la fiecare iteratie).

Valorile implicite vin din research (docs/NOISY_ENGINE_RESEARCH.md): USDJPY, M5, mean reversion la
EMA20 ± 2×ATR14, SL 1,5×ATR, tinta = EMA20, stop de timp 20 de bare, doar in fereastra lichida.
Toate limitele sunt OPTIONALE (enabled true/false). Prima versiune ruleaza DOAR in SHADOW
(trade-uri virtuale, zero ordine) — executia reala vine dupa validarea din shadow.
"""
from __future__ import annotations

import copy
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_PATH = os.path.join(ROOT, "noisy_engine", "config.json")
DATA_DIR = os.path.join(ROOT, "data", "noisy_engine")

MODES = ("shadow",)            # „execute” se adauga dupa validarea din shadow (criteriile din research §20)
TIMEFRAMES = {"M1": 1, "M5": 5}  # minute pe bara; M1 = implicit (decizia userului: multe trade-uri / ora)
MAGIC = 990001                 # rezervat pentru ordinele reale viitoare

DEFAULTS: dict = {
    "mode": "shadow",
    "symbol": "USDJPY",
    # M1 = implicit: scopul e FRECVENTA (mai multe trade-uri / ora), nu profitul — decizia userului
    # 2026-11-01. Research: pe M1 rezultatul e ~0 dupa costuri (USDJPY −0,01R/trade la spread 0,1 pip,
    # puternic negativ cu comision Raw). M5 ramane optiune (~3–4/zi, +0,08R in backtest).
    "timeframe": "M1",
    "poll_seconds": 5,
    "notify_telegram": True,
    "notify_trades": False,          # pe M1 ar fi zeci de mesaje / zi; pornire / blocari / buget se trimit mereu
    # fereastra in care are voie sa INTRE (ora RO). Pozitiile deschise se termina dupa regulile lor
    # (stop de timp) — nimic peste noapte.
    "window": {"start": "10:00", "end": "20:00", "days": [0, 1, 2, 3, 4]},
    "strategy": {
        "ema": 20, "atr": 14,
        "dev_atr": 2.0,               # intrare cand inchiderea e la > 2×ATR de EMA20 (contra miscarii)
        "sl_atr": 1.5,                # SL = 1,5×ATR de la intrare
        "time_stop_bars": 20,         # iesire la inchidere dupa 20 de bare (M1 = 20 min) daca nu a atins SL/TP
        # pauza dupa iesire: OPRITA implicit — in backtest (12 luni USDJPY) pauza 3/6 bare scadea
        # expectancy de la +0,070R la +0,059R (test ≈ 0): mean reversion reintra des pe acelasi dezechilibru
        "cooldown_bars": 0,
        "cooldown_after_sl_bars": 0,
        "max_flips_per_hour": 3,      # > 3 schimbari de directie intr-o ora → fara intrari pana la ora urmatoare
        "trend_filter": False,        # OPTIONAL: nu intra cand piata e in trend (efficiency ratio)
        "er_bars": 20, "er_trend": 0.35,
        "spread_floor": 0.001,        # spread-ul median REAL (tick-uri) — USDJPY 1 punct; barele MT5 au minimul (0)
        "spread_max_mult": 1.5,       # spread-ul LIVE (tick) la semnal ≤ 1,5× spread_floor, altfel semnalul e respins
        "min_atr_over_cost": 5.0,     # ATR ≥ 5× costul dus-intors (pe M1; M5 testat cu 15), altfel miscarea e prea mica
        "slip_frac": 0.25,            # slippage presupus: 25% din spread la intrare si la iesire
        "comm_price": 0.0,            # comision in unitati de pret (0 = contul actual)
    },
    "news": {"enabled": True, "pre_min": 5, "post_min": 15},   # stiri High pe valutele pietei
    "limits": {                                              # toate OPTIONALE, resetate zilnic (ora RO)
        # M1: ~25–30 de trade-uri / zi in fereastra 10–20 (~3 / ora). Limitele taie doar zilele extreme
        # (backtest 12 luni: drawdown −130R → −117R). Pe M5 valorile testate erau 6 / 4 / 3.
        "max_trades_day": {"enabled": True, "value": 60},
        "max_losses_day": {"enabled": True, "value": 25},
        "max_consec_losses": {"enabled": True, "value": 8},
    },
    # buget IZOLAT: P&L-ul trade-urilor Noisy (realizat + flotant), NU equity-ul contului
    "budget": {"capital": 40.0, "min_remaining": 30.0},
    "sizing": {"risk_pct": 0.01},                            # risc per trade, % din bugetul engine-ului
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def hm_to_min(s: str) -> int:
    h, m = str(s).split(":")
    return int(h) * 60 + int(m)


def _num(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def sanitize(cfg: dict) -> dict:
    c = _merge(DEFAULTS, cfg)
    c["mode"] = c["mode"] if c["mode"] in MODES else "shadow"
    c["symbol"] = str(c.get("symbol") or "USDJPY").upper()
    c["timeframe"] = c["timeframe"] if c.get("timeframe") in TIMEFRAMES else "M1"
    c["notify_trades"] = bool(c.get("notify_trades", False))
    c["poll_seconds"] = int(_num(c["poll_seconds"], 2, 120, 5))
    w = c["window"]
    for k, d in (("start", "10:00"), ("end", "20:00")):
        try:
            mins = hm_to_min(w[k])
            w[k] = f"{mins // 60 % 24:02d}:{mins % 60:02d}"
        except Exception:
            w[k] = d
    w["days"] = sorted({int(x) for x in w.get("days", []) if str(x).isdigit() and 0 <= int(x) <= 6}) or [0, 1, 2, 3, 4]
    s, d = c["strategy"], DEFAULTS["strategy"]
    s["ema"] = int(_num(s["ema"], 5, 200, 20))
    s["atr"] = int(_num(s["atr"], 5, 100, 14))
    s["dev_atr"] = _num(s["dev_atr"], 0.5, 6, d["dev_atr"])
    s["sl_atr"] = _num(s["sl_atr"], 0.3, 6, d["sl_atr"])
    s["time_stop_bars"] = int(_num(s["time_stop_bars"], 2, 200, 20))
    s["cooldown_bars"] = int(_num(s["cooldown_bars"], 0, 100, 0))
    s["cooldown_after_sl_bars"] = int(_num(s["cooldown_after_sl_bars"], 0, 200, 0))
    s["max_flips_per_hour"] = int(_num(s["max_flips_per_hour"], 0, 50, 3))
    s["trend_filter"] = bool(s["trend_filter"])
    s["er_bars"] = int(_num(s["er_bars"], 5, 200, 20))
    s["er_trend"] = _num(s["er_trend"], 0.05, 1, 0.35)
    s["spread_floor"] = _num(s.get("spread_floor"), 0, 1e6, 0.001)
    s["spread_max_mult"] = _num(s["spread_max_mult"], 0, 20, 1.5)
    s["min_atr_over_cost"] = _num(s["min_atr_over_cost"], 0, 200, 5)
    s["slip_frac"] = _num(s["slip_frac"], 0, 5, 0.25)
    s["comm_price"] = _num(s["comm_price"], 0, 1e6, 0.0)
    n = c["news"]
    n["enabled"] = bool(n["enabled"])
    n["pre_min"] = int(_num(n["pre_min"], 0, 240, 5))
    n["post_min"] = int(_num(n["post_min"], 0, 240, 15))
    for k in ("max_trades_day", "max_losses_day", "max_consec_losses"):
        lim = c["limits"].get(k) or {}
        c["limits"][k] = {"enabled": bool(lim.get("enabled", True)), "value": int(_num(lim.get("value"), 1, 1000, 1))}
    b = c["budget"]
    b["capital"] = _num(b["capital"], 1, 1e6, 40.0)
    b["min_remaining"] = _num(b["min_remaining"], 0, b["capital"], min(30.0, b["capital"]))
    c["sizing"]["risk_pct"] = _num(c["sizing"].get("risk_pct"), 0.0005, 0.05, 0.01)
    return c


def load_config() -> dict:
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            return sanitize(json.load(f))
    except Exception:
        return sanitize({})


def save_config(cfg: dict) -> dict:
    clean = sanitize(cfg)
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)
    return clean


def save_default_config() -> None:
    if not os.path.exists(CFG_PATH):
        save_config({})
