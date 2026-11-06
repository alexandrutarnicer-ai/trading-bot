"""Special Engine — configurare (`special_engine/config.json`, auto-creat; hot-reload la fiecare iteratie).

Doua strategii, evaluate separat si impreuna (docs/SPECIAL_ENGINE.md):
  A = portofoliu intraday ADAPTIV: la inceputul fiecarui trimestru se aleg (doar din TRECUT, ultimele `lookback_months`)
      componentele piata × strategie × varianta (ORB 10 piete × 6 variante + NOISE 8 piete) cu t-stat >= `t_min` si
      medie >= `min_mean_R`, minim `min_trades` trade-uri, cel mult una pe piata si `max_components` in total;
      componentele se tranzactioneaza DOAR in zilele NR4 (range-ul zilei anterioare = minimul ultimelor 4 zile, Crabel).
  B = „Beat the Market” (Zarattini, Aziz, Barbon 2024) pe USTEC, parametrii din lucrare, fara nicio selectie.
Valorile implicite = configuratia PRE-INREGISTRATA pe 04.11 (cercetare) si validata pe 05.11 (platou NR4 pozitiv,
look-ahead verificat, stres de cost, Monte Carlo) — vezi scripts/research_special/validate_special.py.
Mod: DOAR shadow (zero ordine — pachetul nu contine nicio functie de trimitere a ordinelor; verificat de selftest)."""
from __future__ import annotations

import copy
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_PATH = os.path.join(ROOT, "special_engine", "config.json")
DATA_DIR = os.path.join(ROOT, "data", "special_engine")

# Sesiunile = exact cele din cercetare (scripts/research_special/intraday_orb.py / noise_area.py)
ORB_MARKETS = {
    "DE40": ("Europe/Berlin", "09:00", "17:25"), "STOXX50": ("Europe/Berlin", "09:00", "17:25"),
    "UK100": ("Europe/London", "08:00", "16:25"), "US500": ("America/New_York", "09:30", "15:55"),
    "USTEC": ("America/New_York", "09:30", "15:55"), "US30": ("America/New_York", "09:30", "15:55"),
    "XAUUSD": ("America/New_York", "08:20", "16:55"), "JP225": ("Asia/Tokyo", "09:00", "14:55"),
    "AUS200": ("Australia/Sydney", "10:00", "15:55"), "GBPUSD": ("Europe/London", "08:00", "14:25"),
}
NOISE_MARKETS = {
    "US500": ("America/New_York", "09:30", "16:00"), "USTEC": ("America/New_York", "09:30", "16:00"),
    "US30": ("America/New_York", "09:30", "16:00"), "DE40": ("Europe/Berlin", "09:00", "17:30"),
    "XAUUSD": ("America/New_York", "09:30", "16:00"), "JP225": ("Asia/Tokyo", "09:00", "15:00"),
    "UK100": ("Europe/London", "08:00", "16:30"), "STOXX50": ("Europe/Berlin", "09:00", "17:30"),
}
# Costuri (pret) masurate ziua (04.11, contul Standard): slip = 25% din spread-ul live, comm = markup peste istoric
COSTS = {"DE40": (0.125, 0.0), "STOXX50": (0.25, 0.0), "UK100": (0.225, 0.0), "US500": (0.125, 0.0),
         "USTEC": (0.25, 0.0), "US30": (0.30, 0.0), "XAUUSD": (0.045, 0.13), "JP225": (1.0, 0.0),
         "AUS200": (0.30, 0.0), "GBPUSD": (0.0000225, 0.00008)}

DEFAULTS: dict = {
    "mode": "shadow",
    "poll_seconds": 30,
    "notify_telegram": True,          # pornire / selectie trimestriala / rezumat zilnic
    "notify_trades": False,           # fiecare intrare / iesire virtuala (zgomotos)
    "risk_pct": 0.005,                # risc VIRTUAL pe trade (estimare in bani din equity MT5) — 0,5%
    "strategy_a": {"enabled": True, "lookback_months": 36, "t_min": 1.5, "min_mean_R": 0.05, "min_trades": 60,
                   "max_components": 6, "nr_filter": 4},
    "strategy_b": {"enabled": True, "symbol": "USTEC"},
}


def _clamp(v, lo, hi, d, cast=float):
    try:
        return max(lo, min(hi, cast(v)))
    except (TypeError, ValueError):
        return d


def sanitize(cfg: dict | None) -> dict:
    cfg = cfg if isinstance(cfg, dict) else {}
    out = copy.deepcopy(DEFAULTS)
    out["mode"] = "shadow"                                    # DOAR shadow (executia nu exista in acest engine)
    out["poll_seconds"] = _clamp(cfg.get("poll_seconds", 30), 10, 300, 30, int)
    out["notify_telegram"] = bool(cfg.get("notify_telegram", True))
    out["notify_trades"] = bool(cfg.get("notify_trades", False))
    out["risk_pct"] = _clamp(cfg.get("risk_pct", 0.005), 0.0, 0.02, 0.005)
    a = {**DEFAULTS["strategy_a"], **(cfg.get("strategy_a") or {})}
    out["strategy_a"] = {"enabled": bool(a["enabled"]),
                         "lookback_months": _clamp(a["lookback_months"], 12, 60, 36, int),
                         "t_min": _clamp(a["t_min"], 0.5, 4.0, 1.5), "min_mean_R": _clamp(a["min_mean_R"], 0.0, 1.0, 0.05),
                         "min_trades": _clamp(a["min_trades"], 20, 1000, 60, int),
                         "max_components": _clamp(a["max_components"], 1, 10, 6, int),
                         "nr_filter": _clamp(a["nr_filter"], 0, 10, 4, int)}
    b = {**DEFAULTS["strategy_b"], **(cfg.get("strategy_b") or {})}
    out["strategy_b"] = {"enabled": bool(b["enabled"]),
                         "symbol": b["symbol"] if b.get("symbol") in NOISE_MARKETS else "USTEC"}
    return out


def load_config() -> dict:
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            return sanitize(json.load(f))
    except Exception:
        return sanitize(None)


def save_config(cfg: dict) -> dict:
    clean = sanitize(cfg)
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)
    return clean
