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

MAGIC = 660001                    # ordinele reale (special_engine/executor.py); api/mt5_pool → „special”
MARKET_MODES = ("live", "shadow", "pause")

DEFAULTS: dict = {
    "mode": "shadow",                 # REZUMAT: „execute” daca macar o piata e Live (modul real = per piata)
    "poll_seconds": 30,
    "notify_telegram": True,          # pornire / selectie trimestriala / rezumat zilnic / ordine reale
    "notify_trades": False,           # fiecare intrare / iesire virtuala (zgomotos)
    # ── capital + risc (PROPRII engine-ului; Setarile Globale se aplica PESTE ele, „cea mai stricta castiga”) ──
    "capital": {"capital_sync_mt5": True, "capital_usd": None, "fraction": 1.0},   # baza = equity MT5 × fractie
    "risk_pct": 0.01,                 # risc pe trade = 1% din capitalul engine-ului (decizia userului, 12.11)
    "max_open_risk_pct": 0.02,        # riscul TOTAL deschis (toate pietele Special) ≤ 2% din capital
    "max_positions": 2,               # pozitii + ordine Special deschise simultan
    "max_margin_pct": 80.0,           # marja TOTALA a contului dupa ordin ≤ 80% din equity
    "noise_stop_mult": 2.0,           # B: SL de protectie la 2 × unitatea R (strategia iese pe banda / VWAP)
    "markets": {},                    # {SIMBOL: {"mode": live|shadow|pause, "paused_at": ISO}} — lipsa = SHADOW
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
    out["poll_seconds"] = _clamp(cfg.get("poll_seconds", 30), 10, 300, 30, int)
    out["notify_telegram"] = bool(cfg.get("notify_telegram", True))
    out["notify_trades"] = bool(cfg.get("notify_trades", False))
    out["risk_pct"] = _clamp(cfg.get("risk_pct", 0.01), 0.0, 0.02, 0.01)
    cap = {**DEFAULTS["capital"], **(cfg.get("capital") or {})}
    usd = cap.get("capital_usd")
    out["capital"] = {"capital_sync_mt5": bool(cap.get("capital_sync_mt5", True)),
                      "capital_usd": None if usd in (None, "") else _clamp(usd, 10.0, 1_000_000.0, None),
                      "fraction": _clamp(cap.get("fraction", 1.0), 0.05, 1.0, 1.0)}
    out["max_open_risk_pct"] = _clamp(cfg.get("max_open_risk_pct", 0.02), 0.0025, 0.10, 0.02)
    out["max_positions"] = _clamp(cfg.get("max_positions", 2), 1, 10, 2, int)
    out["max_margin_pct"] = _clamp(cfg.get("max_margin_pct", 80.0), 10.0, 95.0, 80.0)
    out["noise_stop_mult"] = _clamp(cfg.get("noise_stop_mult", 2.0), 1.0, 5.0, 2.0)
    known = set(ORB_MARKETS) | set(NOISE_MARKETS)
    mk = {}
    for sym, m in (cfg.get("markets") or {}).items():
        if sym in known and isinstance(m, dict):
            mode = m.get("mode") if m.get("mode") in MARKET_MODES else "shadow"
            mk[sym] = {"mode": mode, "paused_at": m.get("paused_at") if mode == "pause" else None}
    out["markets"] = mk
    out["mode"] = "execute" if any(m["mode"] == "live" for m in mk.values()) else "shadow"
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


def market_mode(cfg: dict, symbol: str) -> str:
    """Modul pietei: live / shadow / pause. O piata noua (ex. aleasa de selectia trimestriala) = SHADOW."""
    return ((cfg.get("markets") or {}).get(symbol) or {}).get("mode", "shadow")


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
